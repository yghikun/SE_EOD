import json
from pathlib import Path

from src.unknown_triage import (
    build_unknown_triage,
    triage_to_markdown,
    write_unknown_triage,
)


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
    assert "UNKNOWN Triage" in outputs["markdown"].read_text(encoding="utf-8")
