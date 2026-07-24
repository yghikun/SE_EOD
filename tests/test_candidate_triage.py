import json
from pathlib import Path

from src.candidate_triage import (
    build_candidate_triage,
    triage_to_markdown,
    write_candidate_triage,
)


def _candidate_report(
    function: str,
    plane: str,
    delta: str,
    root: str,
    key: str,
    line: int,
) -> dict[str, object]:
    return {
        "kind": "UNCLOSED_METADATA_RESIDUAL",
        "function": function,
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
            "residuals": [
                {
                    "plane": plane,
                    "delta": delta,
                    "root": root,
                    "key": key,
                    "value": "nr",
                }
            ],
        },
    }


def test_candidate_triage_ranks_functions_and_residual_identities(tmp_path: Path):
    reports = [
        _candidate_report("work", "ACCOUNTING", "INC", "inode", "i_blocks", 10),
        _candidate_report("work", "ACCOUNTING", "INC", "inode", "i_blocks", 20),
        _candidate_report("other", "RECOVERY", "SET", "root", "state", 30),
        {
            "kind": "METADATA_RESIDUAL_UNKNOWN",
            "function": "ignored",
            "residual_slice": {"residuals": []},
        },
    ]

    triage = build_candidate_triage(reports, top_n=2, examples_per_item=1)

    assert triage["candidate_reports"] == 3
    assert triage["residual_effects"] == 3
    assert triage["top_functions"][0]["function"] == "work"
    assert triage["top_functions"][0]["count"] == 2
    assert triage["top_residual_identities"][0]["identity"] == (
        "ACCOUNTING INC inode.i_blocks"
    )
    assert triage["top_plane_deltas"][0]["plane_delta"] == "ACCOUNTING INC"

    markdown = triage_to_markdown(triage)
    assert "Candidate Triage" in markdown
    assert "inode.i_blocks" in markdown
    assert "work @ fs/btrfs/example.c:10" in markdown

    out_dir = tmp_path / "eval"
    reports_dir = out_dir / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "all_reports.json").write_text(
        json.dumps(reports),
        encoding="utf-8",
    )

    outputs = write_candidate_triage(out_dir, top_n=2, examples_per_item=1)

    assert outputs["json"] == out_dir / "candidate_triage.json"
    assert outputs["markdown"] == out_dir / "candidate_triage.md"
    assert json.loads(outputs["json"].read_text(encoding="utf-8"))[
        "candidate_reports"
    ] == 3
