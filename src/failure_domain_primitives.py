"""Small semantic boundary for filesystem-wide failure containment primitives."""

from __future__ import annotations

from .metadata_residual import FailureDomainKind


# These are terminal kernel primitives, not report/function suppressions.  A
# caller still has to prove that the primitive executes on the audited error
# path before it can contain a residual.
FAILURE_DOMAIN_PRIMITIVES = {
    "f2fs_stop_checkpoint": FailureDomainKind.CHECKPOINT_STOP,
    "xfs_force_shutdown": FailureDomainKind.FATAL_SHUTDOWN,
}

FAILURE_DOMAIN_KEY_PREFIX = "failure_domain:"


def failure_domain_kind(name: str) -> FailureDomainKind | None:
    return FAILURE_DOMAIN_PRIMITIVES.get(name)


def failure_domain_key(kind: FailureDomainKind) -> str:
    return f"{FAILURE_DOMAIN_KEY_PREFIX}{kind.value.lower()}"


def is_failure_domain_key(key: str) -> bool:
    return key.startswith(FAILURE_DOMAIN_KEY_PREFIX)
