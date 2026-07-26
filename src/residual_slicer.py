"""Failure-anchored residual slicing."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Iterable

from .cancellation import effect_protected_by, effects_cancel, normalize_residuals
from .aggregate_snapshot import aggregate_snapshot_restore_cancellations
from .cfg import build_cfg
from .effect_extractor import (
    effect_targets_transient_object,
    extract_metadata_effects_with_skips,
    looks_like_metadata_reader,
    write_only_output_parameters,
)
from .owner_scope import (
    effect_with_visibility,
    embedded_children,
    fresh_owner_descriptor_effect,
    infer_ownership_edges,
    operation_descriptor_effect,
    output_effect,
    owner_scope_proofs,
    private_owner_effect,
)
from .failure_points import FailurePoint, find_failure_points
from .failure_domain_primitives import (
    covered_effects_for_action,
    failure_domain_scope,
    is_failure_domain_key,
    transaction_cancel_owner_index,
)
from .frontend.model import BasicBlockIR, ControlFlowGraphIR, FrontendNode, FunctionIR
from .function_summary import (
    ErrorExitPartition,
    FunctionSummary,
    LifecycleEvent,
    LifecycleExit,
    LifecycleFact,
    LocalLifecycleBinding,
    apply_same_file_summary,
    build_local_lifecycle_bindings,
    extract_owner_teardowns,
)
from .metadata_residual import (
    DemandSummaryRequest,
    DemandSummaryRequirement,
    EffectEvidence,
    EffectProvenanceKind,
    EffectVisibility,
    FailureDomainKind,
    FailureDomainProof,
    MetadataDelta,
    MetadataEffect,
    MetadataPlane,
    OwnerTeardown,
    OwnershipEdge,
    OwnershipRelation,
    ResidualSlice,
    ResidualState,
    SourceSite,
)
from .parser import call_name_and_args, compact_ws
from .smt_solver import SolverResult, failure_branch_feasibility
from .transient_provenance import TransientArgumentProvenance


@dataclass(frozen=True)
class ResidualSlicingResult:
    function: str
    slices: tuple[ResidualSlice, ...]
    unknown_causes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "function": self.function,
            "slices": [item.to_dict() for item in self.slices],
            "unknown_causes": list(self.unknown_causes),
        }


def slice_function_residuals(
    function: FunctionIR,
    *,
    summaries: dict[str, FunctionSummary] | None = None,
    failure_points: tuple[FailurePoint, ...] | None = None,
    transient_provenance: tuple[TransientArgumentProvenance, ...] = (),
) -> ResidualSlicingResult:
    """Compute M5 residual slices for one function.

    This pass is intraprocedural with optional same-file helper summaries.  It
    collects effects that can reach each failure point, then walks the verified
    error edge to collect cancellation and protection effects before the error
    exit.
    """

    if function.body_node is None:
        return ResidualSlicingResult(function.name, (), ("missing function body",))

    cfg = build_cfg(function)
    summaries = summaries or {}
    failure_points = failure_points if failure_points is not None else find_failure_points(function)
    provenance_by_parameter: dict[str, tuple[TransientArgumentProvenance, ...]] = {}
    for item in transient_provenance:
        provenance_by_parameter.setdefault(item.parameter, ())
        provenance_by_parameter[item.parameter] += (item,)
    extraction = extract_metadata_effects_with_skips(function)
    local_effects_list: list[_LocatedEffect] = []
    transient_effects_list: list[_LocatedEffect] = []
    for effect in extraction.effects:
        evidence = (
            provenance_by_parameter.get(effect.root, ())
            if effect.evidence is EffectEvidence.DIRECT_SOURCE
            else ()
        )
        enriched = (
            operation_descriptor_effect(
                replace(effect, transient_provenance=evidence), effect.root
            )
            if evidence
            else effect_with_visibility(effect)
        )
        located = _LocatedEffect(
            enriched,
            _block_for_site(cfg, effect.site),
        )
        if evidence:
            transient_effects_list.append(located)
        else:
            local_effects_list.append(located)
    local_effects = tuple(local_effects_list)
    transient_effects = tuple(transient_effects_list)
    local_lifecycles = build_local_lifecycle_bindings(function, summaries)
    local_effects = tuple(
        replace(
            item,
            effect=_fresh_local_descriptor_effect(
                function,
                item.effect,
                local_lifecycles,
            ),
        )
        for item in local_effects
    )
    ownership_edges = infer_ownership_edges(function, local_lifecycles)
    output_parameters = write_only_output_parameters(function)
    call_apps = tuple(_summary_applications(function, cfg, summaries))
    local_effects = _drop_summarized_name_inferred_call_effects(
        local_effects,
        call_apps,
    )
    known_error_path_effect_sites = _known_error_path_effect_sites(local_effects)
    direct_owner_teardowns = extract_owner_teardowns(function)

    slices: list[ResidualSlice] = []
    all_unknown_causes: list[str] = []
    for point in failure_points:
        reaching_blocks = _reverse_reachable(cfg, point.error_edge.source_block)
        error_path = _forward_reachable_until_returns(
            cfg,
            point.error_edge.target_block,
            point,
        )
        error_blocks = error_path.reachable
        must_error_blocks = error_path.must_execute
        reaching_effects: list[MetadataEffect] = []
        cancellations: list[MetadataEffect] = []
        protections: list[MetadataEffect] = []
        must_owner_teardowns = [
            teardown
            for teardown in direct_owner_teardowns
            if (block_id := _block_for_site(cfg, teardown.teardown_site)) is not None
            and block_id in must_error_blocks
            and teardown.teardown_site.line >= point.check_site.line
        ]
        unknown_causes: list[str] = []
        diagnostic_blockers: list[str] = []
        exact_partition_complete = False
        error_path_unknown_causes: list[str] = []
        unknown_influences: list[_UnknownInfluence] = []
        out_of_scope_effects = [
            item.effect
            for item in transient_effects
            if item.block_id in reaching_blocks
            and _effect_before_failure(item.effect, point)
            and not _effect_is_failure_call(item.effect, point)
        ]

        for item in local_effects:
            if item.block_id not in reaching_blocks or not _effect_before_failure(item.effect, point):
                continue
            if _effect_is_failure_call(item.effect, point):
                continue
            if _is_runtime_progress_effect(item.effect):
                out_of_scope_effects.append(item.effect)
                continue
            if _effect_targets_unpublished_fresh_local(
                item.effect,
                point,
                local_lifecycles,
                tuple(must_owner_teardowns),
                ownership_edges,
            ):
                out_of_scope_effects.append(
                    private_owner_effect(
                        item.effect,
                        _leading_symbol(item.effect.root),
                    )
                )
                continue
            if _leading_symbol(item.effect.root) in output_parameters:
                out_of_scope_effects.append(
                    output_effect(item.effect, _leading_symbol(item.effect.root))
                )
                continue
            if item.effect.delta in _CANCEL_DELTAS:
                cancellations.append(item.effect)
            elif item.effect.delta in _PROTECT_DELTAS:
                protections.append(item.effect)
            else:
                reaching_effects.append(item.effect)

        for item in local_effects:
            if item.block_id not in error_blocks:
                continue
            if item.effect.site.line < point.check_site.line:
                continue
            if item.effect.delta in _CANCEL_DELTAS and item.block_id in must_error_blocks:
                cancellations.append(item.effect)
            elif item.effect.delta in _PROTECT_DELTAS and item.block_id in must_error_blocks:
                protections.append(item.effect)
            elif item.effect.delta in (_CANCEL_DELTAS | _PROTECT_DELTAS):
                cause = _conditional_effect_cause(item.effect)
                unknown_influences.append(
                    _UnknownInfluence(
                        cause,
                        item.effect.site,
                        "conditional_cleanup",
                        (item.effect,),
                    )
                )

        for item in local_effects:
            if not (
                point.call_site.line < item.effect.site.line < point.check_site.line
                and item.block_id is not None
                and _block_dominates(
                    cfg,
                    item.block_id,
                    point.error_edge.source_block,
                )
            ):
                continue
            if item.effect.delta in _CANCEL_DELTAS:
                cancellations.append(item.effect)
            elif item.effect.delta in _PROTECT_DELTAS:
                protections.append(item.effect)

        for app in call_apps:
            is_failure_call = _is_failure_call_application(app, point)
            selected_partition = (
                _select_exact_error_partition(
                    app.error_exit_partitions,
                    point,
                    exhaustive=app.error_partitions_exhaustive,
                )
                if is_failure_call
                else None
            )
            if selected_partition is not None and selected_partition.complete:
                exact_partition_complete = True
            failure_effects_complete = (
                selected_partition.complete
                if selected_partition is not None
                else app.failure_effects_complete
            )
            transfer_order_unknown = (
                is_failure_call
                and app.has_ownership_transfer
                and not failure_effects_complete
            )
            if (
                is_failure_call
                and (
                    app.may_fail
                    or app.failure_effects_complete
                    or _selected_partition_proves_success_only_effects(
                        selected_partition,
                        app,
                    )
                )
                and app.block_id in reaching_blocks
                and app.site.line <= point.call_site.line
            ):
                failure_opens = (
                    _selected_partition_opens(selected_partition)
                    if selected_partition is not None
                    else app.error_opens
                )
                failure_cancels = (
                    selected_partition.cancels
                    if selected_partition is not None
                    else app.error_cancels
                )
                failure_protects = (
                    tuple(dict.fromkeys((
                        *selected_partition.protects,
                        *selected_partition.terminal_actions,
                    )))
                    if selected_partition is not None
                    else app.error_protects
                )
                failure_unknown_causes = (
                    tuple(dict.fromkeys((
                        *(
                            cause
                            for cause in app.failure_unknown_causes
                            if "unresolved_identity:" in cause
                        ),
                        *(
                            (
                                "selected_error_partition_residual_identity_unproven",
                            )
                            if _selected_partition_needs_identity_proof(
                                selected_partition
                            )
                            else ()
                        ),
                        *(
                            f"{app.function_name}: {cause}"
                            for cause in selected_partition.unknown_causes
                        ),
                    )))
                    if selected_partition is not None
                    else app.failure_unknown_causes
                )
                reaching_effects.extend(
                    effect
                    for effect in failure_opens
                    if not _is_runtime_progress_effect(effect)
                )
                out_of_scope_effects.extend(
                    effect
                    for effect in failure_opens
                    if _is_runtime_progress_effect(effect)
                )
                cancellations.extend(failure_cancels)
                protections.extend(failure_protects)
                if failure_unknown_causes:
                    identity_diagnostics = tuple(
                        cause
                        for cause in failure_unknown_causes
                        if cause
                        == "selected_error_partition_residual_identity_unproven"
                    )
                    state_unknowns = tuple(
                        cause
                        for cause in failure_unknown_causes
                        if cause not in identity_diagnostics
                    )
                    diagnostic_blockers.extend(identity_diagnostics)
                    unknown_causes.extend(state_unknowns)
                    unknown_influences.extend(
                        _influences_for_app(
                            app,
                            state_unknowns,
                            phase="failure_call",
                        )
                    )
                    unknown_influences.extend(
                        _influences_for_app(
                            app,
                            identity_diagnostics,
                            phase="proof_diagnostic",
                        )
                    )
                continue
            if (
                app.block_id in reaching_blocks
                and app.site.line <= point.call_site.line
                and not transfer_order_unknown
            ):
                reaching_effects.extend(
                    effect
                    for effect in app.opens
                    if not _is_runtime_progress_effect(effect)
                )
                out_of_scope_effects.extend(
                    effect
                    for effect in app.opens
                    if _is_runtime_progress_effect(effect)
                )
                cancellations.extend(app.cancels_before_failure)
                protections.extend(app.protects_before_failure)
            if app.block_id in error_blocks and app.site.line >= point.check_site.line:
                if app.block_id in must_error_blocks:
                    cancellations.extend(app.cancels)
                    protections.extend(app.protects)
                    must_owner_teardowns.extend(app.owner_teardowns)
                elif app.cancels or app.protects:
                    cause = (
                        "conditional helper cancellation/protection not proven: "
                        f"{app.function_name}"
                    )
                    unknown_influences.append(
                        _UnknownInfluence(
                            cause,
                            app.site,
                            "conditional_cleanup",
                            app.cancels + app.protects,
                        )
                    )
            if app.unknown and (
                app.block_id in reaching_blocks and app.site.line <= point.call_site.line
            ):
                unknown_causes.extend(app.unknown_causes)
                unknown_influences.extend(
                    _influences_for_app(app, app.unknown_causes, phase="reaching")
                )
            elif transfer_order_unknown and (
                app.opens or app.cancels or app.protects
            ):
                cause = f"{app.function_name}: callee_failure_effect_order_unknown"
                unknown_causes.append(cause)
                unknown_influences.extend(
                    _influences_for_app(app, (cause,), phase="failure_call")
                )
            elif app.unknown and app.block_id in error_blocks:
                error_path_unknown_causes.extend(app.unknown_causes)
                unknown_influences.extend(
                    _influences_for_app(app, app.unknown_causes, phase="error_path")
                )

        reaching_effects = [effect_with_visibility(effect) for effect in reaching_effects]
        protections.extend(
            _aborted_transaction_protections(
                tuple(reaching_effects),
                tuple(cancellations),
            )
        )
        cancellations.extend(
            aggregate_snapshot_restore_cancellations(
                function,
                cfg,
                reaching_effects=tuple(reaching_effects),
                failure_line=point.call_site.line,
                check_line=point.check_site.line,
                must_error_blocks=must_error_blocks,
            )
        )
        normalized = normalize_residuals(tuple(reaching_effects), tuple(cancellations), tuple(protections))
        if reaching_effects:
            path_influences = _unknown_calls_on_path(
                    function,
                    cfg,
                    summaries,
                    error_blocks,
                    point.check_site.line,
                    known_error_path_effect_sites,
                )
            unknown_influences.extend(path_influences)
            error_path_unknown_causes.extend(
                influence.cause for influence in path_influences
            )
            unknown_causes.extend(error_path_unknown_causes)
        residuals = normalized.residuals
        lifecycle_unsafe_lines = _lifecycle_events_reachable_on_failure(
            cfg,
            local_lifecycles,
            point,
            error_blocks,
        )
        owner_teardown_proofs = _owner_teardown_proofs(
            tuple(residuals),
            tuple(must_owner_teardowns),
            point,
            local_lifecycles,
            ownership_edges,
            lifecycle_unsafe_lines,
        )
        owner_closed_effects = {
            effect
            for proof in owner_teardown_proofs
            for effect in proof.closed_effects
        }
        residuals = tuple(
            effect for effect in residuals if effect not in owner_closed_effects
        )
        owner_scope_reviews = _owner_scope_review_blockers(
            tuple(residuals),
            tuple(must_owner_teardowns),
            owner_teardown_proofs,
            local_lifecycles,
            lifecycle_unsafe_lines,
        )
        containment_candidates = tuple(residuals)
        certain_residuals = tuple(
            effect
            for effect in residuals
            if not any(
                _unknown_influence_blocks_effect(function, influence, effect)
                for influence in unknown_influences
            )
        )
        blocking_causes = sorted({
            influence.cause
            for influence in unknown_influences
            if any(
                _unknown_influence_blocks_effect(function, influence, effect)
                for effect in residuals
            )
        })
        if certain_residuals:
            residuals = certain_residuals
            unknown_causes = []
        elif residuals:
            unknown_causes = blocking_causes or unknown_causes
        demand_requests = _demand_summary_requests(
            function,
            point,
            tuple(unknown_influences),
            tuple(residuals),
        )
        containment_proofs = _explicit_failure_domain_proofs(
            tuple(reaching_effects),
            tuple(cancellations),
            tuple(protections),
            containment_candidates,
        )
        conditional_shutdown_reviews = _conditional_shutdown_review_blockers(
            tuple(dict.fromkeys((*reaching_effects, *protections))),
            tuple(cancellations),
            containment_candidates,
        )
        containment_covered = {
            effect
            for proof in containment_proofs
            for effect in proof.covered_effects
        }
        if (
            residuals
            and point.check_kind.startswith(("eq:", "ne:"))
            and not exact_partition_complete
            and not all(effect in containment_covered for effect in residuals)
        ):
            diagnostic_blockers.append(
                "exact_return_code_residual_identity_unproven"
            )
        state = (
            ResidualState.UNKNOWN
            if unknown_causes
            else ResidualState.CONTAINED
            if residuals and all(effect in containment_covered for effect in residuals)
            else ResidualState.EXPOSED
            if residuals
            else ResidualState.PROTECTED
            if normalized.protected
            else ResidualState.CLOSED
        )
        exit_site = point.error_edge.exit_site
        scope_proofs = owner_scope_proofs(function, owner_teardown_proofs)
        slices.append(
            ResidualSlice(
                failure_site=point.call_site,
                reaching_effects=tuple(reaching_effects),
                cancellations=tuple(cancellations),
                protections=tuple(protections),
                residuals=tuple(residuals),
                state=state,
                exit_site=exit_site,
                rationale=_rationale(state, residuals, unknown_causes),
                out_of_scope_effects=tuple(out_of_scope_effects),
                containment_proofs=containment_proofs,
                owner_teardown_proofs=owner_teardown_proofs,
                owner_scope_proofs=scope_proofs,
                demand_summary_requests=demand_requests,
                lexical_suppressions=extraction.lexical_suppressions,
                semantic_blockers=tuple(
                    sorted(
                        {
                            *unknown_causes,
                            *diagnostic_blockers,
                            *owner_scope_reviews,
                            *conditional_shutdown_reviews,
                        }
                    )
                ),
            )
        )
        all_unknown_causes.extend(unknown_causes)

    return ResidualSlicingResult(
        function=function.name,
        slices=tuple(slices),
        unknown_causes=tuple(sorted(set(all_unknown_causes))),
    )


_OPEN_DELTAS = {
    MetadataDelta.ADD,
    MetadataDelta.SET,
    MetadataDelta.INC,
    MetadataDelta.RESERVE,
}
_CANCEL_DELTAS = {
    MetadataDelta.REMOVE,
    MetadataDelta.CLEAR,
    MetadataDelta.DEC,
    MetadataDelta.RELEASE,
    MetadataDelta.CLOSE,
}
_PROTECT_DELTAS = {MetadataDelta.PROTECT}
_RUNTIME_PROGRESS_KINDS = {
    EffectProvenanceKind.PROGRESS_CURSOR,
    EffectProvenanceKind.RETRY_STATE,
}


@dataclass(frozen=True)
class _LocatedEffect:
    effect: MetadataEffect
    block_id: int | None


@dataclass(frozen=True)
class _ErrorPathReachability:
    reachable: set[int]
    must_execute: set[int]


@dataclass(frozen=True)
class _UnknownInfluence:
    cause: str
    site: SourceSite
    phase: str
    conditional_effects: tuple[MetadataEffect, ...] = ()


@dataclass(frozen=True)
class _SummaryApp:
    function_name: str
    block_id: int | None
    site: SourceSite
    opens: tuple[MetadataEffect, ...]
    cancels: tuple[MetadataEffect, ...]
    protects: tuple[MetadataEffect, ...]
    error_opens: tuple[MetadataEffect, ...]
    error_cancels: tuple[MetadataEffect, ...]
    error_protects: tuple[MetadataEffect, ...]
    unknown: bool
    unknown_causes: tuple[str, ...]
    failure_unknown: bool
    failure_unknown_causes: tuple[str, ...]
    failure_effects_complete: bool
    may_fail: bool
    has_ownership_transfer: bool
    lifecycle_facts: tuple[LifecycleFact, ...]
    owner_teardowns: tuple[OwnerTeardown, ...]
    error_exit_partitions: tuple[ErrorExitPartition, ...]
    error_partitions_exhaustive: bool

    @property
    def cancels_before_failure(self) -> tuple[MetadataEffect, ...]:
        return self.cancels

    @property
    def protects_before_failure(self) -> tuple[MetadataEffect, ...]:
        return self.protects


def _summary_applications(
    function: FunctionIR,
    cfg: ControlFlowGraphIR,
    summaries: dict[str, FunctionSummary],
) -> Iterable[_SummaryApp]:
    if function.body_node is None:
        return
    for node in function.body_node.walk():
        if node.type != "call_expression":
            continue
        app = apply_same_file_summary(
            summaries,
            node,
            return_lvalue=_return_lvalue_for_call(function, node),
        )
        if app is None:
            continue
        block = _block_for_node(cfg, node)
        site = SourceSite(function.file.as_posix(), node.start_line, compact_ws(node.text))
        unknown_causes: list[str] = []
        unknown_causes.extend(
            f"{app.summary.function_name}: {cause}"
            for cause in app.summary.unknown_causes
        )
        unknown_causes.extend(
            f"{app.summary.function_name}: unresolved_identity: {item}"
            for item in app.unresolved_identities
        )
        failure_unknown_causes: list[str] = []
        failure_unknown_causes.extend(
            f"{app.summary.function_name}: unresolved_identity: {item}"
            for item in app.unresolved_identities
        )
        if app.summary.has_ownership_transfer or app.summary.may_fail:
            failure_unknown_causes.extend(
                f"{app.summary.function_name}: {cause}"
                for cause in app.exit_effects.unknown_causes
            )
        if (
            not app.exit_effects.error_complete
            and app.summary.may_fail
            and app.exit_effects.error_may
        ):
            failure_unknown_causes.append(
                f"{app.summary.function_name}: callee_failure_effect_order_unknown"
            )
            if app.summary.has_ownership_transfer and app.lifecycle_facts:
                failure_unknown_causes.append(
                    f"{app.summary.function_name}: lifecycle_exit_partition_unproven"
                )
                if any(
                    fact.event is LifecycleEvent.PUBLISHED
                    and fact.exit is LifecycleExit.SUCCESS
                    for fact in app.lifecycle_facts
                ):
                    failure_unknown_causes.append(
                        f"{app.summary.function_name}: success_only_publication_not_proven_on_error"
                    )
        transfer_is_caller_owned = _transfer_roots_are_caller_owned(
            function,
            app.ownership_transfer_roots,
        )
        opens = _in_scope_summary_effects(function, app.opens)
        cancels = _in_scope_summary_effects(function, app.cancels)
        protects = _in_scope_summary_effects(function, app.protects)
        error_opens = _in_scope_summary_effects(function, app.error_opens)
        error_cancels = _in_scope_summary_effects(function, app.error_cancels)
        error_protects = _in_scope_summary_effects(function, app.error_protects)
        error_opens = _drop_unexposed_fresh_error_effects(error_opens)
        error_cancels = _drop_unexposed_fresh_error_effects(error_cancels)
        error_protects = _drop_unexposed_fresh_error_effects(error_protects)
        error_exit_partitions = tuple(
            _partition_at_application_site(
                partition,
                function,
                site,
                app.summary.function_name,
            )
            for partition in app.error_exit_partitions
        )
        opens = _effects_at_application_site(opens, site, app.summary.function_name)
        cancels = _effects_at_application_site(cancels, site, app.summary.function_name)
        protects = _effects_at_application_site(
            protects,
            site,
            app.summary.function_name,
        )
        error_opens = _effects_at_application_site(
            error_opens,
            site,
            app.summary.function_name,
        )
        error_cancels = _effects_at_application_site(
            error_cancels,
            site,
            app.summary.function_name,
        )
        error_protects = _effects_at_application_site(
            error_protects,
            site,
            app.summary.function_name,
        )
        if app.ownership_transfer_roots and not transfer_is_caller_owned:
            opens = ()
            cancels = ()
            protects = ()
            error_opens = ()
            error_cancels = ()
            error_protects = ()
            error_exit_partitions = tuple(
                replace(
                    partition,
                    opens=(),
                    cancels=(),
                    protects=(),
                    residuals=(),
                    terminal_actions=(),
                )
                for partition in error_exit_partitions
            )
        yield _SummaryApp(
            function_name=app.summary.function_name,
            block_id=block.id if block is not None else None,
            site=site,
            opens=opens,
            cancels=cancels,
            protects=protects,
            error_opens=error_opens,
            error_cancels=error_cancels,
            error_protects=error_protects,
            unknown=app.unknown,
            unknown_causes=tuple(unknown_causes),
            failure_unknown=bool(failure_unknown_causes),
            failure_unknown_causes=tuple(failure_unknown_causes),
            failure_effects_complete=app.exit_effects.error_complete,
            may_fail=app.summary.may_fail,
            has_ownership_transfer=(
                app.summary.has_ownership_transfer and transfer_is_caller_owned
            ),
            lifecycle_facts=app.lifecycle_facts,
            owner_teardowns=tuple(
                replace(
                    teardown,
                    teardown_site=site,
                    via_function=app.summary.function_name,
                    evidence=(
                        f"{site.expression} via {app.summary.function_name}: "
                        f"{teardown.evidence}"
                    ),
                )
                for teardown in app.owner_teardowns
            ),
            error_exit_partitions=error_exit_partitions,
            error_partitions_exhaustive=app.error_partitions_exhaustive,
        )


def _drop_summarized_name_inferred_call_effects(
    local_effects: tuple[_LocatedEffect, ...],
    call_apps: tuple[_SummaryApp, ...],
) -> tuple[_LocatedEffect, ...]:
    summarized_sites = {
        (app.site.line, compact_ws(app.site.expression))
        for app in call_apps
    }
    return tuple(
        item
        for item in local_effects
        if not (
            item.effect.evidence is EffectEvidence.NAME_INFERRED
            and (
                item.effect.site.line,
                compact_ws(item.effect.site.expression),
            )
            in summarized_sites
            and not _retain_summarized_lifecycle_marker(
                item,
                local_effects,
                call_apps,
            )
        )
    )


def _retain_summarized_lifecycle_marker(
    item: _LocatedEffect,
    local_effects: tuple[_LocatedEffect, ...],
    call_apps: tuple[_SummaryApp, ...],
) -> bool:
    effect = item.effect
    prior = tuple(
        candidate.effect
        for candidate in local_effects
        if candidate.effect.site.line <= effect.site.line
    )
    if effect.delta is MetadataDelta.RELEASE:
        prior_summary_opens = tuple(
            candidate
            for app in call_apps
            if app.site.line <= effect.site.line
            for candidate in app.opens
        )
        return any(
            candidate.delta is MetadataDelta.RESERVE
            and effects_cancel(candidate, effect)
            for candidate in (*prior, *prior_summary_opens)
        )
    if effect.delta is not MetadataDelta.CLOSE or re.search(
        r"(?:^|_)(?:trans|transaction)(?:_|$)",
        effect.key.lower(),
    ) is None:
        return False
    return any(
        candidate.delta is MetadataDelta.SET
        and candidate.evidence is EffectEvidence.DIRECT_SOURCE
        and effects_cancel(candidate, effect)
        for candidate in prior
    )


def _selected_partition_proves_success_only_effects(
    partition: ErrorExitPartition | None,
    app: _SummaryApp,
) -> bool:
    """Use a non-failing summary only to remove source-proven success effects."""

    selected_is_empty = (
        partition is not None
        and partition.complete
        and not _selected_partition_opens(partition)
    )
    every_error_exit_is_empty = bool(app.error_exit_partitions) and all(
        item.complete and not _selected_partition_opens(item)
        for item in app.error_exit_partitions
    )
    opens_are_success_markers = bool(app.opens) and all(
        effect.delta is MetadataDelta.ADD
        and effect.evidence is EffectEvidence.NAME_INFERRED
        for effect in app.opens
    )
    return opens_are_success_markers and (
        selected_is_empty or every_error_exit_is_empty
    )


def _is_failure_call_application(app: _SummaryApp, point: FailurePoint) -> bool:
    return (
        app.site.line == point.call_site.line
        and compact_ws(app.site.expression) == compact_ws(point.call_site.expression)
    )


def _partition_at_application_site(
    partition: ErrorExitPartition,
    function: FunctionIR,
    site: SourceSite,
    callee: str,
) -> ErrorExitPartition:
    def project(effects: tuple[MetadataEffect, ...]) -> tuple[MetadataEffect, ...]:
        in_scope = _in_scope_summary_effects(function, effects)
        in_scope = _drop_unexposed_fresh_error_effects(in_scope)
        return _effects_at_application_site(in_scope, site, callee)

    return replace(
        partition,
        opens=project(partition.opens),
        cancels=project(partition.cancels),
        protects=project(partition.protects),
        residuals=project(partition.residuals),
        terminal_actions=project(partition.terminal_actions),
    )


def _select_exact_error_partition(
    partitions: tuple[ErrorExitPartition, ...],
    point: FailurePoint,
    *,
    exhaustive: bool,
) -> ErrorExitPartition | None:
    """Select one source-proven callee exit, or preserve aggregate MUST semantics."""

    if not exhaustive or not partitions:
        return None
    classifications = tuple(
        _partition_matches_failure_check(partition, point)
        for partition in partitions
    )
    if any(value is None for value in classifications):
        return None
    matches = tuple(
        partition
        for partition, matches in zip(partitions, classifications)
        if matches
    )
    if len(matches) != 1 or not matches[0].complete:
        return None
    return matches[0]


def _partition_matches_failure_check(
    partition: ErrorExitPartition,
    point: FailurePoint,
) -> bool | None:
    constraint = partition.return_constraint
    if constraint in {"IS_ERR", "IS_ERR_OR_NULL", "IS_ERR_VALUE"}:
        if point.check_kind not in {"IS_ERR", "IS_ERR_OR_NULL", "IS_ERR_VALUE"}:
            return None
        return point.error_edge.kind != "false"
    if constraint == "NEGATIVE":
        value = "-1"
    elif constraint.startswith("EXACT:"):
        value = constraint[6:]
    else:
        value = _partition_return_value(partition.return_expression)
    if value is None:
        return None
    check_kind = point.check_kind
    predicate_true = point.error_edge.kind != "false"
    if check_kind == "nonzero":
        result = _constant_not_equal(value, "0")
    elif check_kind.startswith("eq:"):
        result = _constant_equal(value, check_kind[3:])
    elif check_kind.startswith("ne:"):
        equal = _constant_equal(value, check_kind[3:])
        result = None if equal is None else not equal
    elif check_kind in {"<0", "<=0", ">0", ">=0"}:
        result = _constant_order_test(value, check_kind)
    elif check_kind in {"0<", "0<=", "0>", "0>="}:
        reverse = {"0<": ">0", "0<=": ">=0", "0>": "<0", "0>=": "<=0"}
        result = _constant_order_test(value, reverse[check_kind])
    else:
        return None
    if result is None:
        return None
    return result if predicate_true else not result


def _selected_partition_opens(
    partition: ErrorExitPartition,
) -> tuple[MetadataEffect, ...]:
    """Expose selected branch-local opens only when branch evidence can resolve them."""

    return partition.opens


def _selected_partition_needs_identity_proof(
    partition: ErrorExitPartition,
) -> bool:
    return bool(
        partition.opens
        and not partition.cancels
        and not partition.protects
        and not partition.terminal_actions
    )


def _partition_return_value(expression: str) -> str | None:
    value = compact_ws(expression).strip()
    while value.startswith("(") and value.endswith(")"):
        value = value[1:-1].strip()
    name, args = call_name_and_args(value)
    if name in {"ERR_PTR", "PTR_ERR"} and len(args) == 1:
        value = compact_ws(args[0]).strip("() ")
    if value in {"NULL", "0L", "0UL"}:
        return "0"
    return value if re.fullmatch(r"-?(?:[A-Z_]\w*|\d+)", value) else None


def _constant_equal(left: str, right: str) -> bool | None:
    left_value = _partition_return_value(left)
    right_value = _partition_return_value(right)
    if left_value is None or right_value is None:
        return None
    return left_value == right_value


def _constant_not_equal(left: str, right: str) -> bool | None:
    equal = _constant_equal(left, right)
    return None if equal is None else not equal


def _constant_order_test(value: str, operation: str) -> bool | None:
    numeric = _signed_constant_value(value)
    if numeric is None:
        return None
    return {
        "<0": numeric < 0,
        "<=0": numeric <= 0,
        ">0": numeric > 0,
        ">=0": numeric >= 0,
    }[operation]


def _signed_constant_value(value: str) -> int | None:
    normalized = _partition_return_value(value)
    if normalized is None:
        return None
    if re.fullmatch(r"-\d+", normalized):
        return int(normalized)
    if normalized.isdigit():
        return int(normalized)
    if re.fullmatch(r"-[A-Z_]\w*", normalized):
        return -1
    return None


def _drop_unexposed_fresh_error_effects(
    effects: tuple[MetadataEffect, ...],
) -> tuple[MetadataEffect, ...]:
    exposed = _fresh_identities_exposed_by_effects(effects)
    return tuple(
        effect
        for effect in effects
        if not _fresh_identity_tokens(effect) - exposed
    )


def _fresh_identities_exposed_by_effects(
    effects: tuple[MetadataEffect, ...],
) -> set[str]:
    exposed: set[str] = set()
    for effect in effects:
        if effect.delta is MetadataDelta.ADD:
            root_tokens = _fresh_tokens(effect.root)
            value_tokens = _fresh_tokens(effect.value)
            if value_tokens and not root_tokens:
                exposed.update(value_tokens)
        elif effect.delta is MetadataDelta.SET:
            root_tokens = _fresh_tokens(effect.root)
            value_tokens = _fresh_tokens(effect.value)
            if value_tokens and not root_tokens:
                exposed.update(value_tokens)
    return exposed


def _fresh_identity_tokens(effect: MetadataEffect) -> set[str]:
    return (
        _fresh_tokens(effect.root)
        | _fresh_tokens(effect.key)
        | _fresh_tokens(effect.value)
    )


def _fresh_tokens(text: str) -> set[str]:
    return set(re.findall(r"\b__fresh_[A-Za-z0-9_]+__\b", text))


def _in_scope_summary_effects(
    function: FunctionIR,
    effects: tuple[MetadataEffect, ...],
) -> tuple[MetadataEffect, ...]:
    return tuple(
        effect
        for effect in effects
        if not effect_targets_transient_object(function, effect)
    )


def _transfer_roots_are_caller_owned(
    function: FunctionIR,
    roots: tuple[str, ...],
) -> bool:
    if not roots:
        return True
    local_symbols = _caller_local_symbols(function)
    return all(
        (symbol := _leading_symbol(root)) and symbol not in local_symbols
        for root in roots
    )


def _caller_local_symbols(function: FunctionIR) -> set[str]:
    if function.body_node is None:
        return set()
    symbols: set[str] = set()
    declarator_types = {
        "array_declarator",
        "attributed_declarator",
        "identifier",
        "init_declarator",
        "parenthesized_declarator",
        "pointer_declarator",
    }
    for node in function.body_node.walk():
        if node.type == "declaration":
            declarators = tuple(
                child
                for child in node.children
                if child.type in declarator_types
            )
            if not declarators:
                declarator = node.child_by_field_name("declarator")
                declarators = (declarator,) if declarator is not None else ()
            for declarator in declarators:
                name = _declarator_name(declarator)
                if name:
                    symbols.add(name)
        elif node.type == "call_expression":
            name, args = call_name_and_args(compact_ws(node.text))
            if name in {"LIST_HEAD", "HLIST_HEAD"} and args:
                symbol = compact_ws(args[0])
                if re.fullmatch(r"[A-Za-z_]\w*", symbol):
                    symbols.add(symbol)
    return symbols - set(function.parameters)


def _leading_symbol(path: str) -> str:
    match = re.match(r"^([A-Za-z_]\w*)", compact_ws(path).lstrip("&*()"))
    return match.group(1) if match else ""


def _unknown_calls_on_path(
    function: FunctionIR,
    cfg: ControlFlowGraphIR,
    summaries: dict[str, FunctionSummary],
    block_ids: set[int],
    min_line: int,
    known_error_path_effect_sites: set[tuple[int, str]],
) -> tuple[_UnknownInfluence, ...]:
    if function.body_node is None:
        return ()
    influences: list[_UnknownInfluence] = []
    for node in function.body_node.walk():
        if node.type != "call_expression":
            continue
        block = _block_for_node(cfg, node)
        if block is None or block.id not in block_ids or node.start_line < min_line:
            continue
        site_key = (node.start_line, compact_ws(node.text))
        if site_key in known_error_path_effect_sites:
            continue
        expression = compact_ws(node.text)
        name, _ = call_name_and_args(expression)
        site = SourceSite(function.file.as_posix(), node.start_line, expression)
        if name in summaries:
            continue
        callee_node = node.child_by_field_name("function")
        if callee_node is not None and callee_node.type != "identifier":
            influences.append(
                _UnknownInfluence(
                    f"indirect call on error path: {expression}",
                    site,
                    "error_path",
                )
            )
        elif _looks_like_metadata_helper(name):
            influences.append(
                _UnknownInfluence(
                    f"unresolved metadata helper on error path: {name}",
                    site,
                    "error_path",
                )
            )
    return tuple(influences)


def _influences_for_app(
    app: _SummaryApp,
    causes: tuple[str, ...],
    *,
    phase: str,
) -> tuple[_UnknownInfluence, ...]:
    return tuple(
        _UnknownInfluence(
            cause,
            app.site,
            (
                "conditional_cleanup"
                if cause.endswith(": unbound_callee_local_identity")
                else phase
            ),
            (
                app.cancels + app.protects
                if cause.endswith(": unbound_callee_local_identity")
                else ()
            ),
        )
        for cause in causes
    )


def _effects_at_application_site(
    effects: tuple[MetadataEffect, ...],
    site: SourceSite,
    callee_name: str,
) -> tuple[MetadataEffect, ...]:
    return tuple(
        replace(
            effect,
            site=SourceSite(
                site.file,
                site.line,
                f"{site.expression} via {callee_name}: {effect.site.expression}",
            ),
        )
        for effect in effects
    )


def _unknown_influence_blocks_effect(
    function: FunctionIR,
    influence: _UnknownInfluence,
    effect: MetadataEffect,
) -> bool:
    """Return whether an unknown call can still invalidate one residual.

    A source-visible effect performed after a reaching unknown cannot have
    been cancelled by that earlier call.  In every other case the helper is
    conservatively allowed to affect the residual.  This deliberately avoids
    treating shallow argument-root mismatch as a proof of non-aliasing.

    A cancellation or protection that is reachable but does not dominate all
    feasible error exits is a separate kind of uncertainty. It blocks only a
    residual it can actually cancel or protect; unrelated conditional cleanup
    must not downgrade a source-proven residual.
    """

    if influence.phase == "proof_diagnostic":
        return False
    if influence.phase == "conditional_cleanup":
        return _conditional_effect_can_affect(
            effect,
            influence.conditional_effects,
        )
    if (
        influence.phase == "reaching"
        and effect.site.file == function.file.as_posix()
        and effect.site.line > influence.site.line
    ):
        return False
    return True


def _conditional_effect_can_affect(
    residual: MetadataEffect,
    conditional_effects: tuple[MetadataEffect, ...],
) -> bool:
    for effect in conditional_effects:
        if (
            residual.delta is MetadataDelta.SET
            and residual.evidence is EffectEvidence.DIRECT_SOURCE
            and effect.delta is MetadataDelta.CLOSE
            and _leading_symbol(residual.root) == _leading_symbol(effect.root)
        ):
            # A conditional owner close is not a MUST cleanup. Retain the
            # source-visible descriptor residual on the path that skips it.
            continue
        if effects_cancel(residual, effect) or effect_protected_by(residual, effect):
            return True
        if is_failure_domain_key(effect.key):
            try:
                kind = FailureDomainKind(effect.value)
            except ValueError:
                kind = None
            if (
                kind is FailureDomainKind.TRANSACTION_ABORT
                and covered_effects_for_action(effect, (residual,))
            ):
                return True
        if not _is_transaction_abort(effect):
            continue
        transaction = _leading_symbol(effect.root)
        if transaction and _effect_mentions_transaction(residual, transaction):
            return True
    return False


def _return_lvalue_for_call(function: FunctionIR, node: FrontendNode) -> str:
    if function.body_node is None:
        return ""
    for parent in function.body_node.walk():
        if parent.type == "assignment_expression":
            right = parent.child_by_field_name("right")
            left = parent.child_by_field_name("left")
            if (
                left is not None
                and right is not None
                and _node_contains(right, node)
            ):
                return compact_ws(left.text)
        if parent.type == "init_declarator":
            value = parent.child_by_field_name("value")
            declarator = parent.child_by_field_name("declarator")
            if value is not None and declarator is not None and _node_contains(value, node):
                name = _declarator_name(declarator)
                if name:
                    return name
    return ""


def _node_contains(parent: FrontendNode, child: FrontendNode) -> bool:
    return parent.start_byte <= child.start_byte and child.end_byte <= parent.end_byte


def _declarator_name(node: FrontendNode | None) -> str:
    if node is None:
        return ""
    if node.type == "identifier":
        return compact_ws(node.text)
    nested = node.child_by_field_name("declarator")
    if nested is not None:
        return _declarator_name(nested)
    identifiers = [child for child in node.walk() if child.type == "identifier"]
    return compact_ws(identifiers[-1].text) if identifiers else ""


def _reverse_reachable(cfg: ControlFlowGraphIR, target: int) -> set[int]:
    pending = [target]
    seen: set[int] = set()
    while pending:
        block_id = pending.pop(0)
        if block_id in seen:
            continue
        seen.add(block_id)
        pending.extend(edge.source for edge in cfg.predecessors(block_id))
    return seen


def _block_dominates(
    cfg: ControlFlowGraphIR,
    dominator: int,
    target: int,
) -> bool:
    nodes = set(cfg.blocks)
    dominators = {
        block_id: ({cfg.entry} if block_id == cfg.entry else set(nodes))
        for block_id in nodes
    }
    changed = True
    while changed:
        changed = False
        for block_id in nodes - {cfg.entry}:
            parents = [edge.source for edge in cfg.predecessors(block_id)]
            updated = (
                {block_id}
                if not parents
                else {block_id}
                | set.intersection(*(dominators[parent] for parent in parents))
            )
            if updated != dominators[block_id]:
                dominators[block_id] = updated
                changed = True
    return dominator in dominators.get(target, set())


def _forward_reachable_until_returns(
    cfg: ControlFlowGraphIR,
    start: int,
    point: FailurePoint,
) -> _ErrorPathReachability:
    pending = [start]
    seen: set[int] = set()
    feasible_edges: set[tuple[int, int]] = set()
    while pending:
        block_id = pending.pop(0)
        if block_id in seen:
            continue
        seen.add(block_id)
        block = cfg.blocks[block_id]
        if block.kind == "return_statement" or block_id == cfg.exit:
            continue
        for edge in cfg.successors(block_id):
            if not _edge_feasible_for_failure(cfg.blocks[block_id], edge.kind, point):
                continue
            feasible_edges.add((edge.source, edge.target))
            pending.append(edge.target)
    terminal_blocks = {
        block_id
        for block_id in seen
        if cfg.blocks[block_id].kind == "return_statement" or block_id == cfg.exit
    }
    if not terminal_blocks:
        return _ErrorPathReachability(seen, set())
    predecessors = {
        block_id: {
            source
            for source, target in feasible_edges
            if target == block_id and source in seen
        }
        for block_id in seen
    }
    dominators = {
        block_id: ({start} if block_id == start else set(seen))
        for block_id in seen
    }
    changed = True
    while changed:
        changed = False
        for block_id in seen - {start}:
            parents = predecessors[block_id]
            if not parents:
                updated = {block_id}
            else:
                updated = {block_id} | set.intersection(
                    *(dominators[parent] for parent in parents)
                )
            if updated != dominators[block_id]:
                dominators[block_id] = updated
                changed = True
    must_execute = set.intersection(
        *(dominators[block_id] for block_id in terminal_blocks)
    )
    return _ErrorPathReachability(seen, must_execute)


def _conditional_effect_cause(effect: MetadataEffect) -> str:
    return (
        "conditional error-path cancellation/protection not proven: "
        f"{effect.site.expression}"
    )


def _edge_feasible_for_failure(
    block: BasicBlockIR,
    edge_kind: str,
    point: FailurePoint,
) -> bool:
    if edge_kind not in {"true", "false"}:
        return True
    result = failure_branch_feasibility(
        result_symbol=point.result_symbol,
        check_kind=point.check_kind,
        condition=compact_ws(block.text),
        branch_kind=edge_kind,
    )
    return result is not SolverResult.UNSAT


def _block_for_site(cfg: ControlFlowGraphIR, site: SourceSite) -> int | None:
    matches = [
        block
        for block in cfg.blocks.values()
        if block.start_line <= site.line <= block.end_line and block.start_line
    ]
    if not matches:
        return None
    exact = [block for block in matches if compact_ws(site.expression) in compact_ws(block.text)]
    chosen = exact or matches
    return min(chosen, key=lambda block: (block.end_line - block.start_line, block.id)).id


def _block_for_node(cfg: ControlFlowGraphIR, node: FrontendNode) -> BasicBlockIR | None:
    matches = [
        block
        for block in cfg.blocks.values()
        if block.start_byte <= node.start_byte and node.end_byte <= block.end_byte and block.start_byte
    ]
    if matches:
        return min(matches, key=lambda block: (block.end_byte - block.start_byte, block.id))
    return cfg.block_at_line(node.start_line)


def _effect_before_failure(effect: MetadataEffect, point: FailurePoint) -> bool:
    return effect.site.line <= point.call_site.line


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


def _known_error_path_effect_sites(
    local_effects: tuple[_LocatedEffect, ...],
) -> set[tuple[int, str]]:
    return {
        (item.effect.site.line, compact_ws(item.effect.site.expression))
        for item in local_effects
        if item.effect.delta in _CANCEL_DELTAS or item.effect.delta in _PROTECT_DELTAS
    }


def _looks_like_metadata_helper(name: str) -> bool:
    if looks_like_metadata_reader(name):
        return False
    lowered = name.lower()
    return any(
        token in lowered
        for token in (
            "inode",
            "dquot",
            "quota",
            "qgroup",
            "trans",
            "journal",
            "orphan",
            "block_rsv",
            "reserv",
            "reloc",
            "root",
            "extent",
            "chunk",
            "device",
        )
    )


def _demand_summary_requests(
    function: FunctionIR,
    point: FailurePoint,
    influences: tuple[_UnknownInfluence, ...],
    residuals: tuple[MetadataEffect, ...],
) -> tuple[DemandSummaryRequest, ...]:
    """Describe the exact missing semantics for residual-blocking calls."""

    if not residuals:
        return ()
    requests: list[DemandSummaryRequest] = []
    report_id = (
        f"{function.name}:{point.call_site.file}:{point.call_site.line}:"
        f"{point.error_edge.exit_site.line}"
    )
    for influence in influences:
        if not any(
            _unknown_influence_blocks_effect(function, influence, effect)
            for effect in residuals
        ):
            continue
        helper, args = call_name_and_args(compact_ws(influence.site.expression))
        if not helper:
            helper = influence.cause.split(":", 1)[0].strip()
        if not helper or helper in {"if", "switch", "return"}:
            continue
        requirement = {
            "failure_call": DemandSummaryRequirement.ERROR_PARTITION,
            "error_path": DemandSummaryRequirement.MUST_CANCEL,
            "conditional_cleanup": DemandSummaryRequirement.MUST_CANCEL,
            "reaching": DemandSummaryRequirement.OWNER_BINDING,
        }.get(influence.phase, DemandSummaryRequirement.OWNER_BINDING)
        expected_root = (
            influence.conditional_effects[0].root
            if influence.conditional_effects
            else compact_ws(args[0]).strip("&() ") if args else residuals[0].root
        )
        requests.append(
            DemandSummaryRequest(
                report_id=report_id,
                helper=helper,
                call_site=influence.site,
                expected_root=expected_root,
                required_semantics=requirement,
                transitive_body_budget=3,
                reason=influence.cause,
            )
        )
    return tuple(dict.fromkeys(requests))


def _rationale(
    state: ResidualState,
    residuals: tuple[MetadataEffect, ...],
    unknown_causes: list[str],
) -> str:
    if state is ResidualState.UNKNOWN:
        return "; ".join(sorted(set(unknown_causes)))
    if state is ResidualState.EXPOSED:
        return f"{len(residuals)} metadata effect(s) remain after error-path normalization"
    if state is ResidualState.CONTAINED:
        return (
            f"{len(residuals)} metadata effect(s) remain at function return, "
            "but an explicit terminal failure domain prevents ordinary continuation"
        )
    if state is ResidualState.PROTECTED:
        return "all reaching metadata effects are explicitly protected"
    return "all reaching metadata effects are cancelled on the error path"
