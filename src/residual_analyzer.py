"""Residual analyzer orchestration."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

from .function_summary import FunctionSummary, build_same_file_summaries
from .failure_domain import refine_static_callee_containment
from .frontend.model import FunctionIR
from .metadata_residual import (
    MetadataResidualReport,
    ReportKind,
    ResidualSlice,
    ResidualState,
    residual_report,
)
from .residual_report import ResidualWitnessReport
from .residual_slicer import ResidualSlicingResult, slice_function_residuals
from .transient_provenance import TransientArgumentProvenance


DEFAULT_SCOPE_RATIONALE = (
    "source-visible filesystem metadata effects are in STRUCTURAL, "
    "ACCOUNTING, or RECOVERY residual scope"
)


@dataclass(frozen=True)
class ResidualAnalysisResult:
    function: str
    source_version: str
    reports: tuple[ResidualWitnessReport, ...]
    slicing_result: ResidualSlicingResult

    @property
    def candidates(self) -> tuple[ResidualWitnessReport, ...]:
        return tuple(
            report
            for report in self.reports
            if report.kind is ReportKind.UNCLOSED_METADATA_RESIDUAL
            and report.confidence == "candidate"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "function": self.function,
            "source_version": self.source_version,
            "reports": [report.to_dict() for report in self.reports],
            "candidate_count": len(self.candidates),
            "candidate_count_legacy_alias_of": "function_boundary_residual_count",
            "function_boundary_residual_count": len(self.candidates),
            "unknown_count": sum(
                report.kind is ReportKind.METADATA_RESIDUAL_UNKNOWN
                for report in self.reports
            ),
            "slicing_result": self.slicing_result.to_dict(),
        }


def analyze_function_residuals(
    function: FunctionIR,
    *,
    all_functions: Iterable[FunctionIR] | None = None,
    summaries: dict[str, FunctionSummary] | None = None,
    include_all: bool = False,
    scope_rationale: str = DEFAULT_SCOPE_RATIONALE,
    mdr_evidence: str = "",
    transient_provenance: dict[str, tuple[TransientArgumentProvenance, ...]] | None = None,
) -> ResidualAnalysisResult:
    """Run slicing and emit M6 witness reports for one function."""

    source_version = source_version_for(function)
    if summaries is None and all_functions is not None:
        summaries = build_same_file_summaries(all_functions)
    slicing = slice_function_residuals(
        function,
        summaries=summaries or {},
        transient_provenance=(transient_provenance or {}).get(function.function_id, ()),
    )
    return _analysis_from_slicing(
        function,
        slicing,
        include_all=include_all,
        scope_rationale=scope_rationale,
        mdr_evidence=mdr_evidence,
    )


def _analysis_from_slicing(
    function: FunctionIR,
    slicing: ResidualSlicingResult,
    *,
    include_all: bool,
    scope_rationale: str,
    mdr_evidence: str = "",
) -> ResidualAnalysisResult:
    source_version = source_version_for(function)
    reports: list[ResidualWitnessReport] = []

    for residual_slice in slicing.slices:
        report = residual_report(
            function=function.name,
            residual_slice=residual_slice,
            scope_rationale=_scope_rationale_for(residual_slice, scope_rationale),
            mdr_evidence=mdr_evidence,
        )
        if _should_emit(report, include_all=include_all):
            reports.append(
                ResidualWitnessReport(
                    report=report,
                    source_version=source_version,
                    unknown_causes=_unknown_causes_for(residual_slice),
                )
            )

    return ResidualAnalysisResult(
        function=function.name,
        source_version=source_version,
        reports=tuple(reports),
        slicing_result=slicing,
    )


def analyze_functions(
    functions: Iterable[FunctionIR],
    *,
    inherited_summaries: dict[str, FunctionSummary] | None = None,
    include_all: bool = False,
    scope_rationale: str = DEFAULT_SCOPE_RATIONALE,
    transient_provenance: dict[str, tuple[TransientArgumentProvenance, ...]] | None = None,
) -> tuple[ResidualAnalysisResult, ...]:
    """Analyze a set of functions using same-file static helper summaries."""

    function_tuple = tuple(functions)
    inherited = inherited_summaries or {}
    summaries = {
        **inherited,
        **build_same_file_summaries(
            function_tuple,
            inherited_summaries=inherited,
        ),
    }
    slicings = {
        function.function_id: slice_function_residuals(
            function,
            summaries=summaries,
            transient_provenance=(transient_provenance or {}).get(function.function_id, ()),
        )
        for function in function_tuple
    }
    slicings = refine_static_callee_containment(
        function_tuple,
        slicings,
        summaries,
    )
    return tuple(
        _analysis_from_slicing(
            function,
            slicings[function.function_id],
            include_all=include_all,
            scope_rationale=scope_rationale,
        )
        for function in function_tuple
    )


def source_version_for(function: FunctionIR) -> str:
    payload = function.source.encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()[:16]


def _should_emit(
    report: MetadataResidualReport,
    *,
    include_all: bool,
) -> bool:
    if report.kind in {
        ReportKind.UNCLOSED_METADATA_RESIDUAL,
        ReportKind.CONTAINED_METADATA_RESIDUAL,
        ReportKind.METADATA_RESIDUAL_UNKNOWN,
        ReportKind.METADATA_RESIDUAL_REVIEW,
    }:
        return True
    return include_all


def _scope_rationale_for(
    residual_slice: ResidualSlice,
    default: str,
) -> str:
    if residual_slice.state in {ResidualState.CLOSED, ResidualState.PROTECTED}:
        return "no in-scope filesystem metadata residual remains after normalization"
    if residual_slice.state is ResidualState.CONTAINED:
        return (
            "a source-visible residual remains, but source-proven teardown or a "
            "terminal failure domain prevents ordinary live continuation"
        )
    return default


def _unknown_causes_for(residual_slice: ResidualSlice) -> tuple[str, ...]:
    if residual_slice.state is not ResidualState.UNKNOWN or not residual_slice.rationale:
        return ()
    return tuple(
        item.strip()
        for item in residual_slice.rationale.split(";")
        if item.strip()
    )
