import json
from pathlib import Path

from src.metadata_finding_review import (
    apply_source_review_annotations,
    build_review_queue,
    main,
)


def _write_source(root: Path) -> None:
    path = root / "fs" / "fixture" / "work.c"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "int work(void)",
                "{",
                "    int ret = step();",
                "    if (ret)",
                "        return 0;",
                "    return 0;",
                "}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _discovery_report(source_root: Path) -> dict:
    return {
        "schema_version": 1,
        "source_root": str(source_root / "fs"),
        "source_version": "fixture-v1",
        "summary": {
            "protocol_candidate_occurrences": 1,
            "discovery_review_occurrences": 0,
        },
        "analyses": [
            {
                "protocol_id": "test.protocol",
                "operation_id": "op",
                "function": "work",
                "source_file": str(source_root / "fs" / "fixture" / "work.c"),
                "source_version": "fixture-v1",
                "candidates": [
                    {
                        "classification": "PROTOCOL_CANDIDATE",
                        "candidate_id": "candidate-1",
                        "protocol_id": "test.protocol",
                        "operation_id": "op",
                        "violation_type": "metadata_state_divergence",
                        "exit_kind": "success",
                        "exit_id": "success",
                        "static_certainty": "high",
                        "source_file": "fixture/work.c",
                        "source_version": "fixture-v1",
                        "function": "work",
                        "family_fingerprint": "family-1",
                        "occurrence_fingerprint": "occurrence-1",
                        "open_effects": [],
                        "unresolved_failures": [],
                        "accounting_state": [
                            {
                                "obligation_id": "pending_requires_reservation",
                                "observed_state": "pending_without_reservation",
                                "satisfied": False,
                            }
                        ],
                        "representative_witness": [
                            {
                                "kind": "necessary_step",
                                "detail": "step starts attempt",
                                "line": 3,
                            },
                            {
                                "kind": "exit",
                                "detail": "return 0",
                                "line": 5,
                            },
                        ],
                    }
                ],
                "discovery_review": [],
                "unknown": [],
            }
        ],
        "quarantine": [],
    }


def test_build_review_queue_extracts_source_context_and_hints(tmp_path):
    _write_source(tmp_path)

    report = build_review_queue(
        _discovery_report(tmp_path),
        source_root=tmp_path / "fs",
        source_report="discovery.json",
        context_lines=1,
    ).to_dict()

    item = report["items"][0]
    assert report["summary"]["review_items"] == 1
    assert report["summary"]["protocol_candidates"] == 1
    assert item["review_id"] == "mocc_review_occurrence-1"
    assert item["source_context"][0]["start_line"] == 2
    assert "int ret = step();" in item["source_context"][0]["snippet"]
    assert "review reservation/accounting summaries" in item["missing_summary_hints"][0]
    assert item["review_template"]["verdict"].startswith("true_candidate")


def test_cli_writes_json_and_markdown_review_queue(tmp_path):
    _write_source(tmp_path)
    discovery_path = tmp_path / "discovery.json"
    discovery_path.write_text(
        json.dumps(_discovery_report(tmp_path)),
        encoding="utf-8",
    )
    out_json = tmp_path / "queue.json"
    out_md = tmp_path / "queue.md"

    assert (
        main(
            [
                "--discovery-report",
                str(discovery_path),
                "--source-root",
                str(tmp_path / "fs"),
                "--context-lines",
                "1",
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

    assert payload["schema_version"] == 1
    assert payload["summary"]["by_violation_type"] == {
        "metadata_state_divergence": 1
    }
    assert "MOCC-SE Finding Review Queue" in markdown
    assert "This is a development review queue" in markdown


def test_source_review_annotations_attach_to_matching_items(tmp_path):
    _write_source(tmp_path)
    report = build_review_queue(
        _discovery_report(tmp_path),
        source_root=tmp_path / "fs",
        source_report="discovery.json",
        context_lines=1,
    )

    annotated = apply_source_review_annotations(
        report,
        {
            "schema_version": 1,
            "annotations": [
                {
                    "match": {
                        "function": "work",
                        "violation_type": "metadata_state_divergence",
                    },
                    "verdict": "likely_true_candidate",
                    "confidence": "medium",
                    "root_cause": "source path reaches changed metadata with stale accounting",
                    "needs_summary_change": False,
                    "suggested_change": "keep for source review",
                }
            ],
        },
    ).to_dict()

    assert annotated["summary"]["source_review"]["reviewed_items"] == 1
    assert annotated["summary"]["source_review"]["by_verdict"] == {
        "likely_true_candidate": 1
    }
    assert annotated["items"][0]["source_review"]["confidence"] == "medium"
    assert "review_template" not in annotated["items"][0]


def test_source_review_annotations_report_unmatched_records(tmp_path):
    _write_source(tmp_path)
    report = build_review_queue(
        _discovery_report(tmp_path),
        source_root=tmp_path / "fs",
        source_report="discovery.json",
        context_lines=1,
    )

    annotated = apply_source_review_annotations(
        report,
        {
            "schema_version": 1,
            "annotations": [
                {
                    "match": {"function": "not_work"},
                    "verdict": "false_positive",
                    "confidence": "high",
                }
            ],
        },
    ).to_dict()

    source_review = annotated["summary"]["source_review"]
    assert source_review["reviewed_items"] == 0
    assert source_review["unreviewed_items"] == 1
    assert source_review["unmatched_annotations"][0]["match"] == {
        "function": "not_work"
    }
