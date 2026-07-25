from __future__ import annotations

import json
from pathlib import Path

from scripts.compare_residual_runs import compare_runs, write_comparison_artifacts


def _effect(*, line: int = 5, delta: str = "SET") -> dict[str, object]:
    return {
        "root": "inode",
        "key": "i_flags",
        "plane": "RECOVERY",
        "delta": delta,
        "value": "flag",
        "evidence": "DIRECT_SOURCE",
        "site": {
            "file": "linux/fs/btrfs/example.c",
            "line": line,
            "expression": "inode->i_flags = flag;",
        },
    }


def _slice(
    state: str,
    *,
    residuals: list[dict[str, object]] | None = None,
    reaching: list[dict[str, object]] | None = None,
    cancellations: list[dict[str, object]] | None = None,
    protections: list[dict[str, object]] | None = None,
    out_of_scope: list[dict[str, object]] | None = None,
    rationale: str = "",
) -> dict[str, object]:
    return {
        "failure_site": {
            "file": "linux/fs/btrfs/example.c",
            "line": 10,
            "expression": "ret = fail_metadata();",
        },
        "exit_site": {
            "file": "linux/fs/btrfs/example.c",
            "line": 20,
            "expression": "return ret;",
        },
        "state": state,
        "residuals": residuals or [],
        "reaching_effects": reaching or [],
        "cancellations": cancellations or [],
        "protections": protections or [],
        "out_of_scope_effects": out_of_scope or [],
        "rationale": rationale,
    }


def _write_evaluation(directory: Path, slices: list[dict[str, object]]) -> Path:
    evaluation = directory / "files" / "fs_btrfs_example.c" / "evaluation.json"
    evaluation.parent.mkdir(parents=True)
    evaluation.write_text(
        json.dumps(
            {
                "analyses": [
                    {
                        "function": "work",
                        "slicing_result": {"slices": slices},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return directory


def test_compare_runs_requires_current_effect_witness_for_closed(tmp_path: Path):
    effect = _effect()
    baseline = _write_evaluation(
        tmp_path / "baseline",
        [_slice("EXPOSED", residuals=[effect], reaching=[effect])],
    )
    current = _write_evaluation(
        tmp_path / "current",
        [_slice("CLOSED", reaching=[effect], cancellations=[_effect(delta="CLEAR")])],
    )

    comparison = compare_runs(baseline, current)

    matrix = comparison["report_transition_matrix"]["transition_matrix"]
    assert matrix == [{"old_state": "CANDIDATE", "new_state": "CLOSED", "count": 1}]
    resolved = comparison["resolved_candidates"]
    assert resolved[0]["resolution_reason"] == [
        "classification:CANDIDATE->CLOSED",
        "source_visible_cancellation",
    ]
    assert resolved[0]["stable_witness"]["effect"]["site"]["line"] == 5
    assert resolved[0]["new_cancellation_evidence"][0]["delta"] == "CLEAR"


def test_compare_runs_keeps_missing_current_witness_unmatched(tmp_path: Path):
    effect = _effect()
    baseline = _write_evaluation(
        tmp_path / "baseline",
        [_slice("UNKNOWN", residuals=[effect], reaching=[effect], rationale="indirect_call")],
    )
    current = _write_evaluation(tmp_path / "current", [])

    comparison = compare_runs(baseline, current)

    assert comparison["report_transition_matrix"]["unmatched_baseline_witness_count"] == 1
    lost = comparison["lost_known_witnesses"]
    assert lost[0]["old_state"] == "UNKNOWN"
    assert lost[0]["new_state"] == "UNMATCHED"
    assert lost[0]["resolution_reason"] == ["current_witness_unmatched"]


def test_compare_runs_retains_nonresidual_reaching_effect_without_resolving_it(
    tmp_path: Path,
):
    retained = _effect(line=5)
    certain = _effect(line=6)
    certain["key"] = "certain_flag"
    baseline = _write_evaluation(
        tmp_path / "baseline",
        [_slice("UNKNOWN", residuals=[retained], reaching=[retained])],
    )
    current = _write_evaluation(
        tmp_path / "current",
        [_slice("EXPOSED", residuals=[certain], reaching=[retained, certain])],
    )

    comparison = compare_runs(baseline, current)

    assert comparison["report_transition_matrix"]["transition_matrix"] == [
        {
            "old_state": "UNKNOWN",
            "new_state": "RETAINED_REACHING",
            "count": 1,
        }
    ]
    assert comparison["report_transition_matrix"]["unmatched_baseline_witness_count"] == 0
    assert comparison["resolved_unknowns"] == []
    assert comparison["lost_known_witnesses"] == []


def test_compare_runs_tracks_closed_effect_inside_mixed_slice(tmp_path: Path):
    closed_effect = _effect(line=5)
    remaining_effect = _effect(line=6)
    remaining_effect["key"] = "compress_log_size"
    baseline = _write_evaluation(
        tmp_path / "baseline",
        [_slice("EXPOSED", residuals=[closed_effect], reaching=[closed_effect])],
    )
    restore = _effect(delta="RESTORE")
    restore["snapshot_relation"] = {"source_identity": "inode->mount_opt"}
    current = _write_evaluation(
        tmp_path / "current",
        [
            _slice(
                "EXPOSED",
                residuals=[remaining_effect],
                reaching=[closed_effect, remaining_effect],
                cancellations=[restore],
            )
        ],
    )

    comparison = compare_runs(baseline, current)

    assert comparison["resolved_candidates"][0]["new_state"] == "CLOSED"
    relation = comparison["resolved_candidates"][0]["new_cancellation_evidence"][0][
        "snapshot_relation"
    ]
    assert relation["source_identity"] == "inode->mount_opt"
    assert comparison["lost_known_witnesses"] == []


def test_compare_runs_writes_review_artifacts_and_detects_new_candidate(tmp_path: Path):
    effect = _effect()
    baseline = _write_evaluation(tmp_path / "baseline", [])
    current = _write_evaluation(
        tmp_path / "current",
        [_slice("EXPOSED", residuals=[effect], reaching=[effect])],
    )

    comparison = compare_runs(baseline, current)
    paths = write_comparison_artifacts(comparison, tmp_path / "artifacts")

    assert comparison["report_transition_matrix"]["new_candidate_count"] == 1
    assert json.loads(paths["new_candidates"].read_text(encoding="utf-8"))[0][
        "classification"
    ] == "CANDIDATE"
    assert set(path.name for path in paths.values()) == {
        "report_transition_matrix.json",
        "resolved_candidates.json",
        "resolved_unknowns.json",
        "new_candidates.json",
        "lost_known_witnesses.json",
    }


def test_compare_runs_matches_transient_effect_as_out_of_scope(tmp_path: Path):
    effect = _effect()
    baseline = _write_evaluation(
        tmp_path / "baseline",
        [_slice("EXPOSED", residuals=[effect], reaching=[effect])],
    )
    transient = dict(effect)
    transient["transient_provenance"] = [
        {
            "parameter": "inode",
            "parameter_index": 0,
            "pointee_type": "struct inode",
            "caller_function": "caller",
            "caller_local": "operation",
        }
    ]
    current = _write_evaluation(
        tmp_path / "current",
        [_slice("CLOSED", out_of_scope=[transient])],
    )

    comparison = compare_runs(baseline, current)

    assert comparison["report_transition_matrix"]["transition_matrix"] == [
        {"old_state": "CANDIDATE", "new_state": "OUT_OF_SCOPE", "count": 1}
    ]
    resolved = comparison["resolved_candidates"][0]
    assert resolved["new_out_of_scope_evidence"][0]["caller_local"] == "operation"
    assert comparison["lost_known_witnesses"] == []
