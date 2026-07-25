#!/usr/bin/env python3
"""Fail closed when an M35 four-filesystem regression contract is broken."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


FILESYSTEMS = ("btrfs", "ext4", "xfs", "f2fs")
EVALUATION_SCHEMA_VERSION = 4
COMPARISON_SCHEMA_VERSION = 3
ORACLE_AUDIT_SCHEMA_VERSION = 2
GATE_SCHEMA_VERSION = 1
M33_XFS_CONTAINED_COUNT = 9
M33_XFS_RETAINED_STATES = {"CLOSED", "PROTECTED", "CONTAINED"}
HIGH_VALUE_FUNCTIONS = {
    "btrfs": {
        "btrfs_dev_replace_start",
        "btrfs_recover_relocation",
        "btrfs_reconfigure",
        "btrfs_create_uuid_tree",
        "btrfs_init_new_device",
    },
    "ext4": {"make_indexed_dir"},
}


def check_m35_regression_gate(
    runs: dict[str, Path],
    comparisons: dict[str, Path],
    oracle_audit: Path,
    xfs_contained_baseline: Path,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    missing_runs = sorted(set(FILESYSTEMS) - set(runs))
    missing_comparisons = sorted(set(FILESYSTEMS) - set(comparisons))
    _record(checks, "four_filesystem_runs_present", not missing_runs, missing_runs)
    _record(
        checks,
        "four_filesystem_comparisons_present",
        not missing_comparisons,
        missing_comparisons,
    )

    reports_by_fs: dict[str, list[dict[str, Any]]] = {}
    evaluation_schemas: dict[str, Any] = {}
    for filesystem in FILESYSTEMS:
        if filesystem not in runs:
            continue
        evaluation = _load_json(_artifact_path(runs[filesystem], "evaluation.json"))
        summary = _dict(evaluation.get("summary"))
        schema = summary.get("schema_version")
        evaluation_schemas[filesystem] = schema
        _record(
            checks,
            f"{filesystem}_evaluation_schema",
            schema == EVALUATION_SCHEMA_VERSION,
            {"expected": EVALUATION_SCHEMA_VERSION, "actual": schema},
        )
        zero_count = summary.get("zero_residual_finding_count")
        _record(
            checks,
            f"{filesystem}_zero_residual_findings",
            zero_count == 0,
            {"actual": zero_count},
        )
        reports = _load_json(_artifact_path(runs[filesystem], "reports/all_reports.json"))
        if not isinstance(reports, list):
            raise ValueError(f"{filesystem} reports/all_reports.json must contain a list")
        reports_by_fs[filesystem] = [item for item in reports if isinstance(item, dict)]

    _record(
        checks,
        "evaluation_schema_consistent",
        len(set(evaluation_schemas.values())) <= 1,
        evaluation_schemas,
    )

    for filesystem, required_functions in HIGH_VALUE_FUNCTIONS.items():
        visible = {
            str(report.get("function", ""))
            for report in reports_by_fs.get(filesystem, ())
        }
        missing = sorted(required_functions - visible)
        _record(
            checks,
            f"{filesystem}_high_value_witnesses_visible",
            not missing,
            missing,
        )

    comparison_schemas: dict[str, Any] = {}
    for filesystem in FILESYSTEMS:
        if filesystem not in comparisons:
            continue
        comparison = _load_json(
            _artifact_path(comparisons[filesystem], "report_transition_matrix.json")
        )
        schema = comparison.get("schema_version")
        comparison_schemas[filesystem] = schema
        _record(
            checks,
            f"{filesystem}_comparison_schema",
            schema == COMPARISON_SCHEMA_VERSION,
            {"expected": COMPARISON_SCHEMA_VERSION, "actual": schema},
        )
        _record(
            checks,
            f"{filesystem}_no_new_candidates",
            comparison.get("new_candidate_count") == 0,
            {"actual": comparison.get("new_candidate_count")},
        )
        _record(
            checks,
            f"{filesystem}_no_unmatched_baseline_witnesses",
            comparison.get("unmatched_baseline_witness_count") == 0,
            {"actual": comparison.get("unmatched_baseline_witness_count")},
        )
    _record(
        checks,
        "comparison_schema_consistent",
        len(set(comparison_schemas.values())) <= 1,
        comparison_schemas,
    )

    oracle = _load_json(oracle_audit)
    oracle_summary = _dict(oracle.get("summary"))
    _record(
        checks,
        "oracle_schema",
        oracle.get("schema_version") == ORACLE_AUDIT_SCHEMA_VERSION,
        {
            "expected": ORACLE_AUDIT_SCHEMA_VERSION,
            "actual": oracle.get("schema_version"),
        },
    )
    oracle_contract = {
        "new_safety_regression_count": 0,
        "manual_live_residuals_retained": 6,
        "manual_live_residuals_lost": 0,
        "unmatched_oracle_entries": 0,
        "unmatched_effect_count": 0,
    }
    for field, expected in oracle_contract.items():
        _record(
            checks,
            f"oracle_{field}",
            oracle_summary.get(field) == expected,
            {"expected": expected, "actual": oracle_summary.get(field)},
        )

    baseline_reports = _load_json(
        _artifact_path(xfs_contained_baseline, "reports/all_reports.json")
    )
    if not isinstance(baseline_reports, list):
        raise ValueError("XFS contained baseline reports must contain a list")
    baseline_keys = {
        _slice_key(report)
        for report in baseline_reports
        if isinstance(report, dict) and _is_contained(report)
    }
    current_keys = _xfs_retained_slice_keys(
        runs.get("xfs"),
        reports_by_fs.get("xfs", ()),
    )
    _record(
        checks,
        "m33_xfs_baseline_has_nine_contained_slices",
        len(baseline_keys) == M33_XFS_CONTAINED_COUNT,
        {"expected": M33_XFS_CONTAINED_COUNT, "actual": len(baseline_keys)},
    )
    lost_xfs = sorted(baseline_keys - current_keys)
    _record(checks, "m33_xfs_contained_slices_retained", not lost_xfs, lost_xfs)

    failures = [check for check in checks if not check["passed"]]
    return {
        "schema_version": GATE_SCHEMA_VERSION,
        "passed": not failures,
        "check_count": len(checks),
        "failure_count": len(failures),
        "failures": failures,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="append", default=[], metavar="FS=PATH")
    parser.add_argument("--comparison", action="append", default=[], metavar="FS=PATH")
    parser.add_argument("--oracle-audit", required=True)
    parser.add_argument("--xfs-contained-baseline", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    try:
        result = check_m35_regression_gate(
            _parse_paths(args.run, "--run"),
            _parse_paths(args.comparison, "--comparison"),
            Path(args.oracle_audit),
            Path(args.xfs_contained_baseline),
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        result = {
            "schema_version": GATE_SCHEMA_VERSION,
            "passed": False,
            "failure_count": 1,
            "failures": [{"name": "artifact_load", "passed": False, "detail": str(error)}],
            "checks": [],
        }
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


def _parse_paths(values: list[str], option: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"{option} expects FS=PATH, got {value!r}")
        filesystem, path = value.split("=", 1)
        filesystem = filesystem.lower().strip()
        if filesystem not in FILESYSTEMS or filesystem in result:
            raise ValueError(f"invalid or duplicate filesystem for {option}: {filesystem!r}")
        result[filesystem] = Path(path)
    return result


def _record(checks: list[dict[str, Any]], name: str, passed: bool, detail: Any) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})


def _artifact_path(path: Path, relative: str) -> Path:
    return path if path.is_file() else path / relative


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _is_contained(report: dict[str, Any]) -> bool:
    return (
        report.get("classification") == "CONTAINED_METADATA_RESIDUAL"
        or report.get("kind") == "CONTAINED_METADATA_RESIDUAL"
    )


def _xfs_retained_slice_keys(
    run: Path | None,
    reports: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> set[str]:
    keys = {
        _slice_key(report)
        for report in reports
        if _is_contained(report)
    }
    if run is None:
        return keys
    for evaluation_path in _evaluation_paths(run):
        evaluation = _load_json(evaluation_path)
        for analysis in _list(evaluation.get("analyses")):
            function = str(_dict(analysis).get("function", ""))
            slicing = _dict(_dict(analysis).get("slicing_result"))
            for residual_slice in _list(slicing.get("slices")):
                residual_slice = _dict(residual_slice)
                if residual_slice.get("state") not in M33_XFS_RETAINED_STATES:
                    continue
                keys.add(_slice_key_from_parts(
                    function,
                    _dict(residual_slice.get("failure_site")),
                    _dict(residual_slice.get("exit_site")),
                ))
    return keys


def _evaluation_paths(run: Path) -> list[Path]:
    if run.is_file():
        return [run]
    paths: list[Path] = []
    root_evaluation = run / "evaluation.json"
    if root_evaluation.is_file():
        paths.append(root_evaluation)
    files_dir = run / "files"
    if files_dir.is_dir():
        paths.extend(sorted(files_dir.glob("*/evaluation.json")))
    return paths


def _slice_key(report: dict[str, Any]) -> str:
    residual_slice = _dict(report.get("residual_slice"))
    failure = _dict(residual_slice.get("failure_site"))
    exit_site = _dict(residual_slice.get("exit_site"))
    return _slice_key_from_parts(str(report.get("function", "")), failure, exit_site)


def _slice_key_from_parts(
    function: str,
    failure: dict[str, Any],
    exit_site: dict[str, Any],
) -> str:
    return json.dumps(
        [
            function,
            failure.get("file", ""),
            failure.get("line", ""),
            failure.get("expression", ""),
            exit_site.get("file", ""),
            exit_site.get("line", ""),
            exit_site.get("expression", ""),
        ],
        separators=(",", ":"),
    )


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


if __name__ == "__main__":
    raise SystemExit(main())
