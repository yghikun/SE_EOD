"""Container cleanup and existential member identity binding."""

from __future__ import annotations

import re
from dataclasses import replace

from ..frontend.model import FrontendNode, FunctionIR
from ..metadata_residual import (
    ContainerIterationCleanup,
    ExistentialMemberIdentity,
    MetadataDelta,
    MetadataEffect,
    SourceSite,
)
from ..parser import call_name_and_args, compact_ws
from .syntax import declarator_name


_LOOP_ESCAPE_TYPES = {
    "break_statement",
    "continue_statement",
    "goto_statement",
    "return_statement",
}


def bind_exhaustive_container_cleanups(
    function: FunctionIR,
    effects: tuple[MetadataEffect, ...],
    parameters: tuple[str, ...],
    pointer_locals: set[str],
) -> tuple[MetadataEffect, ...]:
    """Bind an unconditional safe-list drain to its parameter container."""

    relations = _exhaustive_container_cleanup_relations(
        function, parameters, pointer_locals
    )
    if not relations:
        return effects
    result: list[MetadataEffect] = []
    for effect in effects:
        relation = relations.get((effect.site.line, compact_ws(effect.site.expression)))
        if relation is None:
            result.append(effect)
            continue
        result.append(
            replace(
                effect,
                root=relation.container_root,
                value="*",
                container_iteration_cleanup=relation,
            )
        )
    return tuple(result)


def bind_existential_member_identities(
    function: FunctionIR,
    effects: tuple[MetadataEffect, ...],
    pointer_locals: set[str],
) -> tuple[MetadataEffect, ...]:
    """Preserve one aggregate-derived member without naming a caller object."""

    if function.body_node is None:
        return effects
    assignments: list[tuple[str, str, FrontendNode]] = []
    for node in function.body_node.walk():
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is not None and right is not None:
                assignments.append((compact_ws(left.text), compact_ws(right.text), node))
        elif node.type == "init_declarator":
            declarator = node.child_by_field_name("declarator")
            value = node.child_by_field_name("value")
            local = declarator_name(declarator) or ""
            if local and value is not None:
                assignments.append((local, compact_ws(value.text), node))

    aggregate_sources: dict[str, set[str]] = {}
    aggregate_sites: dict[tuple[str, str], SourceSite] = {}
    for left, right, node in assignments:
        left_family = _aggregate_member_family(left)
        right_family = _aggregate_member_family(right)
        if left_family is None or right_family is None:
            continue
        aggregate_sources.setdefault(left_family, set()).add(right_family)
        aggregate_sites[(left_family, right_family)] = SourceSite(
            function.file.as_posix(), node.start_line, compact_ws(node.text)
        )

    local_assignments: dict[str, list[tuple[str, FrontendNode]]] = {}
    for left, right, node in assignments:
        if left in pointer_locals:
            local_assignments.setdefault(left, []).append((right, node))

    provenance: dict[str, tuple[str, SourceSite, SourceSite]] = {}
    for local, values in local_assignments.items():
        if len(values) != 1:
            continue
        right, node = values[0]
        right_family = _aggregate_member_family(right)
        if right_family is None:
            continue
        sources = aggregate_sources.get(right_family, set())
        if len(sources) != 1:
            continue
        origin = next(iter(sources))
        store_site = aggregate_sites[(right_family, origin)]
        load_site = SourceSite(
            function.file.as_posix(), node.start_line, compact_ws(node.text)
        )
        if store_site.line <= load_site.line:
            provenance[local] = (origin, store_site, load_site)

    bound: list[MetadataEffect] = []
    next_index = 0
    for effect in effects:
        if effect.delta is not MetadataDelta.ADD or effect.key != "list_membership":
            bound.append(effect)
            continue
        match = re.fullmatch(r"([A-Za-z_]\w*)->([A-Za-z_]\w*)", effect.value)
        local = match.group(1) if match is not None else ""
        member_field = match.group(2) if match is not None else ""
        if local not in provenance:
            expanded = _expanded_existential_member(effect.value, provenance, local_assignments)
            if expanded is None:
                bound.append(effect)
                continue
            local, member_field = expanded
        origin, store_site, load_site = provenance[local]
        placeholder = f"__exists_member{next_index}__"
        next_index += 1
        relation = ExistentialMemberIdentity(
            placeholder=placeholder,
            origin_expression=origin,
            destination_container=effect.root,
            member_field=member_field,
            binding_site=load_site,
            source_identity=(
                f"{store_site.expression} -> {load_site.expression} -> "
                f"{effect.site.expression}"
            ),
        )
        bound.append(
            replace(
                effect,
                value=f"{placeholder}->{member_field}",
                existential_member_identity=relation,
            )
        )
    return tuple(bound)


def _expanded_existential_member(
    value: str,
    provenance: dict[str, tuple[str, SourceSite, SourceSite]],
    local_assignments: dict[str, list[tuple[str, FrontendNode]]],
) -> tuple[str, str] | None:
    matches: list[tuple[str, str]] = []
    for local in provenance:
        assignments = local_assignments.get(local, [])
        if len(assignments) != 1:
            continue
        aggregate, _ = assignments[0]
        prefix = compact_ws(aggregate).strip("() ")
        candidate = compact_ws(value).strip("() ")
        if not candidate.startswith(f"{prefix}->"):
            continue
        member_field = candidate[len(prefix) + 2 :]
        if re.fullmatch(r"[A-Za-z_]\w*", member_field):
            matches.append((local, member_field))
    return matches[0] if len(matches) == 1 else None


def _aggregate_member_family(expression: str) -> str | None:
    value = compact_ws(expression).strip("() ")
    if "[" not in value or not re.fullmatch(
        r"[A-Za-z_]\w*(?:(?:->|\.)[A-Za-z_]\w*|\[[^\]]+\])+", value
    ):
        return None
    return re.sub(r"\[[^\]]+\]", "[*]", value)


def _exhaustive_container_cleanup_relations(
    function: FunctionIR,
    parameters: tuple[str, ...],
    pointer_locals: set[str],
) -> dict[tuple[int, str], ContainerIterationCleanup]:
    if function.body_node is None:
        return {}
    parameter_set = set(parameters)
    result: dict[tuple[int, str], ContainerIterationCleanup] = {}
    for parent in function.body_node.walk():
        children = parent.children
        for index, statement in enumerate(children[:-1]):
            if statement.type != "expression_statement":
                continue
            loop_call = _single_direct_call(statement)
            if loop_call is None:
                continue
            name, args = call_name_and_args(compact_ws(loop_call.text))
            if name != "list_for_each_entry_safe" or len(args) != 4:
                continue
            body = children[index + 1]
            if body.type != "compound_statement":
                continue
            iterator = compact_ws(args[0])
            next_iterator = compact_ws(args[1])
            member_field = compact_ws(args[3])
            if (
                iterator not in pointer_locals
                or next_iterator not in pointer_locals
                or iterator == next_iterator
                or re.fullmatch(r"[A-Za-z_]\w*", member_field) is None
            ):
                continue
            container_root = _parameter_container_path(args[2], parameter_set)
            if not container_root or any(
                node.type in _LOOP_ESCAPE_TYPES for node in body.walk()
            ):
                continue
            removal = _unconditional_iterator_removal(body, iterator, member_field)
            if removal is None:
                continue
            relation = ContainerIterationCleanup(
                container_root=container_root,
                iterator=iterator,
                next_iterator=next_iterator,
                member_field=member_field,
                iteration_site=SourceSite(
                    function.file.as_posix(), loop_call.start_line, compact_ws(loop_call.text)
                ),
                source_identity=(
                    f"{function.file.as_posix()}:{loop_call.start_line}:"
                    f"{iterator}:{container_root}:{member_field}"
                ),
            )
            result[(removal.start_line, compact_ws(removal.text))] = relation
    return result


def _single_direct_call(statement: FrontendNode) -> FrontendNode | None:
    calls = [child for child in statement.children if child.type == "call_expression"]
    return calls[0] if len(calls) == 1 else None


def _parameter_container_path(text: str, parameters: set[str]) -> str:
    path = compact_ws(text).strip("()")
    while path.startswith("&"):
        path = path[1:].strip()
    match = re.fullmatch(
        r"([A-Za-z_]\w*)((?:(?:->|\.)[A-Za-z_]\w*)+)", path
    )
    if match is None or match.group(1) not in parameters:
        return ""
    return path


def _unconditional_iterator_removal(
    body: FrontendNode,
    iterator: str,
    member_field: str,
) -> FrontendNode | None:
    expected = {f"{iterator}->{member_field}", f"{iterator}.{member_field}"}
    matches: list[FrontendNode] = []
    for statement in body.children:
        if statement.type != "expression_statement":
            continue
        call = _single_direct_call(statement)
        if call is None:
            continue
        name, args = call_name_and_args(compact_ws(call.text))
        if name not in {"list_del", "list_del_init"} or len(args) != 1:
            continue
        target = compact_ws(args[0]).strip("()")
        while target.startswith("&"):
            target = target[1:].strip()
        if target in expected:
            matches.append(call)
    return matches[0] if len(matches) == 1 else None
