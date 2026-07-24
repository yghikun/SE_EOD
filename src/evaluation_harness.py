"""Small evaluation driver for metadata residual analysis."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from fnmatch import fnmatch
from typing import Any, Iterable

from .frontend.tree_sitter_frontend import TreeSitterFrontend
from .function_summary import FunctionSummary, build_project_summaries
from .frontend.model import FunctionIR
from .metadata_residual import ReportKind
from .residual_analyzer import ResidualAnalysisResult, analyze_functions
from .residual_report import (
    ResidualWitnessReport,
    reports_to_json,
    reports_to_markdown,
)
from .unknown_triage import unknown_cause_category


EVALUATION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ConfirmedBugRecord:
    bug_id: int
    filesystem: str = ""
    function: str = ""
    bug_type: str = ""
    status: str = ""
    evidence: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "bug_id": self.bug_id,
            "filesystem": self.filesystem,
            "function": self.function,
            "bug_type": self.bug_type,
            "status": self.status,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class EvaluationResult:
    source_file: str
    output_dir: str
    source_root: str
    analyses: tuple[ResidualAnalysisResult, ...]
    reports: tuple[ResidualWitnessReport, ...]
    confirmed_bug_records: tuple[ConfirmedBugRecord, ...] = ()

    @property
    def summary(self) -> dict[str, object]:
        kind_counts = Counter(report.kind.value for report in self.reports)
        state_counts = Counter(
            residual_slice.state.value
            for analysis in self.analyses
            for residual_slice in analysis.slicing_result.slices
        )
        unknown_cause_counts = Counter(
            unknown_cause_category(cause)
            for report in self.reports
            for cause in report.unknown_causes
        )
        candidate_count = kind_counts[ReportKind.UNCLOSED_METADATA_RESIDUAL.value]
        unknown_count = kind_counts[ReportKind.METADATA_RESIDUAL_UNKNOWN.value]
        out_of_scope_count = kind_counts[ReportKind.OUT_OF_SCOPE.value]
        mapped_functions = {
            _function_name_key(record.function)
            for record in self.confirmed_bug_records
            if record.function
        }
        analyzed_functions = {_function_name_key(analysis.function) for analysis in self.analyses}
        return {
            "schema_version": EVALUATION_SCHEMA_VERSION,
            "source_file": self.source_file,
            "source_root": self.source_root,
            "output_dir": self.output_dir,
            "functions_analyzed": len(self.analyses),
            "functions_with_failure_points": sum(
                bool(analysis.slicing_result.slices) for analysis in self.analyses
            ),
            "reports_written": len(self.reports),
            "candidate_count": candidate_count,
            "unknown_count": unknown_count,
            "out_of_scope_count": out_of_scope_count,
            "report_kind_counts": dict(sorted(kind_counts.items())),
            "residual_state_counts": dict(sorted(state_counts.items())),
            "unknown_cause_counts": dict(sorted(unknown_cause_counts.items())),
            "confirmed_bug_records": len(self.confirmed_bug_records),
            "confirmed_bug_functions_in_source": sorted(
                mapped_functions & analyzed_functions
            ),
            "configuration_note": (
                "uses metadata scope plus source-derived summaries; no protocol "
                "family or rule registry is loaded"
            ),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "analyses": [analysis.to_dict() for analysis in self.analyses],
            "confirmed_bug_records": [
                record.to_dict() for record in self.confirmed_bug_records
            ],
        }


@dataclass(frozen=True)
class BatchEvaluationResult:
    source_path: str
    output_dir: str
    source_root: str
    results: tuple[EvaluationResult, ...]
    confirmed_bug_records: tuple[ConfirmedBugRecord, ...] = ()
    exclude_globs: tuple[str, ...] = ()

    @property
    def reports(self) -> tuple[ResidualWitnessReport, ...]:
        return tuple(report for result in self.results for report in result.reports)

    @property
    def analyses(self) -> tuple[ResidualAnalysisResult, ...]:
        return tuple(
            analysis
            for result in self.results
            for analysis in result.analyses
        )

    @property
    def summary(self) -> dict[str, object]:
        kind_counts = Counter(report.kind.value for report in self.reports)
        state_counts = Counter(
            residual_slice.state.value
            for analysis in self.analyses
            for residual_slice in analysis.slicing_result.slices
        )
        unknown_cause_counts = Counter(
            unknown_cause_category(cause)
            for report in self.reports
            for cause in report.unknown_causes
        )
        mapped_functions = {
            _function_name_key(record.function)
            for record in self.confirmed_bug_records
            if record.function
        }
        analyzed_functions = {_function_name_key(analysis.function) for analysis in self.analyses}
        return {
            "schema_version": EVALUATION_SCHEMA_VERSION,
            "source_path": self.source_path,
            "source_root": self.source_root,
            "output_dir": self.output_dir,
            "exclude_globs": list(self.exclude_globs),
            "source_files_analyzed": len(self.results),
            "source_files": [result.source_file for result in self.results],
            "functions_analyzed": len(self.analyses),
            "functions_with_failure_points": sum(
                bool(analysis.slicing_result.slices) for analysis in self.analyses
            ),
            "reports_written": len(self.reports),
            "candidate_count": kind_counts[ReportKind.UNCLOSED_METADATA_RESIDUAL.value],
            "unknown_count": kind_counts[ReportKind.METADATA_RESIDUAL_UNKNOWN.value],
            "out_of_scope_count": kind_counts[ReportKind.OUT_OF_SCOPE.value],
            "report_kind_counts": dict(sorted(kind_counts.items())),
            "residual_state_counts": dict(sorted(state_counts.items())),
            "unknown_cause_counts": dict(sorted(unknown_cause_counts.items())),
            "confirmed_bug_records": len(self.confirmed_bug_records),
            "confirmed_bug_functions_in_source": sorted(
                mapped_functions & analyzed_functions
            ),
            "configuration_note": (
                "batch run using metadata scope plus source-derived summaries; "
                "no protocol family or rule registry is loaded"
            ),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "files": [result.summary for result in self.results],
            "confirmed_bug_records": [
                record.to_dict() for record in self.confirmed_bug_records
            ],
        }


def run_evaluation(
    source_file: str | Path,
    output_dir: str | Path,
    *,
    source_root: str | Path | None = None,
    confirmed_bug_mapping: str | Path | None = None,
    include_all: bool = False,
) -> EvaluationResult:
    """Analyze one C source file and write JSON/Markdown evaluation artifacts."""

    source_path = Path(source_file)
    output_path = Path(output_dir)
    reports_dir = output_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    frontend = TreeSitterFrontend(source_root or source_path.parent)
    unit = frontend.parse(source_path)
    bug_records = (
        load_confirmed_bug_mapping(confirmed_bug_mapping)
        if confirmed_bug_mapping is not None
        else ()
    )
    result = _evaluate_functions_to_dir(
        source_file=source_path,
        output_path=output_path,
        source_root_path=Path(source_root) if source_root else source_path.parent,
        functions=unit.functions,
        confirmed_bug_records=bug_records,
        include_all=include_all,
        inherited_summaries=None,
    )
    return result


def run_batch_evaluation(
    source_path: str | Path,
    output_dir: str | Path,
    *,
    source_root: str | Path | None = None,
    confirmed_bug_mapping: str | Path | None = None,
    include_all: bool = False,
    exclude_globs: Iterable[str] = (),
) -> BatchEvaluationResult:
    """Analyze every C source file under a file or directory and aggregate results."""

    source = Path(source_path)
    output_path = Path(output_dir)
    root = Path(source_root) if source_root is not None else (source if source.is_dir() else source.parent)
    bug_records = (
        load_confirmed_bug_mapping(confirmed_bug_mapping)
        if confirmed_bug_mapping is not None
        else ()
    )
    results: list[EvaluationResult] = []
    excludes = tuple(exclude_globs)
    source_files = _source_files(source, root, excludes)
    frontend = TreeSitterFrontend(root)
    parsed_units = [(source_file, frontend.parse(source_file)) for source_file in source_files]
    all_functions = tuple(
        function for _, unit in parsed_units for function in unit.functions
    )
    project_summaries = build_project_summaries(all_functions)
    for source_file, unit in parsed_units:
        result = _evaluate_functions_to_dir(
            source_file=source_file,
            output_path=output_path / "files" / _source_stem(source_file, root),
            source_root_path=root,
            functions=unit.functions,
            confirmed_bug_records=bug_records,
            include_all=include_all,
            inherited_summaries=_summaries_visible_from_file(
                project_summaries,
                source_file,
            ),
        )
        results.append(result)

    batch = BatchEvaluationResult(
        source_path=source.as_posix(),
        output_dir=output_path.as_posix(),
        source_root=root.as_posix(),
        results=tuple(results),
        confirmed_bug_records=bug_records,
        exclude_globs=excludes,
    )
    _write_reports(output_path / "reports", batch.reports)
    _write_json(output_path / "summary.json", batch.summary)
    _write_json(output_path / "evaluation.json", batch.to_dict())
    return batch


def _evaluate_functions_to_dir(
    *,
    source_file: Path,
    output_path: Path,
    source_root_path: Path,
    functions: Iterable[FunctionIR],
    confirmed_bug_records: tuple[ConfirmedBugRecord, ...],
    include_all: bool,
    inherited_summaries: dict[str, FunctionSummary] | None,
) -> EvaluationResult:
    reports_dir = output_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    analyses = analyze_functions(
        functions,
        inherited_summaries=inherited_summaries,
        include_all=include_all,
    )
    reports = tuple(report for analysis in analyses for report in analysis.reports)
    result = EvaluationResult(
        source_file=source_file.as_posix(),
        output_dir=output_path.as_posix(),
        source_root=source_root_path.as_posix(),
        analyses=analyses,
        reports=reports,
        confirmed_bug_records=confirmed_bug_records,
    )
    _write_reports(reports_dir, reports)
    _write_json(output_path / "summary.json", result.summary)
    _write_json(output_path / "evaluation.json", result.to_dict())
    return result


def _summaries_visible_from_file(
    summaries: dict[str, FunctionSummary],
    source_file: Path,
) -> dict[str, FunctionSummary]:
    return dict(summaries)


def load_confirmed_bug_mapping(
    path: str | Path,
) -> tuple[ConfirmedBugRecord, ...]:
    """Load a light confirmed-bug mapping from JSON or the curated Markdown table."""

    source = Path(path)
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".json":
        return _records_from_json(json.loads(text))
    return _records_from_markdown(text)


def _write_reports(
    reports_dir: Path,
    reports: tuple[ResidualWitnessReport, ...],
) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    for path in reports_dir.iterdir():
        if path.is_file() and re.match(r"^\d{4,}_.+\.(?:json|md)$", path.name):
            path.unlink()
    _write_text(reports_dir / "all_reports.json", reports_to_json(reports))
    _write_text(reports_dir / "all_reports.md", reports_to_markdown(reports))
    for index, report in enumerate(reports, start=1):
        stem = _report_stem(index, report)
        _write_text(reports_dir / f"{stem}.json", report.to_json())
        _write_text(reports_dir / f"{stem}.md", report.to_markdown())


def _report_stem(index: int, report: ResidualWitnessReport) -> str:
    return f"{index:04d}_{_slug(report.report.function)}_{_slug(report.kind.value)}"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _source_files(
    path: Path,
    source_root: Path,
    exclude_globs: tuple[str, ...] = (),
) -> tuple[Path, ...]:
    if path.is_file():
        candidates = (path,) if path.suffix == ".c" else ()
    else:
        candidates = tuple(sorted(item for item in path.rglob("*.c") if item.is_file()))
    return tuple(
        item
        for item in candidates
        if not _excluded_source(item, source_root, exclude_globs)
    )


def _excluded_source(
    source_file: Path,
    source_root: Path,
    exclude_globs: tuple[str, ...],
) -> bool:
    if not exclude_globs:
        return False
    try:
        relative = source_file.relative_to(source_root).as_posix()
    except ValueError:
        relative = source_file.as_posix()
    absolute = source_file.as_posix()
    return any(
        fnmatch(relative, pattern) or fnmatch(absolute, pattern)
        for pattern in exclude_globs
    )


def _source_stem(source_file: Path, source_root: Path) -> str:
    try:
        relative = source_file.relative_to(source_root)
    except ValueError:
        relative = source_file.name
    return _slug(Path(relative).as_posix())


def _records_from_json(payload: Any) -> tuple[ConfirmedBugRecord, ...]:
    if isinstance(payload, dict):
        if isinstance(payload.get("confirmed_bugs"), list):
            payload = payload["confirmed_bugs"]
        else:
            payload = [payload]
    if not isinstance(payload, list):
        return ()
    records: list[ConfirmedBugRecord] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        bug_id = item.get("bug_id", item.get("id"))
        if bug_id is None:
            continue
        records.append(
            ConfirmedBugRecord(
                bug_id=int(bug_id),
                filesystem=str(item.get("filesystem", item.get("fs", ""))),
                function=str(item.get("function", "")),
                bug_type=str(item.get("bug_type", item.get("type", ""))),
                status=str(item.get("status", "")),
                evidence=str(item.get("evidence", "")),
            )
        )
    return tuple(records)


def _records_from_markdown(text: str) -> tuple[ConfirmedBugRecord, ...]:
    records: list[ConfirmedBugRecord] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 6 or not re.fullmatch(r"\d+", cells[0]):
            continue
        records.append(
            ConfirmedBugRecord(
                bug_id=int(cells[0]),
                filesystem=cells[1],
                function=_strip_code(cells[2]),
                bug_type=cells[3],
                status=cells[4],
                evidence=cells[5],
            )
        )
    return tuple(records)


def _strip_code(value: str) -> str:
    return value.strip().strip("`")


def _function_name_key(value: str) -> str:
    return re.sub(r"\s*\([^)]*\)\s*$", "", _strip_code(value).strip())


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return slug.strip("_") or "report"
