"""Transaction and terminal failure-domain proofs for residual slicing."""

from __future__ import annotations

import re

from ..semantics.failure_domain_primitives import (
    covered_effects_for_action,
    failure_domain_scope,
    is_failure_domain_key,
    transaction_cancel_owner_index,
)
from ..failure_points import FailurePoint
from ..metadata_residual import (
    EffectEvidence,
    FailureDomainKind,
    FailureDomainProof,
    MetadataDelta,
    MetadataEffect,
    SourceSite,
)
from ..parser import call_name_and_args, compact_ws
from .owner_proofs import _leading_symbol


def _aborted_transaction_protections(
    reaching_effects: tuple[MetadataEffect, ...],
    cancellations: tuple[MetadataEffect, ...],
) -> tuple[MetadataEffect, ...]:
    """Bind an explicit error-path transaction abort to its recorded effects.

    An abort is evidence of transaction-owned recovery only for effects that
    source syntax binds to the same transaction handle.  This deliberately
    does not protect unrelated inode, device, or reservation mutations.
    """

    aborts = tuple(
        effect
        for effect in cancellations
        if _is_transaction_abort(effect)
    )
    protections: list[MetadataEffect] = []
    for abort in aborts:
        transaction = _exact_transaction_identity(abort.root)
        if not transaction:
            continue
        for effect in reaching_effects:
            if not _effect_mentions_transaction(effect, transaction):
                continue
            protections.append(
                MetadataEffect(
                    root=effect.root,
                    key=effect.key,
                    plane=effect.plane,
                    delta=MetadataDelta.PROTECT,
                    value=effect.value,
                    site=SourceSite(
                        abort.site.file,
                        abort.site.line,
                        f"{abort.site.expression} protects transaction-bound effect",
                    ),
                    evidence=EffectEvidence.EXPLICIT_PRIMITIVE,
                )
            )
    return tuple(dict.fromkeys(protections))


def _is_transaction_abort(effect: MetadataEffect) -> bool:
    name, _ = call_name_and_args(compact_ws(effect.site.expression))
    return effect.delta is MetadataDelta.CLOSE and (
        transaction_cancel_owner_index(name) is not None
        or transaction_cancel_owner_index(effect.key) is not None
    )


def _effect_mentions_transaction(effect: MetadataEffect, transaction: str) -> bool:
    token = rf"(?<![A-Za-z0-9_]){re.escape(transaction)}(?![A-Za-z0-9_])"
    return any(
        re.search(token, value) is not None
        for value in (effect.root, effect.key, effect.value)
    )


def _effect_is_failure_call(effect: MetadataEffect, point: FailurePoint) -> bool:
    """Exclude unproven helper effects originating at the failing call itself."""

    return (
        effect.site.line == point.call_site.line
        and compact_ws(effect.site.expression) == compact_ws(point.call_site.expression)
    )


def _explicit_failure_domain_proofs(
    reaching_effects: tuple[MetadataEffect, ...],
    cancellations: tuple[MetadataEffect, ...],
    protections: tuple[MetadataEffect, ...],
    residuals: tuple[MetadataEffect, ...],
) -> tuple[FailureDomainProof, ...]:
    proofs = []
    for protection in protections:
        if not is_failure_domain_key(protection.key):
            continue
        try:
            kind = FailureDomainKind(protection.value)
        except ValueError:
            continue
        coverage_candidates = residuals
        if kind is FailureDomainKind.TRANSACTION_ABORT:
            coverage_candidates = tuple(
                dict.fromkeys((*residuals, *reaching_effects))
            )
        covered_effects = covered_effects_for_action(
            protection,
            coverage_candidates,
        )
        if not covered_effects:
            continue
        proofs.append(
            FailureDomainProof(
                kind=kind,
                site=protection.site,
                owner=protection.root,
                evidence=(
                    f"{protection.site.expression} is an explicit terminal "
                    "failure-domain primitive on the must-execute error path"
                ),
                covered_effects=covered_effects,
                scope=failure_domain_scope(kind),
            )
        )
    for cancellation in cancellations:
        name, _ = call_name_and_args(compact_ws(cancellation.site.expression))
        if (
            transaction_cancel_owner_index(name) is None
            and transaction_cancel_owner_index(cancellation.key) is None
        ):
            continue
        transaction = _exact_transaction_identity(cancellation.root)
        if not transaction:
            continue
        if not _transaction_has_dirty_evidence(transaction, reaching_effects):
            continue
        covered = _transaction_cancel_covered_residuals(
            transaction,
            tuple(dict.fromkeys((*reaching_effects, *protections))),
            residuals,
        )
        if not covered:
            continue
        proofs.append(
            FailureDomainProof(
                kind=FailureDomainKind.FATAL_SHUTDOWN,
                site=cancellation.site,
                owner=transaction,
                evidence=(
                    "xfs_trans_cancel() observes transaction-owned dirty state; "
                    "its source contract forces shutdown when that state cannot be restored"
                ),
                covered_effects=covered,
                scope=failure_domain_scope(FailureDomainKind.FATAL_SHUTDOWN),
            )
        )
    return tuple(dict.fromkeys(proofs))


def _conditional_shutdown_review_blockers(
    reaching_effects: tuple[MetadataEffect, ...],
    cancellations: tuple[MetadataEffect, ...],
    residuals: tuple[MetadataEffect, ...],
) -> tuple[str, ...]:
    """Keep transaction-bound recovery residuals in Review without dirty proof."""

    blockers: list[str] = []
    for cancellation in cancellations:
        name, _ = call_name_and_args(compact_ws(cancellation.site.expression))
        if (
            transaction_cancel_owner_index(name) is None
            and transaction_cancel_owner_index(cancellation.key) is None
        ):
            continue
        transaction = _exact_transaction_identity(cancellation.root)
        if not transaction or _transaction_has_dirty_evidence(
            transaction, reaching_effects
        ):
            continue
        for effect in residuals:
            if not any(
                _transaction_relation_covers_effect(
                    relation_effect, transaction, effect
                )
                for relation_effect in reaching_effects
            ):
                continue
            owner = _leading_symbol(effect.root)
            if owner:
                blockers.append(f"conditional_shutdown_review:{owner}")
    return tuple(dict.fromkeys(blockers))


def _transaction_has_dirty_evidence(
    transaction: str,
    reaching_effects: tuple[MetadataEffect, ...],
) -> bool:
    """Require source-visible log/dirty state before applying XFS shutdown semantics."""

    for effect in reaching_effects:
        relation = effect.transaction_ownership
        if (
            relation is not None
            and compact_ws(relation.transaction_root) == transaction
            and relation.primitive == "xfs_trans_log_inode"
        ):
            return True
        if effect.delta not in {
            MetadataDelta.ADD,
            MetadataDelta.SET,
            MetadataDelta.INC,
            MetadataDelta.RESERVE,
        }:
            continue
        if not _effect_mentions_transaction(effect, transaction):
            continue
        dirty_text = compact_ws(
            f"{effect.key} {effect.value} {effect.site.expression}"
        ).lower()
        if "xfs_trans_dirty" in dirty_text or re.search(
            r"(?:^|[^a-z0-9])dirty(?:$|[^a-z0-9])", dirty_text
        ):
            return True
    return False


def _transaction_cancel_covered_residuals(
    transaction: str,
    reaching_effects: tuple[MetadataEffect, ...],
    residuals: tuple[MetadataEffect, ...],
) -> tuple[MetadataEffect, ...]:
    directly_bound = tuple(
        effect for effect in residuals if _effect_mentions_transaction(effect, transaction)
    )
    relation_bound = tuple(
        effect
        for effect in residuals
        if any(
            _transaction_relation_covers_effect(relation_effect, transaction, effect)
            for relation_effect in reaching_effects
        )
    )
    return tuple(dict.fromkeys((*directly_bound, *relation_bound)))


def _transaction_relation_covers_effect(
    relation_effect: MetadataEffect,
    transaction: str,
    effect: MetadataEffect,
) -> bool:
    relation = relation_effect.transaction_ownership
    if relation is None:
        return False
    if compact_ws(relation.transaction_root) != transaction:
        return False
    owned = compact_ws(relation.owned_root)
    root = compact_ws(effect.root)
    return root == owned or root.startswith((f"{owned}->", f"{owned}."))


def _exact_transaction_identity(text: str) -> str:
    value = compact_ws(text).strip("&*() ")
    return value if re.fullmatch(
        r"[A-Za-z_]\w*(?:(?:->|\.)[A-Za-z_]\w*)*",
        value,
    ) else ""
