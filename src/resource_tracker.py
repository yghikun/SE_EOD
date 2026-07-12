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
from .resource_expr import norm_resource_expr, same_resource_expr
from .function_summary import FunctionSummaryDB
from .resource_state import ResourceAction, ResourceState, join_states
from .cfg import BasicBlock, CFGEdge, build_cfg
from .dataflow import DisjunctiveDataflowResult, solve_forward_disjunctive


_UNKNOWN_FUNCTION_TARGET = "<unknown>"


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
    scope_cleanup_function: str = ""
    scope_cleanup_decl_line: int | None = None

    @property
    def release_suggestion(self) -> str:
        if self.release_suggestion_template:
            return self.release_suggestion_template.format(var=self.var)
        release = self.release_functions[0] if self.release_functions else "release"
        return f"{release}({self.var})"

    def to_csv_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResourceFlowState:
    resources: dict[str, tuple[HeldResource, ResourceState]]
    aliases: dict[str, str]
    scope_cleanups: dict[str, tuple[str, int]]
    function_targets: dict[str, frozenset[str]]
    unresolved_indirect_calls: frozenset[str] = frozenset()
    path_facts: frozenset[tuple[str, bool]] = frozenset()

    def clone(self) -> "ResourceFlowState":
        return ResourceFlowState(
            resources={
                key: (HeldResource(**resource.to_csv_dict()), state)
                for key, (resource, state) in self.resources.items()
            },
            aliases=dict(self.aliases),
            scope_cleanups=dict(self.scope_cleanups),
            function_targets=dict(self.function_targets),
            unresolved_indirect_calls=frozenset(self.unresolved_indirect_calls),
            path_facts=frozenset(self.path_facts),
        )


def load_resource_map(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _strip_condition_parens(condition: str) -> str:
    value = condition.strip()
    while value.startswith("(") and value.endswith(")"):
        depth = 0
        encloses_all = True
        for index, char in enumerate(value):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and index != len(value) - 1:
                    encloses_all = False
                    break
        if not encloses_all or depth != 0:
            break
        value = value[1:-1].strip()
    return value


def _literal_truth(expression: str) -> bool | None:
    value = _strip_condition_parens(expression.strip())
    if value == "true":
        return True
    if value in {"false", "NULL"}:
        return False
    if re.fullmatch(r"[+-]?(?:0[xX][0-9A-Fa-f]+|\d+)", value):
        try:
            return int(value, 0) != 0
        except ValueError:
            return None
    return None


def _condition_fact(condition: str, branch_truth: bool) -> tuple[str, bool] | None:
    value = _strip_condition_parens(condition)
    negated = False
    while value.startswith("!") and not value.startswith("!="):
        negated = not negated
        value = _strip_condition_parens(value[1:])
    truth = branch_truth != negated

    wrapper = re.fullmatch(r"IS_ERR(?:_OR_NULL)?\s*\((.+)\)", value)
    if wrapper:
        return f"valid:{norm_resource_expr(wrapper.group(1))}", not truth

    null_cmp = re.fullmatch(r"(.+?)\s*(==|!=)\s*(?:NULL|0)", value)
    if null_cmp:
        expression, operator = null_cmp.groups()
        valid = truth if operator == "!=" else not truth
        return f"valid:{norm_resource_expr(expression)}", valid

    reverse_null_cmp = re.fullmatch(r"(?:NULL|0)\s*(==|!=)\s*(.+)", value)
    if reverse_null_cmp:
        operator, expression = reverse_null_cmp.groups()
        valid = truth if operator == "!=" else not truth
        return f"valid:{norm_resource_expr(expression)}", valid

    zero_cmp = re.fullmatch(r"(.+?)\s*(>=|<)\s*0", value)
    if zero_cmp:
        expression, operator = zero_cmp.groups()
        nonnegative = truth if operator == ">=" else not truth
        return f"nonnegative:{norm_resource_expr(expression)}", nonnegative

    reverse_zero_cmp = re.fullmatch(r"0\s*(<=|>)\s*(.+)", value)
    if reverse_zero_cmp:
        operator, expression = reverse_zero_cmp.groups()
        nonnegative = truth if operator == "<=" else not truth
        return f"nonnegative:{norm_resource_expr(expression)}", nonnegative

    if re.fullmatch(r"[A-Za-z_]\w*(?:(?:->|\.)[A-Za-z_]\w*|\[[^\]]+\])*", value):
        return f"valid:{norm_resource_expr(value)}", truth

    if any(token in value for token in ("&&", "||", "?")):
        return None
    return f"expr:{norm_resource_expr(value)}", truth


def _condition_facts(condition: str, branch_truth: bool) -> list[tuple[str, bool]]:
    value = _strip_condition_parens(condition)
    if branch_truth:
        conjunction = _split_top_level_condition(value, "&&")
        if len(conjunction) > 1:
            facts: list[tuple[str, bool]] = []
            for term in conjunction:
                fact = _condition_fact(term, True)
                if fact is not None:
                    facts.append(fact)
            return facts
    fact = _condition_fact(condition, branch_truth)
    return [fact] if fact is not None else []


def _split_top_level_condition(expression: str, operator: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    index = 0
    while index < len(expression):
        char = expression[index]
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        elif depth == 0 and expression.startswith(operator, index):
            parts.append(expression[start:index].strip())
            start = index + len(operator)
            index += len(operator) - 1
        index += 1
    parts.append(expression[start:].strip())
    return parts


def _assignment_lhs(text: str, eq_idx: int) -> str:
    left = text[:eq_idx].rstrip()
    left = re.sub(r"\s+__free\s*\(\s*[A-Za-z_]\w*\s*\)\s*$", "", left)
    match = re.search(
        r"([A-Za-z_]\w*(?:(?:->|\.)[A-Za-z_]\w*|\[[^\]]+\])*)\s*$",
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


def _simple_assignments(text: str) -> list[tuple[str, str]]:
    """Return assignments whose RHS is a resource-like expression."""

    found: list[tuple[str, str]] = []
    for match in re.finditer(r"(?<![=!<>])=(?!=)", text):
        lhs = _assignment_lhs(text, match.start())
        rhs = _strip_assignment_rhs_casts(text[match.end() :].split(";", 1)[0].strip())
        if lhs and re.fullmatch(
            r"[A-Za-z_]\w*(?:(?:->|\.)[A-Za-z_]\w*)*(?:\[[^\]]+\])?", rhs
        ):
            found.append((lhs, rhs))
    return found


def _function_target_assignments(text: str) -> list[tuple[str, str, bool]]:
    """Return simple function pointer target assignments."""

    found: list[tuple[str, str, bool]] = []
    for match in re.finditer(
        r"\(\s*\*\s*([A-Za-z_]\w*)\s*\)\s*\([^;=]*\)\s*=\s*([A-Za-z_]\w*)",
        text,
    ):
        found.append((match.group(1), match.group(2), True))

    for match in re.finditer(r"(?<![=!<>])=(?!=)", text):
        lhs = _assignment_lhs(text, match.start())
        rhs = _strip_assignment_rhs_casts(text[match.end() :].split(";", 1)[0].strip())
        if lhs and re.fullmatch(r"[A-Za-z_]\w*", rhs):
            found.append((lhs, rhs, False))
    return found


def _assignment_path_facts(text: str) -> list[tuple[str, bool]]:
    facts: list[tuple[str, bool]] = []
    for lhs, call_name, args in _assignment_calls(text):
        lhs_key = norm_resource_expr(lhs)
        if call_name == "PTR_ERR" and args:
            facts.append((f"valid:{lhs_key}", True))
            facts.append((f"nonnegative:{lhs_key}", False))
            facts.append(
                (f"error_source:{lhs_key}:{norm_resource_expr(args[0])}", True)
            )
        elif call_name == "PTR_ERR_OR_ZERO" and args:
            facts.append(
                (f"error_source:{lhs_key}:{norm_resource_expr(args[0])}", True)
            )
    return facts


def _assigned_expressions(text: str) -> set[str]:
    assigned: set[str] = set()
    for match in re.finditer(r"(?<![=!<>])=(?!=)", text):
        lhs = _assignment_lhs(text, match.start())
        if lhs:
            assigned.add(norm_resource_expr(lhs))
    for match in re.finditer(
        r"(?:\+\+|--)\s*([A-Za-z_]\w*)|([A-Za-z_]\w*)\s*(?:\+\+|--)", text
    ):
        assigned.add(match.group(1) or match.group(2))
    return assigned


def _fact_mentions_assignment(atom: str, assigned: str) -> bool:
    expression = atom.split(":", 1)[1] if ":" in atom else atom
    return bool(re.search(rf"(?<![A-Za-z0-9_]){re.escape(assigned)}(?![A-Za-z0-9_])", expression))


def _strip_assignment_rhs_casts(rhs: str) -> str:
    while True:
        match = re.match(r"^\([^()]*\*[^()]*\)\s*(.+)$", rhs)
        if not match:
            return rhs
        rhs = match.group(1).strip()


def _is_field_expr(expr: str) -> bool:
    normalized = norm_resource_expr(expr)
    return "->" in normalized or "." in normalized


def _same_stored_resource(stored: str, resource_var: str) -> bool:
    stored_norm = norm_resource_expr(stored)
    resource_norm = norm_resource_expr(resource_var)
    if stored_norm == resource_norm:
        return True
    if _is_field_expr(stored):
        return False
    return same_resource_expr(stored, resource_var)


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
    def __init__(
        self,
        resource_map: dict[str, Any],
        function_summaries: FunctionSummaryDB | None = None,
    ):
        self.acquire_functions = resource_map.get("acquire_functions", {})
        self.callee_resource_consumers = resource_map.get(
            "callee_resource_consumers", {}
        )
        self.resource_ownership_transfers = resource_map.get(
            "resource_ownership_transfers", []
        )
        self.scope_cleanup_macros = resource_map.get("scope_cleanup_macros", {})
        self.function_summaries = function_summaries or FunctionSummaryDB()
        self.release_functions_by_type = self._release_functions_by_type()
        self._cfg_cache: dict[
            tuple[str, int], tuple[Any, DisjunctiveDataflowResult[ResourceFlowState]]
        ] = {}
        self._cfg_function_names: dict[tuple[str, int], str] = {}

    def held_before_cfg(
        self,
        function: Any,
        error_line: int,
        condition: ConditionInfo,
        error_source_expr: str,
    ) -> list[HeldResource] | None:
        if function.body_node is None:
            return None
        cache_key = (str(function.file), function.start_line)
        cached = self._cfg_cache.get(cache_key)
        if cached is None:
            cfg = build_cfg(function)
            initial = ResourceFlowState({}, {}, {}, {})
            result = solve_forward_disjunctive(
                cfg,
                initial,
                lambda block, state: self._transfer_cfg_block(
                    block, state, function.name
                ),
                self._join_flow_states,
                lambda state: state.clone(),
                edge_transfer=self._transfer_cfg_edge,
            )
            cached = (cfg, result)
            self._cfg_cache[cache_key] = cached
            self._cfg_function_names[cache_key] = function.name
        cfg, result = cached
        block = cfg.block_at_line(error_line)
        if block is None or block.id not in result.in_states:
            return None
        held_by_identity: dict[tuple[str, str, int], HeldResource] = {}
        for state in result.in_states[block.id]:
            if not self._state_allows_condition(state, condition.condition):
                continue
            for resource, resource_state in state.resources.values():
                if resource_state is not ResourceState.ACQUIRED:
                    continue
                if resource.acquire_line > error_line:
                    continue
                if self._state_marks_acquire_failure_source(
                    state, condition, resource
                ):
                    continue
                identity = (resource.var, resource.acquire_func, resource.acquire_line)
                held_by_identity[identity] = HeldResource(**resource.to_csv_dict())
        held = list(held_by_identity.values())
        return self._filter_held_resources(
            held, condition, error_source_expr, function.name
        )

    def cfg_diagnostics(self) -> dict[str, Any]:
        functions: list[dict[str, Any]] = []
        unresolved_calls: set[str] = set()
        total_iterations = 0
        total_widened_blocks = 0
        truncated_functions = 0
        max_states_per_block = 0
        for cache_key, (cfg, result) in self._cfg_cache.items():
            total_iterations += result.iterations
            total_widened_blocks += len(result.widened_blocks)
            if result.truncated:
                truncated_functions += 1
            for states in result.in_states.values():
                max_states_per_block = max(max_states_per_block, len(states))
                for state in states:
                    unresolved_calls.update(state.unresolved_indirect_calls)
            functions.append(
                {
                    "function": self._cfg_function_names.get(cache_key, "unknown"),
                    "file": cache_key[0],
                    "start_line": cache_key[1],
                    "iterations": result.iterations,
                    "truncated": result.truncated,
                    "widened_blocks": len(result.widened_blocks),
                }
            )
        return {
            "functions": len(functions),
            "iterations": total_iterations,
            "truncated_functions": truncated_functions,
            "widened_blocks": total_widened_blocks,
            "max_states_per_block": max_states_per_block,
            "unresolved_indirect_calls": len(unresolved_calls),
            "unresolved_indirect_call_names": sorted(unresolved_calls)[:20],
            "function_details": functions,
        }

    @staticmethod
    def _state_allows_condition(
        state: ResourceFlowState, condition: str
    ) -> bool:
        facts = _condition_facts(condition, True)
        known_facts = dict(state.path_facts)
        return all(known_facts.get(atom) in {None, truth} for atom, truth in facts)

    @staticmethod
    def _state_marks_acquire_failure_source(
        state: ResourceFlowState, condition: ConditionInfo, resource: HeldResource
    ) -> bool:
        if not ResourceTracker._condition_requires_nonzero_error(condition):
            return False
        error_var = norm_resource_expr(condition.error_var)
        if not error_var:
            return False
        expected = f"error_source:{error_var}:{norm_resource_expr(resource.var)}"
        return any(atom == expected and truth for atom, truth in state.path_facts)

    def _transfer_cfg_block(
        self, block: BasicBlock, state: ResourceFlowState, function_name: str
    ) -> ResourceFlowState:
        if block.kind in {"entry", "exit", "empty", "condition", "loop_condition", "loop_exit", "label"}:
            return state
        text = block.text
        assigned = _assigned_expressions(text)
        if assigned:
            state.path_facts = frozenset(
                (atom, truth)
                for atom, truth in state.path_facts
                if not any(
                    _fact_mentions_assignment(atom, expression)
                    for expression in assigned
                )
            )
        assignment_facts = _assignment_path_facts(text)
        if assignment_facts:
            facts = dict(state.path_facts)
            for atom, truth in assignment_facts:
                facts[atom] = truth
            state.path_facts = frozenset(facts.items())
        for var, release in self._scope_cleanup_declarations(text):
            state.scope_cleanups[var] = (release, block.start_line)

        for lhs, target, from_declaration in _function_target_assignments(text):
            self._flow_assign_function_target(state, lhs, target, from_declaration)

        for call in extract_call_expressions(text):
            name, args = call_name_and_args(call)
            if name == "swap" and len(args) >= 2:
                self._swap_aliases(state, args[0], args[1])
                continue
            self._flow_apply_call(state, name, args)
            cfg = self.acquire_functions.get(name)
            if not isinstance(cfg, dict):
                for var, summary_cfg in self._summary_argument_acquires(name, args):
                    self._flow_acquire(
                        state,
                        var,
                        name,
                        summary_cfg,
                        block.start_line,
                        function_name,
                    )
                continue
            if "out_resource_arg" in cfg:
                var = _out_resource_var(args, cfg)
            elif "direct_resource_arg" in cfg:
                index = int(cfg.get("direct_resource_arg", 0))
                var = args[index].strip() if index < len(args) else ""
            else:
                var = ""
            if var:
                self._flow_acquire(
                    state, var, name, cfg, block.start_line, function_name
                )

        for lhs, call_name, args in _assignment_calls(text):
            cfg = self.acquire_functions.get(call_name) or self._summary_return_acquire(
                call_name, args
            )
            if not cfg:
                continue
            var = _out_resource_var(args, cfg) if "out_resource_arg" in cfg else lhs
            self._flow_acquire(
                state, var, call_name, cfg, block.start_line, function_name
            )

        for lhs, rhs in _simple_assignments(text):
            lhs_key = norm_resource_expr(lhs)
            rhs_key = self._resolve_alias(state, rhs)
            if _is_field_expr(lhs) or "[" in lhs_key:
                if rhs_key in state.resources:
                    resource, _ = state.resources[rhs_key]
                    state.resources[rhs_key] = (resource, ResourceState.ESCAPED)
                continue
            if rhs_key in state.resources:
                state.aliases[lhs_key] = rhs_key
                cleanup = state.scope_cleanups.get(lhs)
                if cleanup:
                    resource, resource_state = state.resources[rhs_key]
                    resource.scope_cleanup_function = cleanup[0]
                    resource.scope_cleanup_decl_line = cleanup[1]
                    state.resources[rhs_key] = (resource, resource_state)
            else:
                state.aliases.pop(lhs_key, None)
        return state

    @staticmethod
    def _transfer_cfg_edge(
        edge: CFGEdge, state: ResourceFlowState
    ) -> ResourceFlowState | None:
        if edge.kind not in {"true", "false"} or not edge.condition:
            return state
        edge_facts = _condition_facts(edge.condition, edge.kind == "true")
        if not edge_facts:
            return state
        facts = dict(state.path_facts)
        for atom, truth in edge_facts:
            if atom in facts and facts[atom] != truth:
                return None
            facts[atom] = truth
        state.path_facts = frozenset(facts.items())
        return state

    def _flow_acquire(
        self,
        state: ResourceFlowState,
        var: str,
        call_name: str,
        cfg: dict[str, Any],
        line: int,
        function_name: str,
    ) -> None:
        if not var or is_contract_restore_acquire(function_name, call_name, var):
            return
        key = norm_resource_expr(var)
        state.aliases[key] = key
        state.resources[key] = (
            self._resource(
                var, call_name, cfg, line, state.scope_cleanups.get(var)
            ),
            ResourceState.ACQUIRED,
        )
        state.path_facts = frozenset(
            (atom, truth)
            for atom, truth in state.path_facts
            if not same_resource_expr(atom, key)
            and not atom.endswith(f":{key}")
        )

    def _flow_assign_function_target(
        self,
        state: ResourceFlowState,
        lhs: str,
        target: str,
        from_declaration: bool = False,
    ) -> None:
        lhs_key = norm_resource_expr(lhs)
        if not re.fullmatch(r"[A-Za-z_]\w*", lhs_key):
            return
        target_name = target.strip()
        if (
            from_declaration
            or target_name in state.function_targets
            or self._known_function_target(target_name)
        ):
            state.function_targets[lhs_key] = frozenset({target_name})
        elif lhs_key in state.function_targets:
            state.function_targets[lhs_key] = frozenset({_UNKNOWN_FUNCTION_TARGET})

    def _known_function_target(self, name: str) -> bool:
        if name in self.acquire_functions or name in self.callee_resource_consumers:
            return True
        if self.function_summaries.find(name) is not None:
            return True
        return any(
            name in release_functions
            for release_functions in self.release_functions_by_type.values()
        )

    def _flow_apply_call(
        self, state: ResourceFlowState, name: str, args: list[str]
    ) -> None:
        resolved_name = norm_resource_expr(name)
        target_names = state.function_targets.get(resolved_name)
        if target_names is not None:
            self._flow_apply_indirect_call(state, resolved_name, target_names, args)
            return

        for key, (resource, resource_state) in list(state.resources.items()):
            resolved_args = [self._resolve_alias(state, arg) for arg in args]
            if self._call_consumes_resource(name, resolved_args, resource):
                state.resources[key] = (resource, ResourceState.RELEASED)
                continue
            summary = self.function_summaries.find(name)
            if summary is None and any(
                same_resource_expr(actual, key) for actual in resolved_args
            ) and self._looks_indirect_call(name):
                state.resources[key] = (resource, ResourceState.UNKNOWN)
                state.unresolved_indirect_calls = frozenset(
                    {*state.unresolved_indirect_calls, name}
                )

    def _flow_apply_indirect_call(
        self,
        state: ResourceFlowState,
        name: str,
        target_names: frozenset[str],
        args: list[str],
    ) -> None:
        concrete_targets = {
            target for target in target_names if target != _UNKNOWN_FUNCTION_TARGET
        }
        has_unknown_target = len(concrete_targets) != len(target_names)
        for key, (resource, resource_state) in list(state.resources.items()):
            resolved_args = [self._resolve_alias(state, arg) for arg in args]
            if not any(same_resource_expr(actual, key) for actual in resolved_args):
                continue
            consumes = [
                self._call_consumes_resource(target, resolved_args, resource)
                for target in sorted(concrete_targets)
            ]
            if consumes and all(consumes) and not has_unknown_target:
                state.resources[key] = (resource, ResourceState.RELEASED)
            elif has_unknown_target or any(consumes):
                state.resources[key] = (resource, ResourceState.UNKNOWN)
                state.unresolved_indirect_calls = frozenset(
                    {*state.unresolved_indirect_calls, name}
                )

    def _call_consumes_resource(
        self, name: str, args: list[str], resource: HeldResource
    ) -> bool:
        return (
            call_releases_resource(name, args, resource)
            or self._consumer_releases(name, args, resource, "always")
            or self._summary_consumes(name, args, resource)
        )

    @staticmethod
    def _looks_indirect_call(name: str) -> bool:
        return bool(re.fullmatch(r"(?:cb|callback|fn|func|handler|ops?)\w*", name, re.I))

    def _resolve_alias(self, state: ResourceFlowState, expression: str) -> str:
        key = norm_resource_expr(expression)
        visited: set[str] = set()
        while key in state.aliases and key not in visited:
            visited.add(key)
            target = state.aliases[key]
            if target == key:
                break
            key = target
        return key

    def _swap_aliases(
        self, state: ResourceFlowState, left: str, right: str
    ) -> None:
        left_key = norm_resource_expr(left)
        right_key = norm_resource_expr(right)
        left_target = self._resolve_alias(state, left_key)
        right_target = self._resolve_alias(state, right_key)
        if right_target in state.resources:
            state.aliases[left_key] = right_target
        else:
            state.aliases.pop(left_key, None)
        if left_target in state.resources:
            state.aliases[right_key] = left_target
        else:
            state.aliases.pop(right_key, None)

    @staticmethod
    def _join_flow_states(
        left: ResourceFlowState, right: ResourceFlowState
    ) -> ResourceFlowState:
        resources: dict[str, tuple[HeldResource, ResourceState]] = {}
        for key in set(left.resources) | set(right.resources):
            left_item = left.resources.get(key)
            right_item = right.resources.get(key)
            if left_item and right_item:
                resource = left_item[0]
                state = join_states(left_item[1], right_item[1])
            elif left_item:
                resource = left_item[0]
                state = join_states(left_item[1], ResourceState.UNSEEN)
            else:
                resource = right_item[0]
                state = join_states(ResourceState.UNSEEN, right_item[1])
            resources[key] = (HeldResource(**resource.to_csv_dict()), state)
        aliases = {
            key: value
            for key, value in left.aliases.items()
            if right.aliases.get(key) == value
        }
        cleanups = dict(left.scope_cleanups)
        cleanups.update(right.scope_cleanups)
        facts = left.path_facts & right.path_facts
        function_targets: dict[str, frozenset[str]] = {}
        for name in set(left.function_targets) | set(right.function_targets):
            left_targets = left.function_targets.get(name)
            right_targets = right.function_targets.get(name)
            targets = set(left_targets or {_UNKNOWN_FUNCTION_TARGET})
            targets.update(right_targets or {_UNKNOWN_FUNCTION_TARGET})
            function_targets[name] = frozenset(targets)
        unresolved = left.unresolved_indirect_calls | right.unresolved_indirect_calls
        return ResourceFlowState(
            resources, aliases, cleanups, function_targets, unresolved, facts
        )

    def _filter_held_resources(
        self,
        held: list[HeldResource],
        condition: ConditionInfo,
        error_source_expr: str,
        function_name: str,
    ) -> list[HeldResource]:
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

    def held_before(
        self,
        statements: list[Statement],
        error_line: int,
        condition: ConditionInfo,
        error_source_expr: str,
        function_name: str = "",
    ) -> list[HeldResource]:
        held: list[HeldResource] = []
        scope_cleanups: dict[str, tuple[str, int]] = {}

        for stmt in statements:
            if stmt.line >= error_line:
                break

            for var, release in self._scope_cleanup_declarations(stmt.text):
                scope_cleanups[var] = (release, stmt.line)

            for call in extract_call_expressions(stmt.text):
                name, args = call_name_and_args(call)
                self._apply_release(held, name, args)

            for lhs, call_name, args in _assignment_calls(stmt.text):
                cfg = self.acquire_functions.get(call_name)
                if not cfg:
                    cfg = self._summary_return_acquire(call_name, args)
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
                held.append(
                    self._resource(
                        var, call_name, cfg, stmt.line, scope_cleanups.get(var)
                    )
                )

            for call in extract_call_expressions(stmt.text):
                name, args = call_name_and_args(call)
                cfg = self.acquire_functions.get(name)
                if not cfg:
                    for var, summary_cfg in self._summary_argument_acquires(name, args):
                        if is_contract_restore_acquire(function_name, name, var):
                            continue
                        held = [
                            res
                            for res in held
                            if not self._same_resource_arg(res.var, var)
                        ]
                        held.append(
                            self._resource(
                                var,
                                name,
                                summary_cfg,
                                stmt.line,
                                scope_cleanups.get(var),
                            )
                        )
                    continue
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
                held.append(
                    self._resource(var, name, cfg, stmt.line, scope_cleanups.get(var))
                )

            # A cleanup-managed alias keeps the allocation alive under its original
            # variable while arranging release through the alias at scope exit.
            for lhs, rhs in _simple_assignments(stmt.text):
                if _is_field_expr(lhs):
                    held = [
                        resource
                        for resource in held
                        if not _same_stored_resource(rhs, resource.var)
                    ]
                    continue
                cleanup = scope_cleanups.get(lhs)
                if not cleanup:
                    continue
                for resource in held:
                    if self._same_resource_arg(resource.var, rhs):
                        resource.scope_cleanup_function = cleanup[0]
                        resource.scope_cleanup_decl_line = cleanup[1]

        return self._filter_held_resources(
            held, condition, error_source_expr, function_name
        )

    def missing_cleanup_candidates(
        self, held: list[HeldResource], cleanup_calls: list[str]
    ) -> list[str]:
        missing: list[str] = []
        for res in held:
            if self._scope_cleanup_releases(res):
                continue
            released = False
            for call in cleanup_calls:
                name, args = call_name_and_args(call)
                if cleanup_call_releases_resource(call, res) or self._consumer_releases(
                    name, args, res, "always"
                ) or self._summary_consumes(name, args, res):
                    released = True
                    break
            if not released:
                missing.append(res.release_suggestion)
        return missing

    def _resource(
        self,
        var: str,
        acquire_func: str,
        cfg: dict[str, Any],
        line: int,
        scope_cleanup: tuple[str, int] | None = None,
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
            scope_cleanup_function=scope_cleanup[0] if scope_cleanup else "",
            scope_cleanup_decl_line=scope_cleanup[1] if scope_cleanup else None,
        )

    def _scope_cleanup_declarations(self, text: str) -> list[tuple[str, str]]:
        declarations: list[tuple[str, str]] = []
        for match in re.finditer(
            r"\b([A-Za-z_]\w*)\s+__free\s*\(\s*([A-Za-z_]\w*)\s*\)", text
        ):
            declarations.append((match.group(1), match.group(2)))

        for call in extract_call_expressions(text):
            name, args = call_name_and_args(call)
            release = self.scope_cleanup_macros.get(name)
            if not release or not args:
                continue
            if isinstance(release, dict):
                release = release.get("release", "")
            release_name = str(release).strip()
            var = args[0].strip()
            if release_name and re.fullmatch(r"[A-Za-z_]\w*", var):
                declarations.append((var, release_name))
        return declarations

    @staticmethod
    def _scope_cleanup_releases(resource: HeldResource) -> bool:
        cleanup = resource.scope_cleanup_function
        return bool(cleanup and cleanup in resource.release_functions)

    def _apply_release(self, held: list[HeldResource], name: str, args: list[str]) -> None:
        kept: list[HeldResource] = []
        for res in held:
            if call_releases_resource(name, args, res) or self._consumer_releases(
                name, args, res, "always"
            ) or self._summary_consumes(name, args, res):
                continue
            kept.append(res)
        held[:] = kept

    def _summary_consumes(
        self, name: str, args: list[str], resource: HeldResource
    ) -> bool:
        summary = self.function_summaries.find(name)
        if summary is None:
            return False
        consuming = {
            ResourceAction.RELEASE.value,
            ResourceAction.TRANSFER.value,
            ResourceAction.ESCAPE.value,
        }
        for effect, actual in summary.effects_for_call(args):
            if effect.action not in consuming:
                continue
            if not self._summary_condition_matches(
                effect.condition, args, resource.var
            ):
                continue
            if effect.resource_type and effect.resource_type != resource.resource_type:
                continue
            if same_resource_expr(actual, resource.var):
                return True
        return False

    def _summary_return_acquire(
        self, name: str, args: list[str]
    ) -> dict[str, Any] | None:
        summary = self.function_summaries.find(name)
        if summary is None:
            return None
        for effect in summary.effects:
            if (
                effect.resource == "return"
                and effect.action == ResourceAction.ACQUIRE.value
                and self._summary_condition_matches(effect.condition, args)
            ):
                return self._summary_acquire_config(
                    effect.resource_type, effect.release_functions
                )
        return None

    def _summary_argument_acquires(
        self, name: str, args: list[str]
    ) -> list[tuple[str, dict[str, Any]]]:
        summary = self.function_summaries.find(name)
        if summary is None:
            return []
        acquired: list[tuple[str, dict[str, Any]]] = []
        for effect, actual in summary.effects_for_call(args):
            if (
                effect.action != ResourceAction.ACQUIRE.value
                or not self._summary_condition_matches(effect.condition, args)
            ):
                continue
            var = actual.strip()
            while var.startswith("&"):
                var = var[1:].strip()
            if var:
                acquired.append(
                    (
                        var,
                        self._summary_acquire_config(
                            effect.resource_type, effect.release_functions
                        ),
                    )
                )
        return acquired

    def _summary_acquire_config(
        self, resource_type: str, release_functions: tuple[str, ...] = ()
    ) -> dict[str, Any]:
        return {
            "resource_type": resource_type or "unknown",
            "release": list(release_functions)
            or self.release_functions_by_type.get(resource_type, []),
        }

    @staticmethod
    def _summary_condition_matches(
        condition: str, args: list[str], held_resource: str = ""
    ) -> bool:
        condition = _strip_condition_parens(condition.strip())
        if condition == "always":
            return True
        if condition in {"1", "true"}:
            return True
        if condition in {"0", "false", "never"}:
            return False

        match = re.fullmatch(
            r"(!\s*)?arg(\d+)(?:\s*(==|!=)\s*(NULL|0))?", condition
        )
        if not match:
            return False
        negated, raw_index, operator, expected = match.groups()
        index = int(raw_index)
        if index >= len(args):
            return False
        actual = args[index].strip()
        literal_truth = _literal_truth(actual)
        is_null = literal_truth is False
        is_held = bool(held_resource and same_resource_expr(actual, held_resource))

        if operator == "==":
            return is_null
        if operator == "!=":
            return is_held or literal_truth is True
        if negated:
            return is_null
        return is_held or literal_truth is True

    def _release_functions_by_type(self) -> dict[str, list[str]]:
        releases: dict[str, list[str]] = {}
        for cfg in self.acquire_functions.values():
            resource_type = str(cfg.get("resource_type", "unknown"))
            names = cfg.get("release", [])
            if isinstance(names, str):
                names = [names]
            bucket = releases.setdefault(resource_type, [])
            for name in names:
                value = str(name)
                if value not in bucket:
                    bucket.append(value)
        return releases

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
        condition_resource = self._failure_condition_resource(condition.condition)
        if condition_resource and same_resource_expr(condition_resource, res.var):
            return True
        source_name, source_args = call_name_and_args(error_source_expr)
        if (
            source_name in {"PTR_ERR", "PTR_ERR_OR_ZERO"}
            and source_args
            and self._same_resource_arg(source_args[0], res.var)
            and self._condition_requires_nonzero_error(condition)
        ):
            return True

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
        if condition.condition_type in {"is_err", "is_err_or_null", "err_ptr_check"}:
            return True
        if error_source_expr == "unknown":
            return True
        return error_source_expr.startswith(f"{res.acquire_func}(")

    @staticmethod
    def _failure_condition_resource(condition: str) -> str:
        value = _strip_condition_parens(condition.strip())
        direct = re.fullmatch(r"!\s*(.+)", value)
        if direct:
            return _strip_condition_parens(direct.group(1))
        wrapper = re.fullmatch(r"IS_ERR(?:_OR_NULL)?\s*\((.+)\)", value)
        if wrapper:
            return wrapper.group(1).strip()
        null_cmp = re.fullmatch(r"(.+?)\s*==\s*(?:NULL|0)", value)
        if null_cmp:
            return null_cmp.group(1).strip()
        return ""

    @staticmethod
    def _condition_requires_nonzero_error(condition: ConditionInfo) -> bool:
        var = condition.error_var.strip()
        cond = condition.condition.strip()
        if not var:
            return False
        if condition.condition_type in {
            "ret_nonzero",
            "negative_error",
            "specific_error_code",
        }:
            return True
        return bool(
            re.match(rf"^{re.escape(var)}\s*&&", cond)
            or re.fullmatch(rf"{re.escape(var)}", cond)
            or re.match(rf"^{re.escape(var)}\s*!=\s*0$", cond)
        )

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
