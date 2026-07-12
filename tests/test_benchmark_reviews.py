import pytest

from scripts.compare_benchmark_reviews import compare


def _label(sample_id: str, verdict: str) -> dict:
    return {"sample_id": sample_id, "verdict": verdict}


def test_compare_reviews_reports_agreement_and_kappa():
    first = [_label("one", "true_bug"), _label("two", "false_positive")]
    second = [_label("one", "true_bug"), _label("two", "true_bug")]

    result = compare(first, second)

    assert result["agreement_rate"] == 0.5
    assert result["cohen_kappa"] == 0.0
    assert result["disagreements"] == [
        {"sample_id": "two", "first": "false_positive", "second": "true_bug"}
    ]


def test_compare_reviews_rejects_unfilled_labels():
    with pytest.raises(ValueError, match="invalid second verdict"):
        compare([_label("one", "true_bug")], [_label("one", None)])
