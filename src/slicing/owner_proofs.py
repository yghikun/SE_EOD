"""Owner identity and teardown proofs for residual slicing."""

from __future__ import annotations

import re
from dataclasses import replace

from ..failure_points import FailurePoint
from ..frontend.model import ControlFlowGraphIR, FunctionIR
from ..function_summary import LocalLifecycleBinding
from ..metadata_residual import (
    EffectEvidence,
    EffectProvenanceKind,
    EffectVisibility,
    MetadataDelta,
    MetadataEffect,
    MetadataPlane,
    OwnerTeardown,
    OwnershipEdge,
    OwnershipRelation,
)
from ..semantics.owner_scope import embedded_children, fresh_owner_descriptor_effect
from ..parser import compact_ws


_RUNTIME_PROGRESS_KINDS = {
    EffectProvenanceKind.PROGRESS_CURSOR,
    EffectProvenanceKind.RETRY_STATE,
}


def _leading_symbol(path: str) -> str:
    match = re.match(r"^([A-Za-z_]\w*)", compact_ws(path).lstrip("&*()"))
    return match.group(1) if match else ""


def _effect_targets_unpublished_fresh_local(
    effect: MetadataEffect,
    point: FailurePoint,
    lifecycles: tuple[LocalLifecycleBinding, ...],
    teardowns: tuple[OwnerTeardown, ...] = (),
    ownership_edges: tuple[OwnershipEdge, ...] = (),
) -> bool:
    root = _leading_symbol(effect.root)
    binding = next(
        (item for item in lifecycles if item.local_identity == root),
        None,
    )
    if binding is None or effect.site.line < binding.allocation_line:
        return False
    if any(_exact_owner_symbol(teardown.owner) == root for teardown in teardowns):
        return False
    teardown_owners = {
        _exact_owner_symbol(teardown.owner)
        for teardown in teardowns
        if _exact_owner_symbol(teardown.owner)
    }
    if any(
        edge.child == root
        and edge.parent in teardown_owners
        and edge.relation is not OwnershipRelation.EMBEDDED
        for edge in ownership_edges
    ):
        return False
    if any(line <= point.call_site.line for line in binding.rebind_lines):
        return False
    return not any(line <= point.call_site.line for line in binding.publication_lines)


def _lifecycle_events_reachable_on_failure(
    cfg: ControlFlowGraphIR,
    lifecycles: tuple[LocalLifecycleBinding, ...],
    point: FailurePoint,
    error_blocks: set[int],
) -> dict[str, set[int]]:
    """Return lifecycle events that can occur on this checked failure path.

    Lifecycle bindings are function-wide facts.  A publication located solely
    on the normal-success continuation must not invalidate a teardown that is
    proved on the alternate error edge (a common ``goto out`` shape).
    """

    result: dict[str, set[int]] = {}
    for binding in lifecycles:
        unsafe: set[int] = set()
        for line in (
            *binding.publication_lines,
            *binding.escape_lines,
            *binding.rebind_lines,
        ):
            if line <= point.call_site.line:
                unsafe.add(line)
                continue
            block = cfg.block_at_line(line)
            if block is not None and block.id in error_blocks:
                unsafe.add(line)
        result[binding.local_identity] = unsafe
    return result


def _fresh_local_descriptor_effect(
    function: FunctionIR,
    effect: MetadataEffect,
    lifecycles: tuple[LocalLifecycleBinding, ...],
) -> MetadataEffect:
    """Refine caller-field copies into a fresh owner as private descriptors."""

    owner = _leading_symbol(effect.root)
    binding = next(
        (item for item in lifecycles if item.local_identity == owner),
        None,
    )
    if (
        binding is None
        or effect.site.line < binding.allocation_line
        or effect.delta is not MetadataDelta.SET
    ):
        return effect
    value_root = _leading_symbol(effect.value)
    parameter_names = set(function.parameters) | {
        symbol.name for symbol in function.symbols if symbol.kind == "parameter"
    }
    value = compact_ws(effect.value)
    if value_root not in parameter_names or not re.search(r"(?:->|\.)", value):
        return effect
    return fresh_owner_descriptor_effect(effect, owner)


def _is_runtime_progress_effect(effect: MetadataEffect) -> bool:
    return any(
        provenance.kind in _RUNTIME_PROGRESS_KINDS
        for provenance in effect.semantic_provenance
    )


def _owner_scope_review_blockers(
    residuals: tuple[MetadataEffect, ...],
    teardowns: tuple[OwnerTeardown, ...],
    proofs: tuple[OwnerTeardown, ...],
    lifecycles: tuple[LocalLifecycleBinding, ...],
    lifecycle_unsafe_lines: dict[str, set[int]],
) -> tuple[str, ...]:
    """Audit owner-scope ambiguity without turning a visible residual UNKNOWN."""

    proved = {proof.owner for proof in proofs}
    teardown_owners = {
        owner
        for teardown in teardowns
        if (owner := _exact_owner_symbol(teardown.owner))
    }
    escape_lines = {
        binding.local_identity: set(binding.escape_lines)
        for binding in lifecycles
    }
    owners = {
        owner
        for effect in residuals
        if (owner := _leading_symbol(effect.root)) in teardown_owners - proved
        and lifecycle_unsafe_lines.get(owner, set())
        & escape_lines.get(owner, set())
    }
    return tuple(f"owner_scope_escape_review:{owner}" for owner in sorted(owners))


def _owner_teardown_proofs(
    residuals: tuple[MetadataEffect, ...],
    teardowns: tuple[OwnerTeardown, ...],
    point: FailurePoint,
    lifecycles: tuple[LocalLifecycleBinding, ...],
    ownership_edges: tuple[OwnershipEdge, ...],
    lifecycle_unsafe_lines: dict[str, set[int]],
) -> tuple[OwnerTeardown, ...]:
    proofs: list[OwnerTeardown] = []
    already_closed: set[MetadataEffect] = set()
    for teardown in teardowns:
        owner = _exact_owner_symbol(teardown.owner)
        if not owner:
            continue
        binding = next(
            (item for item in lifecycles if item.local_identity == owner),
            None,
        )
        if binding is None or binding.allocation_line > point.call_site.line:
            continue
        if any(
            line <= teardown.teardown_site.line
            for line in lifecycle_unsafe_lines.get(owner, set())
        ):
            continue
        children = embedded_children(owner, ownership_edges)
        covered_roots = (owner, *children)
        closed = tuple(
            effect
            for effect in residuals
            if effect not in already_closed
            and any(
                _teardown_covers_embedded_effect(covered_owner, effect)
                for covered_owner in covered_roots
            )
        )
        if not closed:
            continue
        already_closed.update(closed)
        proofs.append(
            replace(
                teardown,
                owner=owner,
                allocation_site=binding.allocation_site,
                closed_effects=closed,
                ownership_edges=tuple(
                    edge
                    for edge in ownership_edges
                    if edge.parent in covered_roots or edge.child in children
                ),
                transitively_destroyed_children=children,
                nonclosable_effects=tuple(
                    effect
                    for effect in residuals
                    if effect not in closed
                    and _leading_symbol(effect.root) in set(children)
                ),
                evidence=(
                    f"{teardown.evidence}; owner is source-proven fresh, remains "
                    "unpublished, unescaped, and never rebound, and teardown must execute before "
                    "the verified error exit"
                ),
            )
        )
    return tuple(proofs)


def _teardown_covers_embedded_effect(
    owner: str,
    effect: MetadataEffect,
) -> bool:
    descriptor_provenance = any(
        item.kind is EffectProvenanceKind.OPERATION_DESCRIPTOR
        for item in effect.semantic_provenance
    )
    if effect.visibility is EffectVisibility.PERSISTENT_EXTERNAL:
        return False
    if (
        effect.plane is MetadataPlane.RECOVERY
        or effect.visibility is EffectVisibility.RECOVERY_VISIBLE
    ) and not descriptor_provenance:
        return False
    root = compact_ws(effect.root)
    if not (
        root == owner
        or root.startswith(f"{owner}->")
        or root.startswith(f"{owner}.")
    ):
        return False
    if effect.key in {"list_membership", "tree_membership"} or effect.key.startswith(
        ("xarray:", "radix_tree:")
    ):
        return False
    return (
        effect.evidence is EffectEvidence.DIRECT_SOURCE
        or (
            effect.evidence is EffectEvidence.EXPLICIT_PRIMITIVE
            and effect.key.startswith("bit:")
        )
    )


def _exact_owner_symbol(text: str) -> str:
    value = compact_ws(text).strip()
    while match := re.fullmatch(r"\(\s*([A-Za-z_]\w*)\s*\)", value):
        value = match.group(1)
    return value if re.fullmatch(r"[A-Za-z_]\w*", value) else ""
