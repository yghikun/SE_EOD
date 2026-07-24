"""Lightweight same-file function summaries for metadata residual analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .effect_extractor import extract_metadata_effects, looks_like_metadata_reader
from .cfg import build_cfg
from .failure_points import find_failure_points
from .frontend.model import FrontendNode, FunctionIR
from .metadata_residual import MetadataDelta, MetadataEffect, MetadataPlane, SourceSite
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
    "kzalloc",
    "kvcalloc",
    "kvmalloc",
    "kvzalloc",
    "malloc",
    "mempool_alloc",
    "vmalloc",
    "vzalloc",
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
    exit_effects: ExitSensitiveEffects = ExitSensitiveEffects()
    unresolved_calls: tuple[str, ...] = ()
    source_file: str = ""
    may_fail: bool = False
    unknown_escape: bool = False
    unknown_causes: tuple[str, ...] = ()
    source: SummarySource = SummarySource.UNKNOWN

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
            "exit_effects": self.exit_effects.to_dict(),
            "unresolved_calls": list(self.unresolved_calls),
            "source_file": self.source_file,
            "may_fail": self.may_fail,
            "unknown_escape": self.unknown_escape,
            "unknown_causes": list(self.unknown_causes),
            "source": self.source.value,
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
    exit_effects: ExitSensitiveEffects = ExitSensitiveEffects()
    returns: tuple[str, ...] = ()
    unresolved_identities: tuple[str, ...] = ()
    ownership_transfer_roots: tuple[str, ...] = ()

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
            "exit_effects": self.exit_effects.to_dict(),
            "returns": list(self.returns),
            "unresolved_identities": list(self.unresolved_identities),
            "ownership_transfer_roots": list(self.ownership_transfer_roots),
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
    return_symbols = _success_return_symbols(function, pointer_locals)
    raw_effects = tuple(extract_metadata_effects(function))
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
    )
    output_mapping = _output_transfer_mapping(
        function,
        parameters,
        pointer_locals,
        fresh_allocation_lines,
    )
    transfer_mapping = {**transfer_mapping, **output_mapping}
    exposure_facts = _build_exposure_facts(
        function,
        raw_effects,
        parameters,
        pointer_locals,
        fresh_allocation_lines,
        transfer_mapping,
        return_symbols,
    )
    parameterized_effects = tuple(
        _parameterize_effect(
            effect,
            parameters,
            return_symbols,
            transfer_mapping,
        )
        for effect in raw_effects
    )
    returns = tuple(
        _replace_symbols(
            item,
            _summary_symbol_mapping(parameters, return_symbols, transfer_mapping),
        )
        for item in _success_return_expressions(function)
    )
    unbound_local_symbols = local_symbols - set(transfer_mapping)
    dropped_effects = tuple(
        effect
        for effect in parameterized_effects
        if _references_unbound_local(effect, unbound_local_symbols)
    )
    effects = tuple(
        effect
        for effect in parameterized_effects
        if effect not in dropped_effects
    )
    private_fresh_locals = set(fresh_allocation_lines) - set(transfer_mapping)
    dropped_unbound_effect = any(
        not _references_only_private_fresh(effect, unbound_local_symbols, private_fresh_locals)
        for effect in dropped_effects
    )
    has_return_bound_effect = any(
        _effect_references_return(effect)
        for effect in effects
    )
    unresolved_helper_names = _unresolved_metadata_helper_names(function, raw_effects)
    unknown_causes: list[str] = []
    unknown_causes.extend(_unknown_escape_causes(function))
    if dropped_unbound_effect:
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
    error_opens = tuple(
        effect for effect in exit_effects.error_must if effect.delta in OPEN_DELTAS
    )
    error_cancels = tuple(
        effect for effect in exit_effects.error_must if effect.delta in CANCEL_DELTAS
    )
    error_protects = tuple(
        effect for effect in exit_effects.error_must if effect.delta in PROTECT_DELTAS
    )
    lifecycle_facts = _build_lifecycle_facts(
        function,
        effects,
        exit_effects.error_may,
        transfer_mapping,
        return_symbols,
        fresh_allocation_lines,
    )
    cleanup_footprints = tuple(_cleanup_footprint(effect) for effect in cancels)
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
        error_opens=error_opens,
        error_cancels=error_cancels,
        error_protects=error_protects,
        failure_effects_complete=exit_effects.error_complete,
        error_unknown_causes=exit_effects.unknown_causes,
        lifecycle_facts=lifecycle_facts,
        exposure_facts=exposure_facts,
        cleanup_footprints=cleanup_footprints,
        exit_effects=exit_effects,
        unresolved_calls=unresolved_helper_names,
        source_file=function.file.as_posix(),
        may_fail=bool(find_failure_points(function)) or _has_error_return(function),
        unknown_escape=bool(unknown_causes),
        unknown_causes=tuple(sorted(set(unknown_causes))),
        source=SummarySource.AUTO_LOCAL,
    )


def build_same_file_summaries(
    functions: Iterable[FunctionIR],
    *,
    inherited_summaries: dict[str, FunctionSummary] | None = None,
) -> dict[str, FunctionSummary]:
    """Build summaries for visible static helpers in a translation unit."""

    function_tuple = tuple(functions)
    static_functions = tuple(function for function in function_tuple if _is_static_function(function))
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
            for function in static_functions
        }
        discovered = {
            name
            for name, summary in summaries.items()
            if summary.returns_fresh_identity
        }
        if discovered <= fresh_return_helpers:
            break
        fresh_return_helpers.update(discovered)
    summaries = _resolve_source_visible_noop_direct_unknowns(summaries)
    return _resolve_bounded_noop_indirect_unknowns(summaries, function_tuple)


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
        built_summaries = _resolve_source_visible_noop_direct_unknowns(built_summaries)
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
    return _resolve_bounded_noop_indirect_unknowns(summaries, function_tuple)


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
    return tuple(
        LocalLifecycleBinding(
            local_identity=local,
            allocation_line=line,
            publication_lines=tuple(sorted(publication_lines.get(local, set()))),
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
    exit_effects = _instantiate_exit_sensitive_effects(summary.exit_effects, mapping)
    returns = tuple(_replace_symbols(item, mapping) for item in summary.returns)
    transfer_roots = tuple(
        _replace_symbols(item, mapping)
        for item in summary.ownership_transfer_roots
    )
    return SummaryApplication(
        summary,
        opens,
        cancels,
        protects,
        error_opens,
        error_cancels,
        error_protects,
        summary.failure_effects_complete,
        summary.error_unknown_causes,
        lifecycle_facts,
        exposure_facts,
        cleanup_footprints,
        exit_effects,
        returns,
        unresolved,
        transfer_roots,
    )


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
    return MetadataEffect(
        root=_replace_symbols(effect.root, mapping),
        key=_replace_symbols(effect.key, key_mapping),
        plane=effect.plane,
        delta=effect.delta,
        value=_replace_symbols(effect.value, mapping),
        site=effect.site,
    )


def _instantiate_effect(
    effect: MetadataEffect,
    mapping: dict[str, str],
) -> MetadataEffect:
    return MetadataEffect(
        root=_replace_symbols(effect.root, mapping),
        key=_replace_symbols(effect.key, mapping),
        plane=effect.plane,
        delta=effect.delta,
        value=_replace_symbols(effect.value, mapping),
        site=effect.site,
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

        if not _is_parameter_owned(effect.root, parameter_set):
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
                        target=_parameterize_path(effect.root, parameters),
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
    return tuple(sorted(set(unresolved)))


def _summary_tokens(effect: MetadataEffect) -> set[str]:
    joined = " ".join([effect.root, effect.key, effect.value])
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
        if not _is_parameter_owned(effect.root, parameter_set):
            continue
        if effect.delta is MetadataDelta.SET:
            local = _plain_local_symbol(effect.value, allocation_lines)
            if local is not None and allocation_lines[local] <= effect.site.line:
                target = _parameterize_path(
                    _field_path(effect.root, effect.key),
                    parameters,
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
        exit_effects=summary.exit_effects,
        unresolved_calls=summary.unresolved_calls,
        source_file=summary.source_file,
        may_fail=summary.may_fail,
        unknown_escape=summary.unknown_escape,
        unknown_causes=summary.unknown_causes,
        source=source,
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
        and not summary.unknown_causes
        and not summary.unresolved_calls
        and set(summary.error_unknown_causes) <= {"unclassified_return_exit"}
    )


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


def _summary_is_residual_noop(summary: FunctionSummary) -> bool:
    return (
        not summary.opens
        and not summary.cancels
        and not summary.protects
        and not summary.error_opens
        and not summary.error_cancels
        and not summary.error_protects
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
    targets = {
        item
        for item in re.findall(
            rf"\.\s*{re.escape(field)}\s*=\s*&?\s*([A-Za-z_]\w*)",
            text,
        )
        if item in summaries
    }
    return tuple(sorted(targets)) if len(targets) == 1 else ()


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
        exit_effects=summary.exit_effects,
        unresolved_calls=unresolved_calls,
        source_file=summary.source_file,
        may_fail=summary.may_fail,
        unknown_escape=bool(unknown_causes),
        unknown_causes=unknown_causes,
        source=summary.source,
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
        exit_effects=ExitSensitiveEffects(
            error_complete=summary.exit_effects.error_complete,
        ),
        unresolved_calls=summary.unresolved_calls,
        source_file=summary.source_file,
        may_fail=summary.may_fail,
        unknown_escape=False,
        unknown_causes=(),
        source=SummarySource.AUTO_INTERPROCEDURAL,
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


def _is_parameter_owned(path: str, parameters: set[str]) -> bool:
    match = re.match(r"^([A-Za-z_]\w*)", compact_ws(path).lstrip("&*()"))
    return bool(match and match.group(1) in parameters)


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


def _parameterize_path(path: str, parameters: tuple[str, ...]) -> str:
    return _replace_symbols(path, {name: f"arg{index}" for index, name in enumerate(parameters)})


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
        if callee_node is not None and callee_node.type != "identifier":
            causes.append(f"indirect_call: {compact_ws(node.text)}")
        if name in function.parameters:
            causes.append(f"function_pointer_parameter_call: {name}")
    return tuple(sorted(set(causes)))


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
