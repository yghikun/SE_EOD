"""Lightweight same-file function summaries for metadata residual analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import Iterable

from .cancellation import normalize_residuals
from .effect_extractor import extract_metadata_effects, looks_like_metadata_reader
from .failure_domain_primitives import (
    covered_effects_for_action,
    failure_domain_guard,
    failure_domain_key,
    failure_domain_kind,
    is_failure_domain_key,
)
from .cfg import build_cfg
from .failure_points import find_failure_points
from .frontend.model import BasicBlockIR, FrontendNode, FunctionIR
from .metadata_residual import (
    ContainerIterationCleanup,
    EffectEvidence,
    ExistentialMemberIdentity,
    IndirectTargetSet,
    MetadataDelta,
    MetadataEffect,
    MetadataPlane,
    OwnerTeardown,
    PerCpuSlotRelation,
    SourceSite,
    TransactionOwnershipRelation,
)
from .parser import call_name_and_args, compact_ws, extract_return_expr, split_args


class SummarySource(str, Enum):
    AUTO_LOCAL = "AUTO_LOCAL"
    AUTO_INTERPROCEDURAL = "AUTO_INTERPROCEDURAL"
    PINNED_CORE_SUMMARY = "PINNED_CORE_SUMMARY"
    UNKNOWN = "UNKNOWN"


class LifecycleEvent(str, Enum):
    """A source-derived ownership/lifecycle transition."""

    ALLOCATED = "ALLOCATED"
    PUBLISHED = "PUBLISHED"
    RELEASED = "RELEASED"
    PROTECTED = "PROTECTED"


class LifecycleExit(str, Enum):
    ALL = "ALL"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    BOTH = "BOTH"


class ExposureKind(str, Enum):
    FRESH_LOCAL = "FRESH_LOCAL"
    PRIVATE_LOCAL = "PRIVATE_LOCAL"
    BOUND_TO = "BOUND_TO"
    RETURNED = "RETURNED"
    OUTPUT_BOUND = "OUTPUT_BOUND"
    PUBLISHED_IN_FIELD = "PUBLISHED_IN_FIELD"
    MEMBER_OF_CONTAINER = "MEMBER_OF_CONTAINER"


class OwnerIdentityKind(str, Enum):
    """Source form that makes a callee-local owner caller-bindable."""

    PARAM = "PARAM"
    FIELD = "FIELD"
    RETURN = "RETURN"
    OUT_PARAM = "OUT_PARAM"
    FRESH = "FRESH"


@dataclass(frozen=True)
class LifecycleFact:
    subject: str
    owner: str
    event: LifecycleEvent
    exit: LifecycleExit
    site: SourceSite
    evidence: str

    def to_dict(self) -> dict[str, object]:
        return {
            "subject": self.subject,
            "owner": self.owner,
            "event": self.event.value,
            "exit": self.exit.value,
            "site": self.site.to_dict(),
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class ExposureFact:
    local_identity: str
    summary_identity: str
    kind: ExposureKind
    target: str
    site: SourceSite
    evidence: str

    def to_dict(self) -> dict[str, object]:
        return {
            "local_identity": self.local_identity,
            "summary_identity": self.summary_identity,
            "kind": self.kind.value,
            "target": self.target,
            "site": self.site.to_dict(),
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class OwnerIdentityBinding:
    local_identity: str
    kind: OwnerIdentityKind
    summary_identity: str
    bound_identity: str
    site: SourceSite
    evidence: str

    def to_dict(self) -> dict[str, object]:
        return {
            "local_identity": self.local_identity,
            "kind": self.kind.value,
            "summary_identity": self.summary_identity,
            "bound_identity": self.bound_identity,
            "site": self.site.to_dict(),
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class CleanupFootprint:
    root_pattern: str
    key_pattern: str
    plane: MetadataPlane
    inverse_delta: MetadataDelta
    value_pattern: str
    owner_or_container: str
    site: SourceSite
    evidence: str

    def to_dict(self) -> dict[str, object]:
        return {
            "root_pattern": self.root_pattern,
            "key_pattern": self.key_pattern,
            "plane": self.plane.value,
            "inverse_delta": self.inverse_delta.value,
            "value_pattern": self.value_pattern,
            "owner_or_container": self.owner_or_container,
            "site": self.site.to_dict(),
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class LocalLifecycleBinding:
    local_identity: str
    allocation_line: int
    publication_lines: tuple[int, ...]
    allocation_site: SourceSite | None = None
    escape_lines: tuple[int, ...] = ()
    rebind_lines: tuple[int, ...] = ()


@dataclass(frozen=True)
class ExitSensitiveEffects:
    """Source-derived effect coverage across classified function exits."""

    success_must: tuple[MetadataEffect, ...] = ()
    success_may: tuple[MetadataEffect, ...] = ()
    error_must: tuple[MetadataEffect, ...] = ()
    error_may: tuple[MetadataEffect, ...] = ()
    error_complete: bool = False
    unknown_causes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "success_must": [item.to_dict() for item in self.success_must],
            "success_may": [item.to_dict() for item in self.success_may],
            "error_must": [item.to_dict() for item in self.error_must],
            "error_may": [item.to_dict() for item in self.error_may],
            "error_complete": self.error_complete,
            "unknown_causes": list(self.unknown_causes),
        }


@dataclass(frozen=True)
class ErrorExitPartition:
    """Effects that remain correlated on one exact source-visible error exit."""

    exit_site: SourceSite
    return_expression: str
    return_constraint: str = ""
    opens: tuple[MetadataEffect, ...] = ()
    cancels: tuple[MetadataEffect, ...] = ()
    protects: tuple[MetadataEffect, ...] = ()
    residuals: tuple[MetadataEffect, ...] = ()
    terminal_actions: tuple[MetadataEffect, ...] = ()
    failed_owner_destructions: tuple[LifecycleFact, ...] = ()
    path: tuple[SourceSite, ...] = ()
    complete: bool = False
    unknown_causes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "exit_site": self.exit_site.to_dict(),
            "return_expression": self.return_expression,
            "return_constraint": self.return_constraint,
            "opens": [item.to_dict() for item in self.opens],
            "cancels": [item.to_dict() for item in self.cancels],
            "protects": [item.to_dict() for item in self.protects],
            "residuals": [item.to_dict() for item in self.residuals],
            "terminal_actions": [item.to_dict() for item in self.terminal_actions],
            "failed_owner_destructions": [
                item.to_dict() for item in self.failed_owner_destructions
            ],
            "path": [item.to_dict() for item in self.path],
            "complete": self.complete,
            "unknown_causes": list(self.unknown_causes),
        }


OPEN_DELTAS = {
    MetadataDelta.ADD,
    MetadataDelta.SET,
    MetadataDelta.INC,
    MetadataDelta.RESERVE,
}
CANCEL_DELTAS = {
    MetadataDelta.REMOVE,
    MetadataDelta.CLEAR,
    MetadataDelta.DEC,
    MetadataDelta.RELEASE,
    MetadataDelta.CLOSE,
}
PROTECT_DELTAS = {MetadataDelta.PROTECT}
UNKNOWN_CALLS = {
    "call_rcu",
    "queue_work",
    "schedule_work",
    "delayed_work",
    "kthread_run",
}
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
OWNER_DEALLOCATOR_ARGUMENTS = {
    "free_percpu": 0,
    "kfree": 0,
    "kmem_cache_free": 1,
    "kvfree": 0,
    "vfree": 0,
}


@dataclass(frozen=True)
class FunctionSummary:
    function_name: str
    parameters: tuple[str, ...]
    returns: tuple[str, ...]
    fresh_identities: tuple[str, ...]
    has_ownership_transfer: bool
    ownership_transfer_roots: tuple[str, ...]
    returns_fresh_identity: bool
    opens: tuple[MetadataEffect, ...]
    cancels: tuple[MetadataEffect, ...]
    protects: tuple[MetadataEffect, ...]
    output_identities: tuple[str, ...] = ()
    error_opens: tuple[MetadataEffect, ...] = ()
    error_cancels: tuple[MetadataEffect, ...] = ()
    error_protects: tuple[MetadataEffect, ...] = ()
    failure_effects_complete: bool = False
    error_unknown_causes: tuple[str, ...] = ()
    lifecycle_facts: tuple[LifecycleFact, ...] = ()
    exposure_facts: tuple[ExposureFact, ...] = ()
    cleanup_footprints: tuple[CleanupFootprint, ...] = ()
    owner_teardowns: tuple[OwnerTeardown, ...] = ()
    escaping_parameters: tuple[int, ...] = ()
    exit_effects: ExitSensitiveEffects = ExitSensitiveEffects()
    error_exit_partitions: tuple[ErrorExitPartition, ...] = ()
    error_partitions_exhaustive: bool = False
    unresolved_calls: tuple[str, ...] = ()
    source_file: str = ""
    may_fail: bool = False
    unknown_escape: bool = False
    unknown_causes: tuple[str, ...] = ()
    source: SummarySource = SummarySource.UNKNOWN
    owner_bindings: tuple[OwnerIdentityBinding, ...] = ()
    indirect_target_sets: tuple[IndirectTargetSet, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "function_name": self.function_name,
            "parameters": list(self.parameters),
            "returns": list(self.returns),
            "fresh_identities": list(self.fresh_identities),
            "has_ownership_transfer": self.has_ownership_transfer,
            "ownership_transfer_roots": list(self.ownership_transfer_roots),
            "returns_fresh_identity": self.returns_fresh_identity,
            "opens": [item.to_dict() for item in self.opens],
            "cancels": [item.to_dict() for item in self.cancels],
            "protects": [item.to_dict() for item in self.protects],
            "output_identities": list(self.output_identities),
            "error_opens": [item.to_dict() for item in self.error_opens],
            "error_cancels": [item.to_dict() for item in self.error_cancels],
            "error_protects": [item.to_dict() for item in self.error_protects],
            "failure_effects_complete": self.failure_effects_complete,
            "error_unknown_causes": list(self.error_unknown_causes),
            "lifecycle_facts": [item.to_dict() for item in self.lifecycle_facts],
            "exposure_facts": [item.to_dict() for item in self.exposure_facts],
            "cleanup_footprints": [item.to_dict() for item in self.cleanup_footprints],
            "owner_teardowns": [item.to_dict() for item in self.owner_teardowns],
            "escaping_parameters": list(self.escaping_parameters),
            "exit_effects": self.exit_effects.to_dict(),
            "error_exit_partitions": [
                item.to_dict() for item in self.error_exit_partitions
            ],
            "error_partitions_exhaustive": self.error_partitions_exhaustive,
            "unresolved_calls": list(self.unresolved_calls),
            "source_file": self.source_file,
            "may_fail": self.may_fail,
            "unknown_escape": self.unknown_escape,
            "unknown_causes": list(self.unknown_causes),
            "source": self.source.value,
            "owner_bindings": [item.to_dict() for item in self.owner_bindings],
            "indirect_target_sets": [
                item.to_dict() for item in self.indirect_target_sets
            ],
        }


@dataclass(frozen=True)
class SummaryApplication:
    summary: FunctionSummary
    opens: tuple[MetadataEffect, ...]
    cancels: tuple[MetadataEffect, ...]
    protects: tuple[MetadataEffect, ...]
    error_opens: tuple[MetadataEffect, ...] = ()
    error_cancels: tuple[MetadataEffect, ...] = ()
    error_protects: tuple[MetadataEffect, ...] = ()
    failure_effects_complete: bool = False
    error_unknown_causes: tuple[str, ...] = ()
    lifecycle_facts: tuple[LifecycleFact, ...] = ()
    exposure_facts: tuple[ExposureFact, ...] = ()
    cleanup_footprints: tuple[CleanupFootprint, ...] = ()
    owner_teardowns: tuple[OwnerTeardown, ...] = ()
    exit_effects: ExitSensitiveEffects = ExitSensitiveEffects()
    error_exit_partitions: tuple[ErrorExitPartition, ...] = ()
    error_partitions_exhaustive: bool = False
    returns: tuple[str, ...] = ()
    unresolved_identities: tuple[str, ...] = ()
    ownership_transfer_roots: tuple[str, ...] = ()
    owner_bindings: tuple[OwnerIdentityBinding, ...] = ()
    indirect_target_sets: tuple[IndirectTargetSet, ...] = ()

    @property
    def unknown(self) -> bool:
        return bool(self.unresolved_identities) or bool(self.summary.unknown_causes)

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary.to_dict(),
            "opens": [item.to_dict() for item in self.opens],
            "cancels": [item.to_dict() for item in self.cancels],
            "protects": [item.to_dict() for item in self.protects],
            "error_opens": [item.to_dict() for item in self.error_opens],
            "error_cancels": [item.to_dict() for item in self.error_cancels],
            "error_protects": [item.to_dict() for item in self.error_protects],
            "failure_effects_complete": self.failure_effects_complete,
            "error_unknown_causes": list(self.error_unknown_causes),
            "lifecycle_facts": [item.to_dict() for item in self.lifecycle_facts],
            "exposure_facts": [item.to_dict() for item in self.exposure_facts],
            "cleanup_footprints": [item.to_dict() for item in self.cleanup_footprints],
            "owner_teardowns": [item.to_dict() for item in self.owner_teardowns],
            "exit_effects": self.exit_effects.to_dict(),
            "error_exit_partitions": [
                item.to_dict() for item in self.error_exit_partitions
            ],
            "error_partitions_exhaustive": self.error_partitions_exhaustive,
            "returns": list(self.returns),
            "unresolved_identities": list(self.unresolved_identities),
            "ownership_transfer_roots": list(self.ownership_transfer_roots),
            "owner_bindings": [item.to_dict() for item in self.owner_bindings],
            "indirect_target_sets": [
                item.to_dict() for item in self.indirect_target_sets
            ],
            "unknown": self.unknown,
        }


def build_function_summary(
    function: FunctionIR,
    *,
    fresh_return_helpers: set[str] | None = None,
) -> FunctionSummary:
    """Generate an AUTO_LOCAL summary for one visible helper body."""

    parameters = _ordered_parameters(function)
    local_symbols = _local_symbols(function)
    pointer_locals = _local_pointer_symbols(function)
    owner_aliases = _parameter_derived_owner_aliases(
        function,
        parameters,
        pointer_locals,
    )
    direct_owner_aliases = _direct_owner_identity_aliases(
        function,
        parameters,
        pointer_locals,
        owner_aliases,
    )
    return_symbols = _success_return_symbols(function, pointer_locals)
    raw_effects = _bind_percpu_slot_effects(
        function,
        tuple(extract_metadata_effects(function)),
        parameters,
        local_symbols,
        pointer_locals,
    )
    raw_effects = _bind_exhaustive_container_cleanups(
        function,
        raw_effects,
        parameters,
        pointer_locals,
    )
    raw_effects = _bind_existential_member_identities(
        function,
        raw_effects,
        pointer_locals,
    )
    fresh_allocation_lines = _direct_fresh_allocation_lines(
        function,
        pointer_locals,
        fresh_return_helpers or set(),
    )
    transfer_mapping = _ownership_transfer_mapping(
        function,
        raw_effects,
        parameters,
        pointer_locals,
        fresh_return_helpers or set(),
        owner_aliases,
    )
    output_mapping = _output_transfer_mapping(
        function,
        parameters,
        pointer_locals,
        fresh_allocation_lines,
    )
    return_field_output_mapping = _return_field_output_mapping(
        function,
        parameters,
        return_symbols,
    )
    transfer_mapping = {
        **transfer_mapping,
        **output_mapping,
        **return_field_output_mapping,
    }
    symbol_mapping = {**owner_aliases, **transfer_mapping}
    owner_symbol_mapping = {
        **owner_aliases,
        **direct_owner_aliases,
        **transfer_mapping,
    }
    owner_bindings = _build_owner_identity_bindings(
        function,
        owner_symbol_mapping,
        return_symbols,
        fresh_allocation_lines,
    )
    exposure_facts = _build_exposure_facts(
        function,
        raw_effects,
        parameters,
        pointer_locals,
        fresh_allocation_lines,
        transfer_mapping,
        return_symbols,
        owner_aliases,
    )
    parameterized_effects = tuple(
        _parameterize_effect(
            effect,
            parameters,
            return_symbols,
            (
                owner_symbol_mapping
                if is_failure_domain_key(effect.key)
                else symbol_mapping
            ),
        )
        for effect in raw_effects
    )
    returns = tuple(
        _replace_symbols(
            item,
            _summary_symbol_mapping(parameters, return_symbols, symbol_mapping),
        )
        for item in _success_return_expressions(function)
    )
    unbound_local_symbols = local_symbols - set(symbol_mapping)
    dropped_effects = tuple(
        effect
        for effect in parameterized_effects
        if _references_unbound_local(effect, unbound_local_symbols)
    )
    bound_effects = tuple(
        effect
        for effect in parameterized_effects
        if effect not in dropped_effects
    )
    effects = tuple(
        effect for effect in bound_effects if not is_failure_domain_key(effect.key)
    )
    private_fresh_locals = set(fresh_allocation_lines) - set(transfer_mapping)
    dropped_unbound_cancellation = any(
        not _references_only_private_fresh(effect, unbound_local_symbols, private_fresh_locals)
        and (
            effect.delta in (CANCEL_DELTAS | PROTECT_DELTAS)
            or is_failure_domain_key(effect.key)
        )
        for effect in dropped_effects
    )
    has_return_bound_effect = any(
        _effect_references_return(effect)
        for effect in effects
    )
    unresolved_helper_names = _unresolved_metadata_helper_names(function, raw_effects)
    unknown_causes: list[str] = []
    unknown_causes.extend(_unknown_escape_causes(function))
    if dropped_unbound_cancellation or _has_unbound_failure_domain_owner(
        function,
        set(parameters),
        local_symbols,
        owner_symbol_mapping,
    ):
        unknown_causes.append("unbound_callee_local_identity")
    if has_return_bound_effect:
        unknown_causes.extend(
            f"return_bound_unresolved_helper: {name}"
            for name in unresolved_helper_names
        )
    opens = tuple(effect for effect in effects if effect.delta in OPEN_DELTAS)
    cancels = tuple(effect for effect in effects if effect.delta in CANCEL_DELTAS)
    protects = tuple(effect for effect in effects if effect.delta in PROTECT_DELTAS)
    exit_effects = _exit_sensitive_effects(function, effects)
    lifecycle_facts = _build_lifecycle_facts(
        function,
        effects,
        exit_effects.error_may,
        transfer_mapping,
        return_symbols,
        fresh_allocation_lines,
    )
    error_exit_partitions = _error_exit_partitions(
        function,
        bound_effects,
        lifecycle_facts,
    )
    error_partitions_exhaustive = _partitions_cover_error_outcomes(
        function,
        error_exit_partitions,
    )
    projected_opens, projected_cancels, projected_protects = (
        _failure_effect_projection(error_exit_partitions, exit_effects)
    )
    cleanup_footprints = tuple(_cleanup_footprint(effect) for effect in cancels)
    owner_teardowns = extract_owner_teardowns(
        function,
        parameterize=True,
        unconditional_only=True,
    )
    transfer_identities = set(transfer_mapping.values())
    ownership_transfer_roots = tuple(sorted({
        effect.root
        for effect in effects
        if (
            effect.delta is MetadataDelta.ADD
            and any(identity in effect.value for identity in transfer_identities)
        ) or (
            effect.delta is MetadataDelta.SET
            and effect.value in transfer_identities
        )
    }))
    return FunctionSummary(
        function_name=function.name,
        parameters=parameters,
        returns=returns,
        fresh_identities=tuple(sorted(
            value
            for value in set(transfer_mapping.values())
            if value.startswith(FRESH_PLACEHOLDER_PREFIX)
        )),
        has_ownership_transfer=bool(transfer_mapping),
        ownership_transfer_roots=ownership_transfer_roots,
        returns_fresh_identity=bool(return_symbols & set(fresh_allocation_lines)),
        opens=opens,
        cancels=cancels,
        protects=protects,
        output_identities=tuple(sorted(
            value
            for value in set(transfer_mapping.values())
            if value.startswith(OUTPUT_PLACEHOLDER_PREFIX)
        )),
        error_opens=projected_opens,
        error_cancels=projected_cancels,
        error_protects=projected_protects,
        failure_effects_complete=error_partitions_exhaustive,
        error_unknown_causes=(
            () if error_partitions_exhaustive else exit_effects.unknown_causes
        ),
        lifecycle_facts=lifecycle_facts,
        exposure_facts=exposure_facts,
        cleanup_footprints=cleanup_footprints,
        owner_teardowns=owner_teardowns,
        exit_effects=exit_effects,
        error_exit_partitions=error_exit_partitions,
        error_partitions_exhaustive=error_partitions_exhaustive,
        unresolved_calls=unresolved_helper_names,
        source_file=function.file.as_posix(),
        may_fail=bool(find_failure_points(function)) or _has_error_return(function),
        unknown_escape=bool(unknown_causes),
        unknown_causes=tuple(sorted(set(unknown_causes))),
        source=SummarySource.AUTO_LOCAL,
        owner_bindings=owner_bindings,
    )


def build_same_file_summaries(
    functions: Iterable[FunctionIR],
    *,
    inherited_summaries: dict[str, FunctionSummary] | None = None,
) -> dict[str, FunctionSummary]:
    """Build summaries for source-visible helpers in one translation unit.

    File-local calls can target both ``static`` helpers and externally visible
    functions defined in the same C file.  Name ambiguity is a project-level
    concern; within one parsed translation unit the visible body is exact.
    """

    function_tuple = tuple(functions)
    directly_called = {
        name
        for caller in function_tuple
        if caller.body_node is not None
        for node in caller.body_node.walk()
        if node.type == "call_expression"
        for name, _ in (call_name_and_args(compact_ws(node.text)),)
    }
    visible_functions = tuple(
        function
        for function in function_tuple
        if function.body_node is not None
        and (_is_static_function(function) or function.name in directly_called)
    )
    inherited = inherited_summaries or {}
    fresh_return_helpers: set[str] = {
        name for name, summary in inherited.items() if summary.returns_fresh_identity
    }
    summaries: dict[str, FunctionSummary] = {}
    for _ in range(3):
        summaries = {
            function.name: build_function_summary(
                function,
                fresh_return_helpers=fresh_return_helpers,
            )
            for function in visible_functions
        }
        discovered = {
            name
            for name, summary in summaries.items()
            if summary.returns_fresh_identity
        }
        if discovered <= fresh_return_helpers:
            break
        fresh_return_helpers.update(discovered)
    summaries = _resolve_source_visible_cleanup_direct_summaries(
        summaries,
        function_tuple,
        inherited_summaries=inherited,
    )
    summaries = _resolve_source_visible_noop_direct_unknowns(summaries)
    summaries = _refine_parameter_escapes(
        summaries,
        function_tuple,
        inherited_summaries=inherited,
    )
    summaries = _compose_source_visible_owner_teardowns(
        summaries,
        function_tuple,
        inherited_summaries=inherited,
    )
    summaries = _compose_source_visible_exit_partitions(
        summaries,
        function_tuple,
        inherited_summaries=inherited,
    )
    summaries = _resolve_bounded_noop_indirect_unknowns(summaries, function_tuple)
    return _attach_indirect_target_sets(summaries, function_tuple)


def build_project_summaries(
    functions: Iterable[FunctionIR],
    *,
    max_depth: int = 3,
) -> dict[str, FunctionSummary]:
    """Build bounded cross-translation-unit summaries for unique external helpers."""

    function_tuple = tuple(functions)
    by_name: dict[str, list[FunctionIR]] = {}
    for function in function_tuple:
        if not _is_project_summary_candidate(function):
            continue
        by_name.setdefault(function.name, []).append(function)
    recursive = _recursive_function_names(function_tuple)
    eligible = {
        name: items[0]
        for name, items in by_name.items()
        if len(items) == 1 and name not in recursive
    }
    summaries: dict[str, FunctionSummary] = {}
    fresh_return_helpers: set[str] = set()
    for _ in range(max_depth):
        built_summaries = {
            name: build_function_summary(
                function,
                fresh_return_helpers=fresh_return_helpers,
            )
            for name, function in eligible.items()
        }
        built_summaries = _resolve_source_visible_cleanup_direct_summaries(
            built_summaries,
            function_tuple,
            inherited_summaries=summaries,
        )
        built_summaries = _resolve_source_visible_noop_direct_unknowns(built_summaries)
        built_summaries = _refine_parameter_escapes(
            built_summaries,
            function_tuple,
            inherited_summaries=summaries,
        )
        built_summaries = _compose_source_visible_owner_teardowns(
            built_summaries,
            function_tuple,
            inherited_summaries=summaries,
        )
        built_summaries = _compose_source_visible_exit_partitions(
            built_summaries,
            function_tuple,
            inherited_summaries=summaries,
            max_depth=max_depth,
        )
        next_summaries = {
            name: exported
            for name, summary in built_summaries.items()
            if (exported := _project_export_summary(summary)) is not None
        }
        discovered = {
            name
            for name, summary in built_summaries.items()
            if summary.returns_fresh_identity
        }
        summaries = next_summaries
        if discovered <= fresh_return_helpers:
            break
        fresh_return_helpers.update(discovered)
    summaries = _resolve_bounded_noop_indirect_unknowns(summaries, function_tuple)
    return _attach_indirect_target_sets(summaries, function_tuple)


def _compose_source_visible_exit_partitions(
    summaries: dict[str, FunctionSummary],
    functions: tuple[FunctionIR, ...],
    *,
    inherited_summaries: dict[str, FunctionSummary] | None = None,
    max_depth: int = 3,
) -> dict[str, FunctionSummary]:
    """Compose exact error alternatives through bounded visible call chains."""

    function_map = {function.name: function for function in functions}
    base = dict(summaries)
    current = dict(summaries)
    inherited = inherited_summaries or {}
    for _ in range(max_depth):
        visible = {**inherited, **current}
        next_summaries = {
            name: _compose_function_exit_partitions(
                function_map.get(name),
                summary,
                visible,
            )
            for name, summary in base.items()
        }
        if next_summaries == current:
            break
        current = next_summaries
    return current


def _compose_function_exit_partitions(
    function: FunctionIR | None,
    summary: FunctionSummary,
    summaries: dict[str, FunctionSummary],
) -> FunctionSummary:
    if function is None or function.body_node is None:
        return summary
    seed_partitions = tuple(dict.fromkeys((
        *summary.error_exit_partitions,
        *_return_bound_error_partitions(function, summaries),
    )))
    if not seed_partitions:
        return summary
    cfg = build_cfg(function)
    dominators = _dominators(cfg)
    points = find_failure_points(function)
    calls = tuple(sorted(
        (
            node
            for node in function.body_node.walk()
            if node.type == "call_expression"
        ),
        key=lambda node: (node.start_byte, node.end_byte),
    ))
    composed: list[ErrorExitPartition] = []
    for partition in seed_partitions:
        exit_block = _exit_block_for_partition(cfg, partition)
        if exit_block is None:
            composed.append(partition)
            continue
        variants = [partition]
        for call in calls:
            callee, _ = call_name_and_args(compact_ws(call.text))
            callee_summary = summaries.get(callee)
            if callee_summary is None or callee == function.name:
                continue
            call_block = _containing_cfg_block(cfg, call)
            if (
                call_block is None
                or call_block.id not in dominators.get(exit_block.id, set())
                or call.start_line > partition.exit_site.line
            ):
                continue
            application = instantiate_summary(
                callee_summary,
                call,
                return_lvalue=_call_result_lvalue(function, call),
            )
            direct_failure = any(
                _point_matches_partition(point, call, partition)
                for point in points
            )
            if direct_failure and application.error_exit_partitions:
                variants = [
                    _merge_partition_call_outcome(
                        variant,
                        function,
                        call,
                        callee,
                        _live_partition_residuals(callee_partition),
                        callee_partition.terminal_actions,
                        callee_partition.failed_owner_destructions,
                        callee_partition.path,
                        complete=callee_partition.complete,
                        unknown_causes=callee_partition.unknown_causes,
                    )
                    for variant in variants
                    for callee_partition in application.error_exit_partitions
                ]
            elif direct_failure:
                cause = f"callee_exit_partition_unproven: {callee}"
                variants = [
                    _merge_partition_call_outcome(
                        variant,
                        function,
                        call,
                        callee,
                        application.error_opens,
                        tuple(
                            effect
                            for effect in application.error_protects
                            if is_failure_domain_key(effect.key)
                        ),
                        (),
                        (),
                        complete=False,
                        unknown_causes=(cause,),
                    )
                    for variant in variants
                ]
            else:
                success_effects = application.exit_effects.success_must
                if success_effects:
                    variants = [
                        _merge_partition_call_outcome(
                            variant,
                            function,
                            call,
                            callee,
                            success_effects,
                            (),
                            (),
                            (),
                            complete=True,
                            unknown_causes=(),
                        )
                        for variant in variants
                    ]
        composed.extend(variants)
    partitions = tuple(dict.fromkeys(composed))
    error_opens, error_cancels, error_protects = _failure_effect_projection(
        partitions,
        summary.exit_effects,
    )
    partition_causes = tuple(sorted({
        cause
        for partition in partitions
        for cause in partition.unknown_causes
    }))
    exhaustive = _partitions_cover_error_outcomes(function, partitions)
    complete = exhaustive and all(partition.complete for partition in partitions)
    return replace(
        summary,
        error_opens=error_opens,
        error_cancels=error_cancels,
        error_protects=error_protects,
        failure_effects_complete=complete,
        error_unknown_causes=tuple(sorted(set(
            (() if exhaustive else summary.error_unknown_causes) + partition_causes
        ))),
        error_exit_partitions=partitions,
        error_partitions_exhaustive=exhaustive,
    )


def _return_bound_error_partitions(
    function: FunctionIR,
    summaries: dict[str, FunctionSummary],
) -> tuple[ErrorExitPartition, ...]:
    if function.body_node is None:
        return ()
    parameters = _ordered_parameters(function)
    result: list[ErrorExitPartition] = []
    for return_node in function.body_node.walk():
        if return_node.type != "return_statement":
            continue
        expression = compact_ws(_return_expression(return_node))
        calls = [
            node
            for node in return_node.walk()
            if node.type == "call_expression"
            and compact_ws(node.text) == expression
        ]
        if len(calls) != 1:
            continue
        call = calls[0]
        callee, _ = call_name_and_args(expression)
        callee_summary = summaries.get(callee)
        if callee_summary is None or not callee_summary.error_partitions_exhaustive:
            continue
        application = instantiate_summary(callee_summary, call)
        site = SourceSite(
            function.file.as_posix(),
            return_node.start_line,
            expression,
        )
        for partition in application.error_exit_partitions:
            residuals = tuple(
                _parameterize_effect(
                    _effect_at_summary_call_site(effect, function, call, callee),
                    parameters,
                )
                for effect in _live_partition_residuals(partition)
            )
            actions = tuple(
                _parameterize_effect(
                    _effect_at_summary_call_site(effect, function, call, callee),
                    parameters,
                )
                for effect in partition.terminal_actions
            )
            result.append(
                ErrorExitPartition(
                    exit_site=site,
                    return_expression=expression,
                    return_constraint=partition.return_constraint,
                    opens=tuple(
                        effect for effect in residuals if effect.delta in OPEN_DELTAS
                    ),
                    cancels=tuple(
                        effect for effect in residuals if effect.delta in CANCEL_DELTAS
                    ),
                    protects=tuple(
                        effect for effect in residuals if effect.delta in PROTECT_DELTAS
                    ),
                    residuals=residuals,
                    terminal_actions=actions,
                    failed_owner_destructions=partition.failed_owner_destructions,
                    path=tuple(dict.fromkeys((site, *partition.path))),
                    complete=partition.complete,
                    unknown_causes=partition.unknown_causes,
                )
            )
    return tuple(dict.fromkeys(result))


def _merge_partition_call_outcome(
    partition: ErrorExitPartition,
    function: FunctionIR,
    call: FrontendNode,
    callee: str,
    effects: tuple[MetadataEffect, ...],
    terminal_actions: tuple[MetadataEffect, ...],
    destructions: tuple[LifecycleFact, ...],
    path: tuple[SourceSite, ...],
    *,
    complete: bool,
    unknown_causes: tuple[str, ...],
) -> ErrorExitPartition:
    parameters = _ordered_parameters(function)
    projected_effects = tuple(
        _parameterize_effect(
            _effect_at_summary_call_site(effect, function, call, callee),
            parameters,
        )
        for effect in effects
    )
    all_effects = tuple(dict.fromkeys((
        *partition.opens,
        *partition.cancels,
        *partition.protects,
        *projected_effects,
    )))
    opens = tuple(effect for effect in all_effects if effect.delta in OPEN_DELTAS)
    cancels = tuple(effect for effect in all_effects if effect.delta in CANCEL_DELTAS)
    protects = tuple(effect for effect in all_effects if effect.delta in PROTECT_DELTAS)
    normalized = normalize_residuals(opens, cancels, protects)
    site = SourceSite(
        function.file.as_posix(),
        call.start_line,
        compact_ws(call.text),
    )
    return replace(
        partition,
        opens=opens,
        cancels=cancels,
        protects=protects,
        residuals=normalized.residuals,
        terminal_actions=tuple(dict.fromkeys((
            *partition.terminal_actions,
            *(
                _parameterize_effect(
                    _effect_at_summary_call_site(effect, function, call, callee),
                    parameters,
                )
                for effect in terminal_actions
            ),
        ))),
        failed_owner_destructions=tuple(dict.fromkeys((
            *partition.failed_owner_destructions,
            *(
                replace(
                    fact,
                    site=site,
                    evidence=f"{compact_ws(call.text)} via {callee}: {fact.evidence}",
                )
                for fact in destructions
            ),
        ))),
        path=tuple(dict.fromkeys((*partition.path, site, *path))),
        complete=partition.complete and complete,
        unknown_causes=tuple(sorted(set(
            partition.unknown_causes + unknown_causes
        ))),
    )


def _effect_at_summary_call_site(
    effect: MetadataEffect,
    function: FunctionIR,
    call: FrontendNode,
    callee: str,
) -> MetadataEffect:
    return replace(
        effect,
        site=SourceSite(
            function.file.as_posix(),
            call.start_line,
            f"{compact_ws(call.text)} via {callee}: {compact_ws(effect.site.expression)}",
        ),
    )


def _exit_block_for_partition(cfg, partition: ErrorExitPartition) -> BasicBlockIR | None:
    matches = [
        block
        for block in cfg.blocks.values()
        if block.kind == "return_statement"
        and block.start_line == partition.exit_site.line
    ]
    return min(matches, key=lambda block: block.id) if matches else None


def _containing_cfg_block(cfg, node: FrontendNode) -> BasicBlockIR | None:
    matches = [
        block
        for block in cfg.blocks.values()
        if block.kind not in {"entry", "exit"}
        and block.start_byte <= node.start_byte
        and node.end_byte <= block.end_byte
    ]
    return min(
        matches,
        key=lambda block: (block.end_byte - block.start_byte, block.id),
    ) if matches else None


def _point_matches_partition(
    point,
    call: FrontendNode,
    partition: ErrorExitPartition,
) -> bool:
    return (
        point.call_site.line == call.start_line
        and compact_ws(point.call_site.expression) == compact_ws(call.text)
        and point.error_edge.exit_site.line == partition.exit_site.line
        and compact_ws(point.error_edge.exit_expression)
        == compact_ws(partition.return_expression)
    )


def build_local_lifecycle_bindings(
    function: FunctionIR,
    summaries: dict[str, FunctionSummary] | None = None,
) -> tuple[LocalLifecycleBinding, ...]:
    """Find fresh locals and source-visible publication points in one function."""

    fresh_return_helpers = {
        name
        for name, summary in (summaries or {}).items()
        if summary.returns_fresh_identity
    }
    pointer_locals = _local_pointer_symbols(function)
    allocation_lines = _direct_fresh_allocation_lines(
        function,
        pointer_locals,
        fresh_return_helpers,
    )
    if not allocation_lines:
        return ()
    publication_lines = _local_publication_lines(
        function,
        tuple(extract_metadata_effects(function)),
        _ordered_parameters(function),
        allocation_lines,
    )
    allocation_sites = _fresh_allocation_sites(function, allocation_lines)
    escape_lines = _local_escape_lines(
        function,
        allocation_lines,
        summaries or {},
    )
    rebind_lines = _local_rebind_lines(function, allocation_lines)
    return tuple(
        LocalLifecycleBinding(
            local_identity=local,
            allocation_line=line,
            publication_lines=tuple(sorted(publication_lines.get(local, set()))),
            allocation_site=allocation_sites.get(local),
            escape_lines=tuple(sorted(escape_lines.get(local, set()))),
            rebind_lines=tuple(sorted(rebind_lines.get(local, set()))),
        )
        for local, line in sorted(allocation_lines.items())
    )


def instantiate_summary(
    summary: FunctionSummary,
    call: str | FrontendNode,
    *,
    return_lvalue: str = "",
) -> SummaryApplication:
    """Instantiate argN summary effects at a call site."""

    call_text = compact_ws(call.text if isinstance(call, FrontendNode) else call)
    _, args = call_name_and_args(call_text)
    mapping = {f"arg{index}": compact_ws(arg) for index, arg in enumerate(args)}
    if return_lvalue:
        mapping[RETURN_PLACEHOLDER] = compact_ws(return_lvalue)
    for index, placeholder in enumerate(summary.fresh_identities):
        mapping[placeholder] = _fresh_call_identity(summary, call, index)
    for index, placeholder in enumerate(_existential_summary_tokens(summary)):
        mapping[placeholder] = _existential_call_identity(
            summary,
            call,
            index,
        )
    for placeholder in summary.output_identities:
        mapping[placeholder] = _output_call_identity(placeholder, mapping)
    unresolved = _unresolved_parameters(summary, mapping)
    opens = tuple(_instantiate_effect(effect, mapping) for effect in summary.opens)
    cancels = tuple(_instantiate_effect(effect, mapping) for effect in summary.cancels)
    protects = tuple(_instantiate_effect(effect, mapping) for effect in summary.protects)
    error_opens = tuple(_instantiate_effect(effect, mapping) for effect in summary.error_opens)
    error_cancels = tuple(_instantiate_effect(effect, mapping) for effect in summary.error_cancels)
    error_protects = tuple(_instantiate_effect(effect, mapping) for effect in summary.error_protects)
    lifecycle_facts = tuple(
        _instantiate_lifecycle_fact(fact, mapping)
        for fact in summary.lifecycle_facts
    )
    exposure_facts = tuple(
        _instantiate_exposure_fact(fact, mapping)
        for fact in summary.exposure_facts
    )
    cleanup_footprints = tuple(
        _instantiate_cleanup_footprint(footprint, mapping)
        for footprint in summary.cleanup_footprints
    )
    owner_teardowns = tuple(
        _instantiate_owner_teardown(teardown, mapping)
        for teardown in summary.owner_teardowns
    )
    exit_effects = _instantiate_exit_sensitive_effects(summary.exit_effects, mapping)
    error_exit_partitions = tuple(
        _instantiate_error_exit_partition(partition, mapping)
        for partition in summary.error_exit_partitions
    )
    owner_bindings = tuple(
        _instantiate_owner_identity_binding(binding, mapping)
        for binding in summary.owner_bindings
    )
    returns = tuple(_replace_symbols(item, mapping) for item in summary.returns)
    transfer_roots = tuple(
        _replace_symbols(item, mapping)
        for item in summary.ownership_transfer_roots
    )
    return SummaryApplication(
        summary=summary,
        opens=opens,
        cancels=cancels,
        protects=protects,
        error_opens=error_opens,
        error_cancels=error_cancels,
        error_protects=error_protects,
        failure_effects_complete=summary.failure_effects_complete,
        error_unknown_causes=summary.error_unknown_causes,
        lifecycle_facts=lifecycle_facts,
        exposure_facts=exposure_facts,
        cleanup_footprints=cleanup_footprints,
        owner_teardowns=owner_teardowns,
        exit_effects=exit_effects,
        error_exit_partitions=error_exit_partitions,
        error_partitions_exhaustive=summary.error_partitions_exhaustive,
        returns=returns,
        unresolved_identities=unresolved,
        ownership_transfer_roots=transfer_roots,
        owner_bindings=owner_bindings,
        indirect_target_sets=summary.indirect_target_sets,
    )


def extract_owner_teardowns(
    function: FunctionIR,
    *,
    parameterize: bool = False,
    unconditional_only: bool = False,
) -> tuple[OwnerTeardown, ...]:
    """Extract exact whole-owner deallocation primitives from visible source."""

    if function.body_node is None:
        return ()
    parameters = _ordered_parameters(function)
    parameter_index = {name: index for index, name in enumerate(parameters)}
    cfg = build_cfg(function) if unconditional_only else None
    dominators = _dominators(cfg) if cfg is not None else {}
    result: list[OwnerTeardown] = []
    for node in function.body_node.walk():
        if node.type != "call_expression":
            continue
        name, args = call_name_and_args(compact_ws(node.text))
        argument_index = OWNER_DEALLOCATOR_ARGUMENTS.get(name)
        if argument_index is None or argument_index >= len(args):
            continue
        owner = _exact_owner_symbol(args[argument_index])
        if not owner:
            continue
        if unconditional_only:
            block = _containing_cfg_block(cfg, node) if cfg is not None else None
            if block is None or block.id not in dominators.get(cfg.exit, set()):
                continue
        if parameterize:
            if owner not in parameter_index:
                continue
            owner = f"arg{parameter_index[owner]}"
        result.append(
            OwnerTeardown(
                owner=owner,
                teardown_site=SourceSite(
                    function.file.as_posix(),
                    node.start_line,
                    compact_ws(node.text),
                ),
                deallocator=name,
                evidence=(
                    f"exact {name} deallocator primitive destroys the complete "
                    f"in-memory owner passed as argument {argument_index}"
                ),
            )
        )
    return tuple(dict.fromkeys(result))


def apply_same_file_summary(
    summaries: dict[str, FunctionSummary],
    call: str | FrontendNode,
    *,
    return_lvalue: str = "",
) -> SummaryApplication | None:
    call_text = compact_ws(call.text if isinstance(call, FrontendNode) else call)
    name, _ = call_name_and_args(call_text)
    summary = summaries.get(name)
    if summary is None:
        return None
    return instantiate_summary(summary, call, return_lvalue=return_lvalue)


def _parameterize_effect(
    effect: MetadataEffect,
    parameters: tuple[str, ...],
    return_symbols: set[str] | None = None,
    transfer_mapping: dict[str, str] | None = None,
) -> MetadataEffect:
    mapping = _summary_symbol_mapping(
        parameters,
        return_symbols or set(),
        transfer_mapping or {},
    )
    key_mapping = _summary_symbol_mapping(parameters, return_symbols or set())
    cleanup = effect.container_iteration_cleanup
    if cleanup is not None:
        cleanup = replace(
            cleanup,
            container_root=_replace_symbols(cleanup.container_root, mapping),
        )
    existential = effect.existential_member_identity
    if existential is not None:
        existential = replace(
            existential,
            destination_container=_replace_symbols(
                existential.destination_container,
                mapping,
            ),
        )
    transaction_ownership = effect.transaction_ownership
    if transaction_ownership is not None:
        transaction_ownership = replace(
            transaction_ownership,
            transaction_root=_replace_symbols(
                transaction_ownership.transaction_root,
                mapping,
            ),
            owned_root=_replace_symbols(transaction_ownership.owned_root, mapping),
        )
    percpu = effect.percpu_slot_relation
    if percpu is not None:
        percpu = replace(
            percpu,
            base_root=_replace_symbols(percpu.base_root, mapping),
        )
    return replace(
        effect,
        root=_replace_symbols(effect.root, mapping),
        key=_replace_symbols(effect.key, key_mapping),
        value=_replace_symbols(effect.value, mapping),
        container_iteration_cleanup=cleanup,
        existential_member_identity=existential,
        transaction_ownership=transaction_ownership,
        percpu_slot_relation=percpu,
    )


def _instantiate_effect(
    effect: MetadataEffect,
    mapping: dict[str, str],
) -> MetadataEffect:
    cleanup = effect.container_iteration_cleanup
    if cleanup is not None:
        cleanup = replace(
            cleanup,
            container_root=_replace_symbols(cleanup.container_root, mapping),
        )
    existential = effect.existential_member_identity
    if existential is not None:
        existential = replace(
            existential,
            placeholder=_replace_symbols(existential.placeholder, mapping),
            destination_container=_replace_symbols(
                existential.destination_container,
                mapping,
            ),
        )
    transaction_ownership = effect.transaction_ownership
    if transaction_ownership is not None:
        transaction_ownership = replace(
            transaction_ownership,
            transaction_root=_replace_symbols(
                transaction_ownership.transaction_root,
                mapping,
            ),
            owned_root=_replace_symbols(transaction_ownership.owned_root, mapping),
        )
    percpu = effect.percpu_slot_relation
    if percpu is not None:
        percpu = replace(
            percpu,
            base_root=_replace_symbols(percpu.base_root, mapping),
        )
    return replace(
        effect,
        root=_replace_symbols(effect.root, mapping),
        key=_replace_symbols(effect.key, mapping),
        value=_replace_symbols(effect.value, mapping),
        container_iteration_cleanup=cleanup,
        existential_member_identity=existential,
        transaction_ownership=transaction_ownership,
        percpu_slot_relation=percpu,
    )


def _instantiate_lifecycle_fact(
    fact: LifecycleFact,
    mapping: dict[str, str],
) -> LifecycleFact:
    return LifecycleFact(
        subject=_replace_symbols(fact.subject, mapping),
        owner=_replace_symbols(fact.owner, mapping),
        event=fact.event,
        exit=fact.exit,
        site=fact.site,
        evidence=fact.evidence,
    )


def _instantiate_exposure_fact(
    fact: ExposureFact,
    mapping: dict[str, str],
) -> ExposureFact:
    return ExposureFact(
        local_identity=fact.local_identity,
        summary_identity=_replace_symbols(fact.summary_identity, mapping),
        kind=fact.kind,
        target=_replace_symbols(fact.target, mapping),
        site=fact.site,
        evidence=fact.evidence,
    )


def _instantiate_owner_identity_binding(
    binding: OwnerIdentityBinding,
    mapping: dict[str, str],
) -> OwnerIdentityBinding:
    return replace(
        binding,
        bound_identity=_replace_symbols(binding.summary_identity, mapping),
    )


def _cleanup_footprint(effect: MetadataEffect) -> CleanupFootprint:
    return CleanupFootprint(
        root_pattern=effect.root,
        key_pattern=effect.key,
        plane=effect.plane,
        inverse_delta=effect.delta,
        value_pattern=effect.value,
        owner_or_container=_cleanup_owner_or_container(effect),
        site=effect.site,
        evidence=effect.site.expression,
    )


def _cleanup_owner_or_container(effect: MetadataEffect) -> str:
    if effect.key == "list_membership":
        return effect.root
    if effect.key == "tree_membership" or effect.key.startswith(("xarray:", "radix_tree:")):
        return effect.root
    return ""


def _instantiate_cleanup_footprint(
    footprint: CleanupFootprint,
    mapping: dict[str, str],
) -> CleanupFootprint:
    return CleanupFootprint(
        root_pattern=_replace_symbols(footprint.root_pattern, mapping),
        key_pattern=_replace_symbols(footprint.key_pattern, mapping),
        plane=footprint.plane,
        inverse_delta=footprint.inverse_delta,
        value_pattern=_replace_symbols(footprint.value_pattern, mapping),
        owner_or_container=_replace_symbols(footprint.owner_or_container, mapping),
        site=footprint.site,
        evidence=footprint.evidence,
    )


def _instantiate_owner_teardown(
    teardown: OwnerTeardown,
    mapping: dict[str, str],
) -> OwnerTeardown:
    return replace(
        teardown,
        owner=_replace_symbols(teardown.owner, mapping),
        closed_effects=tuple(
            _instantiate_effect(effect, mapping)
            for effect in teardown.closed_effects
        ),
    )


def _instantiate_exit_sensitive_effects(
    effects: ExitSensitiveEffects,
    mapping: dict[str, str],
) -> ExitSensitiveEffects:
    return ExitSensitiveEffects(
        success_must=tuple(_instantiate_effect(item, mapping) for item in effects.success_must),
        success_may=tuple(_instantiate_effect(item, mapping) for item in effects.success_may),
        error_must=tuple(_instantiate_effect(item, mapping) for item in effects.error_must),
        error_may=tuple(_instantiate_effect(item, mapping) for item in effects.error_may),
        error_complete=effects.error_complete,
        unknown_causes=effects.unknown_causes,
    )


def _instantiate_error_exit_partition(
    partition: ErrorExitPartition,
    mapping: dict[str, str],
) -> ErrorExitPartition:
    return ErrorExitPartition(
        exit_site=partition.exit_site,
        return_expression=_replace_symbols(partition.return_expression, mapping),
        return_constraint=partition.return_constraint,
        opens=tuple(_instantiate_effect(item, mapping) for item in partition.opens),
        cancels=tuple(_instantiate_effect(item, mapping) for item in partition.cancels),
        protects=tuple(_instantiate_effect(item, mapping) for item in partition.protects),
        residuals=tuple(_instantiate_effect(item, mapping) for item in partition.residuals),
        terminal_actions=tuple(
            _instantiate_effect(item, mapping) for item in partition.terminal_actions
        ),
        failed_owner_destructions=tuple(
            _instantiate_lifecycle_fact(item, mapping)
            for item in partition.failed_owner_destructions
        ),
        path=partition.path,
        complete=partition.complete,
        unknown_causes=partition.unknown_causes,
    )


def _build_lifecycle_facts(
    function: FunctionIR,
    effects: tuple[MetadataEffect, ...],
    error_reachable_effects: tuple[MetadataEffect, ...],
    transfer_mapping: dict[str, str],
    return_symbols: set[str],
    allocation_lines: dict[str, int],
) -> tuple[LifecycleFact, ...]:
    """Build facts only from visible allocation and ownership transitions.

    This is deliberately an evidence index, not a filesystem protocol model.
    A transition is emitted only when an effect exposes a fresh/returned
    identity or when the effect itself explicitly protects a named object.
    """

    symbol_mapping = _summary_symbol_mapping(
        _ordered_parameters(function),
        return_symbols,
        transfer_mapping,
    )
    facts: list[LifecycleFact] = []
    allocation_sites = _fresh_allocation_sites(function, allocation_lines)
    for local, line in allocation_lines.items():
        subject = symbol_mapping.get(local, "")
        if not subject:
            continue
        site = allocation_sites.get(
            local,
            SourceSite(function.file.as_posix(), line, f"allocation({local})"),
        )
        facts.append(
            LifecycleFact(
                subject=subject,
                owner="",
                event=LifecycleEvent.ALLOCATED,
                exit=LifecycleExit.ALL,
                site=site,
                evidence="direct or source-derived fresh allocation",
            )
        )

    error_reachable_effect_set = set(error_reachable_effects)
    for effect in effects:
        event, subject, owner = _lifecycle_transition(effect)
        if event is None or not subject:
            continue
        if effect in error_reachable_effect_set:
            exit_kind = (
                LifecycleExit.ERROR
                if event is LifecycleEvent.RELEASED
                else LifecycleExit.BOTH
            )
        else:
            exit_kind = LifecycleExit.SUCCESS
        facts.append(
            LifecycleFact(
                subject=subject,
                owner=owner,
                event=event,
                exit=exit_kind,
                site=effect.site,
                evidence=effect.site.expression,
            )
        )

    return _dedupe_lifecycle_facts(facts)


def _build_exposure_facts(
    function: FunctionIR,
    effects: tuple[MetadataEffect, ...],
    parameters: tuple[str, ...],
    pointer_locals: set[str],
    allocation_lines: dict[str, int],
    transfer_mapping: dict[str, str],
    return_symbols: set[str],
    owner_aliases: dict[str, str] | None = None,
) -> tuple[ExposureFact, ...]:
    if function.body_node is None:
        return ()
    parameter_set = set(parameters)
    facts: list[ExposureFact] = []
    exposed_locals: set[str] = set()
    allocation_sites = _fresh_allocation_sites(function, allocation_lines)

    for local, line in allocation_lines.items():
        summary_identity = transfer_mapping.get(local)
        if summary_identity is None and local in return_symbols:
            summary_identity = RETURN_PLACEHOLDER
        facts.append(
            ExposureFact(
                local_identity=local,
                summary_identity=summary_identity or local,
                kind=ExposureKind.FRESH_LOCAL,
                target="",
                site=allocation_sites.get(
                    local,
                    SourceSite(function.file.as_posix(), line, f"allocation({local})"),
                ),
                evidence="direct or source-derived fresh allocation",
            )
        )

    for effect in effects:
        if (
            effect.delta is MetadataDelta.SET
            and effect.plane in {MetadataPlane.STRUCTURAL, MetadataPlane.RECOVERY}
        ):
            local_root = _plain_local_symbol(effect.root, allocation_lines)
            if (
                local_root is not None
                and compact_ws(effect.value) in parameter_set
                and allocation_lines[local_root] <= effect.site.line
            ):
                exposed_locals.add(local_root)
                facts.append(
                    ExposureFact(
                        local_identity=local_root,
                        summary_identity=transfer_mapping.get(local_root, local_root),
                        kind=ExposureKind.BOUND_TO,
                        target=_parameterize_path(effect.value, parameters),
                        site=effect.site,
                        evidence=effect.site.expression,
                    )
                )

        if not _is_parameter_owned(effect.root, parameter_set, owner_aliases):
            continue
        if effect.delta is MetadataDelta.SET:
            local = _plain_local_symbol(effect.value, allocation_lines)
            if local is not None and allocation_lines[local] <= effect.site.line:
                exposed_locals.add(local)
                facts.append(
                    ExposureFact(
                        local_identity=local,
                        summary_identity=transfer_mapping.get(local, local),
                        kind=ExposureKind.PUBLISHED_IN_FIELD,
                        target=_parameterize_path(
                            _field_path(effect.root, effect.key),
                            parameters,
                            owner_aliases,
                        ),
                        site=effect.site,
                        evidence=effect.site.expression,
                    )
                )
        elif effect.delta is MetadataDelta.ADD and _is_container_membership_effect(effect):
            local = _base_local_symbol(effect.value, allocation_lines)
            if local is not None and allocation_lines[local] <= effect.site.line:
                exposed_locals.add(local)
                facts.append(
                    ExposureFact(
                        local_identity=local,
                        summary_identity=transfer_mapping.get(local, local),
                        kind=ExposureKind.MEMBER_OF_CONTAINER,
                        target=_parameterize_path(effect.root, parameters, owner_aliases),
                        site=effect.site,
                        evidence=effect.site.expression,
                    )
                )

    for local, target, site in _output_exposure_sites(function, parameters, allocation_lines):
        exposed_locals.add(local)
        facts.append(
            ExposureFact(
                local_identity=local,
                summary_identity=transfer_mapping.get(local, local),
                kind=ExposureKind.OUTPUT_BOUND,
                target=target,
                site=site,
                evidence=site.expression,
            )
        )

    for local, site in _return_exposure_sites(function, allocation_lines):
        exposed_locals.add(local)
        facts.append(
            ExposureFact(
                local_identity=local,
                summary_identity=RETURN_PLACEHOLDER,
                kind=ExposureKind.RETURNED,
                target=RETURN_PLACEHOLDER,
                site=site,
                evidence=site.expression,
            )
        )

    for local, line in allocation_lines.items():
        if local in exposed_locals or local in transfer_mapping or local in return_symbols:
            continue
        facts.append(
            ExposureFact(
                local_identity=local,
                summary_identity=local,
                kind=ExposureKind.PRIVATE_LOCAL,
                target="",
                site=allocation_sites.get(
                    local,
                    SourceSite(function.file.as_posix(), line, f"allocation({local})"),
                ),
                evidence="fresh local has no source-visible return/output/field/container exposure",
            )
        )
    return _dedupe_exposure_facts(facts)


def _is_container_membership_effect(effect: MetadataEffect) -> bool:
    return (
        effect.key == "list_membership"
        or effect.key == "tree_membership"
        or effect.key.startswith("xarray:")
        or effect.key.startswith("radix_tree:")
    )


def _output_exposure_sites(
    function: FunctionIR,
    parameters: tuple[str, ...],
    allocation_lines: dict[str, int],
) -> tuple[tuple[str, str, SourceSite], ...]:
    if function.body_node is None or not allocation_lines:
        return ()
    parameter_set = set(parameters)
    parameter_index = {name: index for index, name in enumerate(parameters)}
    result: list[tuple[str, str, SourceSite]] = []
    for node in function.body_node.walk():
        if node.type != "assignment_expression":
            continue
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        if left is None or right is None:
            continue
        local = _plain_local_symbol(right.text, allocation_lines)
        if local is None or allocation_lines[local] > node.start_line:
            continue
        parameter = _output_parameter_symbol(left.text, parameter_set)
        if parameter is None:
            continue
        result.append(
            (
                local,
                f"{OUTPUT_PLACEHOLDER_PREFIX}{parameter_index[parameter]}__",
                SourceSite(
                    function.file.as_posix(),
                    node.start_line,
                    compact_ws(node.text),
                ),
            )
        )
    return tuple(result)


def _return_exposure_sites(
    function: FunctionIR,
    allocation_lines: dict[str, int],
) -> tuple[tuple[str, SourceSite], ...]:
    if function.body_node is None or not allocation_lines:
        return ()
    result: list[tuple[str, SourceSite]] = []
    for node in function.body_node.walk():
        if node.type != "return_statement":
            continue
        local = _plain_local_symbol(_return_expression(node), allocation_lines)
        if local is None or allocation_lines[local] > node.start_line:
            continue
        result.append(
            (
                local,
                SourceSite(
                    function.file.as_posix(),
                    node.start_line,
                    compact_ws(node.text),
                ),
            )
        )
    return tuple(result)


def _dedupe_exposure_facts(
    facts: Iterable[ExposureFact],
) -> tuple[ExposureFact, ...]:
    seen: set[tuple[object, ...]] = set()
    result: list[ExposureFact] = []
    for fact in facts:
        key = (
            fact.local_identity,
            fact.summary_identity,
            fact.kind,
            fact.target,
            fact.site.line,
            fact.site.expression,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(fact)
    return tuple(result)


def _can_reach_block(cfg, start: int, target: int) -> bool:
    pending = [start]
    seen: set[int] = set()
    while pending:
        block_id = pending.pop()
        if block_id in seen:
            continue
        if block_id == target:
            return True
        seen.add(block_id)
        pending.extend(edge.target for edge in cfg.successors(block_id))
    return False


def _lifecycle_transition(
    effect: MetadataEffect,
) -> tuple[LifecycleEvent | None, str, str]:
    fresh_tokens = set(re.findall(r"\b(?:__fresh\d+__|__return__|__output\d+__)\b", " ".join((effect.root, effect.key, effect.value))))
    if effect.delta is MetadataDelta.ADD and fresh_tokens:
        return LifecycleEvent.PUBLISHED, sorted(fresh_tokens)[0], effect.root
    if effect.delta is MetadataDelta.SET and fresh_tokens:
        return LifecycleEvent.PUBLISHED, sorted(fresh_tokens)[0], effect.root
    if effect.delta is MetadataDelta.SET and _is_self_field_assignment(effect):
        return LifecycleEvent.PUBLISHED, effect.value, effect.root
    if effect.delta in CANCEL_DELTAS and fresh_tokens:
        return LifecycleEvent.RELEASED, sorted(fresh_tokens)[0], effect.root
    if effect.delta is MetadataDelta.PROTECT:
        return LifecycleEvent.PROTECTED, effect.root, ""
    return None, "", ""


def _is_self_field_assignment(effect: MetadataEffect) -> bool:
    normalized_value = compact_ws(effect.value).strip("()")
    return normalized_value in {
        f"{compact_ws(effect.root)}->{compact_ws(effect.key)}",
        f"{compact_ws(effect.root)}.{compact_ws(effect.key)}",
    }


def _fresh_allocation_sites(
    function: FunctionIR,
    allocation_lines: dict[str, int],
) -> dict[str, SourceSite]:
    if function.body_node is None or not allocation_lines:
        return {}
    sites: dict[str, SourceSite] = {}
    for node in function.body_node.walk():
        if node.type != "call_expression":
            continue
        target = _call_result_lvalue(function, node)
        if target not in allocation_lines or allocation_lines[target] != node.start_line:
            continue
        sites[target] = SourceSite(
            function.file.as_posix(),
            node.start_line,
            compact_ws(node.text),
        )
    return sites


def _dedupe_lifecycle_facts(
    facts: Iterable[LifecycleFact],
) -> tuple[LifecycleFact, ...]:
    seen: set[tuple[object, ...]] = set()
    result: list[LifecycleFact] = []
    for fact in facts:
        key = (
            fact.subject,
            fact.owner,
            fact.event,
            fact.exit,
            fact.site.line,
            fact.site.expression,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(fact)
    return tuple(result)


def _replace_symbols(text: str, mapping: dict[str, str]) -> str:
    result = text
    for source, target in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
        pieces: list[str] = []
        last = 0
        for match in re.finditer(rf"\b{re.escape(source)}\b", result):
            if _is_field_component(result, match.start()):
                continue
            pieces.append(result[last:match.start()])
            pieces.append(target)
            last = match.end()
        if pieces:
            pieces.append(result[last:])
            result = "".join(pieces)
    return compact_ws(result)


def _summary_symbol_mapping(
    parameters: tuple[str, ...],
    return_symbols: set[str],
    transfer_mapping: dict[str, str] | None = None,
) -> dict[str, str]:
    mapping = {name: f"arg{index}" for index, name in enumerate(parameters)}
    mapping.update({name: RETURN_PLACEHOLDER for name in return_symbols})
    mapping.update(transfer_mapping or {})
    return mapping


def _unresolved_parameters(
    summary: FunctionSummary,
    mapping: dict[str, str],
) -> tuple[str, ...]:
    unresolved = [
        f"arg{index}"
        for index, _ in enumerate(summary.parameters)
        if not mapping.get(f"arg{index}")
    ]
    for effect in (*summary.opens, *summary.cancels, *summary.protects):
        for token in _summary_tokens(effect):
            if token not in mapping or not mapping[token]:
                unresolved.append(token)
    for effect in (*summary.error_opens, *summary.error_cancels, *summary.error_protects):
        for token in _summary_tokens(effect):
            if token not in mapping or not mapping[token]:
                unresolved.append(token)
    for fact in summary.lifecycle_facts:
        for token in _lifecycle_tokens(fact):
            if token not in mapping or not mapping[token]:
                unresolved.append(token)
    for fact in summary.exposure_facts:
        for token in _exposure_tokens(fact):
            if token not in mapping or not mapping[token]:
                unresolved.append(token)
    for footprint in summary.cleanup_footprints:
        for token in _cleanup_footprint_tokens(footprint):
            if token not in mapping or not mapping[token]:
                unresolved.append(token)
    for teardown in summary.owner_teardowns:
        for token in re.findall(r"\barg\d+\b", teardown.owner):
            if token not in mapping or not mapping[token]:
                unresolved.append(token)
    return tuple(sorted(set(unresolved)))


def _summary_tokens(effect: MetadataEffect) -> set[str]:
    joined = " ".join([effect.root, effect.key, effect.value])
    if effect.transaction_ownership is not None:
        joined = " ".join((
            joined,
            effect.transaction_ownership.transaction_root,
            effect.transaction_ownership.owned_root,
        ))
    tokens = set(re.findall(r"\barg\d+\b", joined))
    if RETURN_PLACEHOLDER in joined:
        tokens.add(RETURN_PLACEHOLDER)
    tokens.update(re.findall(r"\b__fresh\d+__\b", joined))
    tokens.update(re.findall(r"\b__output\d+__\b", joined))
    return tokens


def _lifecycle_tokens(fact: LifecycleFact) -> set[str]:
    joined = " ".join((fact.subject, fact.owner))
    tokens = set(re.findall(r"\barg\d+\b", joined))
    if RETURN_PLACEHOLDER in joined:
        tokens.add(RETURN_PLACEHOLDER)
    tokens.update(re.findall(r"\b__fresh\d+__\b", joined))
    tokens.update(re.findall(r"\b__output\d+__\b", joined))
    return tokens


def _exposure_tokens(fact: ExposureFact) -> set[str]:
    joined = " ".join((fact.summary_identity, fact.target))
    tokens = set(re.findall(r"\barg\d+\b", joined))
    if RETURN_PLACEHOLDER in joined:
        tokens.add(RETURN_PLACEHOLDER)
    tokens.update(re.findall(r"\b__fresh\d+__\b", joined))
    tokens.update(re.findall(r"\b__output\d+__\b", joined))
    tokens.update(re.findall(r"\b__exists_member\d+__\b", joined))
    return tokens


def _cleanup_footprint_tokens(footprint: CleanupFootprint) -> set[str]:
    joined = " ".join(
        (
            footprint.root_pattern,
            footprint.key_pattern,
            footprint.value_pattern,
            footprint.owner_or_container,
        )
    )
    tokens = set(re.findall(r"\barg\d+\b", joined))
    if RETURN_PLACEHOLDER in joined:
        tokens.add(RETURN_PLACEHOLDER)
    tokens.update(re.findall(r"\b__fresh\d+__\b", joined))
    tokens.update(re.findall(r"\b__output\d+__\b", joined))
    return tokens


def _fresh_call_identity(
    summary: FunctionSummary,
    call: str | FrontendNode,
    index: int,
) -> str:
    if isinstance(call, FrontendNode):
        return (
            f"__fresh_{summary.function_name}_{call.start_line}_"
            f"{call.start_byte}_{index}__"
        )
    return f"__fresh_{summary.function_name}_{index}__"


def _existential_call_identity(
    summary: FunctionSummary,
    call: str | FrontendNode,
    index: int,
) -> str:
    if isinstance(call, FrontendNode):
        return (
            f"__exists_member_{summary.function_name}_{call.start_line}_"
            f"{call.start_byte}_{index}__"
        )
    return f"__exists_member_{summary.function_name}_{index}__"


def _existential_summary_tokens(summary: FunctionSummary) -> tuple[str, ...]:
    effects = (
        *summary.opens,
        *summary.cancels,
        *summary.protects,
        *summary.error_opens,
        *summary.error_cancels,
        *summary.error_protects,
        *(
            effect
            for partition in summary.error_exit_partitions
            for effect in (
                *partition.opens,
                *partition.cancels,
                *partition.protects,
                *partition.residuals,
                *partition.terminal_actions,
            )
        ),
    )
    return tuple(sorted({
        token
        for effect in effects
        for token in re.findall(r"__exists_member\d+__", effect.value)
    }))


def _output_call_identity(
    placeholder: str,
    mapping: dict[str, str],
) -> str:
    match = re.fullmatch(r"__output(\d+)__", placeholder)
    if not match:
        return ""
    value = mapping.get(f"arg{match.group(1)}", "")
    value = compact_ws(value).strip()
    value = value.strip("()")
    while value.startswith("&"):
        value = value[1:].strip()
    return compact_ws(value)


def _effect_references_return(effect: MetadataEffect) -> bool:
    return RETURN_PLACEHOLDER in " ".join([effect.root, effect.key, effect.value])


def _ownership_transfer_mapping(
    function: FunctionIR,
    effects: tuple[MetadataEffect, ...],
    parameters: tuple[str, ...],
    pointer_locals: set[str],
    fresh_return_helpers: set[str],
    owner_aliases: dict[str, str] | None = None,
) -> dict[str, str]:
    """Bind directly allocated locals only after caller ownership is visible."""

    allocation_lines = _direct_fresh_allocation_lines(
        function,
        pointer_locals,
        fresh_return_helpers,
    )
    if not allocation_lines:
        return {}

    parameter_set = set(parameters)
    field_targets: dict[str, set[str]] = {}
    container_transfers: set[str] = set()
    for effect in effects:
        if not _is_parameter_owned(effect.root, parameter_set, owner_aliases):
            continue
        if effect.delta is MetadataDelta.SET:
            local = _plain_local_symbol(effect.value, allocation_lines)
            if local is not None and allocation_lines[local] <= effect.site.line:
                target = _parameterize_path(
                    _field_path(effect.root, effect.key),
                    parameters,
                    owner_aliases,
                )
                field_targets.setdefault(local, set()).add(target)
            continue
        if effect.delta is not MetadataDelta.ADD:
            continue
        if effect.key != "list_membership" and not (
            effect.key == "tree_membership"
            or effect.key.startswith("xarray:")
            or effect.key.startswith("radix_tree:")
        ):
            continue
        local = _base_local_symbol(effect.value, allocation_lines)
        if local is not None and allocation_lines[local] <= effect.site.line:
            container_transfers.add(local)

    mapping: dict[str, str] = {}
    fresh_index = 0
    for local in sorted(set(field_targets) | container_transfers):
        targets = field_targets.get(local, set())
        if len(targets) == 1:
            mapping[local] = next(iter(targets))
            continue
        if local in container_transfers:
            mapping[local] = f"{FRESH_PLACEHOLDER_PREFIX}{fresh_index}__"
            fresh_index += 1
    return mapping


def _output_transfer_mapping(
    function: FunctionIR,
    parameters: tuple[str, ...],
    pointer_locals: set[str],
    allocation_lines: dict[str, int],
) -> dict[str, str]:
    if function.body_node is None or not allocation_lines:
        return {}
    parameter_index = {name: index for index, name in enumerate(parameters)}
    mapping: dict[str, str] = {}
    for node in function.body_node.walk():
        if node.type != "assignment_expression":
            continue
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        if left is None or right is None:
            continue
        local = _plain_local_symbol(right.text, allocation_lines)
        if local is None or local not in pointer_locals:
            continue
        if allocation_lines[local] > node.start_line:
            continue
        parameter = _output_parameter_symbol(left.text, set(parameters))
        if parameter is None:
            continue
        mapping[local] = f"{OUTPUT_PLACEHOLDER_PREFIX}{parameter_index[parameter]}__"
    return mapping


def _return_field_output_mapping(
    function: FunctionIR,
    parameters: tuple[str, ...],
    return_symbols: set[str],
) -> dict[str, str]:
    if function.body_node is None or not return_symbols:
        return {}
    parameter_index = {name: index for index, name in enumerate(parameters)}
    parameter_set = set(parameters)
    mapping: dict[str, str] = {}
    for node in function.body_node.walk():
        if node.type != "assignment_expression":
            continue
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        if left is None or right is None or left.type != "field_expression":
            continue
        output_parameter = _output_parameter_symbol(right.text, parameter_set)
        if output_parameter is None:
            continue
        left_text = compact_ws(left.text)
        match = re.fullmatch(
            r"([A-Za-z_]\w*)((?:(?:->|\.)[A-Za-z_]\w*)+)",
            left_text,
        )
        if not match:
            continue
        local = match.group(1)
        if local not in return_symbols:
            continue
        mapping[left_text] = (
            f"{OUTPUT_PLACEHOLDER_PREFIX}{parameter_index[output_parameter]}__"
        )
    return mapping


def _local_publication_lines(
    function: FunctionIR,
    effects: tuple[MetadataEffect, ...],
    parameters: tuple[str, ...],
    allocation_lines: dict[str, int],
) -> dict[str, set[int]]:
    publications: dict[str, set[int]] = {
        local: set() for local in allocation_lines
    }
    parameter_set = set(parameters)
    for effect in effects:
        # A fresh object becomes failure-relevant once it is structurally bound
        # to a caller-owned object, even before its final output publication.
        # Keep this deliberately narrow: a bare parameter RHS excludes scalar
        # initialization, calls, address-taking, and dereference expressions.
        local_root = _plain_local_symbol(effect.root, allocation_lines)
        if (
            local_root is not None
            and effect.delta is MetadataDelta.SET
            and effect.plane in {MetadataPlane.STRUCTURAL, MetadataPlane.RECOVERY}
            and compact_ws(effect.value) in parameter_set
            and allocation_lines[local_root] <= effect.site.line
        ):
            publications[local_root].add(effect.site.line)

        if not _is_parameter_owned(effect.root, parameter_set):
            continue
        local: str | None = None
        if effect.delta is MetadataDelta.SET:
            local = _plain_local_symbol(effect.value, allocation_lines)
        elif effect.delta is MetadataDelta.ADD:
            local = _base_local_symbol(effect.value, allocation_lines)
        if local is not None and allocation_lines[local] <= effect.site.line:
            publications[local].add(effect.site.line)

    if function.body_node is None:
        return publications
    for node in function.body_node.walk():
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is None or right is None:
                continue
            local = _plain_local_symbol(right.text, allocation_lines)
            if local is None or allocation_lines[local] > node.start_line:
                continue
            if _output_parameter_symbol(left.text, parameter_set) is not None:
                publications[local].add(node.start_line)
        elif node.type == "return_statement":
            local = _plain_local_symbol(_return_expression(node), allocation_lines)
            if local is not None and allocation_lines[local] <= node.start_line:
                publications[local].add(node.start_line)
    return publications


def _local_escape_lines(
    function: FunctionIR,
    allocation_lines: dict[str, int],
    summaries: dict[str, FunctionSummary],
) -> dict[str, set[int]]:
    escapes = {local: set() for local in allocation_lines}
    if function.body_node is None:
        return escapes
    for node in function.body_node.walk():
        if node.type != "call_expression":
            continue
        name, args = call_name_and_args(compact_ws(node.text))
        deallocator_index = OWNER_DEALLOCATOR_ARGUMENTS.get(name)
        callee_summary = summaries.get(name)
        for index, argument in enumerate(args):
            local = _bare_owner_symbol(argument)
            if local not in allocation_lines or allocation_lines[local] > node.start_line:
                continue
            if (
                deallocator_index == index
                and _exact_owner_symbol(argument) == local
            ):
                continue
            if (
                callee_summary is not None
                and index not in callee_summary.escaping_parameters
            ):
                continue
            escapes[local].add(node.start_line)
    return escapes


def _local_rebind_lines(
    function: FunctionIR,
    allocation_lines: dict[str, int],
) -> dict[str, set[int]]:
    """Invalidate a fresh identity when its local pointer is assigned again."""

    rebinds = {local: set() for local in allocation_lines}
    if function.body_node is None:
        return rebinds
    for node in function.body_node.walk():
        if node.type != "assignment_expression":
            continue
        left = node.child_by_field_name("left")
        if left is None:
            continue
        local = _bare_owner_symbol(left.text)
        if local in allocation_lines and node.start_line > allocation_lines[local]:
            rebinds[local].add(node.start_line)
    return rebinds


def _refine_parameter_escapes(
    summaries: dict[str, FunctionSummary],
    functions: Iterable[FunctionIR],
    *,
    inherited_summaries: dict[str, FunctionSummary] | None = None,
    max_depth: int = 4,
) -> dict[str, FunctionSummary]:
    function_map = {function.name: function for function in functions}
    current = {
        name: replace(
            summary,
            escaping_parameters=tuple(range(len(summary.parameters))),
        )
        for name, summary in summaries.items()
    }
    inherited = inherited_summaries or {}
    for _ in range(max_depth):
        visible = {**inherited, **current}
        next_result = {
            name: replace(
                summary,
                escaping_parameters=_parameter_escape_indices(
                    function_map.get(name),
                    visible,
                ),
            )
            for name, summary in current.items()
        }
        if next_result == current:
            break
        current = next_result
    return current


def _parameter_escape_indices(
    function: FunctionIR | None,
    summaries: dict[str, FunctionSummary],
) -> tuple[int, ...]:
    if function is None or function.body_node is None:
        return ()
    parameters = _ordered_parameters(function)
    parameter_index = {parameter: index for index, parameter in enumerate(parameters)}
    escaped: set[int] = set()
    for node in function.body_node.walk():
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is None or right is None:
                continue
            parameter = _bare_owner_symbol(right.text)
            if parameter in parameter_index and not _path_is_rooted_at(
                left.text, parameter
            ):
                escaped.add(parameter_index[parameter])
        elif node.type == "return_statement":
            parameter = _bare_owner_symbol(_return_expression(node))
            if parameter in parameter_index:
                escaped.add(parameter_index[parameter])
        elif node.type == "call_expression":
            name, args = call_name_and_args(compact_ws(node.text))
            deallocator_index = OWNER_DEALLOCATOR_ARGUMENTS.get(name)
            callee_summary = summaries.get(name)
            for argument_index, argument in enumerate(args):
                parameter = _bare_owner_symbol(argument)
                if parameter not in parameter_index:
                    continue
                if (
                    deallocator_index == argument_index
                    and _exact_owner_symbol(argument) == parameter
                ):
                    continue
                if (
                    callee_summary is None
                    or argument_index in callee_summary.escaping_parameters
                ):
                    escaped.add(parameter_index[parameter])
    return tuple(sorted(escaped))


def _compose_source_visible_owner_teardowns(
    summaries: dict[str, FunctionSummary],
    functions: Iterable[FunctionIR],
    *,
    inherited_summaries: dict[str, FunctionSummary] | None = None,
    max_depth: int = 3,
) -> dict[str, FunctionSummary]:
    function_map = {function.name: function for function in functions}
    inherited = inherited_summaries or {}
    current = dict(summaries)
    for _ in range(max_depth):
        visible = {**inherited, **current}
        next_result: dict[str, FunctionSummary] = {}
        for name, summary in current.items():
            function = function_map.get(name)
            if function is None or function.body_node is None:
                next_result[name] = summary
                continue
            cfg = build_cfg(function)
            dominators = _dominators(cfg)
            parameters = _ordered_parameters(function)
            parameter_index = {
                parameter: index for index, parameter in enumerate(parameters)
            }
            teardowns = list(summary.owner_teardowns)
            for call in function.body_node.walk():
                if call.type != "call_expression":
                    continue
                callee, _ = call_name_and_args(compact_ws(call.text))
                callee_summary = visible.get(callee)
                if callee_summary is None or not callee_summary.owner_teardowns:
                    continue
                block = _containing_cfg_block(cfg, call)
                if (
                    block is None
                    or block.id not in dominators.get(cfg.exit, set())
                ):
                    continue
                application = instantiate_summary(callee_summary, call)
                for teardown in application.owner_teardowns:
                    owner = _exact_owner_symbol(teardown.owner)
                    if owner not in parameter_index:
                        continue
                    teardowns.append(
                        replace(
                            teardown,
                            owner=f"arg{parameter_index[owner]}",
                            teardown_site=SourceSite(
                                function.file.as_posix(),
                                call.start_line,
                                compact_ws(call.text),
                            ),
                            via_function=callee,
                            evidence=(
                                f"{compact_ws(call.text)} via {callee}: "
                                f"{teardown.evidence}"
                            ),
                        )
                    )
            next_result[name] = replace(
                summary,
                owner_teardowns=tuple(dict.fromkeys(teardowns)),
            )
        if next_result == current:
            break
        current = next_result
    return current


def _bare_owner_symbol(text: str) -> str:
    value = compact_ws(text).strip()
    while value.startswith("(") and value.endswith(")"):
        value = value[1:-1].strip()
    while value.startswith(("&", "*")):
        value = value[1:].strip()
    return value if re.fullmatch(r"[A-Za-z_]\w*", value) else ""


def _exact_owner_symbol(text: str) -> str:
    """Accept one owner identity, excluding dereference/address/field expressions."""

    value = compact_ws(text).strip()
    while match := re.fullmatch(r"\(\s*([A-Za-z_]\w*)\s*\)", value):
        value = match.group(1)
    return value if re.fullmatch(r"[A-Za-z_]\w*", value) else ""


def _path_is_rooted_at(text: str, root: str) -> bool:
    value = compact_ws(text).strip("()")
    return value == root or value.startswith((f"{root}->", f"{root}."))


def _output_parameter_symbol(text: str, parameters: set[str]) -> str | None:
    value = compact_ws(text).strip("()")
    while value.startswith("*"):
        value = value[1:].strip()
    return value if value in parameters else None


def _exit_sensitive_effects(
    function: FunctionIR,
    effects: tuple[MetadataEffect, ...],
) -> ExitSensitiveEffects:
    if function.body_node is None:
        return ExitSensitiveEffects(unknown_causes=("missing_function_body",))
    exits = _classified_return_nodes(function)
    success_returns = tuple(node for node, kind in exits if kind == "success")
    error_returns = tuple(node for node, kind in exits if kind == "error")
    unknown_returns = tuple(node for node, kind in exits if kind == "unknown")
    cfg = build_cfg(function)
    success_blocks = _exit_blocks(cfg, success_returns)
    error_blocks = _exit_blocks(cfg, error_returns)
    causes: list[str] = []
    if unknown_returns:
        causes.append("unclassified_return_exit")
    if len(success_blocks) != len(success_returns):
        causes.append("unclassified_success_exit_block")
    if len(error_blocks) != len(error_returns):
        causes.append("unclassified_error_exit_block")
    success_must, success_may = _effects_for_exit_blocks(
        cfg,
        effects,
        success_blocks,
    )
    error_must, error_may = _effects_for_exit_blocks(cfg, effects, error_blocks)
    return ExitSensitiveEffects(
        success_must=success_must,
        success_may=success_may,
        error_must=error_must,
        error_may=error_may,
        error_complete=bool(error_returns) and not causes,
        unknown_causes=tuple(causes),
    )


def _error_exit_partitions(
    function: FunctionIR,
    effects: tuple[MetadataEffect, ...],
    lifecycle_facts: tuple[LifecycleFact, ...] = (),
) -> tuple[ErrorExitPartition, ...]:
    """Keep effect correlation for each classified source error return."""

    if function.body_node is None:
        return ()
    cfg = build_cfg(function)
    partitions: list[ErrorExitPartition] = []
    for return_node, kind in _classified_return_nodes(function):
        if kind != "error":
            continue
        block = _block_for_return_node(cfg, return_node)
        expression = compact_ws(_return_expression(return_node))
        site = SourceSite(
            function.file.as_posix(),
            return_node.start_line,
            expression,
        )
        if block is None:
            partitions.append(
                ErrorExitPartition(
                    exit_site=site,
                    return_expression=expression,
                    complete=False,
                    unknown_causes=("unclassified_error_exit_block",),
                )
            )
            continue
        must, _ = _effects_for_exit_blocks(cfg, effects, (block,))
        must = tuple(dict.fromkeys((
            *must,
            *_failure_domain_guard_actions_for_return(function, cfg, block),
        )))
        terminal_actions = tuple(
            effect for effect in must if is_failure_domain_key(effect.key)
        )
        ordinary = tuple(
            effect for effect in must if not is_failure_domain_key(effect.key)
        )
        opens = tuple(effect for effect in ordinary if effect.delta in OPEN_DELTAS)
        cancels = tuple(effect for effect in ordinary if effect.delta in CANCEL_DELTAS)
        protects = tuple(effect for effect in ordinary if effect.delta in PROTECT_DELTAS)
        normalized = normalize_residuals(opens, cancels, protects)
        destructions = tuple(
            fact
            for fact in lifecycle_facts
            if fact.event is LifecycleEvent.RELEASED
            and any(fact.site == effect.site for effect in must)
        )
        partitions.append(
            ErrorExitPartition(
                exit_site=site,
                return_expression=expression,
                return_constraint=_return_constraint(expression),
                opens=opens,
                cancels=cancels,
                protects=protects,
                residuals=normalized.residuals,
                terminal_actions=terminal_actions,
                failed_owner_destructions=destructions,
                path=(site,),
                complete=True,
            )
        )
    partitions.extend(
        _conditional_error_exit_partitions(
            function,
            cfg,
            effects,
            lifecycle_facts,
        )
    )
    return tuple(dict.fromkeys(partitions))


def _conditional_error_exit_partitions(
    function: FunctionIR,
    cfg,
    effects: tuple[MetadataEffect, ...],
    lifecycle_facts: tuple[LifecycleFact, ...],
) -> tuple[ErrorExitPartition, ...]:
    """Split a shared return by a source-visible checked error outcome."""

    partitions: list[ErrorExitPartition] = []
    for point in find_failure_points(function):
        if point.check_kind not in {"IS_ERR", "IS_ERR_OR_NULL", "IS_ERR_VALUE"}:
            continue
        exit_block = next(
            (
                block
                for block in cfg.blocks.values()
                if block.kind == "return_statement"
                and block.start_line == point.error_edge.exit_site.line
            ),
            None,
        )
        if exit_block is None:
            continue
        reachable = _reachable_blocks_without(
            cfg,
            point.error_edge.target_block,
            forbidden={point.error_edge.source_block},
        )
        if exit_block.id not in reachable:
            continue
        dominators = _subset_dominators(
            cfg,
            point.error_edge.target_block,
            reachable,
        )
        must_effects = tuple(
            effect
            for effect in effects
            if (block_id := _block_for_effect_site(cfg, effect)) is not None
            and block_id in dominators.get(exit_block.id, set())
            and effect.site.line >= point.check_site.line
        )
        terminal_actions = tuple(
            effect for effect in must_effects if is_failure_domain_key(effect.key)
        )
        if not terminal_actions:
            continue
        ordinary = tuple(
            effect for effect in must_effects if not is_failure_domain_key(effect.key)
        )
        opens = tuple(effect for effect in ordinary if effect.delta in OPEN_DELTAS)
        cancels = tuple(effect for effect in ordinary if effect.delta in CANCEL_DELTAS)
        protects = tuple(effect for effect in ordinary if effect.delta in PROTECT_DELTAS)
        normalized = normalize_residuals(opens, cancels, protects)
        destructions = tuple(
            fact
            for fact in lifecycle_facts
            if fact.event is LifecycleEvent.RELEASED
            and any(fact.site == effect.site for effect in must_effects)
        )
        partitions.append(
            ErrorExitPartition(
                exit_site=point.error_edge.exit_site,
                return_expression=point.error_edge.exit_expression,
                return_constraint=point.check_kind,
                opens=opens,
                cancels=cancels,
                protects=protects,
                residuals=normalized.residuals,
                terminal_actions=terminal_actions,
                failed_owner_destructions=destructions,
                path=tuple(dict.fromkeys((
                    point.check_site,
                    *(effect.site for effect in terminal_actions),
                    point.error_edge.exit_site,
                ))),
                complete=True,
            )
        )
    return tuple(partitions)


def _failure_domain_guard_actions_for_return(
    function: FunctionIR,
    cfg,
    return_block: BasicBlockIR,
) -> tuple[MetadataEffect, ...]:
    if function.body_node is None:
        return ()
    parameter_index = {
        name: index for index, name in enumerate(_ordered_parameters(function))
    }
    actions: list[MetadataEffect] = []
    for if_node in function.body_node.walk():
        if if_node.type != "if_statement":
            continue
        condition = if_node.child_by_field_name("condition")
        if condition is None:
            continue
        condition_block = next(
            (
                block
                for block in cfg.blocks.values()
                if block.kind == "condition" and block.start_line == if_node.start_line
            ),
            None,
        )
        if condition_block is None:
            continue
        true_targets = [
            edge.target for edge in cfg.successors(condition_block.id) if edge.kind == "true"
        ]
        false_targets = [
            edge.target for edge in cfg.successors(condition_block.id) if edge.kind == "false"
        ]
        if not true_targets or not false_targets:
            continue
        true_reaches = any(
            _can_reach_block(cfg, target, return_block.id) for target in true_targets
        )
        false_reaches = any(
            _can_reach_block(cfg, target, return_block.id) for target in false_targets
        )
        if not true_reaches or false_reaches:
            continue
        for call in condition.walk():
            if call.type != "call_expression":
                continue
            name, args = call_name_and_args(compact_ws(call.text))
            guard = failure_domain_guard(name)
            if guard is None:
                continue
            owner_index, kind = guard
            if owner_index >= len(args):
                continue
            owner = compact_ws(args[owner_index]).strip("() ")
            if owner not in parameter_index:
                continue
            actions.append(
                MetadataEffect(
                    root=f"arg{parameter_index[owner]}",
                    key=failure_domain_key(kind),
                    plane=MetadataPlane.RECOVERY,
                    delta=MetadataDelta.PROTECT,
                    value=kind.value,
                    site=SourceSite(
                        function.file.as_posix(),
                        call.start_line,
                        compact_ws(call.text),
                    ),
                    evidence=EffectEvidence.EXPLICIT_PRIMITIVE,
                )
            )
    return tuple(dict.fromkeys(actions))


def _reachable_blocks_without(
    cfg,
    start: int,
    *,
    forbidden: set[int],
) -> set[int]:
    pending = [start]
    seen: set[int] = set()
    while pending:
        block_id = pending.pop()
        if block_id in seen or block_id in forbidden:
            continue
        seen.add(block_id)
        pending.extend(edge.target for edge in cfg.successors(block_id))
    return seen


def _subset_dominators(cfg, start: int, nodes: set[int]) -> dict[int, set[int]]:
    dominators = {node: set(nodes) for node in nodes}
    dominators[start] = {start}
    changed = True
    while changed:
        changed = False
        for node in sorted(nodes - {start}):
            predecessors = [
                edge.source
                for edge in cfg.predecessors(node)
                if edge.source in nodes
            ]
            new = (
                set.intersection(*(dominators[item] for item in predecessors))
                if predecessors
                else set()
            )
            new.add(node)
            if new != dominators[node]:
                dominators[node] = new
                changed = True
    return dominators


def _return_constraint(expression: str) -> str:
    value = compact_ws(expression).strip()
    name, args = call_name_and_args(value)
    if name == "ERR_PTR" and len(args) == 1:
        inner = compact_ws(args[0]).strip("() ")
        if re.fullmatch(r"-?(?:[A-Z_]\w*|\d+)", inner):
            return f"EXACT:{inner}"
        return "IS_ERR"
    if name == "PTR_ERR" and len(args) == 1:
        return "NEGATIVE"
    if re.fullmatch(r"-?(?:[A-Z_]\w*|\d+)", value):
        return f"EXACT:{value}"
    return ""


def _partitions_cover_error_outcomes(
    function: FunctionIR,
    partitions: tuple[ErrorExitPartition, ...],
) -> bool:
    if not partitions or not all(partition.complete for partition in partitions):
        return False
    covered_lines = {partition.exit_site.line for partition in partitions}
    return all(
        kind == "success" or node.start_line in covered_lines
        for node, kind in _classified_return_nodes(function)
    )


def _failure_effect_projection(
    partitions: tuple[ErrorExitPartition, ...],
    exit_effects: ExitSensitiveEffects,
) -> tuple[
    tuple[MetadataEffect, ...],
    tuple[MetadataEffect, ...],
    tuple[MetadataEffect, ...],
]:
    """Project exact alternatives without mixing branch-local cleanup proofs."""

    # Keep the established MUST projection until the caller slicer can analyze
    # alternatives independently.  Unioning partition residuals here would
    # discard their cleanup/terminal correlation and inflate Candidates.
    common_opens = tuple(
        effect
        for effect in exit_effects.error_must
        if effect.delta in OPEN_DELTAS
    )
    common_cancels = tuple(
        effect
        for effect in exit_effects.error_must
        if effect.delta in CANCEL_DELTAS
    )
    common_protects = tuple(
        effect
        for effect in exit_effects.error_must
        if effect.delta in PROTECT_DELTAS
    )
    terminal_actions: tuple[MetadataEffect, ...] = ()
    complete = partitions and all(partition.complete for partition in partitions)
    if complete and all(partition.terminal_actions for partition in partitions):
        terminal_actions = tuple(dict.fromkeys(
            action
            for partition in partitions
            for action in partition.terminal_actions
        ))
    return (
        common_opens,
        common_cancels,
        tuple(dict.fromkeys((*common_protects, *terminal_actions))),
    )


def _live_partition_residuals(
    partition: ErrorExitPartition,
) -> tuple[MetadataEffect, ...]:
    terminally_covered = {
        effect
        for action in partition.terminal_actions
        for effect in covered_effects_for_action(action, partition.residuals)
    }
    return tuple(
        effect
        for effect in partition.residuals
        if effect not in terminally_covered
        and not any(
            _destruction_covers_effect(destruction, effect)
            for destruction in partition.failed_owner_destructions
        )
    )


def _destruction_covers_effect(
    destruction: LifecycleFact,
    effect: MetadataEffect,
) -> bool:
    subject = compact_ws(destruction.subject)
    root = compact_ws(effect.root)
    return bool(subject) and (
        root == subject
        or root.startswith(f"{subject}->")
        or root.startswith(f"{subject}.")
    )


def _exit_blocks(cfg, returns: tuple[FrontendNode, ...]) -> tuple[BasicBlockIR, ...]:
    return tuple(
        block
        for node in returns
        if (block := _block_for_return_node(cfg, node)) is not None
    )


def _effects_for_exit_blocks(
    cfg,
    effects: tuple[MetadataEffect, ...],
    exit_blocks: tuple[BasicBlockIR, ...],
) -> tuple[tuple[MetadataEffect, ...], tuple[MetadataEffect, ...]]:
    if not exit_blocks:
        return (), ()
    dominators = _dominators(cfg)
    must: list[MetadataEffect] = []
    may: list[MetadataEffect] = []
    for effect in effects:
        block_id = _block_for_effect_site(cfg, effect)
        if block_id is None:
            continue
        reaches_exit = tuple(
            _can_reach_block(cfg, block_id, exit_block.id)
            and effect.site.line <= exit_block.start_line
            for exit_block in exit_blocks
        )
        if not any(reaches_exit):
            continue
        may.append(effect)
        if all(
            block_id in dominators.get(exit_block.id, set())
            and effect.site.line <= exit_block.start_line
            for exit_block in exit_blocks
        ):
            must.append(effect)
    return tuple(must), tuple(may)


def _has_error_return(function: FunctionIR) -> bool:
    return any(kind == "error" for _, kind in _classified_return_nodes(function))


def _classified_return_nodes(
    function: FunctionIR,
) -> tuple[tuple[FrontendNode, str], ...]:
    if function.body_node is None:
        return ()
    pointer_locals = _local_pointer_symbols(function)
    success_symbols = _success_return_symbols(function, pointer_locals)
    known_error_expressions = {
        compact_ws(point.error_edge.exit_expression)
        for point in find_failure_points(function)
    }
    result: list[tuple[FrontendNode, str]] = []
    for node in function.body_node.walk():
        if node.type != "return_statement":
            continue
        expr = _return_expression(node)
        kind = _return_kind(expr, success_symbols, known_error_expressions)
        result.append((node, kind))
    return tuple(result)


def _return_kind(
    expression: str,
    success_symbols: set[str],
    known_error_expressions: set[str],
) -> str:
    expr = compact_ws(expression)
    if not expr:
        return "unknown"
    if expr in {"0", "NULL", "false", "FALSE"} or expr in success_symbols:
        return "success"
    if expr.startswith("-") or expr in known_error_expressions:
        return "error"
    name, _ = call_name_and_args(expr)
    if name in {"ERR_PTR", "PTR_ERR"}:
        return "error"
    return "unknown"


def _dominators(cfg) -> dict[int, set[int]]:
    nodes = set(cfg.blocks)
    dominators = {block_id: set(nodes) for block_id in nodes}
    dominators[cfg.entry] = {cfg.entry}
    changed = True
    while changed:
        changed = False
        for block_id in sorted(nodes - {cfg.entry}):
            preds = [edge.source for edge in cfg.predecessors(block_id)]
            if not preds:
                new = {block_id}
            else:
                pred_sets = [dominators[pred] for pred in preds]
                new = set.intersection(*pred_sets) if pred_sets else set()
                new.add(block_id)
            if new != dominators[block_id]:
                dominators[block_id] = new
                changed = True
    return dominators


def _block_for_return_node(cfg, node: FrontendNode):
    matches = [
        block
        for block in cfg.blocks.values()
        if block.kind == "return_statement"
        and block.start_byte == node.start_byte
        and block.end_byte == node.end_byte
    ]
    if matches:
        return min(matches, key=lambda block: block.id)
    return cfg.block_at_line(node.start_line)


def _block_for_effect_site(cfg, effect: MetadataEffect) -> int | None:
    matches = [
        block
        for block in cfg.blocks.values()
        if block.start_line <= effect.site.line <= block.end_line and block.start_line
    ]
    if not matches:
        return None
    exact = [block for block in matches if compact_ws(effect.site.expression) in compact_ws(block.text)]
    chosen = exact or matches
    return min(chosen, key=lambda block: (block.end_line - block.start_line, block.id)).id


def _recursive_function_names(functions: tuple[FunctionIR, ...]) -> set[str]:
    names = {function.name for function in functions}
    graph: dict[str, set[str]] = {name: set() for name in names}
    for function in functions:
        if function.body_node is None:
            continue
        for node in function.body_node.walk():
            if node.type != "call_expression":
                continue
            name, _ = call_name_and_args(compact_ws(node.text))
            if name in names:
                graph.setdefault(function.name, set()).add(name)

    recursive: set[str] = set()
    for name in names:
        if _can_reach(name, name, graph, set()):
            recursive.add(name)
    return recursive


def _can_reach(
    current: str,
    target: str,
    graph: dict[str, set[str]],
    seen: set[str],
) -> bool:
    for callee in graph.get(current, set()):
        if callee == target:
            return True
        if callee in seen:
            continue
        seen.add(callee)
        if _can_reach(callee, target, graph, seen):
            return True
    return False


def _with_source(
    summary: FunctionSummary,
    source: SummarySource,
) -> FunctionSummary:
    return FunctionSummary(
        function_name=summary.function_name,
        parameters=summary.parameters,
        returns=summary.returns,
        fresh_identities=summary.fresh_identities,
        has_ownership_transfer=summary.has_ownership_transfer,
        ownership_transfer_roots=summary.ownership_transfer_roots,
        returns_fresh_identity=summary.returns_fresh_identity,
        opens=summary.opens,
        cancels=summary.cancels,
        protects=summary.protects,
        output_identities=summary.output_identities,
        error_opens=summary.error_opens,
        error_cancels=summary.error_cancels,
        error_protects=summary.error_protects,
        failure_effects_complete=summary.failure_effects_complete,
        error_unknown_causes=summary.error_unknown_causes,
        lifecycle_facts=summary.lifecycle_facts,
        exposure_facts=summary.exposure_facts,
        cleanup_footprints=summary.cleanup_footprints,
        owner_teardowns=summary.owner_teardowns,
        escaping_parameters=summary.escaping_parameters,
        exit_effects=summary.exit_effects,
        error_exit_partitions=summary.error_exit_partitions,
        error_partitions_exhaustive=summary.error_partitions_exhaustive,
        unresolved_calls=summary.unresolved_calls,
        source_file=summary.source_file,
        may_fail=summary.may_fail,
        unknown_escape=summary.unknown_escape,
        unknown_causes=summary.unknown_causes,
        source=source,
        owner_bindings=summary.owner_bindings,
    )


def _project_export_summary(summary: FunctionSummary) -> FunctionSummary | None:
    if summary.has_ownership_transfer:
        if (
            summary.failure_effects_complete
            and not summary.unknown_causes
            and not summary.error_unknown_causes
        ):
            return _with_source(summary, SummarySource.AUTO_INTERPROCEDURAL)
        return None
    if summary.returns_fresh_identity:
        return _fresh_fact_summary(summary)
    if _is_exportable_owner_teardown_summary(summary):
        return _with_source(summary, SummarySource.AUTO_INTERPROCEDURAL)
    if _is_exportable_terminal_partition_summary(summary):
        return _with_source(summary, SummarySource.AUTO_INTERPROCEDURAL)
    if _is_exportable_cleanup_summary(summary):
        return _with_source(summary, SummarySource.AUTO_INTERPROCEDURAL)
    if _is_exportable_noop_summary(summary):
        return _with_source(summary, SummarySource.AUTO_INTERPROCEDURAL)
    return None


def _is_exportable_cleanup_summary(summary: FunctionSummary) -> bool:
    """Recognize a non-failing, parameter-bound cleanup helper.

    These summaries are usable across translation units because they cannot add
    a residual before a caller failure: source extraction found only
    cancellation effects, and the helper has no source-visible failure exit.
    A bare ``return;`` can leave the generic error-exit classifier undecided,
    so that one diagnostic is accepted only for a helper already proven not to
    have failure points.
    """

    return (
        not summary.has_ownership_transfer
        and not summary.may_fail
        and not summary.opens
        and bool(summary.cancels)
        and not summary.protects
        and not summary.error_opens
        and not summary.error_protects
        and not summary.unknown_causes
        and set(summary.error_unknown_causes) <= {"unclassified_return_exit"}
        and all(_effect_is_parameter_bound(effect) for effect in summary.cancels)
    )


def _is_exportable_terminal_partition_summary(summary: FunctionSummary) -> bool:
    return (
        summary.may_fail
        and summary.error_partitions_exhaustive
        and bool(summary.error_exit_partitions)
        and all(partition.complete for partition in summary.error_exit_partitions)
        and all(
            partition.terminal_actions
            and not partition.residuals
            and not partition.cancels
            and not partition.protects
            for partition in summary.error_exit_partitions
        )
        and all(
            _effect_is_parameter_bound(action)
            for partition in summary.error_exit_partitions
            for action in partition.terminal_actions
        )
        and not summary.unknown_causes
        and not summary.error_unknown_causes
    )


def _is_exportable_owner_teardown_summary(summary: FunctionSummary) -> bool:
    return (
        not summary.has_ownership_transfer
        and not summary.may_fail
        and bool(summary.owner_teardowns)
        and not summary.opens
        and not summary.protects
        and not summary.error_opens
        and not summary.error_protects
        and not summary.unknown_causes
        and not summary.unresolved_calls
        and set(summary.error_unknown_causes) <= {"unclassified_return_exit"}
        and all(re.fullmatch(r"arg\d+", item.owner) for item in summary.owner_teardowns)
        and all(_effect_is_parameter_bound(effect) for effect in summary.cancels)
    )


def _is_exportable_noop_summary(summary: FunctionSummary) -> bool:
    """Export source-proven helpers that do not touch metadata residual state."""

    return (
        not summary.has_ownership_transfer
        and not summary.may_fail
        and not summary.opens
        and not summary.cancels
        and not summary.protects
        and not summary.error_opens
        and not summary.error_cancels
        and not summary.error_protects
        and not summary.owner_teardowns
        and not summary.unknown_causes
        and not summary.unresolved_calls
        and set(summary.error_unknown_causes) <= {"unclassified_return_exit"}
    )


def _resolve_source_visible_cleanup_direct_summaries(
    summaries: dict[str, FunctionSummary],
    functions: Iterable[FunctionIR],
    *,
    inherited_summaries: dict[str, FunctionSummary] | None = None,
) -> dict[str, FunctionSummary]:
    """Propagate exact cancellation effects through source-visible wrappers."""

    if not summaries:
        return summaries
    function_map = {function.name: function for function in functions}
    inherited = inherited_summaries or {}
    result = dict(summaries)
    changed = True
    while changed:
        changed = False
        visible = {**inherited, **result}
        next_result = dict(result)
        for name, summary in result.items():
            function = function_map.get(name)
            if (
                function is None
                or not summary.unresolved_calls
                or summary.may_fail
                or summary.opens
                or summary.protects
                or summary.has_ownership_transfer
            ):
                continue
            propagated: list[MetadataEffect] = []
            resolved: set[str] = set()
            for callee_name in summary.unresolved_calls:
                callee_summary = visible.get(callee_name)
                if (
                    callee_summary is None
                    or not _is_exportable_cleanup_summary(callee_summary)
                ):
                    continue
                calls = _direct_calls_to(function, callee_name)
                if not calls:
                    continue
                applications = tuple(
                    instantiate_summary(callee_summary, call)
                    for call in calls
                )
                if any(application.unresolved_identities for application in applications):
                    continue
                call_effects = tuple(
                    _effect_at_call_site(effect, function, call, callee_name)
                    for call, application in zip(calls, applications)
                    for effect in application.cancels
                )
                if not call_effects:
                    continue
                propagated.extend(call_effects)
                resolved.add(callee_name)
            if not resolved:
                continue
            next_result[name] = _with_propagated_cleanup_effects(
                function,
                summary,
                tuple(propagated),
                resolved,
            )
            changed = True
        result = next_result
    return result


def _direct_calls_to(
    function: FunctionIR,
    callee_name: str,
) -> tuple[FrontendNode, ...]:
    if function.body_node is None:
        return ()
    calls: list[FrontendNode] = []
    for node in function.body_node.walk():
        if node.type != "call_expression":
            continue
        callee = node.child_by_field_name("function")
        name, _ = call_name_and_args(compact_ws(node.text))
        if callee is not None and callee.type == "identifier" and name == callee_name:
            calls.append(node)
    return tuple(calls)


def _effect_at_call_site(
    effect: MetadataEffect,
    function: FunctionIR,
    call: FrontendNode,
    callee_name: str,
) -> MetadataEffect:
    call_text = compact_ws(call.text)
    evidence = compact_ws(effect.site.expression)
    return replace(
        effect,
        site=SourceSite(
            function.file.as_posix(),
            call.start_line,
            f"{call_text} via {callee_name}: {evidence}",
        ),
    )


def _with_propagated_cleanup_effects(
    function: FunctionIR,
    summary: FunctionSummary,
    propagated: tuple[MetadataEffect, ...],
    resolved: set[str],
) -> FunctionSummary:
    parameters = _ordered_parameters(function)
    parameterized = tuple(
        _parameterize_effect(effect, parameters)
        for effect in propagated
    )
    cancels = tuple(dict.fromkeys((*summary.cancels, *parameterized)))
    all_effects = tuple((*summary.opens, *cancels, *summary.protects))
    exit_effects = _exit_sensitive_effects(function, all_effects)
    error_exit_partitions = _error_exit_partitions(
        function,
        all_effects,
        summary.lifecycle_facts,
    )
    error_opens, error_cancels, error_protects = _failure_effect_projection(
        error_exit_partitions,
        exit_effects,
    )
    unresolved_calls = tuple(
        call for call in summary.unresolved_calls if call not in resolved
    )
    unknown_causes = tuple(
        cause
        for cause in summary.unknown_causes
        if not any(
            cause == f"return_bound_unresolved_helper: {call}"
            for call in resolved
        )
    )
    return FunctionSummary(
        function_name=summary.function_name,
        parameters=summary.parameters,
        returns=summary.returns,
        fresh_identities=summary.fresh_identities,
        has_ownership_transfer=summary.has_ownership_transfer,
        ownership_transfer_roots=summary.ownership_transfer_roots,
        returns_fresh_identity=summary.returns_fresh_identity,
        opens=summary.opens,
        cancels=cancels,
        protects=summary.protects,
        output_identities=summary.output_identities,
        error_opens=error_opens,
        error_cancels=error_cancels,
        error_protects=error_protects,
        failure_effects_complete=exit_effects.error_complete,
        error_unknown_causes=exit_effects.unknown_causes,
        lifecycle_facts=summary.lifecycle_facts,
        exposure_facts=summary.exposure_facts,
        cleanup_footprints=tuple(_cleanup_footprint(effect) for effect in cancels),
        owner_teardowns=summary.owner_teardowns,
        escaping_parameters=summary.escaping_parameters,
        exit_effects=exit_effects,
        error_exit_partitions=error_exit_partitions,
        error_partitions_exhaustive=summary.error_partitions_exhaustive,
        unresolved_calls=unresolved_calls,
        source_file=summary.source_file,
        may_fail=summary.may_fail,
        unknown_escape=bool(unknown_causes),
        unknown_causes=unknown_causes,
        source=summary.source,
        owner_bindings=summary.owner_bindings,
    )


def _attach_indirect_target_sets(
    summaries: dict[str, FunctionSummary],
    functions: Iterable[FunctionIR],
    *,
    max_targets: int = 4,
) -> dict[str, FunctionSummary]:
    """Serialize exact visible target sets even when their semantics differ."""

    function_map = {function.name: function for function in functions}
    result = dict(summaries)
    for name, summary in summaries.items():
        function = function_map.get(name)
        if function is None or function.body_node is None:
            continue
        sets: list[IndirectTargetSet] = []
        resolved = _local_indirect_call_targets(function, summaries)
        pointer_parameters = _called_function_pointer_parameters(function)
        for node in function.body_node.walk():
            if node.type != "call_expression":
                continue
            call_text = compact_ws(node.text)
            callee, _ = call_name_and_args(call_text)
            targets = resolved.get(call_text, ())
            if not targets and callee in pointer_parameters:
                targets = _visible_callback_targets(
                    function.name,
                    pointer_parameters[callee],
                    tuple(functions),
                    summaries,
                )
            has_indirect_cause = (
                f"indirect_call: {call_text}" in summary.unknown_causes
                or f"function_pointer_parameter_call: {callee}" in summary.unknown_causes
            )
            if not targets and not has_indirect_cause:
                continue
            callee_node = node.child_by_field_name("function")
            expression = compact_ws(callee_node.text) if callee_node is not None else callee
            target_tuple = tuple(sorted(set(targets)))
            site = SourceSite(function.file.as_posix(), node.start_line, call_text)
            sets.append(
                IndirectTargetSet(
                    call_site=site,
                    receiver_type=_receiver_type(function, expression),
                    ops_table=expression,
                    possible_targets=target_tuple,
                    complete=(
                        bool(target_tuple)
                        and len(target_tuple) <= max_targets
                        and all(target in summaries for target in target_tuple)
                    ),
                    source_evidence=(site,),
                )
            )
        if sets:
            result[name] = replace(
                summary,
                indirect_target_sets=tuple(dict.fromkeys(sets)),
            )
    return result


def _receiver_type(function: FunctionIR, expression: str) -> str:
    match = re.match(r"[&*()\s]*([A-Za-z_]\w*)", expression)
    if not match:
        return ""
    root = match.group(1)
    symbol = next((item for item in function.symbols if item.name == root), None)
    return compact_ws(symbol.type_spelling) if symbol is not None else ""


def _resolve_bounded_noop_indirect_unknowns(
    summaries: dict[str, FunctionSummary],
    functions: Iterable[FunctionIR],
    *,
    max_targets: int = 4,
) -> dict[str, FunctionSummary]:
    if not summaries:
        return summaries
    function_map = {function.name: function for function in functions}
    result = dict(summaries)
    for name, summary in summaries.items():
        function = function_map.get(name)
        if function is None or not summary.unknown_causes:
            continue
        causes = set(summary.unknown_causes)
        for parameter, index in _called_function_pointer_parameters(function).items():
            cause = f"function_pointer_parameter_call: {parameter}"
            if cause not in causes:
                continue
            targets = _visible_callback_targets(
                function.name,
                index,
                tuple(functions),
                result,
            )
            if _targets_are_residual_noop(targets, result, max_targets=max_targets):
                causes.remove(cause)

        for expression, targets in _local_indirect_call_targets(function, result).items():
            cause = f"indirect_call: {expression}"
            if cause not in causes:
                continue
            if _targets_are_residual_noop(targets, result, max_targets=max_targets):
                causes.remove(cause)
                continue
            common_cleanup = _common_indirect_cleanup(
                function,
                expression,
                targets,
                result,
                max_targets=max_targets,
            )
            if common_cleanup:
                summary = _with_propagated_cleanup_effects(
                    function,
                    summary,
                    common_cleanup,
                    set(),
                )
                causes.remove(cause)

        if causes != set(summary.unknown_causes):
            result[name] = _with_unknown_causes(summary, tuple(sorted(causes)))
    return result


def _resolve_source_visible_noop_direct_unknowns(
    summaries: dict[str, FunctionSummary],
) -> dict[str, FunctionSummary]:
    result = dict(summaries)
    changed = True
    while changed:
        changed = False
        next_result = dict(result)
        for name, summary in result.items():
            resolved = {
                call
                for call in summary.unresolved_calls
                if (callee_summary := result.get(call)) is not None
                and _summary_is_residual_noop(callee_summary)
            }
            if not resolved:
                continue
            unresolved_calls = tuple(
                call for call in summary.unresolved_calls if call not in resolved
            )
            unknown_causes = tuple(
                cause
                for cause in summary.unknown_causes
                if not any(
                    cause == f"return_bound_unresolved_helper: {call}"
                    for call in resolved
                )
            )
            next_result[name] = _with_unresolved_calls_and_unknown_causes(
                summary,
                unresolved_calls,
                unknown_causes,
            )
            changed = True
        result = next_result
    return result


def _targets_are_residual_noop(
    targets: tuple[str, ...],
    summaries: dict[str, FunctionSummary],
    *,
    max_targets: int,
) -> bool:
    if not targets or len(targets) > max_targets:
        return False
    return all(
        (target_summary := summaries.get(target)) is not None
        and _summary_is_residual_noop(target_summary)
        for target in targets
    )


def _common_indirect_cleanup(
    function: FunctionIR,
    expression: str,
    targets: tuple[str, ...],
    summaries: dict[str, FunctionSummary],
    *,
    max_targets: int,
) -> tuple[MetadataEffect, ...]:
    if not targets or len(targets) > max_targets or function.body_node is None:
        return ()
    call = next(
        (
            node
            for node in function.body_node.walk()
            if node.type == "call_expression"
            and compact_ws(node.text) == expression
        ),
        None,
    )
    if call is None:
        return ()
    applications = []
    for target in targets:
        summary = summaries.get(target)
        if summary is None:
            return ()
        application = instantiate_summary(summary, call)
        if (
            application.unknown
            or summary.may_fail
            or application.opens
            or application.protects
            or not application.cancels
        ):
            return ()
        applications.append(application)
    signatures = tuple(
        tuple(_effect_semantic_key(effect) for effect in application.cancels)
        for application in applications
    )
    if not signatures or any(signature != signatures[0] for signature in signatures[1:]):
        return ()
    first_target = targets[0]
    return tuple(
        _effect_at_call_site(effect, function, call, first_target)
        for effect in applications[0].cancels
    )


def _effect_semantic_key(effect: MetadataEffect) -> tuple[str, str, str, str, str]:
    return (
        effect.root,
        effect.key,
        effect.plane.value,
        effect.delta.value,
        effect.value,
    )


def _summary_is_residual_noop(summary: FunctionSummary) -> bool:
    return (
        not summary.opens
        and not summary.cancels
        and not summary.protects
        and not summary.error_opens
        and not summary.error_cancels
        and not summary.error_protects
        and not summary.owner_teardowns
        and not summary.unknown_causes
        and not summary.unresolved_calls
        and not summary.has_ownership_transfer
    )


def _called_function_pointer_parameters(function: FunctionIR) -> dict[str, int]:
    if function.body_node is None:
        return {}
    parameters = _ordered_parameters(function)
    parameter_index = {parameter: index for index, parameter in enumerate(parameters)}
    result: dict[str, int] = {}
    for node in function.body_node.walk():
        if node.type != "call_expression":
            continue
        name, _ = call_name_and_args(compact_ws(node.text))
        if name in parameter_index:
            result[name] = parameter_index[name]
    return result


def _visible_callback_targets(
    callee_name: str,
    parameter_index: int,
    functions: tuple[FunctionIR, ...],
    summaries: dict[str, FunctionSummary],
) -> tuple[str, ...]:
    targets: set[str] = set()
    saw_call = False
    for function in functions:
        if function.body_node is None:
            continue
        for node in function.body_node.walk():
            if node.type != "call_expression":
                continue
            name, args = call_name_and_args(compact_ws(node.text))
            if name != callee_name:
                continue
            saw_call = True
            if parameter_index >= len(args):
                return ()
            target = compact_ws(args[parameter_index]).strip("&()")
            if not re.fullmatch(r"[A-Za-z_]\w*", target):
                return ()
            if target not in summaries:
                return ()
            targets.add(target)
    return tuple(sorted(targets)) if saw_call else ()


def _local_indirect_call_targets(
    function: FunctionIR,
    summaries: dict[str, FunctionSummary],
) -> dict[str, tuple[str, ...]]:
    if function.body_node is None:
        return {}
    assignments = _local_function_pointer_assignments(function, summaries)
    result: dict[str, tuple[str, ...]] = {}
    for node in function.body_node.walk():
        if node.type != "call_expression":
            continue
        callee = node.child_by_field_name("function")
        if callee is None:
            continue
        expression = compact_ws(callee.text)
        target = assignments.get(expression)
        if target:
            result[compact_ws(node.text)] = (target,)
            continue
        targets = _ops_initializer_targets(function, expression, summaries)
        if targets:
            result[compact_ws(node.text)] = targets
    return result


def _local_function_pointer_assignments(
    function: FunctionIR,
    summaries: dict[str, FunctionSummary],
) -> dict[str, str]:
    if function.body_node is None:
        return {}
    result: dict[str, str] = {}
    for node in function.body_node.walk():
        if node.type == "init_declarator":
            declarator = node.child_by_field_name("declarator")
            value = node.child_by_field_name("value")
            name = _declarator_name(declarator) if declarator is not None else None
            target = compact_ws(value.text).strip("&()") if value is not None else ""
            if name and target in summaries:
                result[name] = target
        elif node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is None or right is None:
                continue
            target = compact_ws(right.text).strip("&()")
            if target in summaries:
                result[compact_ws(left.text)] = target
    return result


def _ops_initializer_targets(
    function: FunctionIR,
    expression: str,
    summaries: dict[str, FunctionSummary],
) -> tuple[str, ...]:
    match = re.search(r"(?:->|\.)\s*([A-Za-z_]\w*)$", compact_ws(expression))
    if not match:
        return ()
    field = match.group(1)
    try:
        text = function.file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ()
    matches = re.findall(
        rf"\.\s*{re.escape(field)}\s*=\s*&?\s*([A-Za-z_]\w*)",
        text,
    )
    if not matches or any(item not in summaries for item in matches):
        return ()
    return tuple(sorted(set(matches)))


def _with_unknown_causes(
    summary: FunctionSummary,
    unknown_causes: tuple[str, ...],
) -> FunctionSummary:
    return _with_unresolved_calls_and_unknown_causes(
        summary,
        summary.unresolved_calls,
        unknown_causes,
    )


def _with_unresolved_calls_and_unknown_causes(
    summary: FunctionSummary,
    unresolved_calls: tuple[str, ...],
    unknown_causes: tuple[str, ...],
) -> FunctionSummary:
    return FunctionSummary(
        function_name=summary.function_name,
        parameters=summary.parameters,
        returns=summary.returns,
        fresh_identities=summary.fresh_identities,
        has_ownership_transfer=summary.has_ownership_transfer,
        ownership_transfer_roots=summary.ownership_transfer_roots,
        returns_fresh_identity=summary.returns_fresh_identity,
        opens=summary.opens,
        cancels=summary.cancels,
        protects=summary.protects,
        output_identities=summary.output_identities,
        error_opens=summary.error_opens,
        error_cancels=summary.error_cancels,
        error_protects=summary.error_protects,
        failure_effects_complete=summary.failure_effects_complete,
        error_unknown_causes=summary.error_unknown_causes,
        lifecycle_facts=summary.lifecycle_facts,
        exposure_facts=summary.exposure_facts,
        cleanup_footprints=summary.cleanup_footprints,
        owner_teardowns=summary.owner_teardowns,
        escaping_parameters=summary.escaping_parameters,
        exit_effects=summary.exit_effects,
        error_exit_partitions=summary.error_exit_partitions,
        error_partitions_exhaustive=summary.error_partitions_exhaustive,
        unresolved_calls=unresolved_calls,
        source_file=summary.source_file,
        may_fail=summary.may_fail,
        unknown_escape=bool(unknown_causes),
        unknown_causes=unknown_causes,
        source=summary.source,
        owner_bindings=summary.owner_bindings,
    )


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


@dataclass(frozen=True)
class _PerCpuSlotBinding:
    relation: PerCpuSlotRelation
    body_start_line: int
    body_end_line: int
    accessor_line: int


def _bind_percpu_slot_effects(
    function: FunctionIR,
    effects: tuple[MetadataEffect, ...],
    parameters: tuple[str, ...],
    local_symbols: set[str],
    pointer_locals: set[str],
) -> tuple[MetadataEffect, ...]:
    """Bind effects reached through an exact possible-CPU slot accessor."""

    bindings = _percpu_slot_bindings(
        function,
        parameters,
        local_symbols,
        pointer_locals,
    )
    if not bindings:
        return effects
    result: list[MetadataEffect] = []
    for effect in effects:
        matches = [
            binding
            for binding in bindings
            if (
                binding.accessor_line < effect.site.line <= binding.body_end_line
                and binding.body_start_line <= effect.site.line
                and _rooted_at_symbol(effect.root, binding.relation.slot_local)
            )
        ]
        if len(matches) != 1:
            result.append(effect)
            continue
        relation = matches[0].relation
        result.append(
            replace(
                effect,
                root=_replace_symbols(
                    effect.root,
                    {relation.slot_local: f"PER_CPU_SLOT({relation.base_root})"},
                ),
                percpu_slot_relation=relation,
            )
        )
    return tuple(result)


def _percpu_slot_bindings(
    function: FunctionIR,
    parameters: tuple[str, ...],
    local_symbols: set[str],
    pointer_locals: set[str],
) -> tuple[_PerCpuSlotBinding, ...]:
    if function.body_node is None:
        return ()
    parameter_set = set(parameters)
    result: list[_PerCpuSlotBinding] = []
    for loop in function.body_node.walk():
        if loop.type != "function_definition":
            continue
        loop_type = loop.child_by_field_name("type")
        declarator = loop.child_by_field_name("declarator")
        body = loop.child_by_field_name("body")
        if (
            loop_type is None
            or compact_ws(loop_type.text) != "for_each_possible_cpu"
            or declarator is None
            or declarator.type != "parenthesized_declarator"
            or body is None
            or body.type != "compound_statement"
        ):
            continue
        index_local = compact_ws(declarator.text).strip("()")
        if (
            re.fullmatch(r"[A-Za-z_]\w*", index_local) is None
            or index_local not in local_symbols
            or index_local in pointer_locals
        ):
            continue
        if any(node.type in _CONTAINER_LOOP_ESCAPE_TYPES for node in body.walk()):
            continue
        accessors: list[tuple[FrontendNode, str, str]] = []
        for statement in body.children:
            assignment = _top_level_assignment(statement)
            if assignment is None:
                continue
            left, right = assignment
            slot_local = compact_ws(left.text)
            accessor_name, args = call_name_and_args(compact_ws(right.text))
            if (
                slot_local not in pointer_locals
                or accessor_name != "per_cpu_ptr"
                or len(args) != 2
                or compact_ws(args[1]).strip("()") != index_local
            ):
                continue
            base_root = _parameter_container_path(args[0], parameter_set)
            if not base_root:
                continue
            accessors.append((statement, slot_local, base_root))
        if len(accessors) != 1:
            continue
        accessor, slot_local, base_root = accessors[0]
        if _local_assignment_count(function, slot_local) != 1:
            continue
        if _local_has_initializer(function, slot_local):
            continue
        loop_site = SourceSite(
            function.file.as_posix(),
            loop.start_line,
            f"for_each_possible_cpu({index_local})",
        )
        accessor_site = SourceSite(
            function.file.as_posix(),
            accessor.start_line,
            compact_ws(accessor.text),
        )
        relation = PerCpuSlotRelation(
            base_root=base_root,
            slot_local=slot_local,
            index_local=index_local,
            loop_site=loop_site,
            accessor_site=accessor_site,
            source_identity=(
                f"{function.file.as_posix()}:{loop.start_line}:"
                f"{slot_local}:per_cpu_ptr({base_root},{index_local})"
            ),
        )
        result.append(
            _PerCpuSlotBinding(
                relation=relation,
                body_start_line=body.start_line,
                body_end_line=body.end_line,
                accessor_line=accessor.start_line,
            )
        )
    return tuple(result)


def _top_level_assignment(
    statement: FrontendNode,
) -> tuple[FrontendNode, FrontendNode] | None:
    if statement.type != "expression_statement":
        return None
    assignments = [
        child for child in statement.children if child.type == "assignment_expression"
    ]
    if len(assignments) != 1:
        return None
    assignment = assignments[0]
    left = assignment.child_by_field_name("left")
    right = assignment.child_by_field_name("right")
    return (left, right) if left is not None and right is not None else None


def _local_assignment_count(function: FunctionIR, local: str) -> int:
    if function.body_node is None:
        return 0
    return sum(
        1
        for node in function.body_node.walk()
        if node.type == "assignment_expression"
        and node.child_by_field_name("left") is not None
        and compact_ws(node.child_by_field_name("left").text) == local
    )


def _local_has_initializer(function: FunctionIR, local: str) -> bool:
    if function.body_node is None:
        return False
    return any(
        node.type == "init_declarator"
        and _declarator_name(node.child_by_field_name("declarator")) == local
        for node in function.body_node.walk()
    )


def _rooted_at_symbol(root: str, symbol: str) -> bool:
    return re.match(rf"^{re.escape(symbol)}(?=$|->|\.)", compact_ws(root)) is not None


_CONTAINER_LOOP_ESCAPE_TYPES = {
    "break_statement",
    "continue_statement",
    "goto_statement",
    "return_statement",
}


def _bind_exhaustive_container_cleanups(
    function: FunctionIR,
    effects: tuple[MetadataEffect, ...],
    parameters: tuple[str, ...],
    pointer_locals: set[str],
) -> tuple[MetadataEffect, ...]:
    """Bind an unconditional safe-list drain to its parameter container."""

    relations = _exhaustive_container_cleanup_relations(
        function,
        parameters,
        pointer_locals,
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


def _bind_existential_member_identities(
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
            local = _declarator_name(declarator) or ""
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
            function.file.as_posix(),
            node.start_line,
            compact_ws(node.text),
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
            function.file.as_posix(),
            node.start_line,
            compact_ws(node.text),
        )
        if store_site.line > load_site.line:
            continue
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
        if local not in provenance:
            bound.append(effect)
            continue
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
    """Match an alias-expanded aggregate member to one proven local load."""

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
    if len(matches) != 1:
        return None
    return matches[0]


def _aggregate_member_family(expression: str) -> str | None:
    value = compact_ws(expression).strip("() ")
    if "[" not in value or not re.fullmatch(
        r"[A-Za-z_]\w*(?:(?:->|\.)[A-Za-z_]\w*|\[[^\]]+\])+",
        value,
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
            if not container_root:
                continue
            if any(
                node.type in _CONTAINER_LOOP_ESCAPE_TYPES
                for node in body.walk()
            ):
                continue
            removal = _unconditional_iterator_removal(
                body,
                iterator,
                member_field,
            )
            if removal is None:
                continue
            relation = ContainerIterationCleanup(
                container_root=container_root,
                iterator=iterator,
                next_iterator=next_iterator,
                member_field=member_field,
                iteration_site=SourceSite(
                    function.file.as_posix(),
                    loop_call.start_line,
                    compact_ws(loop_call.text),
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
        r"([A-Za-z_]\w*)((?:(?:->|\.)[A-Za-z_]\w*)+)",
        path,
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


def _is_parameter_owned(
    path: str,
    parameters: set[str],
    owner_aliases: dict[str, str] | None = None,
) -> bool:
    match = re.match(r"^([A-Za-z_]\w*)", compact_ws(path).lstrip("&*()"))
    return bool(
        match
        and (
            match.group(1) in parameters
            or match.group(1) in (owner_aliases or {})
        )
    )


def _plain_local_symbol(
    text: str,
    allocations: dict[str, int],
) -> str | None:
    value = compact_ws(text).strip("()")
    return value if value in allocations else None


def _base_local_symbol(
    text: str,
    allocations: dict[str, int],
) -> str | None:
    match = re.match(r"^([A-Za-z_]\w*)", compact_ws(text).lstrip("&*()"))
    if match and match.group(1) in allocations:
        return match.group(1)
    return None


def _field_path(root: str, key: str) -> str:
    return f"{root}->{key}" if root else key


def _parameterize_path(
    path: str,
    parameters: tuple[str, ...],
    owner_aliases: dict[str, str] | None = None,
) -> str:
    mapping = {name: f"arg{index}" for index, name in enumerate(parameters)}
    mapping.update(owner_aliases or {})
    return _replace_symbols(path, mapping)


def _references_unbound_local(
    effect: MetadataEffect,
    local_symbols: set[str],
) -> bool:
    return bool(_unbound_local_tokens(effect, local_symbols))


def _references_only_private_fresh(
    effect: MetadataEffect,
    local_symbols: set[str],
    private_fresh_locals: set[str],
) -> bool:
    tokens = _unbound_local_tokens(effect, local_symbols)
    if "(" in effect.site.expression:
        tokens.update(_unbound_tokens_in_text(effect.site.expression, local_symbols))
    return bool(tokens) and tokens <= private_fresh_locals


def _unbound_local_tokens(
    effect: MetadataEffect,
    local_symbols: set[str],
) -> set[str]:
    if not local_symbols:
        return set()
    parts = [effect.root]
    if effect.delta in {MetadataDelta.ADD, MetadataDelta.REMOVE, MetadataDelta.PROTECT}:
        parts.append(effect.value)
    return _unbound_tokens_in_text(" ".join(parts), local_symbols)


def _unbound_tokens_in_text(text: str, local_symbols: set[str]) -> set[str]:
    result: set[str] = set()
    for match in re.finditer(r"\b[A-Za-z_]\w*\b", text):
        token = match.group(0)
        if token not in local_symbols:
            continue
        if _is_field_component(text, match.start()):
            continue
        result.add(token)
    return result


def _is_field_component(text: str, start: int) -> bool:
    return text[max(0, start - 2) : start] == "->" or text[max(0, start - 1) : start] == "."


def _local_symbols(function: FunctionIR) -> set[str]:
    if function.body_node is None:
        return set()
    parameters = set(_ordered_parameters(function))
    symbols: set[str] = set()
    for node in function.body_node.walk():
        if node.type != "declaration":
            continue
        for declarator in _declaration_declarators(node):
            name = _declarator_name(declarator)
            if name:
                symbols.add(name)
    return symbols - parameters


def _success_return_symbols(
    function: FunctionIR,
    pointer_local_symbols: set[str],
) -> set[str]:
    expressions = _success_return_expressions(function)
    return {
        expression
        for expression in expressions
        if expression in pointer_local_symbols
    }


def _local_pointer_symbols(function: FunctionIR) -> set[str]:
    if function.body_node is None:
        return set()
    symbols: set[str] = set()
    for node in function.body_node.walk():
        if node.type != "declaration":
            continue
        for declarator in _declaration_declarators(node):
            if not _contains_node_type(declarator, "pointer_declarator"):
                continue
            name = _declarator_name(declarator)
            if name:
                symbols.add(name)
    return symbols


def _declaration_declarators(node: FrontendNode) -> tuple[FrontendNode, ...]:
    declarator_types = {
        "array_declarator",
        "attributed_declarator",
        "identifier",
        "init_declarator",
        "parenthesized_declarator",
        "pointer_declarator",
    }
    result = tuple(child for child in node.children if child.type in declarator_types)
    if result:
        return result
    declarator = node.child_by_field_name("declarator")
    return (declarator,) if declarator is not None else ()


def _contains_node_type(node: FrontendNode | None, node_type: str) -> bool:
    return node is not None and any(child.type == node_type for child in node.walk())


def _success_return_expressions(function: FunctionIR) -> tuple[str, ...]:
    if function.body_node is not None:
        returns = [
            _return_expression(node)
            for node in function.body_node.walk()
            if node.type == "return_statement"
        ]
    else:
        returns = [
            extract_return_expr(line) or ""
            for line in function.body.splitlines()
            if "return" in line
        ]
    returns = [compact_ws(item) for item in returns if compact_ws(item)]
    return (returns[-1],) if returns else ()


def _return_expression(node: FrontendNode) -> str:
    for child in node.children:
        if child.type in {"return", ";"}:
            continue
        return compact_ws(child.text)
    return extract_return_expr(node.text) or ""


def _ordered_parameters(function: FunctionIR) -> tuple[str, ...]:
    if function.ast_node is not None:
        declarator = _find_child_type(function.ast_node, "function_declarator")
        params = _find_child_type(declarator, "parameter_list")
        if params is not None:
            names: list[str] = []
            for child in params.children:
                if child.type not in {"parameter_declaration", "optional_parameter_declaration"}:
                    continue
                name = _parameter_name(child)
                if name and name != "void":
                    names.append(name)
            if names:
                return tuple(names)
    parsed = _parameters_from_signature(function.signature)
    if parsed:
        return parsed
    return tuple(sorted(function.parameters))


def _parameter_name(node: FrontendNode) -> str | None:
    identifiers = [
        child.text.strip()
        for child in node.walk()
        if child.type in {"identifier", "field_identifier"}
    ]
    return identifiers[-1] if identifiers else None


def _declarator_name(node: FrontendNode | None) -> str | None:
    if node is None:
        return None
    if node.type == "identifier":
        return node.text.strip()
    nested = node.child_by_field_name("declarator")
    if nested is not None:
        return _declarator_name(nested)
    identifiers = [
        child.text.strip()
        for child in node.walk()
        if child.type in {"identifier", "field_identifier"}
    ]
    return identifiers[-1] if identifiers else None


def _parameters_from_signature(signature: str) -> tuple[str, ...]:
    close_idx = signature.rfind(")")
    open_idx = signature.rfind("(", 0, close_idx)
    if open_idx == -1 or close_idx == -1 or close_idx <= open_idx:
        return ()
    result: list[str] = []
    for arg in split_args(signature[open_idx + 1 : close_idx]):
        arg = arg.strip()
        if not arg or arg == "void" or arg == "...":
            continue
        match = re.search(r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?$", arg.replace("*", " "))
        if match and match.group(1) != "void":
            result.append(match.group(1))
    return tuple(result)


def _find_child_type(node: FrontendNode | None, node_type: str) -> FrontendNode | None:
    if node is None:
        return None
    if node.type == node_type:
        return node
    for child in node.children:
        found = _find_child_type(child, node_type)
        if found is not None:
            return found
    return None


def _is_static_function(function: FunctionIR) -> bool:
    return bool(re.search(r"\bstatic\b", function.signature))


def _is_project_summary_candidate(function: FunctionIR) -> bool:
    if not _is_static_function(function):
        return True
    return (
        function.file.suffix == ".h"
        and bool(re.search(r"\binline\b", function.signature))
    )


def _unknown_escape_causes(function: FunctionIR) -> tuple[str, ...]:
    if function.body_node is None:
        return ("missing_function_body",)
    causes: list[str] = []
    for node in function.body_node.walk():
        if node.type != "call_expression":
            continue
        name, _ = call_name_and_args(compact_ws(node.text))
        if name in UNKNOWN_CALLS:
            causes.append(f"async_or_deferred_handoff: {name}")
        callee_node = node.child_by_field_name("function")
        if (
            callee_node is not None
            and callee_node.type != "identifier"
            and not _looks_like_scalar_cast_call(compact_ws(node.text))
        ):
            causes.append(f"indirect_call: {compact_ws(node.text)}")
        if name in function.parameters:
            causes.append(f"function_pointer_parameter_call: {name}")
    return tuple(sorted(set(causes)))


def _looks_like_scalar_cast_call(expression: str) -> bool:
    """Reject tree-sitter call-shaped scalar casts from indirect-call UNKNOWNs."""

    return bool(
        re.match(
            r"^\(\s*(?:(?:u|s)(?:8|16|32|64)|size_t|ssize_t|"
            r"unsigned(?:\s+(?:char|short|int|long))?|"
            r"signed(?:\s+(?:char|short|int|long))?|"
            r"char|short|int|long|bool)\s*\)\s*\(",
            expression,
        )
    )


def _unresolved_metadata_helper_names(
    function: FunctionIR,
    raw_effects: tuple[MetadataEffect, ...],
) -> tuple[str, ...]:
    if function.body_node is None:
        return ()
    known_effect_sites = {
        (effect.site.line, compact_ws(effect.site.expression))
        for effect in raw_effects
    }
    names: list[str] = []
    for node in function.body_node.walk():
        if node.type != "call_expression":
            continue
        name, _ = call_name_and_args(compact_ws(node.text))
        if not _looks_like_metadata_helper(name):
            continue
        if (node.start_line, compact_ws(node.text)) in known_effect_sites:
            continue
        names.append(name)
    return tuple(sorted(set(names)))


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
