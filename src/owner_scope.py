"""Source-proven owner, scope, and effect-provenance relations."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Iterable, TYPE_CHECKING

from .frontend.model import FrontendNode, FunctionIR
from .metadata_residual import (
    EffectProvenanceKind,
    EffectSemanticProvenance,
    EffectVisibility,
    EscapeState,
    MetadataEffect,
    MetadataPlane,
    OwnerScopeKind,
    OwnerScopeProof,
    OwnerTeardown,
    OwnershipEdge,
    OwnershipRelation,
    SourceSite,
)
from .parser import call_name_and_args, compact_ws

if TYPE_CHECKING:
    from .function_summary import LocalLifecycleBinding


_LIST_ADD_CALLS = {"list_add", "list_add_tail", "hlist_add_head", "hlist_add_tail"}


def private_owner_effect(effect: MetadataEffect, owner: str) -> MetadataEffect:
    """Attach auditable provenance for an unpublished fresh local owner."""

    proof = EffectSemanticProvenance(
        kind=EffectProvenanceKind.PRIVATE_OWNER,
        subject=owner,
        site=effect.site,
        source_identity=f"{effect.site.file}:{effect.site.line}:{owner}",
        evidence=(
            "effect targets source-proven fresh local storage that is neither "
            "published nor rebound before the checked failure"
        ),
    )
    return replace(
        effect,
        semantic_provenance=tuple(dict.fromkeys((*effect.semantic_provenance, proof))),
        visibility=EffectVisibility.PRIVATE_RUNTIME,
    )


def output_effect(effect: MetadataEffect, parameter: str) -> MetadataEffect:
    """Attach auditable WRITE_ONLY_OUTPUT evidence to an excluded effect."""

    proof = EffectSemanticProvenance(
        kind=EffectProvenanceKind.WRITE_ONLY_OUTPUT,
        subject=parameter,
        site=effect.site,
        source_identity=f"{effect.site.file}:{effect.site.line}:{parameter}",
        evidence=(
            "caller-provided aggregate is source-proven write-only, is not read "
            "as incoming state, and is not passed to another helper"
        ),
    )
    return replace(
        effect,
        semantic_provenance=tuple(dict.fromkeys((*effect.semantic_provenance, proof))),
        visibility=EffectVisibility.PRIVATE_RUNTIME,
    )


def operation_descriptor_effect(effect: MetadataEffect, parameter: str) -> MetadataEffect:
    """Attach the universal-call-site operation-descriptor provenance."""

    proof = EffectSemanticProvenance(
        kind=EffectProvenanceKind.OPERATION_DESCRIPTOR,
        subject=parameter,
        site=effect.site,
        source_identity=f"{effect.site.file}:{effect.site.line}:{parameter}",
        evidence=(
            "every visible caller passes type-compatible automatic aggregate "
            "storage and no source-visible publication or return escapes it"
        ),
    )
    return replace(
        effect,
        semantic_provenance=tuple(dict.fromkeys((*effect.semantic_provenance, proof))),
        visibility=EffectVisibility.PRIVATE_RUNTIME,
    )


def fresh_owner_descriptor_effect(
    effect: MetadataEffect,
    owner: str,
) -> MetadataEffect:
    """Prove that a caller-field copy targets only a fresh local owner."""

    proof = EffectSemanticProvenance(
        kind=EffectProvenanceKind.OPERATION_DESCRIPTOR,
        subject=owner,
        site=effect.site,
        source_identity=f"{effect.site.file}:{effect.site.line}:{owner}",
        evidence=(
            "direct assignment copies caller-owned input into a field of a "
            "source-proven fresh local owner; the input object itself is not mutated"
        ),
    )
    return replace(
        effect,
        semantic_provenance=tuple(dict.fromkeys((*effect.semantic_provenance, proof))),
        visibility=EffectVisibility.PRIVATE_RUNTIME,
    )


def effect_with_visibility(
    effect: MetadataEffect,
    *,
    private_roots: Iterable[str] = (),
) -> MetadataEffect:
    """Assign conservative visibility used by effect-scoped failure domains."""

    if effect.visibility is not EffectVisibility.UNKNOWN:
        return effect
    if effect.transaction_ownership is not None:
        visibility = effect.transaction_ownership.visibility
    elif _leading_symbol(effect.root) in set(private_roots):
        visibility = EffectVisibility.PRIVATE_RUNTIME
    elif effect.plane is MetadataPlane.RECOVERY:
        visibility = EffectVisibility.RECOVERY_VISIBLE
    else:
        visibility = EffectVisibility.OWNER_LOCAL
    return replace(effect, visibility=visibility)


def infer_ownership_edges(
    function: FunctionIR,
    lifecycles: tuple["LocalLifecycleBinding", ...],
) -> tuple[OwnershipEdge, ...]:
    """Infer bounded owner relations; only EMBEDDED edges authorize closure."""

    if function.body_node is None:
        return ()
    lifecycle_by_local = {item.local_identity: item for item in lifecycles}
    edges: list[OwnershipEdge] = []
    for node in function.body_node.walk():
        if node.type in {"assignment_expression", "init_declarator"}:
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right") or node.child_by_field_name("value")
            target = compact_ws(left.text) if left is not None else _declared_name(node)
            value = compact_ws(right.text) if right is not None else ""
            target_symbol = _plain_symbol(target)
            embedded = _addressed_field(value)
            if target_symbol and embedded is not None:
                parent, _ = embedded
                edges.append(
                    _edge(
                        function,
                        node,
                        child=target_symbol,
                        parent=parent,
                        relation=OwnershipRelation.EMBEDDED,
                        escape_state=EscapeState.PRIVATE,
                    )
                )
                continue
            array_parent = _array_member_owner(value)
            if target_symbol and array_parent:
                edges.append(
                    _edge(
                        function,
                        node,
                        child=target_symbol,
                        parent=array_parent,
                        relation=OwnershipRelation.ARRAY_ELEMENT,
                        escape_state=EscapeState.UNKNOWN,
                    )
                )
                continue
            parent_field = _field_target(target)
            child = _plain_symbol(value)
            if parent_field and child and child in lifecycle_by_local:
                parent, _ = parent_field
                child_binding = lifecycle_by_local[child]
                escape = (
                    EscapeState.PRIVATE
                    if not any(line <= node.start_line for line in child_binding.escape_lines)
                    else EscapeState.ESCAPED
                )
                edges.append(
                    _edge(
                        function,
                        node,
                        child=child,
                        parent=parent,
                        relation=OwnershipRelation.UNIQUE_POINTER,
                        escape_state=escape,
                    )
                )
        elif node.type == "call_expression":
            name, args = call_name_and_args(compact_ws(node.text))
            if name not in _LIST_ADD_CALLS or len(args) < 2:
                continue
            child = _leading_symbol(args[0])
            parent = compact_ws(args[1]).strip("&() ")
            if child and parent:
                publication = SourceSite(
                    function.file.as_posix(), node.start_line, compact_ws(node.text)
                )
                edges.append(
                    OwnershipEdge(
                        child=child,
                        parent=parent,
                        relation=OwnershipRelation.CONTAINER_OWNED,
                        acquisition_site=publication,
                        publication_sites=(publication,),
                        escape_state=EscapeState.PUBLISHED,
                        source_identity=(
                            f"{function.file.as_posix()}:{node.start_line}:"
                            f"{child}->{parent}"
                        ),
                    )
                )
    return tuple(dict.fromkeys(edges))


def embedded_children(
    owner: str,
    edges: tuple[OwnershipEdge, ...],
) -> tuple[str, ...]:
    """Return transitive private aliases of storage embedded in owner."""

    result: set[str] = set()
    frontier = {owner}
    while frontier:
        parent = frontier.pop()
        for edge in edges:
            if (
                edge.parent == parent
                and edge.relation is OwnershipRelation.EMBEDDED
                and edge.escape_state is EscapeState.PRIVATE
                and edge.child not in result
            ):
                result.add(edge.child)
                frontier.add(edge.child)
    return tuple(sorted(result))


def owner_scope_proofs(
    function: FunctionIR,
    teardowns: tuple[OwnerTeardown, ...],
) -> tuple[OwnerScopeProof, ...]:
    proofs: list[OwnerScopeProof] = []
    symbol_types = {item.name: item.type_spelling for item in function.symbols}
    for teardown in teardowns:
        kind = (
            OwnerScopeKind.UNPUBLISHED_MOUNT_CONSTRUCTION
            if _mount_construction_type(symbol_types.get(teardown.owner, ""))
            else OwnerScopeKind.FAILED_CONSTRUCTION
        )
        proofs.append(
            OwnerScopeProof(
                kind=kind,
                owner=teardown.owner,
                site=teardown.teardown_site,
                covered_effects=teardown.closed_effects,
                ownership_edges=teardown.ownership_edges,
                evidence=(
                    "source-proven fresh owner remains unpublished and unescaped; "
                    "whole-owner teardown must execute before the error exit"
                ),
            )
        )
    return tuple(proofs)


def _edge(
    function: FunctionIR,
    node: FrontendNode,
    *,
    child: str,
    parent: str,
    relation: OwnershipRelation,
    escape_state: EscapeState,
) -> OwnershipEdge:
    site = SourceSite(function.file.as_posix(), node.start_line, compact_ws(node.text))
    return OwnershipEdge(
        child=child,
        parent=parent,
        relation=relation,
        acquisition_site=site,
        escape_state=escape_state,
        source_identity=(
            f"{function.file.as_posix()}:{node.start_line}:"
            f"{child}->{parent}:{relation.value}"
        ),
    )


def _plain_symbol(text: str) -> str:
    value = compact_ws(text).strip("() ")
    return value if re.fullmatch(r"[A-Za-z_]\w*", value) else ""


def _leading_symbol(text: str) -> str:
    match = re.match(r"[&*()\s]*([A-Za-z_]\w*)", compact_ws(text))
    return match.group(1) if match else ""


def _addressed_field(text: str) -> tuple[str, str] | None:
    match = re.fullmatch(
        r"&\s*\(?\s*([A-Za-z_]\w*)\s*(?:->|\.)\s*([A-Za-z_]\w*)\s*\)?",
        compact_ws(text),
    )
    return (match.group(1), match.group(2)) if match else None


def _field_target(text: str) -> tuple[str, str] | None:
    match = re.fullmatch(
        r"([A-Za-z_]\w*)\s*(?:->|\.)\s*([A-Za-z_]\w*)",
        compact_ws(text),
    )
    return (match.group(1), match.group(2)) if match else None


def _array_member_owner(text: str) -> str:
    match = re.fullmatch(
        r"([A-Za-z_]\w*(?:(?:->|\.)[A-Za-z_]\w*)*)\s*\[[^]]+\]"
        r"(?:(?:->|\.)[A-Za-z_]\w*)?",
        compact_ws(text),
    )
    return match.group(1) if match else ""


def _declared_name(node: FrontendNode) -> str:
    declarator = node.child_by_field_name("declarator")
    if declarator is None:
        return ""
    identifiers = [item.text for item in declarator.walk() if item.type == "identifier"]
    return compact_ws(identifiers[-1]) if identifiers else ""


def _mount_construction_type(type_spelling: str) -> bool:
    return re.search(
        r"\bstruct\s+(?:super_block|[A-Za-z_]\w*(?:fs_info|mount))\b",
        compact_ws(type_spelling),
    ) is not None
