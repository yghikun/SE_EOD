import pytest

from scripts.evaluate_benchmark import evaluate


def _pilot(sample_id: str, candidate_type: str = "missing_cleanup") -> dict:
    return {"sample_id": sample_id, "candidate_type": candidate_type}


def _label(sample_id: str, verdict: str) -> dict:
    return {"sample_id": sample_id, "verdict": verdict}


def test_evaluate_benchmark_reports_precision_and_groups():
    pilot = [
        _pilot("sample_1"),
        _pilot("sample_2", "error_swallowed"),
        _pilot("sample_3"),
    ]
    labels = [
        _label("sample_1", "true_bug"),
        _label("sample_2", "false_positive"),
        _label("sample_3", "uncertain"),
    ]

    result = evaluate(pilot, labels)

    assert result["sample_count"] == 3
    assert result["precision"] == 0.3333
    assert result["verdict_counts"] == {
        "false_positive": 1,
        "true_bug": 1,
        "uncertain": 1,
    }
    assert result["by_candidate_type"]["missing_cleanup"]["count"] == 2
    assert result["by_candidate_type"]["error_swallowed"]["precision"] == 0.0


def test_evaluate_benchmark_rejects_sample_mismatch():
    with pytest.raises(ValueError, match="sample mismatch"):
        evaluate([_pilot("sample_1")], [_label("sample_2", "true_bug")])
