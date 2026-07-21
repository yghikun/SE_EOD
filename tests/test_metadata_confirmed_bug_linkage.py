import json

from src.metadata_confirmed_bug_linkage import (
    build_confirmed_linkage_report,
    main,
    parse_confirmed_bugs_markdown,
)


CONFIRMED_MARKDOWN = """\
# Confirmed Bugs

| # | FS | Function | Bug type | Status | Evidence |
|---:|---|---|---|---|---|
| 1 | ext4 | `fixed_fn()` | swallowed error | already fixed upstream / duplicate finding | upstream commit `abc` |
| 2 | btrfs | `for_next_fn()` | cleanup | QEMU confirmed; added to btrfs for-next | report |
| 3 | xfs | `submitted_fn()` | swallowed error | patch submitted | patch |
| 4 | btrfs | `reviewed_fn()` | divergence | patch v2 submitted; Reviewed-by received | lore |
| 5 | ext4 | `source_fn()` | stale error | source-level confirmed | source diff |

## Details

| 1 | `fixed_fn()` | this numeric detail table must not create a duplicate record |
"""


def _bug_hunt_report():
    return {
        "priority_queues": {
            "repair_evidence_first": [
                {
                    "review_id": "review-fixed",
                    "function": "fixed_fn",
                    "protocol_id": "protocol.a",
                    "violation_type": "failure_reported_as_success",
                },
                {
                    "review_id": "review-for-next",
                    "function": "for_next_fn",
                    "protocol_id": "protocol.b",
                    "violation_type": "incomplete_failure_completion",
                },
            ],
            "persistent_candidates_next": [
                {
                    "review_id": "review-submitted",
                    "function": "submitted_fn",
                    "protocol_id": "protocol.a",
                    "violation_type": "failure_reported_as_success",
                },
                {
                    "review_id": "review-unmatched",
                    "function": "unknown_fn",
                    "protocol_id": "protocol.c",
                    "violation_type": "metadata_state_divergence",
                },
            ],
            "removed_or_cleared_functions": [
                {
                    "review_id": "review-fixed",
                    "function": "fixed_fn",
                    "protocol_id": "protocol.a",
                    "violation_type": "failure_reported_as_success",
                }
            ],
        },
        "added_functions_to_inspect": [
            {
                "review_id": "",
                "function": "reviewed_fn",
                "protocol_id": "protocol.c",
                "violation_type": "metadata_state_divergence",
            }
        ],
    }


def test_parse_confirmed_bugs_markdown_and_classify_statuses():
    records = parse_confirmed_bugs_markdown(CONFIRMED_MARKDOWN)

    assert [record.function for record in records] == [
        "fixed_fn",
        "for_next_fn",
        "submitted_fn",
        "reviewed_fn",
        "source_fn",
    ]
    assert [record.status_class for record in records] == [
        "confirmed_fixed_duplicate",
        "confirmed_for_next",
        "confirmed_submitted",
        "confirmed_submitted_reviewed",
        "confirmed_source_level",
    ]


def test_build_linkage_covers_priority_and_top_level_version_queues():
    report = build_confirmed_linkage_report(
        _bug_hunt_report(), parse_confirmed_bugs_markdown(CONFIRMED_MARKDOWN)
    ).to_dict()

    assert report["summary"]["candidate_links"] == 6
    assert report["summary"]["candidates_with_confirmed_bug"] == 5
    assert report["summary"]["confirmed_bug_records_linked"] == 4
    assert report["summary"]["by_status_class"] == {
        "confirmed_fixed_duplicate": 1,
        "confirmed_for_next": 1,
        "confirmed_source_level": 1,
        "confirmed_submitted": 1,
        "confirmed_submitted_reviewed": 1,
    }
    assert report["summary"]["by_linked_status_class"] == {
        "confirmed_fixed_duplicate": 1,
        "confirmed_for_next": 1,
        "confirmed_submitted": 1,
        "confirmed_submitted_reviewed": 1,
    }
    assert report["summary"]["by_link_source"] == {
        "added_functions_to_inspect": 1,
        "persistent_candidates_next": 2,
        "removed_or_cleared_functions": 1,
        "repair_evidence_first": 2,
    }
    links = {(item["function"], item["priority_queue"]): item for item in report["links"]}
    assert links[("for_next_fn", "repair_evidence_first")]["linkage_class"] == "confirmed_for_next"
    assert links[("fixed_fn", "removed_or_cleared_functions")]["linkage_class"] == "confirmed_fixed_duplicate"
    assert links[("submitted_fn", "persistent_candidates_next")]["linkage_class"] == "confirmed_submitted"
    assert links[("reviewed_fn", "added_functions_to_inspect")]["confirmed_bugs"][0]["status_class"] == "confirmed_submitted_reviewed"
    assert report["unmatched_confirmed_bugs"][0]["function"] == "source_fn"


def test_compatibility_layout_does_not_duplicate_version_queue_items():
    item = {
        "review_id": "review-fixed",
        "function": "fixed_fn",
        "protocol_id": "protocol.a",
        "violation_type": "failure_reported_as_success",
    }
    bug_hunt = {
        "priority_queues": {"removed_or_cleared_functions": [item]},
        "removed_or_cleared_functions": [item],
    }

    report = build_confirmed_linkage_report(
        bug_hunt, parse_confirmed_bugs_markdown(CONFIRMED_MARKDOWN)
    ).to_dict()

    assert report["summary"]["candidate_links"] == 1


def test_cli_writes_linkage_json_and_markdown(tmp_path):
    bug_hunt = tmp_path / "bug-hunt.json"
    confirmed = tmp_path / "confirmed.md"
    out_json = tmp_path / "linkage.json"
    out_md = tmp_path / "linkage.md"
    bug_hunt.write_text(json.dumps(_bug_hunt_report()), encoding="utf-8")
    confirmed.write_text(CONFIRMED_MARKDOWN, encoding="utf-8")

    assert (
        main(
            [
                "--bug-hunt-report",
                str(bug_hunt),
                "--confirmed-bugs",
                str(confirmed),
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
    assert payload["summary"]["candidates_with_confirmed_bug"] == 5
    assert "MOCC-SE Confirmed Bug Linkage" in markdown
    assert "not a frozen benchmark" in markdown
    assert "These records remain confirmed" in markdown
