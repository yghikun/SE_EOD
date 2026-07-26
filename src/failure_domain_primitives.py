"""Small semantic boundary for explicit failure-containment primitives."""

from __future__ import annotations

import re

from .metadata_residual import (
    EffectVisibility,
    EscapeState,
    FailureDomainKind,
    FailureDomainScope,
    MetadataEffect,
    MetadataPlane,
)


# These are terminal kernel primitives, not report/function suppressions.  A
# caller still has to prove that the primitive executes on the audited error
# path before it can contain a residual.
FAILURE_DOMAIN_PRIMITIVES = {
    "btrfs_abort_transaction": FailureDomainKind.TRANSACTION_ABORT,
    "f2fs_stop_checkpoint": FailureDomainKind.CHECKPOINT_STOP,
    "xfs_force_shutdown": FailureDomainKind.FATAL_SHUTDOWN,
}

# Exact source-verified predicates for an already-entered failure domain.  A
# guard is evidence only on its true CFG edge; callers must not treat the call
# itself as an unconditional terminal action.
FAILURE_DOMAIN_GUARDS = {
    "f2fs_cp_error": (0, FailureDomainKind.CHECKPOINT_STOP),
}

FAILURE_DOMAIN_KEY_PREFIX = "failure_domain:"

# Exact transaction lifecycle primitives whose semantics were verified from
# their source bodies.  This is not a name pattern: unlisted helpers retain the
# normal conservative treatment.
TRANSACTION_CANCEL_PRIMITIVES = {
    "xfs_trans_cancel": 0,
}


FAILURE_DOMAIN_SCOPES = {
    FailureDomainKind.TRANSACTION_ABORT: FailureDomainScope(
        action=FailureDomainKind.TRANSACTION_ABORT,
        allowed_planes=tuple(MetadataPlane),
        allowed_visibility=(EffectVisibility.TRANSACTION_LOCAL,),
        forbidden_categories=("transaction_external", "escaped_owner"),
        required_owner_relation=True,
    ),
    FailureDomainKind.FATAL_SHUTDOWN: FailureDomainScope(
        action=FailureDomainKind.FATAL_SHUTDOWN,
        allowed_planes=(MetadataPlane.STRUCTURAL, MetadataPlane.ACCOUNTING),
        allowed_visibility=(
            EffectVisibility.PRIVATE_RUNTIME,
            EffectVisibility.OWNER_LOCAL,
            EffectVisibility.TRANSACTION_LOCAL,
        ),
        forbidden_categories=("recovery_visible", "persistent_external"),
    ),
    FailureDomainKind.CHECKPOINT_STOP: FailureDomainScope(
        action=FailureDomainKind.CHECKPOINT_STOP,
        allowed_planes=(MetadataPlane.STRUCTURAL, MetadataPlane.ACCOUNTING),
        allowed_visibility=(
            EffectVisibility.PRIVATE_RUNTIME,
            EffectVisibility.OWNER_LOCAL,
            EffectVisibility.TRANSACTION_LOCAL,
        ),
        forbidden_categories=("recovery_visible", "persistent_external"),
    ),
}


def failure_domain_kind(name: str) -> FailureDomainKind | None:
    return FAILURE_DOMAIN_PRIMITIVES.get(name)


def failure_domain_guard(name: str) -> tuple[int, FailureDomainKind] | None:
    return FAILURE_DOMAIN_GUARDS.get(name)


def failure_domain_key(kind: FailureDomainKind) -> str:
    return f"{FAILURE_DOMAIN_KEY_PREFIX}{kind.value.lower()}"


def is_failure_domain_key(key: str) -> bool:
    return key.startswith(FAILURE_DOMAIN_KEY_PREFIX)


def transaction_cancel_owner_index(name: str) -> int | None:
    return TRANSACTION_CANCEL_PRIMITIVES.get(name)


def failure_domain_scope(kind: FailureDomainKind) -> FailureDomainScope | None:
    return FAILURE_DOMAIN_SCOPES.get(kind)


def covered_effects_for_action(
    action: MetadataEffect,
    effects: tuple[MetadataEffect, ...],
) -> tuple[MetadataEffect, ...]:
    """Return only effects covered by this explicit terminal action."""

    try:
        kind = FailureDomainKind(action.value)
    except ValueError:
        return ()
    scope = failure_domain_scope(kind)
    if scope is None:
        return ()
    transaction = _exact_symbol(action.root)
    if kind is FailureDomainKind.TRANSACTION_ABORT:
        if not transaction:
            return ()
        return tuple(
            effect
            for effect in effects
            if effect.plane in scope.allowed_planes
            and _transaction_relation_matches(effect, transaction)
        )
    return tuple(
        effect
        for effect in effects
        if (
            effect.plane in scope.allowed_planes
            or effect.visibility is EffectVisibility.TRANSACTION_LOCAL
        )
        and effect.visibility in scope.allowed_visibility
    )


def _transaction_relation_matches(effect: MetadataEffect, transaction: str) -> bool:
    relation = effect.transaction_ownership
    if relation is not None:
        return (
            relation.transaction_root == transaction
            and relation.escape_state is EscapeState.PRIVATE
            and effect.plane in relation.abort_footprint
        )
    return _exact_symbol(effect.root) == transaction


def _exact_symbol(text: str) -> str:
    value = text.strip()
    while match := re.fullmatch(r"\(\s*([A-Za-z_]\w*)\s*\)", value):
        value = match.group(1)
    return value if re.fullmatch(r"[A-Za-z_]\w*", value) else ""
