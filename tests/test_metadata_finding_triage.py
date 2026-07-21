import json

import pytest

from src.metadata_finding_triage import (
    TriageDecision,
    build_triage_report,
    decisions_from_source_reviews,
    main,
)


def _queue():
    return {
        "schema_version": 1,
        "items": [
            {
                "review_id": "review-1",
                "protocol_id": "protocol.a",
                "function": "work",
                "violation_type": "failure_reported_as_success",
                "source_file": "fixture/work.c",
            },
            {
                "review_id": "review-2",
                "protocol_id": "protocol.b",
                "function": "cleanup",
                "violation_type": "incomplete_failure_completion",
                "source_file": "fixture/cleanup.c",
            },
        ],
    }


def test_build_triage_report_merges_decisions_and_summarizes_verdicts():
    report = build_triage_report(
        _queue(),
        [
            TriageDecision(
                "review-1",
                "candidate_survives_initial_review",
                "medium",
                ("return 0 is reachable after step failure",),
                ("source_review",),
            )
        ],
        review_queue_source="queue.json",
        decisions_source="decisions.json",
    ).to_dict()

    assert report["summary"]["triage_items"] == 2
    assert report["summary"]["reviewed_items"] == 1
    assert report["summary"]["unreviewed_items"] == 1
    assert report["summary"]["by_verdict"] == {
        "candidate_survives_initial_review": 1,
        "unreviewed": 1,
    }
    assert report["summary"]["surviving_candidates_by_protocol"] == {"protocol.a": 1}
    assert report["items"][0]["triage"]["source_evidence"] == [
        "return 0 is reachable after step failure"
    ]
    assert report["items"][1]["triage"] is None


def test_build_triage_report_rejects_unknown_review_id():
    with pytest.raises(ValueError, match="unknown review ids"):
        build_triage_report(
            _queue(),
            [TriageDecision("missing", "uncertain", "low", (), ())],
        )


def test_build_triage_report_rejects_duplicate_decisions():
    with pytest.raises(ValueError, match="duplicate triage decision"):
        build_triage_report(
            _queue(),
            [
                TriageDecision("review-1", "uncertain", "low", (), ()),
                TriageDecision("review-1", "likely_false_positive", "low", (), ()),
            ],
        )


def test_cli_writes_triage_json_and_markdown(tmp_path):
    queue_path = tmp_path / "queue.json"
    decisions_path = tmp_path / "decisions.json"
    out_json = tmp_path / "triage.json"
    out_md = tmp_path / "triage.md"
    queue_path.write_text(json.dumps(_queue()), encoding="utf-8")
    decisions_path.write_text(
        json.dumps(
            {
                "decisions": [
                    {
                        "review_id": "review-2",
                        "verdict": "likely_false_positive",
                        "confidence": "medium",
                        "source_evidence": ["helper cleanup is present"],
                        "development_followups": ["add helper summary"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "--review-queue",
                str(queue_path),
                "--decisions",
                str(decisions_path),
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
    assert payload["summary"]["by_verdict"] == {
        "likely_false_positive": 1,
        "unreviewed": 1,
    }
    assert "MOCC-SE Initial Source Triage" in markdown
    assert "helper cleanup is present" in markdown


def test_decisions_from_source_reviews_maps_review_verdicts():
    queue = _queue()
    queue["items"][0]["source_review"] = {
        "verdict": "likely_true_candidate",
        "confidence": "high",
        "root_cause": "return 0 is source-visible after failure",
        "suggested_change": "keep as development candidate",
        "notes": "not a benchmark label",
    }
    queue["items"][1]["source_review"] = {
        "verdict": "false_positive",
        "confidence": "medium",
        "root_cause": "callee cleanup is source-visible",
        "needs_summary_change": True,
    }

    decisions = decisions_from_source_reviews(queue)

    assert [item.verdict for item in decisions] == [
        "candidate_survives_initial_review",
        "likely_false_positive",
    ]
    assert decisions[0].source_evidence == (
        "return 0 is source-visible after failure",
        "not a benchmark label",
    )
    assert "needs summary change" in decisions[1].development_followups


def test_cli_can_derive_decisions_from_reviewed_queue(tmp_path):
    queue = _queue()
    queue["items"][0]["source_review"] = {
        "verdict": "likely_true_candidate",
        "confidence": "high",
        "root_cause": "source evidence survives initial review",
    }
    queue_path = tmp_path / "reviewed-queue.json"
    out_json = tmp_path / "triage.json"
    out_md = tmp_path / "triage.md"
    queue_path.write_text(json.dumps(queue), encoding="utf-8")

    assert (
        main(
            [
                "--review-queue",
                str(queue_path),
                "--out-json",
                str(out_json),
                "--out-md",
                str(out_md),
            ]
        )
        == 0
    )

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["decisions_source"] == "<source_review>"
    assert payload["summary"]["surviving_candidates_by_protocol"] == {
        "protocol.a": 1
    }
