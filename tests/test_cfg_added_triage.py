from typing import Optional

from scripts.triage_cfg_added_candidates import build_report


def _candidate(
    path_id: str,
    function: str,
    candidate_type: str = "missing_cleanup",
    file: str = "fs/ext4/demo.c",
    line: int = 10,
    condition: str = "err",
    missing: Optional[list[str]] = None,
) -> dict:
    return {
        "candidate_id": path_id,
        "file": file,
        "function": function,
        "path_id": path_id,
        "candidate_type": candidate_type,
        "error_line": line,
        "condition": condition,
        "final_return_expr": "-EIO",
        "severity": "P2",
        "evidence_level": "E2_API_PROTOCOL_SUPPORTED",
        "evidence_score": 60,
        "static_evidence": {
            "missing_cleanup_candidates": missing or [],
            "held_resources": [],
        },
    }


def test_cfg_added_triage_classifies_ext4_journal_family():
    before = []
    after = [
        _candidate(
            "__ext4_new_inode#016",
            "__ext4_new_inode",
            file="fs/ext4/ialloc.c",
            line=1090,
            missing=["ext4_journal_stop(handle)"],
        )
    ]

    report = build_report(before, after)

    assert report["summary"]["added"] == 1
    assert report["added"][0]["family"] == "__ext4_new_inode.journal_handle_stop"
    assert report["added"][0]["disposition"] == "retain_high_value_needs_validation"


def test_cfg_added_triage_marks_orphan_partial_cleanup_as_duplicate_view():
    missing = _candidate(
        "ext4_init_orphan_info#006",
        "ext4_init_orphan_info",
        file="fs/ext4/orphan.c",
        line=610,
        condition="bad_magic",
        missing=["brelse(oi->of_binfo[i].ob_bh)"],
    )
    partial = _candidate(
        "ext4_init_orphan_info#006",
        "ext4_init_orphan_info",
        candidate_type="partial_cleanup",
        file="fs/ext4/orphan.c",
        line=610,
        condition="bad_magic",
        missing=["brelse(oi->of_binfo[i].ob_bh)"],
    )
    before = [missing]
    after = [missing, partial]

    report = build_report(before, after)

    assert report["summary"]["added"] == 1
    assert report["added"][0]["family"] == "ext4_init_orphan_info.partial_cleanup_duplicate"
    assert "Duplicate of ext4_init_orphan_info#006" in report["added"][0]["paper_note"]
