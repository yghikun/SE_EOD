"""Identity-aware cancellation and residual normalization."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .metadata_residual import MetadataDelta, MetadataEffect


INVERSE_DELTAS = {
    MetadataDelta.INC: MetadataDelta.DEC,
    MetadataDelta.DEC: MetadataDelta.INC,
    MetadataDelta.SET: MetadataDelta.CLEAR,
    MetadataDelta.CLEAR: MetadataDelta.SET,
    MetadataDelta.ADD: MetadataDelta.REMOVE,
    MetadataDelta.REMOVE: MetadataDelta.ADD,
    MetadataDelta.RESERVE: MetadataDelta.RELEASE,
    MetadataDelta.RELEASE: MetadataDelta.RESERVE,
}


@dataclass(frozen=True)
class CancellationPair:
    opened: MetadataEffect
    closed: MetadataEffect
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "opened": self.opened.to_dict(),
            "closed": self.closed.to_dict(),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ProtectionPair:
    effect: MetadataEffect
    protection: MetadataEffect
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "effect": self.effect.to_dict(),
            "protection": self.protection.to_dict(),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CancellationResult:
    cancelled: tuple[CancellationPair, ...]
    protected: tuple[ProtectionPair, ...]
    residuals: tuple[MetadataEffect, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "cancelled": [item.to_dict() for item in self.cancelled],
            "protected": [item.to_dict() for item in self.protected],
            "residuals": [item.to_dict() for item in self.residuals],
        }


def normalize_residuals(
    reaching_effects: tuple[MetadataEffect, ...],
    cancellations: tuple[MetadataEffect, ...],
    protections: tuple[MetadataEffect, ...] = (),
) -> CancellationResult:
    """Apply inverse effects and explicit protections to reaching effects."""

    remaining = list(reaching_effects)
    unused_cancellations = list(cancellations)
    cancelled: list[CancellationPair] = []

    for effect in list(remaining):
        match_index = next(
            (
                index
                for index, candidate in enumerate(unused_cancellations)
                if effects_cancel(effect, candidate)
            ),
            None,
        )
        if match_index is None:
            continue
        closing = unused_cancellations.pop(match_index)
        remaining.remove(effect)
        cancelled.append(
            CancellationPair(effect, closing, cancellation_reason(effect, closing))
        )

    protected_pairs: list[ProtectionPair] = []
    for effect in list(remaining):
        protection = next(
            (
                candidate
                for candidate in protections
                if effect_protected_by(effect, candidate)
            ),
            None,
        )
        if protection is None:
            continue
        remaining.remove(effect)
        protected_pairs.append(
            ProtectionPair(effect, protection, protection_reason(effect, protection))
        )

    return CancellationResult(
        cancelled=tuple(cancelled),
        protected=tuple(protected_pairs),
        residuals=tuple(remaining),
    )


def effects_cancel(opened: MetadataEffect, closed: MetadataEffect) -> bool:
    """Return true when ``closed`` is an identity-compatible inverse effect."""

    if opened.plane is not closed.plane:
        return False
    if INVERSE_DELTAS.get(opened.delta) is not closed.delta:
        return False
    if not _same_or_compatible_identity(opened, closed):
        return False
    return _same_or_equivalent_value(opened, closed)


def effect_protected_by(effect: MetadataEffect, protection: MetadataEffect) -> bool:
    """Return true when an explicit PROTECT effect binds to ``effect``."""

    if protection.delta is not MetadataDelta.PROTECT:
        return False
    if effect.plane is not protection.plane:
        return False
    if not _same_or_compatible_identity(effect, protection):
        return False
    return _same_or_equivalent_value(effect, protection, allow_empty=True)


def cancellation_reason(opened: MetadataEffect, closed: MetadataEffect) -> str:
    return (
        f"{opened.delta.value} at {opened.site.line} is cancelled by "
        f"{closed.delta.value} at {closed.site.line}"
    )


def protection_reason(effect: MetadataEffect, protection: MetadataEffect) -> str:
    return (
        f"{effect.delta.value} at {effect.site.line} is protected by "
        f"{protection.delta.value} at {protection.site.line}"
    )


def _same_or_compatible_identity(
    left: MetadataEffect,
    right: MetadataEffect,
) -> bool:
    if _norm(left.root) == _norm(right.root) and _norm(left.key) == _norm(right.key):
        return True
    if _is_list_membership(left, right):
        return _list_membership_compatible(left, right)
    return False


def _same_or_equivalent_value(
    left: MetadataEffect,
    right: MetadataEffect,
    *,
    allow_empty: bool = False,
) -> bool:
    left_value = _norm(left.value)
    right_value = _norm(right.value)
    if allow_empty and (not left_value or not right_value):
        return True
    if left.delta in {MetadataDelta.SET, MetadataDelta.CLEAR} and right.delta in {
        MetadataDelta.SET,
        MetadataDelta.CLEAR,
    }:
        return _is_clear_value(left_value) or _is_clear_value(right_value) or left_value == right_value
    if _is_list_membership(left, right):
        return _compatible_path(_list_member(left), _list_member(right))
    return left_value == right_value


def _is_list_membership(left: MetadataEffect, right: MetadataEffect) -> bool:
    return _norm(left.key) == "list_membership" and _norm(right.key) == "list_membership"


def _list_membership_compatible(left: MetadataEffect, right: MetadataEffect) -> bool:
    left_root = _norm(left.root)
    right_root = _norm(right.root)
    left_member = _list_member(left)
    right_member = _list_member(right)
    if left_root == right_root:
        return True
    if left_root == right_member or right_root == left_member:
        return True
    return False


def _compatible_path(left: str, right: str) -> bool:
    if left == right:
        return True
    return left.startswith(f"{right}->") or left.startswith(f"{right}.") or right.startswith(f"{left}->") or right.startswith(f"{left}.")


def _list_member(effect: MetadataEffect) -> str:
    value = _norm(effect.value)
    if value:
        return value
    return _norm(effect.root)


def _norm(value: str) -> str:
    text = " ".join(value.strip().split())
    text = re.sub(r"^\(+", "", text)
    text = re.sub(r"\)+$", "", text)
    while text.startswith("&") or text.startswith("*"):
        text = text[1:].strip()
    text = re.sub(r"\s*(->|\.)\s*", r"\1", text)
    return text


def _is_clear_value(value: str) -> bool:
    return value in {"", "0", "0L", "0UL", "NULL", "false", "FALSE"}
