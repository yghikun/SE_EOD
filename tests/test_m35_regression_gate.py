import json
from pathlib import Path

from scripts.check_m35_regression_gate import (
    FILESYSTEMS,
    HIGH_VALUE_FUNCTIONS,
    check_m35_regression_gate,
)


def _report(function: str, index: int, *, contained: bool = False) -> dict[str, object]:
    classification = (
        "CONTAINED_METADATA_RESIDUAL" if contained else "FUNCTION_BOUNDARY_RESIDUAL"
    )
    return {
        "function": function,
        "classification": classification,
        "kind": classification,
        "residual_slice": {
            "failure_site": {
                "file": "fs/xfs/example.c",
                "line": index,
                "expression": f"fail_{index}()",
            },
            "exit_site": {
                "file": "fs/xfs/example.c",
                "line": index + 1,
                "expression": "return error;",
            },
        },
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _analysis(function: str, index: int, state: str) -> dict[str, object]:
    report = _report(function, index)
    residual_slice = report["residual_slice"]
    assert isinstance(residual_slice, dict)
    residual_slice = {**residual_slice, "state": state}
    return {
        "function": function,
        "slicing_result": {"slices": [residual_slice]},
    }


def _gate_artifacts(tmp_path: Path):
    runs: dict[str, Path] = {}
    comparisons: dict[str, Path] = {}
    for filesystem in FILESYSTEMS:
        run = tmp_path / f"run-{filesystem}"
        reports = [
            _report(function, index + 100)
            for index, function in enumerate(sorted(HIGH_VALUE_FUNCTIONS.get(filesystem, ())))
        ]
        if filesystem == "xfs":
            reports.extend(_report(f"xfs_contained_{index}", index, contained=True) for index in range(9))
        _write_json(
            run / "evaluation.json",
            {"summary": {"schema_version": 4, "zero_residual_finding_count": 0}},
        )
        _write_json(run / "reports/all_reports.json", reports)
        runs[filesystem] = run

        comparison = tmp_path / f"comparison-{filesystem}"
        _write_json(
            comparison / "report_transition_matrix.json",
            {
                "schema_version": 3,
                "new_candidate_count": 0,
                "unmatched_baseline_witness_count": 0,
            },
        )
        comparisons[filesystem] = comparison

    oracle = tmp_path / "oracle.json"
    _write_json(
        oracle,
        {
            "schema_version": 2,
            "summary": {
                "new_safety_regression_count": 0,
                "manual_live_residuals_retained": 6,
                "manual_live_residuals_lost": 0,
                "unmatched_oracle_entries": 0,
                "unmatched_effect_count": 0,
            },
        },
    )
    baseline = tmp_path / "xfs-m33"
    _write_json(
        baseline / "reports/all_reports.json",
        [_report(f"xfs_contained_{index}", index, contained=True) for index in range(9)],
    )
    return runs, comparisons, oracle, baseline


def test_m35_gate_accepts_m33_xfs_slice_retained_as_protected(tmp_path: Path):
    runs, comparisons, oracle, baseline = _gate_artifacts(tmp_path)
    protected_reports = [
        _report(function, index + 100)
        for index, function in enumerate(sorted(HIGH_VALUE_FUNCTIONS.get("xfs", ())))
    ]
    _write_json(runs["xfs"] / "reports/all_reports.json", protected_reports)
    _write_json(
        runs["xfs"] / "evaluation.json",
        {
            "summary": {"schema_version": 4, "zero_residual_finding_count": 0},
            "analyses": [
                _analysis(f"xfs_contained_{index}", index, "PROTECTED")
                for index in range(9)
            ],
        },
    )

    result = check_m35_regression_gate(runs, comparisons, oracle, baseline)

    assert result["passed"] is True


def test_m35_gate_rejects_m33_xfs_slice_that_becomes_exposed(tmp_path: Path):
    runs, comparisons, oracle, baseline = _gate_artifacts(tmp_path)
    protected_reports = [
        _report(function, index + 100)
        for index, function in enumerate(sorted(HIGH_VALUE_FUNCTIONS.get("xfs", ())))
    ]
    _write_json(runs["xfs"] / "reports/all_reports.json", protected_reports)
    _write_json(
        runs["xfs"] / "evaluation.json",
        {
            "summary": {"schema_version": 4, "zero_residual_finding_count": 0},
            "analyses": [
                _analysis(
                    f"xfs_contained_{index}",
                    index,
                    "EXPOSED" if index == 8 else "PROTECTED",
                )
                for index in range(9)
            ],
        },
    )

    result = check_m35_regression_gate(runs, comparisons, oracle, baseline)

    assert result["passed"] is False
    assert any(
        item["name"] == "m33_xfs_contained_slices_retained"
        for item in result["failures"]
    )


def test_m35_gate_accepts_complete_structured_contract(tmp_path: Path):
    result = check_m35_regression_gate(*_gate_artifacts(tmp_path))

    assert result["passed"] is True
    assert result["failure_count"] == 0


def test_m35_gate_reports_all_independent_contract_failures(tmp_path: Path):
    runs, comparisons, oracle, baseline = _gate_artifacts(tmp_path)
    _write_json(
        comparisons["btrfs"] / "report_transition_matrix.json",
        {
            "schema_version": 3,
            "new_candidate_count": 1,
            "unmatched_baseline_witness_count": 2,
        },
    )
    oracle_payload = json.loads(oracle.read_text(encoding="utf-8"))
    oracle_payload["summary"]["manual_live_residuals_retained"] = 5
    _write_json(oracle, oracle_payload)
    xfs_reports_path = runs["xfs"] / "reports/all_reports.json"
    xfs_reports = json.loads(xfs_reports_path.read_text(encoding="utf-8"))
    _write_json(xfs_reports_path, xfs_reports[:-1])

    result = check_m35_regression_gate(runs, comparisons, oracle, baseline)

    assert result["passed"] is False
    failed = {item["name"] for item in result["failures"]}
    assert "btrfs_no_new_candidates" in failed
    assert "btrfs_no_unmatched_baseline_witnesses" in failed
    assert "oracle_manual_live_residuals_retained" in failed
    assert "m33_xfs_contained_slices_retained" in failed
