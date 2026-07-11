"""Track simple function-local resources and suspicious cleanup candidates."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .error_condition import ConditionInfo
from .label_resolver import Statement
from .parser import (
    call_name_and_args,
    extract_call_expressions,
)
from .false_positive_model import (
    is_contract_restore_acquire,
    resource_exempt_by_function_contract,
)
from .resource_release import call_releases_resource, cleanup_call_releases_resource
from .resource_expr import same_resource_expr


@dataclass
class HeldResource:
    var: str
    acquire_func: str
    resource_type: str
    release_functions: list[str]
    acquire_line: int
    out_resource_arg: int | None = None
    release_arg_index: int = 0
    release_arg_requires_address: bool = False
    release_suggestion_template: str = ""

    @property
    def release_suggestion(self) -> str:
        if self.release_suggestion_template:
            return self.release_suggestion_template.format(var=self.var)
        release = self.release_functions[0] if self.release_functions else "release"
        return f"{release}({self.var})"

    def to_csv_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_resource_map(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _assignment_lhs(text: str, eq_idx: int) -> str:
    left = text[:eq_idx].rstrip()
    match = re.search(
        r"([A-Za-z_]\w*(?:(?:->|\.)[A-Za-z_]\w*)*(?:\[[^\]]+\])?)\s*$",
        left,
    )
    return match.group(1) if match else ""


def _assignment_calls(text: str) -> list[tuple[str, str, list[str]]]:
    found: list[tuple[str, str, list[str]]] = []
    idx = 0
    while idx < len(text):
        eq_idx = text.find("=", idx)
        if eq_idx == -1:
            break
        before = text[eq_idx - 1] if eq_idx > 0 else ""
        after = text[eq_idx + 1] if eq_idx + 1 < len(text) else ""
        if before in {"=", "!", "<", ">"} or after == "=":
            idx = eq_idx + 1
            continue
        lhs = _assignment_lhs(text, eq_idx)
        rhs = text[eq_idx + 1 :]
        semi = rhs.find(";")
        if semi != -1:
            rhs = rhs[:semi]
        calls = extract_call_expressions(rhs)
        if lhs and calls:
            call_name, args = call_name_and_args(calls[0])
            found.append((lhs, call_name, args))
        idx = eq_idx + 1
    return found


def _out_resource_var(args: list[str], cfg: dict[str, Any]) -> str:
    if "out_resource_arg" not in cfg:
        return ""
    arg_idx = int(cfg.get("out_resource_arg", 0))
    if arg_idx >= len(args):
        return ""
    raw = args[arg_idx].strip()
    if cfg.get("out_arg_requires_address", False) and not raw.startswith("&"):
        return ""
    while raw.startswith("&"):
        raw = raw[1:].strip()
    while raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1].strip()
    return raw


class ResourceTracker:
    def __init__(self, resource_map: dict[str, Any]):
        self.acquire_functions = resource_map.get("acquire_functions", {})
        self.callee_resource_consumers = resource_map.get(
            "callee_resource_consumers", {}
        )
        self.resource_ownership_transfers = resource_map.get(
            "resource_ownership_transfers", []
        )

    def held_before(
        self,
        statements: list[Statement],
        error_line: int,
        condition: ConditionInfo,
        error_source_expr: str,
        function_name: str = "",
    ) -> list[HeldResource]:
        held: list[HeldResource] = []

        for stmt in statements:
            if stmt.line >= error_line:
                break

            for call in extract_call_expressions(stmt.text):
                name, args = call_name_and_args(call)
                self._apply_release(held, name, args)

            for lhs, call_name, args in _assignment_calls(stmt.text):
                cfg = self.acquire_functions.get(call_name)
                if not cfg:
                    continue
                if "out_resource_arg" in cfg:
                    var = _out_resource_var(args, cfg)
                    if not var:
                        continue
                else:
                    var = lhs
                if is_contract_restore_acquire(function_name, call_name, var):
                    continue
                held = [res for res in held if not self._same_resource_arg(res.var, var)]
                held.append(self._resource(var, call_name, cfg, stmt.line))

            for call in extract_call_expressions(stmt.text):
                name, args = call_name_and_args(call)
                cfg = self.acquire_functions.get(name)
                if not cfg:
                    continue
                if "out_resource_arg" in cfg:
                    var = _out_resource_var(args, cfg)
                elif "direct_resource_arg" in cfg:
                    arg_idx = int(cfg.get("direct_resource_arg", 0))
                    if arg_idx >= len(args):
                        continue
                    var = args[arg_idx].strip()
                else:
                    continue
                if not var:
                    continue
                if is_contract_restore_acquire(function_name, name, var):
                    continue
                held = [res for res in held if not self._same_resource_arg(res.var, var)]
                held.append(self._resource(var, name, cfg, stmt.line))

        return [
            res
            for res in held
            if not self._condition_is_acquire_failure(res, condition, error_source_expr)
            and not self._error_source_consumes_resource(res, error_source_expr)
            and not self._resource_ownership_transferred(function_name, res)
            and not resource_exempt_by_function_contract(
                function_name, condition.condition, error_source_expr, res
            )
        ]

    def missing_cleanup_candidates(
        self, held: list[HeldResource], cleanup_calls: list[str]
    ) -> list[str]:
        missing: list[str] = []
        for res in held:
            released = False
            for call in cleanup_calls:
                name, args = call_name_and_args(call)
                if cleanup_call_releases_resource(call, res) or self._consumer_releases(
                    name, args, res, "always"
                ):
                    released = True
                    break
            if not released:
                missing.append(res.release_suggestion)
        return missing

    def _resource(
        self, var: str, acquire_func: str, cfg: dict[str, Any], line: int
    ) -> HeldResource:
        releases = cfg.get("release", [])
        if isinstance(releases, str):
            releases = [releases]
        return HeldResource(
            var=var,
            acquire_func=acquire_func,
            resource_type=cfg.get("resource_type", "unknown"),
            release_functions=list(releases),
            acquire_line=line,
            out_resource_arg=cfg.get("out_resource_arg"),
            release_arg_index=int(cfg.get("release_arg_index", 0)),
            release_arg_requires_address=bool(
                cfg.get("release_arg_requires_address", False)
            ),
            release_suggestion_template=str(cfg.get("release_suggestion", "")),
        )

    def _apply_release(self, held: list[HeldResource], name: str, args: list[str]) -> None:
        kept: list[HeldResource] = []
        for res in held:
            if call_releases_resource(name, args, res) or self._consumer_releases(
                name, args, res, "always"
            ):
                continue
            kept.append(res)
        held[:] = kept

    def _consumer_releases(
        self,
        name: str,
        args: list[str],
        resource: HeldResource,
        when: str,
    ) -> bool:
        consumers = self.callee_resource_consumers.get(name, [])
        if isinstance(consumers, dict):
            consumers = [consumers]
        for consumer in consumers:
            if not isinstance(consumer, dict) or consumer.get("when", "always") != when:
                continue
            if consumer.get("resource_type") not in {None, "", resource.resource_type}:
                continue
            if consumer.get("match") == "resource_type":
                return True
            if "resource_arg" in consumer:
                index = int(consumer["resource_arg"])
                if index >= len(args):
                    continue
                target = args[index].strip()
                while target.startswith("&"):
                    target = target[1:].strip()
                if same_resource_expr(target, resource.var):
                    return True
            template = str(consumer.get("resource_expr", ""))
            if template:
                target = template
                for index, arg in enumerate(args):
                    target = target.replace(f"{{arg{index}}}", arg.strip())
                if same_resource_expr(target, resource.var):
                    return True
        return False

    def _error_source_consumes_resource(
        self, resource: HeldResource, error_source_expr: str
    ) -> bool:
        name, args = call_name_and_args(error_source_expr)
        return self._consumer_releases(name, args, resource, "error_return")

    def _resource_ownership_transferred(
        self, function_name: str, resource: HeldResource
    ) -> bool:
        for transfer in self.resource_ownership_transfers:
            if not isinstance(transfer, dict):
                continue
            if transfer.get("function") != function_name:
                continue
            if transfer.get("resource_type") not in {None, "", resource.resource_type}:
                continue
            if same_resource_expr(
                str(transfer.get("resource_expr", "")), resource.var
            ):
                return True
        return False

    def _condition_is_acquire_failure(
        self, res: HeldResource, condition: ConditionInfo, error_source_expr: str
    ) -> bool:
        if not self._same_resource_arg(condition.error_var, res.var) and not (
            condition.condition
            and self._condition_mentions_null_resource(condition.condition, res.var)
        ):
            if (
                res.out_resource_arg is not None
                and error_source_expr.startswith(f"{res.acquire_func}(")
                and condition.condition_type
                in {"ret_nonzero", "negative_error", "specific_error_code"}
            ):
                return True
            return False
        null_failure = condition.condition_type in {
            "null_pointer",
            "null_check",
            "is_err",
            "is_err_or_null",
            "err_ptr_check",
        } or self._condition_mentions_null_resource(condition.condition, res.var)
        if not null_failure:
            return False
        if error_source_expr == "unknown":
            return True
        return error_source_expr.startswith(f"{res.acquire_func}(")

    @staticmethod
    def _same_resource_arg(left: str, right: str) -> bool:
        return same_resource_expr(left, right)

    @staticmethod
    def _condition_mentions_null_resource(condition: str, resource_var: str) -> bool:
        cond = condition.strip()
        if cond.startswith("!"):
            return same_resource_expr(cond[1:].strip(), resource_var)
        null_cmp = re.match(r"^(.+?)\s*==\s*NULL$", cond) or re.match(
            r"^NULL\s*==\s*(.+)$", cond
        )
        return bool(null_cmp and same_resource_expr(null_cmp.group(1), resource_var))
