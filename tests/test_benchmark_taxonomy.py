import pytest

from scripts.analyze_benchmark_taxonomy import analyze


def test_analyze_taxonomy_prioritizes_false_positive_causes():
    labels = [
        {"sample_id": "one", "verdict": "false_positive"},
        {"sample_id": "two", "verdict": "false_positive"},
        {"sample_id": "three", "verdict": "true_bug"},
    ]
    taxonomy = [
        {"sample_id": "one", "category": "sentinel", "action": "model contract"},
        {"sample_id": "two", "category": "sentinel", "action": "model contract"},
        {"sample_id": "three", "category": "confirmed_bug", "action": "retain"},
    ]

    result = analyze(labels, taxonomy)

    assert result["false_positive_causes"][0] == {
        "category": "sentinel",
        "count": 2,
        "share": 1.0,
        "actions": [{"action": "model contract", "count": 2}],
    }
    assert result["true_bug_families"] == [{"category": "confirmed_bug", "count": 1}]


def test_analyze_taxonomy_requires_matching_samples():
    with pytest.raises(ValueError, match="sample mismatch"):
        analyze(
            [{"sample_id": "one", "verdict": "true_bug"}],
            [{"sample_id": "two", "category": "confirmed_bug", "action": "retain"}],
        )
