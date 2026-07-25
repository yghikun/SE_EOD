from src.smt_solver import SolverResult, counter_balance_proven, failure_branch_feasibility


def test_z3_prunes_success_only_branch_after_nonzero_failure():
    result = failure_branch_feasibility(
        result_symbol="ret",
        check_kind="nonzero",
        condition="ret == 0",
        branch_kind="true",
    )

    assert result is SolverResult.UNSAT


def test_z3_accepts_error_cleanup_branch_after_negative_failure():
    result = failure_branch_feasibility(
        result_symbol="ret",
        check_kind="<0",
        condition="ret < 0 && ret != 0",
        branch_kind="true",
    )

    assert result is SolverResult.SAT


def test_z3_keeps_unsupported_branch_expression_unknown():
    result = failure_branch_feasibility(
        result_symbol="ret",
        check_kind="nonzero",
        condition="should_retry(ret)",
        branch_kind="true",
    )

    assert result is SolverResult.UNKNOWN


def test_z3_proves_visible_counter_balance():
    assert counter_balance_proven((("INC", "1"), ("INC", "1"), ("DEC", "2")))
    assert not counter_balance_proven((("INC", "count"), ("DEC", "other_count")))
