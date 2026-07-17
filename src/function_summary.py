"""Infer and propagate parameter-level resource effects across local calls."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .cfg import build_cfg
from .function_extractor import Function
from .parser import call_name_and_args, extract_call_expressions, split_args
from .resource_expr import same_resource_expr
from .resource_state import ResourceAction


@dataclass(frozen=True, order=True)
class SummaryEffect:
    resource: str
    action: str
    strength: str = "must"
    exit_class: str = "any"
    return_guard: str = ""
    effect_cardinality: str = "one"
    must_reason: tuple[str, ...] = ()
    condition: str = "always"
    resource_type: str = ""
    release_functions: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["must_reason"] = list(self.must_reason)
        data["release_functions"] = list(self.release_functions)
        data["evidence"] = list(self.evidence)
        return data


@dataclass
class FunctionSummary:
    function: str
    parameters: tuple[str, ...]
    effects: list[SummaryEffect] = field(default_factory=list)
    callees: list[str] = field(default_factory=list)
    unresolved_calls: list[str] = field(default_factory=list)
    iterations: int = 0

    def add_effect(self, effect: SummaryEffect) -> bool:
        identity = _effect_identity(effect)
        for index, existing in enumerate(self.effects):
            if _effect_identity(existing) != identity:
                continue
            if len(effect.evidence) < len(existing.evidence):
                self.effects[index] = effect
                self.effects.sort()
            return False
        self.effects.append(effect)
        self.effects.sort()
        return True

    def effects_for_call(self, args: list[str]) -> list[tuple[SummaryEffect, str]]:
        applied: list[tuple[SummaryEffect, str]] = []
        for effect in self.effects:
            index = _arg_index(effect.resource)
            if index is None or index >= len(args):
                continue
            applied.append((effect, args[index].strip()))
        return applied

    def to_dict(self) -> dict[str, Any]:
        return {
            "function": self.function,
            "parameters": list(self.parameters),
            "effects": [effect.to_dict() for effect in self.effects],
            "callees": self.callees,
            "unresolved_calls": self.unresolved_calls,
            "iterations": self.iterations,
        }


@dataclass
class FunctionSummaryDB:
    summaries: dict[str, FunctionSummary] = field(default_factory=dict)
    call_graph: dict[str, tuple[str, ...]] = field(default_factory=dict)
    converged: bool = True
    iterations: int = 0

    def find(self, function: str) -> FunctionSummary | None:
        return self.summaries.get(function)

    def write_json(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 4,
            "converged": self.converged,
            "iterations": self.iterations,
            "call_graph": {key: list(value) for key, value in sorted(self.call_graph.items())},
            "summaries": [
                self.summaries[name].to_dict() for name in sorted(self.summaries)
            ],
        }
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def infer_function_summaries(
    functions: Iterable[Function],
    resource_map: dict[str, Any],
    max_iterations: int = 50,
) -> FunctionSummaryDB:
    function_list = list(functions)
    local_names = {function.name for function in function_list}
    release_map = _release_map(resource_map)
    acquire_functions = resource_map.get("acquire_functions", {})
    summaries = _seed_effect_summaries(resource_map)
    known_names = local_names | set(summaries)

    for function in function_list:
        params = _ordered_parameters(function.signature)
        calls = _calls(function.body)
        callees = sorted({name for name, _ in calls if name in known_names})
        unresolved = sorted(
            {
                name
                for name, args in calls
                if name not in known_names
                and name not in release_map
                and any(_parameter_index(arg, params) is not None for arg in args)
            }
        )
        summary = FunctionSummary(
            function=function.name,
            parameters=params,
            callees=callees,
            unresolved_calls=unresolved,
        )
        _add_direct_effects(
            summary,
            function,
            function.body,
            calls,
            release_map,
            acquire_functions,
        )
        summaries[function.name] = summary

    converged = False
    iterations = 0
    for iteration in range(1, max_iterations + 1):
        changed = False
        for function in function_list:
            caller = summaries[function.name]
            for callee_name, args in _calls(function.body):
                callee = summaries.get(callee_name)
                if callee is None:
                    continue
                for callee_effect in callee.effects:
                    if callee_effect.resource != "return":
                        continue
                    if not _callee_return_escapes(function.body, callee_name):
                        continue
                    changed |= caller.add_effect(
                        SummaryEffect(
                            resource="return",
                            action=callee_effect.action,
                            strength=callee_effect.strength,
                            exit_class=callee_effect.exit_class,
                            return_guard=callee_effect.return_guard,
                            effect_cardinality=callee_effect.effect_cardinality,
                            must_reason=callee_effect.must_reason,
                            condition=callee_effect.condition,
                            resource_type=callee_effect.resource_type,
                            release_functions=callee_effect.release_functions,
                            evidence=(
                                f"{caller.function} returns result of {callee_name}",
                                *callee_effect.evidence,
                            ),
                        )
                    )
                for callee_effect, actual in callee.effects_for_call(args):
                    caller_index = _parameter_index(actual, caller.parameters)
                    if caller_index is None:
                        continue
                    callee_index = _arg_index(callee_effect.resource)
                    call_strength = _effect_executes_on_all_exits(
                        function,
                        callee_name,
                        callee_index,
                        actual,
                    )
                    strength = (
                        "must"
                        if callee_effect.strength == "must" and call_strength == "must"
                        else "may"
                    )
                    preserves_exit = _preserves_callee_exit_class(
                        function.body,
                        callee_name,
                        callee_effect.return_guard,
                    )
                    exit_class = (
                        callee_effect.exit_class if preserves_exit else "any"
                    )
                    return_guard = (
                        callee_effect.return_guard if preserves_exit else ""
                    )
                    if callee_effect.exit_class != "any" and not preserves_exit:
                        strength = "may"
                    evidence = (
                        f"{caller.function} calls {callee_name}",
                        *callee_effect.evidence,
                    )
                    changed |= caller.add_effect(
                        SummaryEffect(
                            resource=f"arg{caller_index}",
                            action=callee_effect.action,
                            strength=strength,
                            exit_class=exit_class,
                            return_guard=return_guard,
                            effect_cardinality=callee_effect.effect_cardinality,
                            must_reason=(
                                (
                                    "complete_cfg",
                                    "cfg_postdominating_effect",
                                    "exact_callee",
                                    "exact_argument_mapping",
                                )
                                if strength == "must"
                                else ()
                            ),
                            condition=_map_condition_to_caller(
                                callee_effect.condition, args, caller.parameters
                            ),
                            resource_type=callee_effect.resource_type,
                            release_functions=callee_effect.release_functions,
                            evidence=evidence,
                        )
                    )
        iterations = iteration
        if not changed:
            converged = True
            break

    for name in local_names:
        summaries[name].iterations = iterations
    return FunctionSummaryDB(
        summaries=summaries,
        call_graph={name: tuple(summary.callees) for name, summary in summaries.items()},
        converged=converged,
        iterations=iterations,
    )


def _seed_effect_summaries(resource_map: dict[str, Any]) -> dict[str, FunctionSummary]:
    """Load reviewed external API contracts used only by summary analysis."""
    seeded: dict[str, FunctionSummary] = {}
    raw_seeds = resource_map.get("interprocedural_effect_seeds", {})
    if not isinstance(raw_seeds, dict):
        return seeded

    valid_actions = {action.value for action in ResourceAction}
    for function, raw_effects in raw_seeds.items():
        if not isinstance(function, str) or not function.strip():
            continue
        effects = raw_effects if isinstance(raw_effects, list) else [raw_effects]
        summary = FunctionSummary(function=function.strip(), parameters=())
        for raw_effect in effects:
            if not isinstance(raw_effect, dict):
                continue
            resource = str(raw_effect.get("resource", "")).strip()
            action = str(raw_effect.get("action", "")).strip()
            strength = str(raw_effect.get("strength", "must")).strip()
            exit_class = str(raw_effect.get("exit_class", "any")).strip()
            return_guard = str(raw_effect.get("return_guard", "")).strip()
            effect_cardinality = str(
                raw_effect.get("effect_cardinality", "one")
            ).strip()
            if (
                not re.fullmatch(r"arg\d+|return", resource)
                or action not in valid_actions
                or strength not in {"must", "may"}
                or exit_class not in {"any", "success", "error"}
                or effect_cardinality not in {"one", "all", "unknown"}
                or (exit_class != "any" and not return_guard)
            ):
                continue
            release_functions = raw_effect.get("release_functions", [])
            if isinstance(release_functions, str):
                release_functions = [release_functions]
            evidence = raw_effect.get("evidence", [f"reviewed external contract for {function}"])
            if isinstance(evidence, str):
                evidence = [evidence]
            summary.add_effect(
                SummaryEffect(
                    resource=resource,
                    action=action,
                    strength=strength,
                    exit_class=exit_class,
                    return_guard=return_guard,
                    effect_cardinality=effect_cardinality,
                    must_reason=("reviewed_seed",) if strength == "must" else (),
                    condition=str(raw_effect.get("condition", "always")),
                    resource_type=str(raw_effect.get("resource_type", "")),
                    release_functions=tuple(str(name) for name in release_functions),
                    evidence=tuple(str(item) for item in evidence),
                )
            )
        if summary.effects:
            seeded[summary.function] = summary
    return seeded


def _ordered_parameters(signature: str) -> tuple[str, ...]:
    close = signature.rfind(")")
    if close < 0:
        return ()
    depth = 0
    open_index = -1
    for index in range(close, -1, -1):
        if signature[index] == ")":
            depth += 1
        elif signature[index] == "(":
            depth -= 1
            if depth == 0:
                open_index = index
                break
    if open_index < 0:
        return ()
    names: list[str] = []
    for raw in split_args(signature[open_index + 1 : close]):
        raw = raw.strip()
        if not raw or raw in {"void", "..."}:
            continue
        identifiers = re.findall(r"[A-Za-z_]\w*", re.sub(r"\[[^\]]*\]", "", raw))
        if identifiers:
            names.append(identifiers[-1])
    return tuple(names)


def _release_map(resource_map: dict[str, Any]) -> dict[str, list[tuple[str, int]]]:
    releases: dict[str, list[tuple[str, int]]] = {}
    for cfg in resource_map.get("acquire_functions", {}).values():
        resource_type = str(cfg.get("resource_type", ""))
        argument = int(cfg.get("release_arg_index", 0))
        names = cfg.get("release", [])
        if isinstance(names, str):
            names = [names]
        for name in names:
            spec = (resource_type, argument)
            releases.setdefault(str(name), [])
            if spec not in releases[str(name)]:
                releases[str(name)].append(spec)
    return releases


def _calls(body: str) -> list[tuple[str, list[str]]]:
    return [call_name_and_args(call) for call in extract_call_expressions(body)]


def _add_direct_effects(
    summary: FunctionSummary,
    function: Function,
    body: str,
    calls: list[tuple[str, list[str]]],
    release_map: dict[str, list[tuple[str, int]]],
    acquire_functions: dict[str, Any],
) -> None:
    for name, args in calls:
        for resource_type, argument in release_map.get(name, []):
            if argument >= len(args):
                continue
            index = _parameter_index(args[argument], summary.parameters)
            if index is not None:
                raw_condition = _call_condition(body, name)
                effect_strength = _direct_release_strength(
                    function,
                    name,
                    argument,
                    args[argument],
                    raw_condition,
                )
                summary.add_effect(
                    SummaryEffect(
                        resource=f"arg{index}",
                        action=ResourceAction.RELEASE.value,
                        strength=effect_strength,
                        must_reason=(
                            (
                                "complete_cfg",
                                "cfg_postdominating_effect",
                                "exact_callee",
                                "exact_argument_mapping",
                                "guard_proven_at_call"
                                if raw_condition != "always"
                                else "unguarded_effect",
                            )
                            if effect_strength == "must"
                            else ()
                        ),
                        condition=_normalize_parameter_condition(
                            raw_condition, summary.parameters
                        ),
                        resource_type=resource_type,
                        evidence=(f"direct call {name}({args[argument].strip()})",),
                    )
                )

        acquire = acquire_functions.get(name)
        if not isinstance(acquire, dict) or "out_resource_arg" not in acquire:
            continue
        out_index = int(acquire["out_resource_arg"])
        if out_index >= len(args):
            continue
        index = _parameter_index(args[out_index], summary.parameters)
        if index is not None:
            effect_strength = _effect_executes_on_all_exits(
                function,
                name,
                out_index,
                args[out_index],
            )
            summary.add_effect(
                SummaryEffect(
                    resource=f"arg{index}",
                    action=ResourceAction.ACQUIRE.value,
                    strength=effect_strength,
                    must_reason=(
                        (
                            "complete_cfg",
                            "cfg_postdominating_effect",
                            "exact_callee",
                            "exact_argument_mapping",
                        )
                        if effect_strength == "must"
                        else ()
                    ),
                    resource_type=str(acquire.get("resource_type", "")),
                    release_functions=_release_names(acquire),
                    evidence=(f"out-parameter acquisition via {name}",),
                )
            )

    for name, cfg in acquire_functions.items():
        if not isinstance(cfg, dict) or "out_resource_arg" in cfg:
            continue
        assignment = re.search(
            rf"\b([A-Za-z_]\w*)\s*=\s*{re.escape(name)}\s*\([^;]*\)\s*;",
            body,
        )
        direct_return = re.search(rf"\breturn\s+{re.escape(name)}\s*\(", body)
        returned_local = assignment and re.search(
            rf"\breturn\s+{re.escape(assignment.group(1))}\s*;", body
        )
        if direct_return or returned_local:
            returned_var = assignment.group(1) if returned_local else ""
            effect_strength = _return_acquire_strength(
                function, returned_var, name
            )
            summary.add_effect(
                SummaryEffect(
                    resource="return",
                    action=ResourceAction.ACQUIRE.value,
                    strength=effect_strength,
                    must_reason=(
                        (
                            "complete_cfg",
                            "all_returns_preserve_acquired_value",
                            "exact_callee",
                        )
                        if effect_strength == "must"
                        else ()
                    ),
                    condition=_return_acquire_condition(
                        body, returned_var, name, summary.parameters
                    ),
                    resource_type=str(cfg.get("resource_type", "")),
                    release_functions=_release_names(cfg),
                    evidence=(f"return value acquired via {name}",),
                )
            )

    for index, parameter in enumerate(summary.parameters):
        escaped = re.search(
            rf"(?:->|\.)[A-Za-z_]\w*\s*=\s*(?:\([^)]+\)\s*)?{re.escape(parameter)}\b",
            body,
        )
        if escaped:
            summary.add_effect(
                SummaryEffect(
                    resource=f"arg{index}",
                    action=ResourceAction.ESCAPE.value,
                    strength="may",
                    evidence=("stored in a field",),
                )
            )
        if re.search(rf"\breturn\s+{re.escape(parameter)}\s*;", body):
            effect_strength = _parameter_return_strength(
                function, body, parameter
            )
            summary.add_effect(
                SummaryEffect(
                    resource=f"arg{index}",
                    action=ResourceAction.TRANSFER.value,
                    strength=effect_strength,
                    must_reason=(
                        (
                            "complete_cfg",
                            "all_returns_transfer_parameter",
                            "exact_argument_mapping",
                        )
                        if effect_strength == "must"
                        else ()
                    ),
                    evidence=("returned to caller",),
                )
            )


def _parameter_index(expression: str, parameters: tuple[str, ...]) -> int | None:
    value = expression.strip()
    while value.startswith("&"):
        value = value[1:].strip()
    for index, parameter in enumerate(parameters):
        if same_resource_expr(value, parameter):
            return index
    return None


def _arg_index(resource: str) -> int | None:
    match = re.fullmatch(r"arg(\d+)", resource)
    return int(match.group(1)) if match else None


def _effect_identity(
    effect: SummaryEffect,
) -> tuple[
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    tuple[str, ...],
]:
    return (
        effect.resource,
        effect.action,
        effect.strength,
        effect.exit_class,
        effect.return_guard,
        effect.effect_cardinality,
        effect.condition,
        effect.resource_type,
        effect.release_functions,
    )


def _effect_executes_on_all_exits(
    function: Function,
    call_name: str,
    argument_index: int | None,
    resource_expression: str,
) -> str:
    """Return must only when every CFG exit crosses the relevant call."""

    if argument_index is None:
        return "may"
    if function.body_node is None:
        return "may"

    try:
        cfg = build_cfg(function)
    except Exception:
        return "may"
    if not _function_cfg_complete(function):
        return "may"
    effect_blocks: set[int] = set()
    for block_id, block in cfg.blocks.items():
        for call in extract_call_expressions(block.text):
            name, args = call_name_and_args(call)
            if name != call_name or argument_index >= len(args):
                continue
            if same_resource_expr(args[argument_index], resource_expression):
                effect_blocks.add(block_id)
    if not effect_blocks:
        return "may"

    reachable = {cfg.entry}
    pending = [cfg.entry]
    while pending:
        block_id = pending.pop()
        if block_id in effect_blocks:
            continue
        for edge in cfg.successors(block_id):
            if edge.target not in reachable:
                reachable.add(edge.target)
                pending.append(edge.target)
    return "may" if cfg.exit in reachable else "must"


def _direct_release_strength(
    function: Function,
    call_name: str,
    argument_index: int,
    resource_expression: str,
    condition: str,
) -> str:
    if not _function_cfg_complete(function):
        return "may"
    if condition == "always":
        return _effect_executes_on_all_exits(
            function, call_name, argument_index, resource_expression
        )
    match = re.search(
        rf"\bif\s*\([^\n{{}}]+\)\s*{{?\s*{re.escape(call_name)}\s*\(",
        function.body,
    )
    if not match:
        return "may"
    prefix = function.body[: match.start()]
    return (
        "may"
        if re.search(
            r"\b(?:if|for|while|switch|return|goto|break|continue)\b",
            prefix,
        )
        else "must"
    )


def _directly_returns_call(body: str, function: str) -> bool:
    return bool(re.search(rf"\breturn\s+{re.escape(function)}\s*\(", body))


def _preserves_callee_exit_class(
    body: str, function: str, return_guard: str
) -> bool:
    if _directly_returns_call(body, function):
        return True
    assignment = re.search(
        rf"\b([A-Za-z_]\w*)\s*=\s*{re.escape(function)}\s*\([^;]*\)\s*;",
        body,
    )
    if assignment is None:
        return False
    result_var = assignment.group(1)
    tail = body[assignment.end() :]
    if re.search(
        rf"\b{re.escape(result_var)}\s*=(?!=)",
        tail,
    ):
        return False
    returns = [expression.strip() for expression in re.findall(r"\breturn\s+([^;]+);", tail)]
    if not returns or "0" not in returns:
        return False
    if any(
        not (same_resource_expr(expression, result_var) or expression == "0")
        for expression in returns
    ):
        return False

    guard = re.sub(r"\breturn\b", result_var, return_guard.strip())
    success_guard = re.fullmatch(
        rf"{re.escape(result_var)}\s*==\s*0", guard
    )
    if success_guard:
        error_condition = rf"(?:{re.escape(result_var)}|{re.escape(result_var)}\s*!=\s*0)"
    else:
        error_guard = re.fullmatch(
            rf"{re.escape(result_var)}\s*<\s*0", guard
        )
        if not error_guard:
            return False
        error_condition = rf"{re.escape(result_var)}\s*<\s*0"
    return bool(
        re.search(
            rf"\bif\s*\(\s*(?:{error_condition})\s*\)\s*"
            rf"(?:{{\s*)?return\s+{re.escape(result_var)}\s*;",
            tail,
        )
    )


def _parameter_return_strength(
    function: Function, body: str, parameter: str
) -> str:
    if not _function_cfg_complete(function):
        return "may"
    returns = re.findall(r"\breturn\s+([^;]+);", body)
    if not returns:
        return "may"
    return (
        "must"
        if all(same_resource_expr(expression, parameter) for expression in returns)
        else "may"
    )


def _return_acquire_strength(
    function: Function, returned_var: str, acquire_name: str
) -> str:
    if not _function_cfg_complete(function):
        return "may"
    returns = re.findall(r"\breturn\s+([^;]+);", function.body)
    if not returns:
        return "may"
    for expression in returns:
        value = expression.strip()
        if returned_var and same_resource_expr(value, returned_var):
            continue
        if re.fullmatch(rf"{re.escape(acquire_name)}\s*\([^;]*\)", value):
            continue
        return "may"
    return "must"


def _function_cfg_complete(function: Function) -> bool:
    if function.body_node is None:
        return False
    if function.analysis_quality != "tree-sitter":
        return False
    try:
        return not build_cfg(function).unsupported_nodes
    except Exception:
        return False


def _release_names(config: dict[str, Any]) -> tuple[str, ...]:
    names = config.get("release", [])
    if isinstance(names, str):
        names = [names]
    return tuple(str(name) for name in names)


def _call_condition(body: str, function: str) -> str:
    match = re.search(
        rf"\bif\s*\(([^\n{{}}]+)\)\s*{{?\s*{re.escape(function)}\s*\(", body
    )
    return match.group(1).strip() if match else "always"


def _normalize_parameter_condition(
    condition: str, parameters: tuple[str, ...]
) -> str:
    normalized = condition.strip()
    if normalized == "always":
        return normalized
    for index, parameter in sorted(
        enumerate(parameters), key=lambda item: len(item[1]), reverse=True
    ):
        normalized = re.sub(
            rf"\b{re.escape(parameter)}\b", f"arg{index}", normalized
        )
    return normalized


def _map_condition_to_caller(
    condition: str, callee_args: list[str], caller_parameters: tuple[str, ...]
) -> str:
    mapped = condition.strip()
    if mapped == "always":
        return mapped
    for index in range(len(callee_args) - 1, -1, -1):
        actual = callee_args[index].strip()
        # Parameter-to-parameter forwarding is already precedence-safe. Adding
        # parentheses at every wrapper creates a fresh condition string on each
        # fixed-point round (e.g. ``((((arg0))))``), preventing convergence.
        replacement = (
            actual
            if re.fullmatch(r"arg\d+", actual)
            or any(same_resource_expr(actual, parameter) for parameter in caller_parameters)
            else f"({actual})"
        )
        mapped = re.sub(rf"\barg{index}\b", lambda _match: replacement, mapped)
    return _normalize_parameter_condition(mapped, caller_parameters)


def _return_acquire_condition(
    body: str, returned_var: str, acquire_function: str, parameters: tuple[str, ...]
) -> str:
    if not returned_var:
        return "always"
    if not _acquire_guarded_by_null_check(body, returned_var, acquire_function):
        return "always"
    index = _nullable_parameter_source(body, returned_var, parameters)
    if index is None:
        return "always"
    return f"arg{index} == NULL"


def _acquire_guarded_by_null_check(
    body: str, returned_var: str, acquire_function: str
) -> bool:
    return bool(
        re.search(
            rf"\bif\s*\(\s*!\s*{re.escape(returned_var)}\s*\)[^;{{}}]*"
            rf"(?:{{[^{{}}]*?)?{re.escape(returned_var)}\s*=\s*"
            rf"{re.escape(acquire_function)}\s*\(",
            body,
            re.S,
        )
    )


def _nullable_parameter_source(
    body: str, returned_var: str, parameters: tuple[str, ...]
) -> int | None:
    for index, parameter in enumerate(parameters):
        if re.search(
            rf"(?:^|[;\n])[^;\n]*\b{re.escape(returned_var)}\s*=\s*"
            rf"{re.escape(parameter)}\s*\?\s*\*?\s*{re.escape(parameter)}\s*:\s*NULL\s*;",
            body,
            re.S,
        ):
            return index
        if re.search(
            rf"(?:^|[;\n])[^;\n]*\b{re.escape(returned_var)}\s*=\s*"
            rf"{re.escape(parameter)}\s*;",
            body,
            re.S,
        ):
            return index
    return None


def _callee_return_escapes(body: str, callee: str) -> bool:
    if re.search(rf"\breturn\s+{re.escape(callee)}\s*\(", body):
        return True
    assignment = re.search(
        rf"\b([A-Za-z_]\w*)\s*=\s*{re.escape(callee)}\s*\([^;]*\)\s*;",
        body,
    )
    return bool(
        assignment
        and re.search(rf"\breturn\s+{re.escape(assignment.group(1))}\s*;", body)
    )
