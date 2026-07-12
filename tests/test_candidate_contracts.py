from src.candidate_rules import _suppressed_by_review_contract


def test_review_contracts_match_confirmed_exceptions_by_path_id():
    contracts = {
        "review_confirmed_bug_exceptions": [
            {
                "function": "demo",
                "candidate_type": "error_swallowed",
                "path_ids": ["demo#true"],
                "match_path_ids": True,
            }
        ],
        "review_false_positive_rules": [
            {
                "function": "demo",
                "candidate_type": "error_swallowed",
                "path_ids": ["demo#false"],
                "match_path_ids": True,
            }
        ],
    }

    true_row = {"function": "demo", "path_id": "demo#true"}
    false_row = {"function": "demo", "path_id": "demo#false"}
    unrelated_row = {"function": "demo", "path_id": "demo#other"}

    assert not _suppressed_by_review_contract(true_row, "error_swallowed", contracts)
    assert _suppressed_by_review_contract(false_row, "error_swallowed", contracts)
    assert not _suppressed_by_review_contract(unrelated_row, "error_swallowed", contracts)


def test_review_contract_error_lines_remain_provenance_only():
    contracts = {
        "review_false_positive_rules": [
            {
                "function": "demo",
                "candidate_type": "error_swallowed",
                "error_lines": [12],
            }
        ]
    }

    assert _suppressed_by_review_contract(
        {"function": "demo", "error_line": "12"}, "error_swallowed", contracts
    )
    assert _suppressed_by_review_contract(
        {"function": "demo", "error_line": "13"}, "error_swallowed", contracts
    )


def test_review_contract_path_ids_are_provenance_without_strict_flag():
    contracts = {
        "review_false_positive_rules": [
            {
                "function": "demo",
                "candidate_type": "error_swallowed",
                "path_ids": ["demo#old-version"],
            }
        ]
    }

    assert _suppressed_by_review_contract(
        {"function": "demo", "path_id": "demo#new-version"},
        "error_swallowed",
        contracts,
    )
