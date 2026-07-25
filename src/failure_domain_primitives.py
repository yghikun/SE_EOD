"""Small semantic boundary for explicit failure-containment primitives."""

from __future__ import annotations

import re

from .metadata_residual import FailureDomainKind, MetadataEffect


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


def covered_effects_for_action(
    action: MetadataEffect,
    effects: tuple[MetadataEffect, ...],
) -> tuple[MetadataEffect, ...]:
    """Return only effects covered by this explicit terminal action."""

    try:
        kind = FailureDomainKind(action.value)
    except ValueError:
        return ()
    if kind is not FailureDomainKind.TRANSACTION_ABORT:
        # M33's accepted shutdown/checkpoint contract is intentionally kept
        # unchanged until recovery scope is modeled as a separate milestone.
        return effects
    transaction = _exact_symbol(action.root)
    if not transaction:
        return ()
    token = rf"\b{re.escape(transaction)}\b"
    return tuple(
        effect
        for effect in effects
        if any(
            re.search(token, value) is not None
            for value in (effect.root, effect.key, effect.value)
        )
    )


def _exact_symbol(text: str) -> str:
    value = text.strip()
    while match := re.fullmatch(r"\(\s*([A-Za-z_]\w*)\s*\)", value):
        value = match.group(1)
    return value if re.fullmatch(r"[A-Za-z_]\w*", value) else ""
