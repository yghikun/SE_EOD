from scripts.compare_interprocedural_ablation import compare


def candidate(candidate_id: str, path_id: str, candidate_type: str = "missing_cleanup"):
    return {
        "candidate_id": candidate_id,
        "file": "fs/ext4/demo.c",
        "function": "demo",
        "path_id": path_id,
        "candidate_type": candidate_type,
        "condition": "ret < 0",
        "final_return_expr": "ret",
        "static_evidence": {"error_source_expr": "work()"},
    }


def test_ablation_reports_pilot_retention_without_claiming_precision():
    before = [candidate("true", "path-1"), candidate("false", "path-2")]
    after = [candidate("true", "path-1")]
    pilot = {
        "true": {"sample_id": "sample-1", "verdict": "true_bug"},
        "false": {"sample_id": "sample-2", "verdict": "false_positive"},
        "missing": {"sample_id": "sample-3", "verdict": "false_positive"},
    }

    result = compare(before, after, pilot)

    assert result["removed"] == 1
    assert result["pilot"]["eligible"] == 2
    assert result["pilot"]["not_in_baseline"] == 1
    assert result["pilot"]["true_positive_retention"] == 1.0
    assert result["pilot"]["labeled_false_positives_removed"] == 1
