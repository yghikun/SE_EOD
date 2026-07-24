import json
from pathlib import Path

from src.unknown_triage import (
    build_unknown_triage,
    triage_to_markdown,
    unknown_cause_taxonomy,
    write_unknown_triage,
)
from scripts.compare_residual_runs import compare_runs


def _unknown_report(function: str, cause: str, line: int) -> dict[str, object]:
    return {
        "kind": "METADATA_RESIDUAL_UNKNOWN",
        "function": function,
        "unknown_causes": [cause],
        "residual_slice": {
            "failure_site": {
                "file": "fs/btrfs/example.c",
                "line": line,
                "expression": "ret = fail_metadata()",
            },
            "exit_site": {
                "file": "fs/btrfs/example.c",
                "line": line + 5,
                "expression": "return ret;",
            },
        },
    }


def test_unknown_triage_ranks_causes_details_and_functions(tmp_path: Path):
    reports = [
        _unknown_report(
            "work",
            "unresolved metadata helper on error path: cleanup_metadata",
            10,
        ),
        _unknown_report(
            "other",
            "unresolved metadata helper on error path: cleanup_metadata",
            20,
        ),
        _unknown_report("work", "helper_body: unbound_callee_local_identity", 30),
        {
            "kind": "UNCLOSED_METADATA_RESIDUAL",
            "function": "candidate",
            "unknown_causes": [
                "unresolved metadata helper on error path: ignored_candidate"
            ],
        },
    ]

    triage = build_unknown_triage(reports, top_n=2, examples_per_item=1)

    assert triage["unknown_reports"] == 3
    assert triage["unknown_cause_mentions"] == 3
    assert triage["unknown_taxonomy_counts"] == {
        "missing_summary": 2,
        "structural": 1,
    }
    categories = {
        item["category"]: item for item in triage["cause_categories"]
    }
    helper_category = categories["unresolved_metadata_helper_on_error_path"]
    assert helper_category["count"] == 2
    assert helper_category["top_details"][0]["detail"] == "cleanup_metadata"
    assert helper_category["top_details"][0]["count"] == 2
    assert categories["unbound_callee_local_identity"]["top_details"][0][
        "detail"
    ] == "helper_body"

    markdown = triage_to_markdown(triage)
    assert "cleanup_metadata" in markdown
    assert "work @ fs/btrfs/example.c:10" in markdown

    out_dir = tmp_path / "eval"
    reports_dir = out_dir / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "all_reports.json").write_text(
        json.dumps(reports),
        encoding="utf-8",
    )

    outputs = write_unknown_triage(out_dir, top_n=2, examples_per_item=1)

    assert outputs["json"] == out_dir / "unknown_triage.json"
    assert outputs["markdown"] == out_dir / "unknown_triage.md"
    assert json.loads(outputs["json"].read_text(encoding="utf-8"))[
        "unknown_cause_mentions"
    ] == 3
    assert (
        "Filesystem Metadata Residual UNKNOWN Triage"
        in outputs["markdown"].read_text(encoding="utf-8")
    )


def test_unknown_cause_taxonomy_labels_structural_and_missing_summary():
    assert (
        unknown_cause_taxonomy(
            "unresolved metadata helper on error path: cleanup_metadata"
        )
        == "missing_summary"
    )
    assert (
        unknown_cause_taxonomy("worker: function_pointer_parameter_call: iterate")
        == "structural"
    )
    assert (
        unknown_cause_taxonomy("helper: return_bound_unresolved_helper: cleanup")
        == "missing_summary"
    )


def test_compare_runs_reports_taxonomy_resolution(tmp_path: Path):
    baseline = [
        _unknown_report(
            "work",
            "unresolved metadata helper on error path: cleanup_metadata",
            10,
        ),
        _unknown_report("other", "helper: indirect_call: cb(arg)", 20),
    ]
    current = [
        {
            **baseline[0],
            "kind": "UNCLOSED_METADATA_RESIDUAL",
        },
        baseline[1],
    ]
    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    current_path.write_text(json.dumps(current), encoding="utf-8")

    matrix = compare_runs(baseline_path, current_path)

    taxonomy = {
        item["taxonomy"]: item for item in matrix["unknown_taxonomy_resolution"]
    }
    assert taxonomy["missing_summary"]["to_candidate"] == 1
    assert taxonomy["structural"]["to_unknown"] == 1
    rows = {item["reason"]: item for item in matrix["unknown_resolution_matrix"]}
    assert rows["unresolved_metadata_helper_on_error_path"]["taxonomy"] == (
        "missing_summary"
    )
