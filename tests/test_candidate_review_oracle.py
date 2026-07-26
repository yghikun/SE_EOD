import json
from pathlib import Path

from src.candidate_review_oracle import (
    audit_oracle,
    build_oracle_record,
    compare_audit_safety,
)


def _effect(line: int = 5) -> dict[str, object]:
    return {
        "root": "inode",
        "key": "i_flags",
        "plane": "RECOVERY",
        "delta": "SET",
        "value": "flag",
        "evidence": "DIRECT_SOURCE",
        "site": {
            "file": "linux-sources/linux-v6.14-fs/fs/btrfs/example.c",
            "line": line,
            "expression": "inode->i_flags = flag;",
        },
    }


def _slice(
    state: str,
    *,
    residuals=None,
    reaching=None,
    out_of_scope=None,
    containment_proofs=None,
):
    return {
        "failure_site": {
            "file": "linux-sources/linux-v6.14-fs/fs/btrfs/example.c",
            "line": 10,
            "expression": "ret = fail_metadata();",
        },
        "exit_site": {
            "file": "linux-sources/linux-v6.14-fs/fs/btrfs/example.c",
            "line": 20,
            "expression": "return ret;",
        },
        "state": state,
        "residuals": residuals or [],
        "reaching_effects": reaching or [],
        "out_of_scope_effects": out_of_scope or [],
        "containment_proofs": containment_proofs or [],
    }


def _review(**overrides):
    review = {
        "id": "BTRFS-001",
        "filesystem": "btrfs",
        "report_validity": "FALSE_POSITIVE",
        "bug_status": "NO_BUG",
        "source_verdict": "FALSE_ALARM",
        "root_cause_family": "PRIVATE_OR_CLEANED_STATE",
        "rationale": "private owner",
        "related_finding": "",
        "reviewed_on": "2026-07-24",
    }
    review.update(overrides)
    return review


def _report(effect):
    return {
        "function": "work",
        "residual_slice": _slice("EXPOSED", residuals=[effect], reaching=[effect]),
    }


def _write_evaluation(path: Path, residual_slice):
    evaluation = path / "files" / "one" / "evaluation.json"
    evaluation.parent.mkdir(parents=True)
    evaluation.write_text(
        json.dumps(
            {
                "analyses": [
                    {
                        "function": "work",
                        "slicing_result": {"slices": [residual_slice]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_oracle_record_is_report_level_and_uses_structured_stable_effects():
    effect = _effect()
    oracle = build_oracle_record(
        _review(),
        _report(effect),
        baseline_run="m32d",
    )

    assert oracle["oracle_granularity"] == "REPORT"
    assert oracle["expected_final_state"] == "OUT_OF_SCOPE"
    assert oracle["manual_class"] == "PRIVATE_OR_TRANSIENT_OR_ALREADY_CLEANED"
    effects = oracle["stable_report"]["residual_effects"]
    assert effects[0]["site"]["line"] == 5
    assert "effect_summary" not in oracle
    assert oracle["stable_key"].startswith("sha256:")


def test_oracle_audit_counts_false_positive_resolution(tmp_path: Path):
    effect = _effect()
    oracle = build_oracle_record(_review(), _report(effect), baseline_run="m32d")
    _write_evaluation(
        tmp_path / "current",
        _slice("CLOSED", out_of_scope=[effect]),
    )

    audit = audit_oracle([oracle], tmp_path / "current")

    assert audit["summary"]["manual_false_positives_correctly_moved"] == 1
    assert audit["summary"]["safety_regression_count"] == 0
    assert audit["transitions"][0]["effect_states"] == ["OUT_OF_SCOPE"]


def test_oracle_audit_keeps_live_residual_visible_and_flags_unknown(tmp_path: Path):
    effect = _effect()
    review = _review(
        report_validity="TRUE_RESIDUAL",
        bug_status="BUG",
        source_verdict="TRUE_ISSUE",
        root_cause_family="PUBLISHED_DEVICE_NOT_ROLLED_BACK",
    )
    oracle = build_oracle_record(review, _report(effect), baseline_run="m32d")
    _write_evaluation(
        tmp_path / "current",
        _slice("EXPOSED", residuals=[effect], reaching=[effect]),
    )

    audit = audit_oracle([oracle], tmp_path / "current")
    assert audit["summary"]["manual_live_residuals_retained"] == 1
    assert audit["summary"]["safety_regression_count"] == 0

    _write_evaluation(
        tmp_path / "live",
        _slice("LIVE", residuals=[effect], reaching=[effect]),
    )
    completed = audit_oracle([oracle], tmp_path / "live")
    assert completed["transitions"][0]["current_classification"] == (
        "LIVE_METADATA_RESIDUAL"
    )
    assert completed["summary"]["manual_live_residuals_retained"] == 1

    _write_evaluation(
        tmp_path / "unknown",
        _slice("UNKNOWN", residuals=[effect], reaching=[effect]),
    )
    regression = audit_oracle([oracle], tmp_path / "unknown")
    assert regression["summary"]["candidate_to_unknown_count"] == 1
    assert regression["summary"]["safety_regression_count"] == 1

    compare_audit_safety(regression, regression)
    assert regression["summary"]["preexisting_safety_issue_ids"] == ["BTRFS-001"]
    assert regression["summary"]["new_safety_regression_count"] == 0


def test_oracle_audit_accepts_unknown_when_manual_review_is_uncertain(tmp_path: Path):
    effect = _effect()
    review = _review(
        report_validity="INCONCLUSIVE",
        source_verdict="UNRESOLVED",
        root_cause_family="ONE_SHOT_STATE_SEMANTICS",
    )
    oracle = build_oracle_record(review, _report(effect), baseline_run="m32d")
    _write_evaluation(
        tmp_path / "current",
        _slice("UNKNOWN", residuals=[effect], reaching=[effect]),
    )

    audit = audit_oracle([oracle], tmp_path / "current")
    assert audit["transitions"][0]["status"] == "EXPECTED_STATE_REACHED"
    assert audit["summary"]["safety_regression_count"] == 0


def test_oracle_audit_reads_effect_scoped_containment_in_mixed_slice(tmp_path: Path):
    effect = _effect()
    unrelated = _effect(line=6)
    unrelated["key"] = "unrelated_state"
    review = _review(
        report_validity="TRUE_RESIDUAL",
        source_verdict="CONTAINED_NOT_BUG",
        root_cause_family="TRANSACTION_OR_FATAL_CONTAINMENT",
    )
    oracle = build_oracle_record(review, _report(effect), baseline_run="m32d")
    _write_evaluation(
        tmp_path / "current",
        _slice(
            "EXPOSED",
            residuals=[effect, unrelated],
            reaching=[effect, unrelated],
            containment_proofs=[
                {
                    "kind": "TRANSACTION_ABORT",
                    "covered_effects": [effect],
                }
            ],
        ),
    )

    audit = audit_oracle([oracle], tmp_path / "current")

    assert audit["transitions"][0]["effect_states"] == [
        "CONTAINED_METADATA_RESIDUAL"
    ]
    assert audit["summary"]["manual_contained_residuals_recognized"] == 1
