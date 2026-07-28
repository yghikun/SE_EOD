"""Exact per-CPU slot identity binding for function summaries."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from ..frontend.model import FrontendNode, FunctionIR
from ..metadata_residual import MetadataEffect, PerCpuSlotRelation, SourceSite
from ..parser import call_name_and_args, compact_ws
from .syntax import declarator_name, replace_symbols


_LOOP_ESCAPE_TYPES = {
    "break_statement",
    "continue_statement",
    "goto_statement",
    "return_statement",
}


@dataclass(frozen=True)
class _PerCpuSlotBinding:
    relation: PerCpuSlotRelation
    body_start_line: int
    body_end_line: int
    accessor_line: int


def bind_percpu_slot_effects(
    function: FunctionIR,
    effects: tuple[MetadataEffect, ...],
    parameters: tuple[str, ...],
    local_symbols: set[str],
    pointer_locals: set[str],
) -> tuple[MetadataEffect, ...]:
    """Bind effects reached through an exact possible-CPU slot accessor."""

    bindings = _percpu_slot_bindings(function, parameters, local_symbols, pointer_locals)
    if not bindings:
        return effects
    result: list[MetadataEffect] = []
    for effect in effects:
        matches = [
            binding
            for binding in bindings
            if (
                binding.accessor_line < effect.site.line <= binding.body_end_line
                and binding.body_start_line <= effect.site.line
                and _rooted_at_symbol(effect.root, binding.relation.slot_local)
            )
        ]
        if len(matches) != 1:
            result.append(effect)
            continue
        relation = matches[0].relation
        result.append(
            replace(
                effect,
                root=replace_symbols(
                    effect.root,
                    {relation.slot_local: f"PER_CPU_SLOT({relation.base_root})"},
                ),
                percpu_slot_relation=relation,
            )
        )
    return tuple(result)


def _percpu_slot_bindings(
    function: FunctionIR,
    parameters: tuple[str, ...],
    local_symbols: set[str],
    pointer_locals: set[str],
) -> tuple[_PerCpuSlotBinding, ...]:
    if function.body_node is None:
        return ()
    parameter_set = set(parameters)
    result: list[_PerCpuSlotBinding] = []
    for loop in function.body_node.walk():
        if loop.type != "function_definition":
            continue
        loop_type = loop.child_by_field_name("type")
        declarator = loop.child_by_field_name("declarator")
        body = loop.child_by_field_name("body")
        if (
            loop_type is None
            or compact_ws(loop_type.text) != "for_each_possible_cpu"
            or declarator is None
            or declarator.type != "parenthesized_declarator"
            or body is None
            or body.type != "compound_statement"
        ):
            continue
        index_local = compact_ws(declarator.text).strip("()")
        if (
            re.fullmatch(r"[A-Za-z_]\w*", index_local) is None
            or index_local not in local_symbols
            or index_local in pointer_locals
        ):
            continue
        if any(node.type in _LOOP_ESCAPE_TYPES for node in body.walk()):
            continue
        accessors: list[tuple[FrontendNode, str, str]] = []
        for statement in body.children:
            assignment = _top_level_assignment(statement)
            if assignment is None:
                continue
            left, right = assignment
            slot_local = compact_ws(left.text)
            accessor_name, args = call_name_and_args(compact_ws(right.text))
            if (
                slot_local not in pointer_locals
                or accessor_name != "per_cpu_ptr"
                or len(args) != 2
                or compact_ws(args[1]).strip("()") != index_local
            ):
                continue
            base_root = _parameter_container_path(args[0], parameter_set)
            if base_root:
                accessors.append((statement, slot_local, base_root))
        if len(accessors) != 1:
            continue
        accessor, slot_local, base_root = accessors[0]
        if _local_assignment_count(function, slot_local) != 1:
            continue
        if _local_has_initializer(function, slot_local):
            continue
        loop_site = SourceSite(
            function.file.as_posix(), loop.start_line, f"for_each_possible_cpu({index_local})"
        )
        accessor_site = SourceSite(
            function.file.as_posix(), accessor.start_line, compact_ws(accessor.text)
        )
        relation = PerCpuSlotRelation(
            base_root=base_root,
            slot_local=slot_local,
            index_local=index_local,
            loop_site=loop_site,
            accessor_site=accessor_site,
            source_identity=(
                f"{function.file.as_posix()}:{loop.start_line}:"
                f"{slot_local}:per_cpu_ptr({base_root},{index_local})"
            ),
        )
        result.append(
            _PerCpuSlotBinding(
                relation=relation,
                body_start_line=body.start_line,
                body_end_line=body.end_line,
                accessor_line=accessor.start_line,
            )
        )
    return tuple(result)


def _top_level_assignment(
    statement: FrontendNode,
) -> tuple[FrontendNode, FrontendNode] | None:
    if statement.type != "expression_statement":
        return None
    assignments = [
        child for child in statement.children if child.type == "assignment_expression"
    ]
    if len(assignments) != 1:
        return None
    assignment = assignments[0]
    left = assignment.child_by_field_name("left")
    right = assignment.child_by_field_name("right")
    return (left, right) if left is not None and right is not None else None


def _local_assignment_count(function: FunctionIR, local: str) -> int:
    if function.body_node is None:
        return 0
    return sum(
        1
        for node in function.body_node.walk()
        if node.type == "assignment_expression"
        and node.child_by_field_name("left") is not None
        and compact_ws(node.child_by_field_name("left").text) == local
    )


def _local_has_initializer(function: FunctionIR, local: str) -> bool:
    if function.body_node is None:
        return False
    return any(
        node.type == "init_declarator"
        and declarator_name(node.child_by_field_name("declarator")) == local
        for node in function.body_node.walk()
    )


def _rooted_at_symbol(root: str, symbol: str) -> bool:
    return re.match(rf"^{re.escape(symbol)}(?=$|->|\.)", compact_ws(root)) is not None


def _parameter_container_path(text: str, parameters: set[str]) -> str:
    path = compact_ws(text).strip("()")
    while path.startswith("&"):
        path = path[1:].strip()
    match = re.fullmatch(
        r"([A-Za-z_]\w*)((?:(?:->|\.)[A-Za-z_]\w*)+)",
        path,
    )
    if match is None or match.group(1) not in parameters:
        return ""
    return path
