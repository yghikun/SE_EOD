from scripts.compare_experiment_v1_3 import cross_version, old_vs_new


def _candidate(path_id: str, function: str = "demo", condition: str = "ret") -> dict:
    return {
        "candidate_id": path_id,
        "file": "fs/ext4/demo.c",
        "function": function,
        "path_id": path_id,
        "candidate_type": "error_swallowed",
        "condition": condition,
        "final_return_expr": "0",
        "static_evidence": {"error_source_expr": "foo()"},
        "evidence_level": "E0_STATIC_RULE_ONLY",
    }


def test_old_vs_new_reports_removed_and_added_candidates():
    old = [_candidate("demo#001"), _candidate("demo#002")]
    new = [_candidate("demo#002"), _candidate("demo#003")]

    result = old_vs_new(old, new)

    assert result["retained"] == 1
    assert result["removed_count"] == 1
    assert result["added_count"] == 1
    assert result["candidate_reduction"] == 0.0


def test_cross_version_attributes_candidates_in_existing_functions():
    old = [_candidate("demo#001", condition="old_error")]
    new = [_candidate("demo#009", condition="new_error")]
    corpus = [{"file": "fs/ext4/demo.c", "function": "demo"}]

    result = cross_version(old, new, corpus, corpus)

    assert result["persisted"] == 0
    assert result["only_v6_8_count"] == 1
    assert result["only_v7_1_count"] == 1
    assert result["v7_1_only_attribution"] == {
        "candidate_changed_in_existing_function": 1
    }
