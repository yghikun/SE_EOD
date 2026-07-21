import json

import pytest

from src.metadata_finding_matrix import (
    build_finding_matrix,
    load_version_report,
    main,
)


def _report(version: str, analyses: list[dict]):
    return {
        "schema_version": 1,
        "source_version": version,
        "source_root": f"/src/{version}/fs",
        "summary": {
            "protocol_candidate_occurrences": sum(
                len(item.get("candidates", ())) for item in analyses
            ),
            "analysis_unknown": sum(len(item.get("unknown", ())) for item in analyses),
        },
        "analyses": analyses,
    }


def _analysis(function: str, candidates: int, unknown: int = 0):
    return {
        "protocol_id": "protocol.a",
        "operation_id": "op",
        "function": function,
        "source_file": f"/src/linux/fs/fixture/{function}.c",
        "candidates": [{} for _ in range(candidates)],
        "discovery_review": [],
        "unknown": [{} for _ in range(unknown)],
    }


def test_build_finding_matrix_tracks_persistent_removed_and_added_functions():
    matrix = build_finding_matrix(
        [
            type("Input", (), {"version": "v1", "path": "v1.json", "report": _report("v1", [_analysis("old", 2), _analysis("keep", 1)])})(),
            type("Input", (), {"version": "v2", "path": "v2.json", "report": _report("v2", [_analysis("keep", 1), _analysis("new", 1, unknown=1)])})(),
        ]
    ).to_dict()

    assert matrix["summary"]["candidate_occurrences_by_version"] == {
        "v1": 3,
        "v2": 2,
    }
    assert matrix["summary"]["persistent_candidate_functions"] == ["keep"]
    assert matrix["summary"]["candidate_removed_functions"] == ["old"]
    assert matrix["summary"]["candidate_added_functions"] == ["new"]
    new_row = next(item for item in matrix["rows"] if item["function"] == "new")
    assert new_row["version_counts"]["v2"]["analysis_unknown"] == 1


def test_load_version_report_requires_version_path_spec(tmp_path):
    with pytest.raises(ValueError, match="VERSION=PATH"):
        load_version_report(str(tmp_path / "report.json"))


def test_cli_writes_matrix_json_and_markdown(tmp_path):
    v1 = tmp_path / "v1.json"
    v2 = tmp_path / "v2.json"
    out_json = tmp_path / "matrix.json"
    out_md = tmp_path / "matrix.md"
    v1.write_text(json.dumps(_report("v1", [_analysis("old", 1)])), encoding="utf-8")
    v2.write_text(json.dumps(_report("v2", [_analysis("new", 1)])), encoding="utf-8")

    assert (
        main(
            [
                "--report",
                f"v1={v1}",
                "--report",
                f"v2={v2}",
                "--out-json",
                str(out_json),
                "--out-md",
                str(out_md),
            ]
        )
        == 0
    )

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    assert payload["summary"]["candidate_removed_functions"] == ["old"]
    assert payload["summary"]["candidate_added_functions"] == ["new"]
    assert "MOCC-SE Discovery Version Matrix" in markdown
