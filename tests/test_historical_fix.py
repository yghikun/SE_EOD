import json

from src.evidence_ranker import E3_HISTORICAL_FIX_CONFIRMED, rank_candidate_rows
from src.historical_fix import HistoricalFixDB
from src.protocol_db import ResourceProtocolDB


def _row(line: int) -> dict[str, str]:
    return {
        "file": "fs/ext4/namei.c",
        "function": "ext4_dx_add_entry",
        "path_id": "ext4_dx_add_entry#007",
        "candidate_type": "missing_cleanup",
        "severity": "P2",
        "error_line": str(line),
        "condition": "err",
        "final_return_expr": "err",
        "evidence": json.dumps(
            {
                "acquired_resources": [],
                "missing_releases": ["brelse(bh2)"],
                "cleanup_calls": [],
            }
        ),
    }


def test_historical_fix_promotes_matching_candidate_and_closes_evidence_gaps():
    db = HistoricalFixDB(
        fixes=[
            {
                "fix_id": "ext4.dx.bh2",
                "file": "fs/ext4/namei.c",
                "function": "ext4_dx_add_entry",
                "candidate_type": "missing_cleanup",
                "affected_version": "linux-v6.8",
                "fixed_version": "linux-v7.1",
                "line_mappings": [
                    {
                        "affected_line": 2570,
                        "fixed_condition_line": 2558,
                        "fixed_action_lines": [2559],
                    }
                ],
            }
        ]
    )

    ranked = rank_candidate_rows(
        [_row(2570)], ResourceProtocolDB(), historical_fixes=db
    )[0]

    assert ranked["evidence_level"] == E3_HISTORICAL_FIX_CONFIRMED
    assert ranked["historical_fix_evidence"][0]["fixed_version"] == "linux-v7.1"
    assert "repair_patch" not in ranked["missing_evidence"]
    assert "upstream_confirmation" not in ranked["missing_evidence"]
    assert ranked["missing_evidence"] == ["dynamic_validation"]


def test_historical_fix_does_not_match_different_line_or_function():
    db = HistoricalFixDB.load_from_file("configs/ext4_historical_fixes.json")

    assert db.match(_row(2571)) == []
    other = _row(2570)
    other["function"] = "other_function"
    assert db.match(other) == []
