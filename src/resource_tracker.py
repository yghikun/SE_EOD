"""Track simple function-local resources and suspicious cleanup candidates."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
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
from .function_summary import FunctionSummaryDB, SummaryEffect
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
    resource_id: str = ""
    generation: int = 1
    multiplicity: str = "one"
    release_cardinality: str = "one"
    validity_guard: str = ""
    validity_guard_source: str = "none"
    out_resource_arg: int | None = None
    release_arg_index: int = 0
    release_arg_requires_address: bool = False
    release_suggestion_template: str = ""
    scope_cleanup_function: str = ""
    scope_cleanup_decl_line: int | None = None
    ownership_state: str = ResourceState.ACQUIRED.value
    uncertainty_causes: list[str] = field(default_factory=list)

    @property
    def release_suggestion(self) -> str:
        if self.release_suggestion_template:
            return self.release_suggestion_template.format(var=self.var)
        release = self.release_functions[0] if self.release_functions else "release"
        return f"{release}({self.var})"

    def to_csv_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CleanupOutcome:
    missing: list[str]
    released: list[str]
    partial: bool


@dataclass(frozen=True)
class PendingSummaryEffect:
    call_site_id: str
    resource_id: str
    result_var: str
    result_version: int
    action: str
    strength: str
    exit_class: str
    return_guard: str
    effect_cardinality: str = "one"


@dataclass
class ScopeFrame:
    aliases: dict[str, str]
    scope_cleanups: dict[str, tuple[str, int]]
    function_targets: dict[str, frozenset[str]]
    function_target_complete: dict[str, bool]
    definition_versions: dict[str, int]
    path_facts: frozenset[tuple[str, bool]]
    declared_names: frozenset[str] = frozenset()


@dataclass
class ResourceFlowState:
    resources: dict[str, tuple[HeldResource, ResourceState]]
    aliases: dict[str, str]
    scope_cleanups: dict[str, tuple[str, int]]
    function_targets: dict[str, frozenset[str]]
    function_target_complete: dict[str, bool] = field(default_factory=dict)
    definition_versions: dict[str, int] = field(default_factory=dict)
    scope_frames: tuple[ScopeFrame, ...] = ()
    pending_summary_effects: tuple[PendingSummaryEffect, ...] = ()
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
            function_target_complete=dict(self.function_target_complete),
            definition_versions=dict(self.definition_versions),
            scope_frames=tuple(
                ScopeFrame(
                    aliases=dict(frame.aliases),
                    scope_cleanups=dict(frame.scope_cleanups),
                    function_targets=dict(frame.function_targets),
                    function_target_complete=dict(frame.function_target_complete),
                    definition_versions=dict(frame.definition_versions),
                    path_facts=frozenset(frame.path_facts),
                    declared_names=frozenset(frame.declared_names),
                )
                for frame in self.scope_frames
            ),
            pending_summary_effects=tuple(self.pending_summary_effects),
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
    branch_wrapper = re.fullmatch(r"(?:likely|unlikely)\s*\((.+)\)", value)
    if branch_wrapper:
        return _condition_fact(branch_wrapper.group(1), branch_truth)
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


def _assigned_call_result(
    assignments: list[tuple[str, str, list[str]]],
    call_name: str,
    args: list[str],
) -> str:
    normalized_args = [norm_resource_expr(arg) for arg in args]
    for lhs, assigned_name, assigned_args in assignments:
        if assigned_name != call_name:
            continue
        if [norm_resource_expr(arg) for arg in assigned_args] == normalized_args:
            return norm_resource_expr(lhs)
    return ""


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
        elif call_name in {"IS_ERR", "IS_ERR_OR_NULL"} and args:
            facts.append(
                (f"is_err_source:{lhs_key}:{norm_resource_expr(args[0])}", True)
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


def _declaration_names(text: str) -> set[str]:
    function_pointer = re.search(r"\(\s*\*\s*([A-Za-z_]\w*)\s*\)", text)
    if function_pointer:
        return {function_pointer.group(1)}
    prefix = text.split("=", 1)[0].split(";", 1)[0]
    identifiers = re.findall(r"[A-Za-z_]\w*", prefix)
    ignored = {
        "const",
        "volatile",
        "static",
        "extern",
        "unsigned",
        "signed",
        "long",
        "short",
        "struct",
        "union",
        "enum",
        "void",
        "char",
        "int",
        "float",
        "double",
    }
    names = [name for name in identifiers if name not in ignored]
    return {names[-1]} if names else set()


def _fact_mentions_assignment(atom: str, assigned: str) -> bool:
    expression = atom.split(":", 1)[1] if ":" in atom else atom
    if re.search(
        rf"(?<![A-Za-z0-9_]){re.escape(assigned)}@\d+:[^\s:]+#\d+",
        expression,
    ):
        return False
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
        cfg, result = self._cfg_analysis(function)
        block = self._error_entry_block(cfg, error_line)
        if block is None or block.id not in result.in_states:
            return None
        held_by_identity: dict[tuple[str, str, int], HeldResource] = {}
        for state in result.in_states[block.id]:
            if not self._state_allows_condition(state, condition.condition):
                continue
            for resource, resource_state in state.resources.values():
                if resource_state not in {
                    ResourceState.ACQUIRED,
                    ResourceState.MAY_ACQUIRED,
                }:
                    continue
                if resource.acquire_line > error_line:
                    continue
                guard_status = self._resource_validity_status(
                    state, resource, condition.condition
                )
                if guard_status is False:
                    continue
                if self._state_marks_acquire_failure_source(
                    state, condition, resource
                ):
                    continue
                identity = self._resource_identity(resource)
                held_resource = HeldResource(**resource.to_csv_dict())
                effective_state = resource_state
                if guard_status is None and resource.validity_guard:
                    effective_state = ResourceState.MAY_ACQUIRED
                    self._add_uncertainty(
                        held_resource, "unresolved_acquire_validity"
                    )
                held_resource.ownership_state = effective_state.value
                existing = held_by_identity.get(identity)
                if existing is None:
                    held_by_identity[identity] = held_resource
                    continue
                existing.uncertainty_causes = sorted(
                    {
                        *existing.uncertainty_causes,
                        *held_resource.uncertainty_causes,
                    }
                )
                if held_resource.multiplicity == "many":
                    existing.multiplicity = "many"
                if effective_state is ResourceState.MAY_ACQUIRED:
                    existing.ownership_state = ResourceState.MAY_ACQUIRED.value
        held = list(held_by_identity.values())
        return self._filter_held_resources(
            held, condition, error_source_expr, function.name
        )

    def _cfg_analysis(
        self, function: Any
    ) -> tuple[Any, DisjunctiveDataflowResult[ResourceFlowState]]:
        cache_key = (str(function.file), function.start_line)
        cached = self._cfg_cache.get(cache_key)
        if cached is not None:
            return cached
        cfg = build_cfg(function)
        result = solve_forward_disjunctive(
            cfg,
            ResourceFlowState({}, {}, {}, {}),
            lambda block, state: self._transfer_cfg_block(
                block, state, function.name
            ),
            self._join_flow_states,
            lambda state: state.clone(),
            edge_transfer=lambda edge, state: self._transfer_cfg_edge(
                edge, state, cfg
            ),
        )
        cached = (cfg, result)
        self._cfg_cache[cache_key] = cached
        self._cfg_function_names[cache_key] = function.name
        return cached

    def missing_cleanup_candidates_cfg(
        self,
        function: Any,
        error_line: int,
        condition: ConditionInfo,
        target_label: str,
        held: list[HeldResource],
    ) -> list[str] | None:
        outcome = self.cleanup_outcome_cfg(
            function, error_line, condition, target_label, held
        )
        return outcome.missing if outcome is not None else None

    def cleanup_outcome_cfg(
        self,
        function: Any,
        error_line: int,
        condition: ConditionInfo,
        target_label: str,
        held: list[HeldResource],
    ) -> CleanupOutcome | None:
        """Read cleanup effects from CFG states at reachable returns.

        ``cleanup_calls`` remains useful evidence, but a call's textual presence
        after a label does not prove that every path executes it.
        """

        if function.body_node is None:
            return None
        cfg, result = self._cfg_analysis(function)
        if target_label:
            start = cfg.labels.get(target_label)
        else:
            block = self._error_entry_block(cfg, error_line)
            start = block.id if block is not None else None
        if start is None:
            return None

        reachable = self._reachable_cfg_blocks(cfg, start)
        return_blocks = [
            block_id
            for block_id in reachable
            if cfg.blocks[block_id].kind == "return_statement"
        ]
        if not return_blocks:
            return None

        observed_states: list[ResourceFlowState] = []
        for block_id in return_blocks:
            states = result.out_states.get(block_id) or result.in_states.get(block_id, [])
            observed_states.extend(
                state
                for state in states
                if self._state_allows_condition(state, condition.condition)
            )
        if not observed_states:
            return None

        missing: list[str] = []
        released: list[str] = []
        partial = False
        held_by_id = {
            self._resource_identity(resource): resource for resource in held
        }
        for state in observed_states:
            state_held: set[str] = set()
            state_released: set[str] = set()
            for state_resource, resource_state in state.resources.values():
                identity = self._resource_identity(state_resource)
                if identity not in held_by_id:
                    continue
                if resource_state in {
                    ResourceState.ACQUIRED,
                    ResourceState.MAY_ACQUIRED,
                }:
                    state_held.add(identity)
                elif resource_state in {
                    ResourceState.RELEASED,
                    ResourceState.TRANSFERRED,
                    ResourceState.ESCAPED,
                }:
                    state_released.add(identity)
            partial |= bool(state_held and state_released)
            for identity in state_released:
                suggestion = held_by_id[identity].release_suggestion
                if suggestion not in released:
                    released.append(suggestion)

        for resource in held:
            if self._scope_cleanup_releases(resource):
                continue
            identity = self._resource_identity(resource)
            possibly_held = False
            uncertain = False
            uncertainty_causes = set(resource.uncertainty_causes)
            for state in observed_states:
                for state_resource, resource_state in state.resources.values():
                    if self._resource_identity(state_resource) != identity:
                        continue
                    if resource_state in {
                        ResourceState.ACQUIRED,
                        ResourceState.MAY_ACQUIRED,
                    }:
                        possibly_held = True
                        uncertain |= resource_state is ResourceState.MAY_ACQUIRED
                        uncertainty_causes.update(
                            state_resource.uncertainty_causes
                        )
            if possibly_held:
                if uncertain:
                    resource.ownership_state = ResourceState.MAY_ACQUIRED.value
                    resource.uncertainty_causes = sorted(uncertainty_causes)
                if resource.release_suggestion not in missing:
                    missing.append(resource.release_suggestion)
        return CleanupOutcome(missing, released, partial)

    @staticmethod
    def _reachable_cfg_blocks(cfg: Any, start: int) -> set[int]:
        reachable: set[int] = set()
        pending = [start]
        while pending:
            block_id = pending.pop()
            if block_id in reachable:
                continue
            reachable.add(block_id)
            pending.extend(
                edge.target
                for edge in cfg.successors(block_id)
                if edge.target not in reachable
            )
        return reachable

    @staticmethod
    def _error_entry_block(cfg: Any, error_line: int) -> BasicBlock | None:
        conditions = [
            block
            for block in cfg.blocks.values()
            if block.kind == "condition"
            and block.start_line <= error_line <= block.end_line
        ]
        if conditions:
            return min(
                conditions,
                key=lambda block: (block.end_line - block.start_line, block.id),
            )
        return cfg.block_at_line(error_line)

    @staticmethod
    def _resource_identity(resource: HeldResource) -> str:
        return resource.resource_id or (
            f"{norm_resource_expr(resource.var)}@{resource.acquire_line}:"
            f"{resource.acquire_func}"
        )

    def cfg_diagnostics(self) -> dict[str, Any]:
        functions: list[dict[str, Any]] = []
        unresolved_calls: set[str] = set()
        inferred_validity_guards: set[str] = set()
        unknown_validity_guards: set[str] = set()
        loop_multiplicity_resources: set[str] = set()
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
                    inferred_validity_guards.update(
                        f"{cache_key[0]}:{cache_key[1]}:{resource.resource_id}"
                        for resource, _resource_state in state.resources.values()
                        if resource.validity_guard_source == "compatibility_default"
                    )
                    unknown_validity_guards.update(
                        f"{cache_key[0]}:{cache_key[1]}:{resource.resource_id}"
                        for resource, resource_state in state.resources.values()
                        if resource.validity_guard
                        and resource_state
                        in {ResourceState.ACQUIRED, ResourceState.MAY_ACQUIRED}
                        and self._resource_validity_status(state, resource) is None
                    )
                    loop_multiplicity_resources.update(
                        f"{cache_key[0]}:{cache_key[1]}:{resource.resource_id}"
                        for resource, _resource_state in state.resources.values()
                        if resource.multiplicity == "many"
                    )
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
            "inferred_validity_guards": len(inferred_validity_guards),
            "unknown_validity_guards": len(unknown_validity_guards),
            "loop_multiplicity_resources": len(loop_multiplicity_resources),
            "function_details": functions,
        }

    def cfg_edge_witness(
        self,
        function: Any,
        error_line: int,
        branch_taken: str,
        condition_start_byte: int = 0,
        condition_end_byte: int = 0,
    ) -> dict[str, Any]:
        if function.body_node is None:
            return {}
        cfg, result = self._cfg_analysis(function)
        edge: CFGEdge | None = None
        if branch_taken in {"true", "false"}:
            blocks = [
                block
                for block in cfg.blocks.values()
                if block.kind == "condition"
                and (
                    (
                        condition_start_byte
                        and block.condition_start_byte == condition_start_byte
                    )
                    or (
                        not condition_start_byte
                        and block.start_line <= error_line <= block.end_line
                    )
                )
            ]
            if blocks:
                source = min(blocks, key=lambda block: block.id)
                edge = next(
                    (
                        candidate
                        for candidate in cfg.successors(source.id)
                        if candidate.kind == branch_taken
                    ),
                    None,
                )
        else:
            source = cfg.block_at_line(error_line)
            if source is not None:
                edge = next(
                    (
                        candidate
                        for candidate in cfg.successors(source.id)
                        if candidate.kind == "return"
                    ),
                    None,
                )
        if edge is None:
            return {}

        reachable = self._reachable_cfg_blocks(cfg, edge.target)
        exits = sorted(
            block_id
            for block_id in reachable
            if cfg.blocks[block_id].kind == "return_statement"
        )
        exit_states: list[dict[str, Any]] = []
        for block_id in exits:
            snapshots: list[dict[str, Any]] = []
            states = result.out_states.get(block_id) or result.in_states.get(
                block_id, []
            )
            for state in states:
                snapshots.append(
                    {
                        "resources": [
                            {
                                "resource_id": resource_id,
                                "state": resource_state.value,
                                "multiplicity": resource.multiplicity,
                                "uncertainty_causes": list(
                                    resource.uncertainty_causes
                                ),
                            }
                            for resource_id, (
                                resource,
                                resource_state,
                            ) in sorted(state.resources.items())
                        ],
                        "path_facts": [
                            {"atom": atom, "truth": truth}
                            for atom, truth in sorted(state.path_facts)
                        ],
                        "pending_summary_effects": [
                            {
                                "call_site_id": pending.call_site_id,
                                "resource_id": pending.resource_id,
                                "result_var": pending.result_var,
                                "result_version": pending.result_version,
                                "action": pending.action,
                                "strength": pending.strength,
                                "exit_class": pending.exit_class,
                                "return_guard": pending.return_guard,
                                "effect_cardinality": pending.effect_cardinality,
                            }
                            for pending in state.pending_summary_effects
                        ],
                    }
                )
            block = cfg.blocks[block_id]
            exit_states.append(
                {
                    "block": block_id,
                    "line": block.start_line,
                    "states": snapshots,
                }
            )
        source_block = cfg.blocks[edge.source]
        scope_unwind_edges = [
            {
                "edge_id": candidate.edge_id,
                "source": candidate.source,
                "target": candidate.target,
                "count": candidate.scope_unwind,
            }
            for candidate in cfg.edges
            if candidate.source in reachable and candidate.scope_unwind
        ]
        return {
            "kind": "cfg_analysis_snapshot",
            "edge_id": edge.edge_id,
            "source_block": edge.source,
            "target_block": edge.target,
            "edge_kind": edge.kind,
            "scope_unwind": edge.scope_unwind,
            "condition": edge.condition,
            "condition_start_byte": (
                condition_start_byte or source_block.condition_start_byte
            ),
            "condition_end_byte": (
                condition_end_byte or source_block.condition_end_byte
            ),
            "source_state_count": len(result.out_states.get(edge.source, [])),
            "reachable_blocks": sorted(reachable),
            "scope_unwind_edges": scope_unwind_edges,
            "reachable_return_blocks": exits,
            "exit_states": exit_states,
            "widened_on_path": bool(result.widened_blocks & reachable),
            "analysis_truncated": result.truncated,
            "cfg_complete": not cfg.unsupported_nodes,
            "unsupported_nodes": list(cfg.unsupported_nodes),
        }

    @staticmethod
    def _state_allows_condition(
        state: ResourceFlowState, condition: str
    ) -> bool:
        facts = _condition_facts(condition, True)
        known_facts = dict(state.path_facts)
        return all(known_facts.get(atom) in {None, truth} for atom, truth in facts)

    def _resource_validity_status(
        self,
        state: ResourceFlowState,
        resource: HeldResource,
        assumed_condition: str = "",
    ) -> bool | None:
        guard = resource.validity_guard.strip()
        if not guard:
            return True
        known_pairs = list(state.path_facts)
        if assumed_condition:
            known_pairs.extend(_condition_facts(assumed_condition, True))
        known = self._expanded_path_facts(state, known_pairs)
        required = self._expanded_path_facts(
            state, _condition_facts(guard, True)
        )
        if not required:
            return None
        if any(known.get(atom) not in {None, truth} for atom, truth in required.items()):
            return False
        if all(known.get(atom) == truth for atom, truth in required.items()):
            # Compatibility defaults can recognize a definite failure edge, but
            # they are not reviewed API contracts and cannot prove acquisition.
            return (
                None
                if resource.validity_guard_source == "compatibility_default"
                else True
            )
        return None

    def _expanded_path_facts(
        self,
        state: ResourceFlowState,
        facts: list[tuple[str, bool]] | frozenset[tuple[str, bool]],
    ) -> dict[str, bool]:
        expanded = dict(facts)
        for atom, truth in list(expanded.items()):
            if atom.startswith(("valid:", "nonnegative:")):
                prefix, expression = atom.split(":", 1)
                resolved = self._resolve_alias(state, expression)
                expanded[f"{prefix}:{resolved}"] = truth
        changed = True
        while changed:
            changed = False
            for relation, enabled in list(expanded.items()):
                if not enabled or not relation.startswith("is_err_source:"):
                    continue
                _, predicate, source = relation.split(":", 2)
                predicate_truth = expanded.get(f"valid:{predicate}")
                if predicate_truth is None:
                    resolved_predicate = self._resolve_alias(state, predicate)
                    predicate_truth = expanded.get(f"valid:{resolved_predicate}")
                if predicate_truth is None:
                    continue
                source_truth = not predicate_truth
                for source_atom in {
                    f"valid:{source}",
                    f"valid:{self._resolve_alias(state, source)}",
                }:
                    if source_atom not in expanded:
                        expanded[source_atom] = source_truth
                        changed = True
        return expanded

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
        if block.kind == "scope_enter":
            self._enter_scope(state)
            return state
        if block.kind == "scope_exit":
            self._leave_scope(state)
            return state
        if block.kind in {"entry", "exit", "empty", "condition", "loop_condition", "loop_exit", "label"}:
            return state
        text = block.text
        assignment_calls = _assignment_calls(text)
        assigned = _assigned_expressions(text)
        if block.kind == "declaration":
            self._record_scope_declarations(state, _declaration_names(text))
        if assigned:
            for expression in assigned:
                state.definition_versions[expression] = (
                    state.definition_versions.get(expression, 0) + 1
                )
            state.path_facts = frozenset(
                (atom, truth)
                for atom, truth in state.path_facts
                if not any(
                    _fact_mentions_assignment(atom, expression)
                    for expression in assigned
                )
            )
            state.pending_summary_effects = tuple(
                pending
                for pending in state.pending_summary_effects
                if pending.result_var not in assigned
            )
        assignment_facts = _assignment_path_facts(text)
        if assignment_facts:
            facts = dict(state.path_facts)
            for atom, truth in assignment_facts:
                facts[atom] = truth
            state.path_facts = frozenset(facts.items())
        for var, release in self._scope_cleanup_declarations(text):
            state.scope_cleanups[var] = (release, block.start_line)

        target_assignments = _function_target_assignments(text)
        handled_function_targets: set[str] = set()
        for lhs, target, from_declaration in target_assignments:
            self._flow_assign_function_target(state, lhs, target, from_declaration)
            handled_function_targets.add(norm_resource_expr(lhs))
        for assigned_expression in assigned:
            if (
                assigned_expression in state.function_targets
                and assigned_expression not in handled_function_targets
            ):
                state.function_targets[assigned_expression] = frozenset(
                    {_UNKNOWN_FUNCTION_TARGET}
                )
                state.function_target_complete[assigned_expression] = False

        for call in extract_call_expressions(text):
            name, args = call_name_and_args(call)
            assigned_result = _assigned_call_result(
                assignment_calls, name, args
            )
            if name == "swap" and len(args) >= 2:
                self._swap_aliases(state, args[0], args[1])
                continue
            self._flow_apply_call(
                state,
                name,
                args,
                _assigned_call_result(assignment_calls, name, args),
                f"{name}@{block.start_line}:b{block.id}",
            )
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
                        assigned_result,
                    )
                continue
            if "out_resource_arg" in cfg and assigned_result:
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
                    state,
                    var,
                    name,
                    cfg,
                    block.start_line,
                    function_name,
                    assigned_result,
                )

        for lhs, call_name, args in assignment_calls:
            cfg = self.acquire_functions.get(call_name) or self._summary_return_acquire(
                call_name, args
            )
            if not cfg:
                continue
            var = _out_resource_var(args, cfg) if "out_resource_arg" in cfg else lhs
            self._flow_acquire(
                state,
                var,
                call_name,
                cfg,
                block.start_line,
                function_name,
                lhs,
            )

        for lhs, rhs in _simple_assignments(text):
            lhs_key = norm_resource_expr(lhs)
            rhs_key = self._resolve_alias(state, rhs)
            if _is_field_expr(lhs) or "[" in lhs_key:
                if rhs_key in state.resources:
                    resource, resource_state = state.resources[rhs_key]
                    if resource_state in {
                        ResourceState.ACQUIRED,
                        ResourceState.MAY_ACQUIRED,
                    }:
                        self._add_uncertainty(
                            resource, "field_store_without_contract"
                        )
                        state.resources[rhs_key] = (
                            resource,
                            ResourceState.MAY_ACQUIRED,
                        )
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
    def _enter_scope(state: ResourceFlowState) -> None:
        frame = ScopeFrame(
            aliases=dict(state.aliases),
            scope_cleanups=dict(state.scope_cleanups),
            function_targets=dict(state.function_targets),
            function_target_complete=dict(state.function_target_complete),
            definition_versions=dict(state.definition_versions),
            path_facts=frozenset(state.path_facts),
        )
        state.scope_frames = (*state.scope_frames, frame)

    @staticmethod
    def _record_scope_declarations(
        state: ResourceFlowState, declared_names: set[str]
    ) -> None:
        if not state.scope_frames or not declared_names:
            return
        frame = state.scope_frames[-1]
        replacement = ScopeFrame(
            aliases=frame.aliases,
            scope_cleanups=frame.scope_cleanups,
            function_targets=frame.function_targets,
            function_target_complete=frame.function_target_complete,
            definition_versions=frame.definition_versions,
            path_facts=frame.path_facts,
            declared_names=frozenset(
                {*frame.declared_names, *map(norm_resource_expr, declared_names)}
            ),
        )
        state.scope_frames = (*state.scope_frames[:-1], replacement)

    @staticmethod
    def _leave_scope(state: ResourceFlowState) -> None:
        if not state.scope_frames:
            return
        frame = state.scope_frames[-1]
        state.scope_frames = state.scope_frames[:-1]
        for name in frame.declared_names:
            if name in frame.aliases:
                state.aliases[name] = frame.aliases[name]
            else:
                state.aliases.pop(name, None)
            if name in frame.scope_cleanups:
                state.scope_cleanups[name] = frame.scope_cleanups[name]
            else:
                state.scope_cleanups.pop(name, None)
            if name in frame.function_targets:
                state.function_targets[name] = frame.function_targets[name]
                state.function_target_complete[name] = (
                    frame.function_target_complete.get(name, False)
                )
            else:
                state.function_targets.pop(name, None)
                state.function_target_complete.pop(name, None)
            if name in frame.definition_versions:
                state.definition_versions[name] = frame.definition_versions[name]
            else:
                state.definition_versions.pop(name, None)

        current_facts = {
            (atom, truth)
            for atom, truth in state.path_facts
            if not any(
                _fact_mentions_assignment(atom, name)
                for name in frame.declared_names
            )
        }
        restored_facts = {
            (atom, truth)
            for atom, truth in frame.path_facts
            if any(
                _fact_mentions_assignment(atom, name)
                for name in frame.declared_names
            )
        }
        state.path_facts = frozenset(current_facts | restored_facts)
        state.pending_summary_effects = tuple(
            pending
            for pending in state.pending_summary_effects
            if pending.result_var not in frame.declared_names
        )

    def _transfer_cfg_edge(
        self,
        edge: CFGEdge,
        state: ResourceFlowState,
        cfg: Any | None = None,
    ) -> ResourceFlowState | None:
        for _ in range(edge.scope_unwind):
            self._leave_scope(state)
        if edge.kind == "backedge":
            modified = self._loop_modified_expressions(cfg, edge) if cfg else set()
            state.path_facts = frozenset(
                (atom, truth)
                for atom, truth in state.path_facts
                if not any(
                    _fact_mentions_assignment(atom, expression)
                    for expression in modified
                )
            )
            return state
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
        state.path_facts = frozenset(
            self._expanded_path_facts(state, list(facts.items())).items()
        )
        self._apply_pending_summary_effects(state)
        return state

    @staticmethod
    def _loop_modified_expressions(cfg: Any, edge: CFGEdge) -> set[str]:
        forward: set[int] = set()
        pending = [edge.target]
        while pending:
            block_id = pending.pop()
            if block_id in forward:
                continue
            forward.add(block_id)
            pending.extend(
                candidate.target
                for candidate in cfg.successors(block_id)
                if candidate.target not in forward
            )

        reverse: set[int] = set()
        pending = [edge.source]
        while pending:
            block_id = pending.pop()
            if block_id in reverse:
                continue
            reverse.add(block_id)
            pending.extend(
                candidate.source
                for candidate in cfg.predecessors(block_id)
                if candidate.source not in reverse
            )

        loop_blocks = forward & reverse
        modified: set[str] = set()
        for block_id in loop_blocks:
            modified.update(_assigned_expressions(cfg.blocks[block_id].text))
        condition = cfg.blocks[edge.target].text
        modified.update(
            identifier
            for identifier in re.findall(r"[A-Za-z_]\w*", condition)
            if identifier not in {"likely", "unlikely", "IS_ERR", "IS_ERR_OR_NULL"}
        )
        return modified

    def _apply_pending_summary_effects(self, state: ResourceFlowState) -> None:
        remaining: list[PendingSummaryEffect] = []
        for pending in state.pending_summary_effects:
            decision = self._pending_effect_guard(state, pending)
            if decision is None:
                remaining.append(pending)
                continue
            if not decision:
                continue
            item = state.resources.get(pending.resource_id)
            if item is None:
                continue
            resource, resource_state = item
            if resource_state not in {
                ResourceState.ACQUIRED,
                ResourceState.MAY_ACQUIRED,
            }:
                continue
            if pending.strength == "may":
                self._add_uncertainty(resource, "may_summary_effect")
                state.resources[pending.resource_id] = (
                    resource,
                    ResourceState.MAY_ACQUIRED,
                )
                continue
            self._discharge_resource(
                state,
                pending.resource_id,
                resource,
                resource_state,
                self._summary_action_state(pending.action),
                pending.effect_cardinality,
            )
        state.pending_summary_effects = tuple(remaining)

    @staticmethod
    def _pending_effect_guard(
        state: ResourceFlowState, pending: PendingSummaryEffect
    ) -> bool | None:
        if state.definition_versions.get(pending.result_var, 0) != pending.result_version:
            return False
        guard = pending.return_guard.strip()
        if not guard:
            guard = "return == 0" if pending.exit_class == "success" else "return != 0"
        expression = re.sub(
            r"\breturn\b", pending.result_var, guard, flags=re.IGNORECASE
        )
        required = _condition_facts(expression, True)
        if not required:
            return None
        known = dict(state.path_facts)
        if any(known.get(atom) not in {None, truth} for atom, truth in required):
            return False
        if all(known.get(atom) == truth for atom, truth in required):
            return True
        return None

    def _flow_acquire(
        self,
        state: ResourceFlowState,
        var: str,
        call_name: str,
        cfg: dict[str, Any],
        line: int,
        function_name: str,
        result_var: str = "",
    ) -> None:
        if not var or is_contract_restore_acquire(function_name, call_name, var):
            return
        expression = norm_resource_expr(var)
        existing = next(
            (
                resource
                for resource, _ in state.resources.values()
                if norm_resource_expr(resource.var) == expression
                and resource.acquire_func == call_name
                and resource.acquire_line == line
            ),
            None,
        )
        acquired_state = ResourceState.ACQUIRED
        if existing is None:
            generation = 1 + max(
                (
                    resource.generation
                    for resource, _ in state.resources.values()
                    if norm_resource_expr(resource.var) == expression
                ),
                default=0,
            )
            resource = self._resource(
                var,
                call_name,
                cfg,
                line,
                state.scope_cleanups.get(var),
                generation,
                self._acquire_validity_guard(var, cfg, result_var),
                self._acquire_validity_guard_source(cfg, result_var),
            )
            if resource.validity_guard:
                resource.validity_guard = resource.validity_guard.replace(
                    norm_resource_expr(var), resource.resource_id
                )
        else:
            resource = HeldResource(**existing.to_csv_dict())
            existing_state = state.resources[resource.resource_id][1]
            if existing_state in {
                ResourceState.ACQUIRED,
                ResourceState.MAY_ACQUIRED,
            }:
                resource.multiplicity = "many"
                self._add_uncertainty(resource, "loop_multiple_instances")
                acquired_state = ResourceState.MAY_ACQUIRED
            else:
                resource.multiplicity = "one"
                resource.uncertainty_causes = []
                acquired_state = ResourceState.ACQUIRED
            resource.ownership_state = acquired_state.value
        state.aliases[expression] = resource.resource_id
        state.resources[resource.resource_id] = (
            resource,
            acquired_state,
        )
        state.path_facts = frozenset(
            (atom, truth)
            for atom, truth in state.path_facts
            if not same_resource_expr(atom, expression)
            and not atom.endswith(f":{expression}")
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
            state.function_target_complete[lhs_key] = True
        elif lhs_key in state.function_targets:
            state.function_targets[lhs_key] = frozenset({_UNKNOWN_FUNCTION_TARGET})
            state.function_target_complete[lhs_key] = False

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
        self,
        state: ResourceFlowState,
        name: str,
        args: list[str],
        result_var: str = "",
        call_site_id: str = "",
    ) -> None:
        resolved_name = norm_resource_expr(name)
        for arg in args:
            normalized_arg = norm_resource_expr(arg)
            if not normalized_arg.startswith("&"):
                continue
            target_var = normalized_arg[1:]
            if target_var in state.definition_versions or any(
                pending.result_var == target_var
                for pending in state.pending_summary_effects
            ):
                state.definition_versions[target_var] = (
                    state.definition_versions.get(target_var, 0) + 1
                )
                state.pending_summary_effects = tuple(
                    pending
                    for pending in state.pending_summary_effects
                    if pending.result_var != target_var
                )
            if target_var in state.function_targets:
                state.function_targets[target_var] = frozenset(
                    {_UNKNOWN_FUNCTION_TARGET}
                )
                state.function_target_complete[target_var] = False
        target_names = state.function_targets.get(resolved_name)
        if target_names is not None:
            self._flow_apply_indirect_call(
                state, resolved_name, target_names, args, result_var
            )
            return

        resolved_args = [self._resolve_alias(state, arg) for arg in args]
        for key, (resource, resource_state) in list(state.resources.items()):
            identity = HeldResource(**resource.to_csv_dict())
            identity.var = key
            directly_released = call_releases_resource(
                name, resolved_args, identity
            ) or self._consumer_releases(name, resolved_args, identity, "always")
            if name == "ext4_fc_free" and call_releases_resource(
                name, resolved_args, resource
            ):
                directly_released = True
            if directly_released:
                self._discharge_resource(
                    state,
                    key,
                    resource,
                    resource_state,
                    ResourceState.RELEASED,
                    resource.release_cardinality,
                )
                continue

            immediate_effect = self._summary_consumption_effect(
                name, resolved_args, identity, exit_sensitive=False
            )
            if immediate_effect is not None and resource_state in {
                ResourceState.ACQUIRED,
                ResourceState.MAY_ACQUIRED,
            }:
                if immediate_effect.strength == "must":
                    self._discharge_resource(
                        state,
                        key,
                        resource,
                        resource_state,
                        self._summary_action_state(immediate_effect.action),
                        immediate_effect.effect_cardinality,
                    )
                else:
                    self._add_uncertainty(resource, "may_summary_effect")
                    state.resources[key] = (resource, ResourceState.MAY_ACQUIRED)
                continue

            exit_effects = self._matching_summary_consumption_effects(
                name, resolved_args, identity, exit_sensitive=True
            )
            if exit_effects and resource_state in {
                ResourceState.ACQUIRED,
                ResourceState.MAY_ACQUIRED,
            }:
                if result_var:
                    pending = list(state.pending_summary_effects)
                    for effect in exit_effects:
                        item = PendingSummaryEffect(
                            call_site_id=call_site_id or name,
                            resource_id=key,
                            result_var=result_var,
                            result_version=state.definition_versions.get(
                                result_var, 0
                            ),
                            action=effect.action,
                            strength=effect.strength,
                            exit_class=effect.exit_class,
                            return_guard=effect.return_guard,
                            effect_cardinality=effect.effect_cardinality,
                        )
                        if item not in pending:
                            pending.append(item)
                    state.pending_summary_effects = tuple(pending)
                else:
                    self._add_uncertainty(
                        resource, "exit_sensitive_summary_unresolved"
                    )
                    state.resources[key] = (resource, ResourceState.MAY_ACQUIRED)
                continue

            summary = self.function_summaries.find(name)
            if (
                summary is None
                and resource_state
                in {ResourceState.ACQUIRED, ResourceState.MAY_ACQUIRED}
                and any(same_resource_expr(actual, key) for actual in resolved_args)
                and self._looks_indirect_call(name)
            ):
                self._add_uncertainty(resource, "unknown_indirect_call")
                state.resources[key] = (resource, ResourceState.MAY_ACQUIRED)
                state.unresolved_indirect_calls = frozenset(
                    {*state.unresolved_indirect_calls, name}
                )

    def _flow_apply_indirect_call(
        self,
        state: ResourceFlowState,
        name: str,
        target_names: frozenset[str],
        args: list[str],
        result_var: str = "",
    ) -> None:
        concrete_targets = {
            target for target in target_names if target != _UNKNOWN_FUNCTION_TARGET
        }
        target_set_complete = state.function_target_complete.get(name, False)
        contains_unknown_target = len(concrete_targets) != len(target_names)
        has_unknown_target = contains_unknown_target or not target_set_complete
        resolved_args = [self._resolve_alias(state, arg) for arg in args]
        for key, (resource, resource_state) in list(state.resources.items()):
            if not any(same_resource_expr(actual, key) for actual in resolved_args):
                continue
            consumes = [
                self._call_consumes_resource(target, resolved_args, resource, key)
                for target in sorted(concrete_targets)
            ]
            if consumes and all(consumes) and not has_unknown_target:
                self._discharge_resource(
                    state, key, resource, resource_state, ResourceState.RELEASED
                )
            elif (
                resource_state
                in {ResourceState.ACQUIRED, ResourceState.MAY_ACQUIRED}
                and (
                    has_unknown_target
                    or any(consumes)
                    or any(
                        self._has_exit_sensitive_summary_effect(
                            target, resolved_args, resource, key
                        )
                        for target in concrete_targets
                    )
                )
            ):
                self._add_uncertainty(
                    resource,
                    "incomplete_function_pointer_targets"
                    if not target_set_complete
                    else (
                        "unknown_indirect_call"
                        if contains_unknown_target
                        else "partial_function_pointer_consumers"
                    ),
                )
                state.resources[key] = (resource, ResourceState.MAY_ACQUIRED)
                state.unresolved_indirect_calls = frozenset(
                    {*state.unresolved_indirect_calls, name}
                )

    def _discharge_resource(
        self,
        state: ResourceFlowState,
        resource_id: str,
        resource: HeldResource,
        current_state: ResourceState,
        discharged_state: ResourceState,
        effect_cardinality: str = "one",
    ) -> None:
        if current_state not in {
            ResourceState.ACQUIRED,
            ResourceState.MAY_ACQUIRED,
        }:
            return
        if resource.multiplicity == "many" and effect_cardinality != "all":
            self._add_uncertainty(resource, "loop_multiple_instances")
            state.resources[resource_id] = (
                resource,
                ResourceState.MAY_ACQUIRED,
            )
            return
        state.resources[resource_id] = (resource, discharged_state)

    @staticmethod
    def _summary_action_state(action: str) -> ResourceState:
        return {
            ResourceAction.TRANSFER.value: ResourceState.TRANSFERRED,
            ResourceAction.ESCAPE.value: ResourceState.ESCAPED,
        }.get(action, ResourceState.RELEASED)

    def _call_consumes_resource(
        self,
        name: str,
        args: list[str],
        resource: HeldResource,
        resource_id: str = "",
    ) -> bool:
        if name == "ext4_fc_free" and call_releases_resource(
            name, args, resource
        ):
            return True
        identity = HeldResource(**resource.to_csv_dict())
        if resource_id:
            identity.var = resource_id
        return (
            call_releases_resource(name, args, identity)
            or self._consumer_releases(name, args, identity, "always")
            or self._summary_consumes(name, args, identity)
        )

    @staticmethod
    def _looks_indirect_call(name: str) -> bool:
        normalized = norm_resource_expr(name)
        if any(token in normalized for token in ("->", ".", "[", "]")):
            return True
        return bool(
            re.fullmatch(
                r"(?:cb|callback|fn|func|handler|ops?|cleanup)\w*",
                normalized,
                re.I,
            )
        )

    def _resolve_alias(self, state: ResourceFlowState, expression: str) -> str:
        key = norm_resource_expr(expression)
        address = key.startswith("&")
        if address:
            key = key[1:]
        visited: set[str] = set()
        while key in state.aliases and key not in visited:
            visited.add(key)
            target = state.aliases[key]
            if target == key:
                break
            key = target
        return f"&{key}" if address else key

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
            joined_resource = HeldResource(**resource.to_csv_dict())
            causes = set(joined_resource.uncertainty_causes)
            if left_item:
                causes.update(left_item[0].uncertainty_causes)
            if right_item:
                causes.update(right_item[0].uncertainty_causes)
            if state is ResourceState.MAY_ACQUIRED:
                causes.add("widening")
            if (
                (left_item and left_item[0].multiplicity == "many")
                or (right_item and right_item[0].multiplicity == "many")
            ):
                joined_resource.multiplicity = "many"
                causes.add("loop_multiple_instances")
            joined_resource.uncertainty_causes = sorted(causes)
            resources[key] = (joined_resource, state)
        aliases = {
            key: value
            for key, value in left.aliases.items()
            if right.aliases.get(key) == value
        }
        cleanups = dict(left.scope_cleanups)
        cleanups.update(right.scope_cleanups)
        facts = left.path_facts & right.path_facts
        function_targets: dict[str, frozenset[str]] = {}
        function_target_complete: dict[str, bool] = {}
        definition_versions: dict[str, int] = {}
        for name in set(left.function_targets) | set(right.function_targets):
            left_targets = left.function_targets.get(name)
            right_targets = right.function_targets.get(name)
            targets = set(left_targets or {_UNKNOWN_FUNCTION_TARGET})
            targets.update(right_targets or {_UNKNOWN_FUNCTION_TARGET})
            function_targets[name] = frozenset(targets)
            function_target_complete[name] = bool(
                left_targets
                and right_targets
                and left.function_target_complete.get(name, False)
                and right.function_target_complete.get(name, False)
                and _UNKNOWN_FUNCTION_TARGET not in targets
            )
        for name in set(left.definition_versions) | set(right.definition_versions):
            left_version = left.definition_versions.get(name, 0)
            right_version = right.definition_versions.get(name, 0)
            definition_versions[name] = (
                left_version if left_version == right_version else -1
            )
        unresolved = left.unresolved_indirect_calls | right.unresolved_indirect_calls
        pending_effects = tuple(
            pending
            for pending in left.pending_summary_effects
            if pending in right.pending_summary_effects
        )
        common_scope_frames: list[ScopeFrame] = []
        for left_frame, right_frame in zip(
            left.scope_frames, right.scope_frames
        ):
            if left_frame != right_frame:
                break
            common_scope_frames.append(left_frame)
        return ResourceFlowState(
            resources=resources,
            aliases=aliases,
            scope_cleanups=cleanups,
            function_targets=function_targets,
            function_target_complete=function_target_complete,
            definition_versions=definition_versions,
            scope_frames=tuple(common_scope_frames),
            pending_summary_effects=pending_effects,
            unresolved_indirect_calls=unresolved,
            path_facts=facts,
        )

    def _filter_held_resources(
        self,
        held: list[HeldResource],
        condition: ConditionInfo,
        error_source_expr: str,
        function_name: str,
    ) -> list[HeldResource]:
        filtered: list[HeldResource] = []
        for res in held:
            if self._condition_is_acquire_failure(
                res, condition, error_source_expr
            ):
                continue
            if self._error_source_consumes_resource(res, error_source_expr):
                continue
            if resource_exempt_by_function_contract(
                function_name, condition.condition, error_source_expr, res
            ):
                continue
            if self._resource_ownership_transfer_hint(function_name, res):
                res.ownership_state = ResourceState.MAY_ACQUIRED.value
                self._add_uncertainty(
                    res, "unreviewed_ownership_transfer_hint"
                )
            filtered.append(res)
        return filtered

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
                    for resource in held:
                        if _same_stored_resource(rhs, resource.var):
                            resource.ownership_state = ResourceState.MAY_ACQUIRED.value
                            self._add_uncertainty(
                                resource, "field_store_without_contract"
                            )
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
        generation: int = 1,
        validity_guard: str = "",
        validity_guard_source: str = "none",
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
            resource_id=(
                f"{norm_resource_expr(var)}@{line}:{acquire_func}#{generation}"
            ),
            generation=generation,
            release_cardinality=str(cfg.get("release_cardinality", "one")),
            validity_guard=validity_guard,
            validity_guard_source=validity_guard_source,
            out_resource_arg=cfg.get("out_resource_arg"),
            release_arg_index=int(cfg.get("release_arg_index", 0)),
            release_arg_requires_address=bool(
                cfg.get("release_arg_requires_address", False)
            ),
            release_suggestion_template=str(cfg.get("release_suggestion", "")),
            scope_cleanup_function=scope_cleanup[0] if scope_cleanup else "",
            scope_cleanup_decl_line=scope_cleanup[1] if scope_cleanup else None,
        )

    @staticmethod
    def _acquire_validity_guard(
        var: str, cfg: dict[str, Any], result_var: str = ""
    ) -> str:
        explicit = str(cfg.get("validity_guard", "")).strip()
        if explicit:
            return explicit.replace("{var}", var).replace(
                "{return}", result_var or "return"
            )
        if "direct_resource_arg" in cfg:
            return ""
        if "out_resource_arg" in cfg:
            success_guard = str(
                cfg.get("acquire_success_guard", "return == 0")
            ).strip()
            return success_guard.replace("return", result_var) if result_var else ""
        failed_check = str(cfg.get("failed_check", "")).strip()
        if failed_check in {"IS_ERR", "IS_ERR_OR_NULL"}:
            return f"!{failed_check}({var})"
        return f"{var} != NULL"

    @staticmethod
    def _acquire_validity_guard_source(
        cfg: dict[str, Any], result_var: str = ""
    ) -> str:
        if str(cfg.get("validity_guard", "")).strip():
            return "explicit"
        if "direct_resource_arg" in cfg:
            return "none"
        if "out_resource_arg" in cfg:
            return (
                "explicit"
                if str(cfg.get("acquire_success_guard", "")).strip()
                else "compatibility_default"
            )
        if str(cfg.get("failed_check", "")).strip():
            return "failed_check"
        return "compatibility_default"

    @staticmethod
    def _add_uncertainty(resource: HeldResource, cause: str) -> None:
        if cause and cause not in resource.uncertainty_causes:
            resource.uncertainty_causes.append(cause)
            resource.uncertainty_causes.sort()

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
            if self._summary_consumption_strength(name, args, res) == "may":
                res.ownership_state = ResourceState.MAY_ACQUIRED.value
                self._add_uncertainty(res, "may_summary_effect")
            kept.append(res)
        held[:] = kept

    def _summary_consumes(
        self, name: str, args: list[str], resource: HeldResource
    ) -> bool:
        return self._summary_consumption_strength(name, args, resource) == "must"

    def _summary_consumption_strength(
        self, name: str, args: list[str], resource: HeldResource
    ) -> str:
        effect = self._summary_consumption_effect(
            name, args, resource, exit_sensitive=False
        )
        return effect.strength if effect is not None else ""

    def _summary_consumption_effect(
        self,
        name: str,
        args: list[str],
        resource: HeldResource,
        exit_sensitive: bool,
    ) -> SummaryEffect | None:
        effects = self._matching_summary_consumption_effects(
            name, args, resource, exit_sensitive
        )
        if not effects:
            return None
        return next(
            (effect for effect in effects if effect.strength == "must"),
            effects[0],
        )

    def _matching_summary_consumption_effects(
        self,
        name: str,
        args: list[str],
        resource: HeldResource,
        exit_sensitive: bool,
    ) -> list[SummaryEffect]:
        summary = self.function_summaries.find(name)
        if summary is None:
            return []
        consuming = {
            ResourceAction.RELEASE.value,
            ResourceAction.TRANSFER.value,
            ResourceAction.ESCAPE.value,
        }
        matched: list[SummaryEffect] = []
        for effect, actual in summary.effects_for_call(args):
            if effect.action not in consuming:
                continue
            is_exit_sensitive = bool(
                effect.exit_class != "any" or effect.return_guard.strip()
            )
            if is_exit_sensitive != exit_sensitive:
                continue
            if not self._summary_condition_matches(
                effect.condition, args, resource.var
            ):
                continue
            if effect.resource_type and effect.resource_type != resource.resource_type:
                continue
            if same_resource_expr(actual, resource.var):
                matched.append(effect)
        return matched

    def _has_exit_sensitive_summary_effect(
        self,
        name: str,
        args: list[str],
        resource: HeldResource,
        resource_id: str,
    ) -> bool:
        identity = HeldResource(**resource.to_csv_dict())
        identity.var = resource_id
        return bool(
            self._matching_summary_consumption_effects(
                name, args, identity, exit_sensitive=True
            )
        )

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
                and effect.strength == "must"
                and effect.exit_class == "any"
                and not effect.return_guard
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
                or effect.strength != "must"
                or effect.exit_class != "any"
                or effect.return_guard
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

    def _resource_ownership_transfer_hint(
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
