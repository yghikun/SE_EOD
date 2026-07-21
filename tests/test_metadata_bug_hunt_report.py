import json

from src.metadata_bug_hunt_report import build_bug_hunt_report, main


def _reviewed():
    return {"summary": {"review_items": 2}, "items": []}


def _triage():
    return {
        "summary": {
            "triage_items": 2,
            "by_verdict": {"candidate_survives_initial_review": 2},
        },
        "items": [
            {
                "review_id": "review-1",
                "protocol_id": "protocol.a",
                "operation_id": "op",
                "function": "fixed",
                "source_file": "fs/fixed.c",
                "violation_type": "failure_reported_as_success",
                "triage": {"verdict": "candidate_survives_initial_review"},
            },
            {
                "review_id": "review-2",
                "protocol_id": "protocol.b",
                "operation_id": "op",
                "function": "persistent",
                "source_file": "fs/persistent.c",
                "violation_type": "incomplete_failure_completion",
                "triage": {"verdict": "candidate_survives_initial_review"},
            },
        ],
    }


def _matrix():
    return {
        "summary": {
            "candidate_occurrences_by_version": {"v1": 2, "v2": 1},
            "persistent_candidate_functions": ["persistent"],
            "candidate_removed_functions": ["fixed"],
            "candidate_added_functions": ["new"],
        },
        "rows": [
            {
                "protocol_id": "protocol.a",
                "operation_id": "op",
                "function": "fixed",
                "source_file": "fs/fixed.c",
                "version_counts": {},
            },
            {
                "protocol_id": "protocol.c",
                "operation_id": "op",
                "function": "new",
                "source_file": "fs/new.c",
                "version_counts": {},
            },
        ],
    }


def _repair():
    return {
        "items": [
            {
                "review_id": "review-1",
                "protocol_id": "protocol.a",
                "operation_id": "op",
                "function": "fixed",
                "source_file": "fs/fixed.c",
                "violation_type": "failure_reported_as_success",
                "triage": {"verdict": "candidate_survives_initial_review"},
                "repair_evidence": [{"semantic_hints": ["local_return_propagation_repair"]}],
            },
            {
                "review_id": "review-2",
                "protocol_id": "protocol.b",
                "operation_id": "op",
                "function": "persistent",
                "source_file": "fs/persistent.c",
                "violation_type": "incomplete_failure_completion",
                "triage": {"verdict": "candidate_survives_initial_review"},
            },
        ]
    }


def test_build_bug_hunt_report_prioritizes_repair_and_matrix_queues():
    report = build_bug_hunt_report(_reviewed(), _triage(), _matrix(), _repair()).to_dict()

    assert report["summary"]["review_items"] == 2
    assert report["summary"]["items_with_repair_evidence"] == 1
    assert report["priority_queues"]["repair_evidence_first"][0]["function"] == "fixed"
    assert report["priority_queues"]["persistent_candidates_next"][0]["function"] == "persistent"
    assert report["priority_queues"]["removed_or_cleared_functions"][0]["function"] == "fixed"
    assert report["priority_queues"]["added_functions_to_inspect"][0]["function"] == "new"


def test_cli_writes_bug_hunt_json_and_markdown(tmp_path):
    reviewed = tmp_path / "reviewed.json"
    triage = tmp_path / "triage.json"
    matrix = tmp_path / "matrix.json"
    repair = tmp_path / "repair.json"
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"
    reviewed.write_text(json.dumps(_reviewed()), encoding="utf-8")
    triage.write_text(json.dumps(_triage()), encoding="utf-8")
    matrix.write_text(json.dumps(_matrix()), encoding="utf-8")
    repair.write_text(json.dumps(_repair()), encoding="utf-8")

    assert (
        main(
            [
                "--reviewed-queue",
                str(reviewed),
                "--triage",
                str(triage),
                "--matrix",
                str(matrix),
                "--repair-evidence",
                str(repair),
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
    assert payload["summary"]["candidate_survives_initial_review"] == 2
    assert "MOCC-SE Development Bug-Hunt Report" in markdown
