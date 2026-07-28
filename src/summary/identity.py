"""Fresh allocation and owner identity binding for function summaries."""

from __future__ import annotations

import re
from dataclasses import replace

from ..semantics.failure_domain_primitives import failure_domain_kind
from ..frontend.model import FrontendNode, FunctionIR
from ..metadata_residual import MetadataEffect, SourceSite
from ..parser import call_name_and_args, compact_ws
from .model import (
    ExitSensitiveEffects,
    FunctionSummary,
    OwnerIdentityBinding,
    OwnerIdentityKind,
    SummarySource,
)
from .syntax import (
    declarator_name as _declarator_name,
    return_expression as _return_expression,
)


RETURN_PLACEHOLDER = "__return__"
FRESH_PLACEHOLDER_PREFIX = "__fresh"
OUTPUT_PLACEHOLDER_PREFIX = "__output"
DIRECT_FRESH_ALLOCATORS = {
    "calloc",
    "kcalloc",
    "kmalloc",
    "kmalloc_array",
    "kmalloc_obj",
    "kmem_cache_alloc",
    "kmem_cache_zalloc",
    "new_inode",
    "kzalloc",
    "kvcalloc",
    "kvmalloc",
    "kvzalloc",
    "malloc",
    "mempool_alloc",
    "vmalloc",
    "vzalloc",
}


def _effect_is_parameter_bound(effect: MetadataEffect) -> bool:
    return bool(re.match(r"^arg\d+(?:\b|->|\.)", compact_ws(effect.root)))


def _fresh_fact_summary(summary: FunctionSummary) -> FunctionSummary:
    return FunctionSummary(
        function_name=summary.function_name,
        parameters=summary.parameters,
        returns=summary.returns,
        fresh_identities=(),
        has_ownership_transfer=False,
        ownership_transfer_roots=(),
        returns_fresh_identity=True,
        opens=(),
        cancels=(),
        protects=(),
        output_identities=(),
        error_opens=(),
        error_cancels=(),
        error_protects=(),
        failure_effects_complete=summary.failure_effects_complete,
        error_unknown_causes=(),
        lifecycle_facts=summary.lifecycle_facts,
        exposure_facts=summary.exposure_facts,
        cleanup_footprints=(),
        owner_teardowns=(),
        escaping_parameters=summary.escaping_parameters,
        exit_effects=ExitSensitiveEffects(
            error_complete=summary.exit_effects.error_complete,
        ),
        error_exit_partitions=(),
        unresolved_calls=summary.unresolved_calls,
        source_file=summary.source_file,
        may_fail=summary.may_fail,
        unknown_escape=False,
        unknown_causes=(),
        source=SummarySource.AUTO_INTERPROCEDURAL,
        owner_bindings=summary.owner_bindings,
    )


def _direct_fresh_allocation_lines(
    function: FunctionIR,
    pointer_locals: set[str],
    fresh_return_helpers: set[str] | None = None,
) -> dict[str, int]:
    if function.body_node is None:
        return {}
    allocations: dict[str, int] = {}
    for node in function.body_node.walk():
        if node.type != "call_expression":
            continue
        name, _ = call_name_and_args(compact_ws(node.text))
        if name not in DIRECT_FRESH_ALLOCATORS and name not in (fresh_return_helpers or set()):
            continue
        target = _call_result_lvalue(function, node)
        if target in pointer_locals:
            allocations[target] = min(allocations.get(target, node.start_line), node.start_line)
    return allocations


def _call_result_lvalue(function: FunctionIR, call: FrontendNode) -> str:
    if function.body_node is None:
        return ""
    for node in function.body_node.walk():
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is not None and right is not None and _node_contains(right, call):
                return compact_ws(left.text)
        elif node.type == "init_declarator":
            declarator = node.child_by_field_name("declarator")
            value = node.child_by_field_name("value")
            if declarator is not None and value is not None and _node_contains(value, call):
                return _declarator_name(declarator) or ""
    return ""


def _node_contains(parent: FrontendNode, child: FrontendNode) -> bool:
    return parent.start_byte <= child.start_byte and child.end_byte <= parent.end_byte


def _parameter_derived_owner_aliases(
    function: FunctionIR,
    parameters: tuple[str, ...],
    pointer_locals: set[str],
) -> dict[str, str]:
    """Bind a narrow, source-visible conversion accessor to its parameter.

    The ``*_sb`` form captures container/cast accessors such as
    ``btrfs_sb(sb)``. Direct field relations are kept in a separate owner-only
    map so they cannot rewrite unrelated metadata effect identities.
    """

    if function.body_node is None:
        return {}
    parameter_index = {name: index for index, name in enumerate(parameters)}
    assignments: dict[str, list[str]] = {}
    for node in function.body_node.walk():
        if node.type not in {"assignment_expression", "init_declarator"}:
            continue
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            local = compact_ws(left.text) if left is not None else ""
            expression = compact_ws(right.text) if right is not None else ""
        else:
            declarator = node.child_by_field_name("declarator")
            value = node.child_by_field_name("value")
            local = _declarator_name(declarator) or ""
            expression = compact_ws(value.text) if value is not None else ""
        if local not in pointer_locals:
            continue
        assignments.setdefault(local, []).append(expression)

    aliases: dict[str, str] = {}
    pending = {
        local: values[0]
        for local, values in assignments.items()
        if len(values) == 1
    }
    for _ in range(len(pending) + 1):
        changed = False
        for local, expression in pending.items():
            if local in aliases:
                continue
            identity = _source_owner_identity(
                expression,
                parameter_index,
                aliases,
                allow_direct=False,
            )
            if identity:
                aliases[local] = identity
                changed = True
        if not changed:
            break
    return aliases


def _source_owner_identity(
    expression: str,
    parameter_index: dict[str, int],
    aliases: dict[str, str],
    *,
    allow_direct: bool,
) -> str:
    text = compact_ws(expression).strip()
    name, args = call_name_and_args(text)
    if name.endswith("_sb") and len(args) == 1:
        argument = compact_ws(args[0]).strip().strip("()")
        if argument in parameter_index:
            return f"arg{parameter_index[argument]}"

    if not allow_direct:
        return ""

    while text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    match = re.fullmatch(
        r"([A-Za-z_]\w*)((?:(?:->|\.)[A-Za-z_]\w*)*)",
        text,
    )
    if not match:
        return ""
    base, suffix = match.groups()
    if base in parameter_index:
        return f"arg{parameter_index[base]}{suffix}"
    if base in aliases:
        return f"{aliases[base]}{suffix}"
    return ""


def _direct_owner_identity_aliases(
    function: FunctionIR,
    parameters: tuple[str, ...],
    pointer_locals: set[str],
    base_aliases: dict[str, str],
) -> dict[str, str]:
    if function.body_node is None:
        return {}
    parameter_index = {name: index for index, name in enumerate(parameters)}
    assignments: dict[str, list[str]] = {}
    for node in function.body_node.walk():
        if node.type not in {"assignment_expression", "init_declarator"}:
            continue
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            local = compact_ws(left.text) if left is not None else ""
            expression = compact_ws(right.text) if right is not None else ""
        else:
            declarator = node.child_by_field_name("declarator")
            value = node.child_by_field_name("value")
            local = _declarator_name(declarator) or ""
            expression = compact_ws(value.text) if value is not None else ""
        if local in pointer_locals:
            assignments.setdefault(local, []).append(expression)

    aliases = dict(base_aliases)
    pending = {
        local: values[0]
        for local, values in assignments.items()
        if len(values) == 1 and local not in aliases
    }
    for _ in range(len(pending) + 1):
        changed = False
        for local, expression in pending.items():
            if local in aliases:
                continue
            identity = _source_owner_identity(
                expression,
                parameter_index,
                aliases,
                allow_direct=True,
            )
            if identity:
                aliases[local] = identity
                changed = True
        if not changed:
            break
    return {
        local: identity
        for local, identity in aliases.items()
        if local not in base_aliases
    }


def _has_unbound_failure_domain_owner(
    function: FunctionIR,
    parameters: set[str],
    local_symbols: set[str],
    symbol_mapping: dict[str, str],
) -> bool:
    if function.body_node is None:
        return False
    for node in function.body_node.walk():
        if node.type != "call_expression":
            continue
        name, args = call_name_and_args(compact_ws(node.text))
        if failure_domain_kind(name) is None or not args:
            continue
        owner = compact_ws(args[0]).strip().strip("()")
        if (
            re.fullmatch(r"[A-Za-z_]\w*", owner)
            and owner in local_symbols
            and owner not in parameters
            and owner not in symbol_mapping
        ):
            return True
    return False


def _build_owner_identity_bindings(
    function: FunctionIR,
    symbol_mapping: dict[str, str],
    return_symbols: set[str],
    allocation_lines: dict[str, int],
) -> tuple[OwnerIdentityBinding, ...]:
    mappings = dict(symbol_mapping)
    mappings.update({local: RETURN_PLACEHOLDER for local in return_symbols})
    bindings: list[OwnerIdentityBinding] = []
    for local, identity in sorted(mappings.items()):
        kind = _owner_identity_kind(identity)
        if kind is None:
            continue
        site = _owner_binding_site(
            function,
            local,
            identity,
            allocation_lines,
        )
        bindings.append(
            OwnerIdentityBinding(
                local_identity=local,
                kind=kind,
                summary_identity=identity,
                bound_identity=identity,
                site=site,
                evidence=site.expression,
            )
        )
    return tuple(bindings)


def _owner_identity_kind(identity: str) -> OwnerIdentityKind | None:
    if identity == RETURN_PLACEHOLDER:
        return OwnerIdentityKind.RETURN
    if identity.startswith(OUTPUT_PLACEHOLDER_PREFIX):
        return OwnerIdentityKind.OUT_PARAM
    if identity.startswith(FRESH_PLACEHOLDER_PREFIX):
        return OwnerIdentityKind.FRESH
    if re.fullmatch(r"arg\d+", identity):
        return OwnerIdentityKind.PARAM
    if re.match(r"^arg\d+(?:->|\.)", identity):
        return OwnerIdentityKind.FIELD
    return None


def _owner_binding_site(
    function: FunctionIR,
    local: str,
    identity: str,
    allocation_lines: dict[str, int],
) -> SourceSite:
    fallback_line = allocation_lines.get(local, function.start_line)
    fallback = SourceSite(
        function.file.as_posix(),
        fallback_line,
        f"source-derived owner binding for {local}",
    )
    if function.body_node is None:
        return fallback
    candidates: list[SourceSite] = []
    for node in function.body_node.walk():
        expression = compact_ws(node.text)
        if identity == RETURN_PLACEHOLDER and node.type == "return_statement":
            if _return_expression(node) == local:
                candidates.append(SourceSite(function.file.as_posix(), node.start_line, expression))
            continue
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            left_text = compact_ws(left.text) if left is not None else ""
            right_text = compact_ws(right.text) if right is not None else ""
            if left_text == local or right_text == local:
                candidates.append(SourceSite(function.file.as_posix(), node.start_line, expression))
        elif node.type == "init_declarator":
            declarator = node.child_by_field_name("declarator")
            if (_declarator_name(declarator) or "") == local:
                candidates.append(SourceSite(function.file.as_posix(), node.start_line, expression))
    return min(candidates, key=lambda item: item.line) if candidates else fallback
