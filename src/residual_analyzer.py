"""Residual analyzer orchestration."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

from .function_summary import FunctionSummary, build_same_file_summaries
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


DEFAULT_SCOPE_RATIONALE = (
    "source-visible metadata effects are in STRUCTURAL, ACCOUNTING, or RECOVERY "
    "residual scope"
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
) -> ResidualAnalysisResult:
    """Run slicing and emit M6 witness reports for one function."""

    source_version = source_version_for(function)
    if summaries is None and all_functions is not None:
        summaries = build_same_file_summaries(all_functions)
    slicing = slice_function_residuals(function, summaries=summaries or {})
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
    return tuple(
        analyze_function_residuals(
            function,
            all_functions=function_tuple,
            summaries=summaries,
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
        ReportKind.METADATA_RESIDUAL_UNKNOWN,
    }:
        return True
    return include_all


def _scope_rationale_for(
    residual_slice: ResidualSlice,
    default: str,
) -> str:
    if residual_slice.state in {ResidualState.CLOSED, ResidualState.PROTECTED}:
        return "no in-scope residual remains after normalization"
    return default


def _unknown_causes_for(residual_slice: ResidualSlice) -> tuple[str, ...]:
    if residual_slice.state is not ResidualState.UNKNOWN or not residual_slice.rationale:
        return ()
    return tuple(
        item.strip()
        for item in residual_slice.rationale.split(";")
        if item.strip()
    )
