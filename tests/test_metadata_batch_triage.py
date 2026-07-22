import json
from pathlib import Path

from src.metadata_batch_triage import (
    build_batch_triage_report,
    main,
    triage_record,
)


ROOT = Path(__file__).parents[1]
BATCH_REPORT = ROOT / "outputs" / "mocc-batch-scan-v1" / "linux-v7.1-fs.json"


def test_protocol_candidate_requires_manual_bug_review():
    decision = triage_record(
        {
            "classification": "PROTOCOL_CANDIDATE",
            "candidate_id": "candidate-1",
            "protocol_id": "mocc.protocol_a.replay_recovery",
            "representative_witness": [
                {"kind": "exit", "line": 10, "detail": "return 0;"}
            ],
        }
    )

    assert decision.verdict == "candidate_for_manual_bug_review"
    assert decision.priority == "P0"
    assert decision.bug_claim_allowed is False


def test_local_preparation_mutation_is_likely_false_positive():
    decision = triage_record(
        {
            "classification": "DISCOVERY_REVIEW",
            "semantic_pattern": "mutation_failure_cleanup",
            "occurrence_fingerprint": "occurrence-1",
            "representative_witness": [
                {"kind": "state_mutation", "line": 1, "detail": "key.offset = 0"},
                {"kind": "fallible_call", "line": 2, "detail": "btrfs_alloc_path() assigned to path"},
            ],
        }
    )

    assert decision.verdict == "likely_false_positive"
    assert "local/search-key/reservation" in decision.followups[0]


def test_ext4_failure_return_review_needs_external_semantics():
    decision = triage_record(
        {
            "classification": "DISCOVERY_REVIEW",
            "protocol_id": "mocc.protocol_a.replay_recovery",
            "semantic_pattern": "failure_return_mismatch",
            "occurrence_fingerprint": "occurrence-2",
            "function": "ext4_ext_clear_bb",
            "representative_witness": [
                {"kind": "fallible_call", "line": 1, "detail": "ext4_map_blocks() assigned to ret"},
                {"kind": "success_exit", "line": 2, "detail": "return 0;"},
            ],
        }
    )

    assert decision.verdict == "needs_external_semantics"
    assert decision.priority == "P0"
    assert "independent ext4" in decision.followups[1]


def test_generic_failure_return_review_still_needs_protocol_instance():
    decision = triage_record(
        {
            "classification": "DISCOVERY_REVIEW",
            "protocol_id": "mocc.protocol_a.replay_recovery",
            "semantic_pattern": "failure_return_mismatch",
            "occurrence_fingerprint": "occurrence-3",
            "function": "some_replay_helper",
            "representative_witness": [
                {"kind": "fallible_call", "line": 1, "detail": "map() assigned to ret"},
                {"kind": "success_exit", "line": 2, "detail": "return 0;"},
            ],
        }
    )

    assert decision.verdict == "needs_protocol_instance"


def test_current_batch_report_triage_summary_matches_expected_groups():
    batch = json.loads(BATCH_REPORT.read_text(encoding="utf-8"))

    report = build_batch_triage_report(
        batch, batch_report_source=str(BATCH_REPORT)
    ).to_dict()

    assert report["bug_claims_allowed"] is False
    assert report["summary"]["triage_items"] == 8
    assert report["summary"]["manual_bug_review_candidates"] == 0
    assert report["summary"]["needs_protocol_instance"] == 0
    assert report["summary"]["needs_external_semantics"] == 2
    assert report["summary"]["likely_false_positive"] == 6
    assert report["summary"]["by_verdict"] == {
        "likely_false_positive": 6,
        "needs_external_semantics": 2,
    }


def test_cli_writes_batch_triage_json_and_markdown(tmp_path):
    out_json = tmp_path / "triage.json"
    out_md = tmp_path / "triage.md"

    assert (
        main(
            [
                "--batch-report",
                str(BATCH_REPORT),
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
    assert payload["summary"]["triage_items"] == 8
    assert "MOCC-SE Batch Scan Triage" in markdown
    assert "not a confirmed-bug list" in markdown
