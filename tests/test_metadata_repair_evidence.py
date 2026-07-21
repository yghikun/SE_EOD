import json

from src.metadata_repair_evidence import (
    build_repair_evidence_report,
    main,
    repair_evidence_from_function_diff,
)


def _triage():
    return {
        "schema_version": 1,
        "items": [
            {
                "review_id": "review-1",
                "protocol_id": "protocol.a",
                "function": "fixed",
                "violation_type": "failure_reported_as_success",
                "triage": {"verdict": "candidate_survives_initial_review"},
            },
            {
                "review_id": "review-2",
                "protocol_id": "protocol.a",
                "function": "unchanged",
                "violation_type": "failure_reported_as_success",
                "triage": {"verdict": "candidate_survives_initial_review"},
            },
        ],
    }


def _function_diff(function: str):
    return {
        "schema_version": 1,
        "function": function,
        "pair_diffs": [
            {
                "from_version": "old",
                "to_version": "new",
                "semantic_hints": [
                    "return_success_changed_to_error_symbol",
                    "local_return_propagation_repair",
                ],
                "removed_lines": ["\treturn 0;"],
                "added_lines": ["\treturn error;"],
            }
        ],
    }


def test_repair_evidence_from_function_diff_filters_by_required_hint():
    evidence = repair_evidence_from_function_diff(
        _function_diff("fixed"),
        source_report="diff.json",
    )

    assert len(evidence) == 1
    assert evidence[0].function == "fixed"
    assert evidence[0].removed_returns == ("\treturn 0;",)
    assert evidence[0].added_returns == ("\treturn error;",)


def test_build_repair_evidence_report_attaches_by_function():
    evidence = repair_evidence_from_function_diff(_function_diff("fixed"))
    report = build_repair_evidence_report(_triage(), evidence).to_dict()

    assert report["summary"]["items_with_repair_evidence"] == 1
    assert report["summary"]["by_repair_hint"]["local_return_propagation_repair"] == 1
    assert report["items"][0]["repair_evidence"][0]["function"] == "fixed"
    assert "repair_evidence" not in report["items"][1]


def test_cli_writes_repair_evidence_json_and_markdown(tmp_path):
    triage = tmp_path / "triage.json"
    diff = tmp_path / "diff.json"
    out_json = tmp_path / "repair.json"
    out_md = tmp_path / "repair.md"
    triage.write_text(json.dumps(_triage()), encoding="utf-8")
    diff.write_text(json.dumps(_function_diff("fixed")), encoding="utf-8")

    assert (
        main(
            [
                "--triage",
                str(triage),
                "--function-diff",
                str(diff),
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
    assert payload["summary"]["items_with_repair_evidence"] == 1
    assert "MOCC-SE Repair Evidence Ledger" in markdown
    assert "return 0" in markdown
