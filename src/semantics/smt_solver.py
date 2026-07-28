"""Bounded Z3 queries for failure-path residual analysis.

This module deliberately models only branch predicates and counter deltas
already visible in the source slice. It does not attempt C memory or alias
semantics. An unsupported expression or unavailable solver yields UNKNOWN,
which callers must handle conservatively.
"""

from __future__ import annotations

import re
from enum import Enum
from functools import lru_cache
from typing import Iterable


class SolverResult(str, Enum):
    SAT = "SAT"
    UNSAT = "UNSAT"
    UNKNOWN = "UNKNOWN"


@lru_cache(maxsize=1)
def _z3():
    try:
        import z3
    except ImportError:
        return None
    return z3


def solver_available() -> bool:
    return _z3() is not None


def failure_branch_feasibility(
    *,
    result_symbol: str,
    check_kind: str,
    condition: str,
    branch_kind: str,
) -> SolverResult:
    """Check whether a branch can execute after a verified failure edge."""

    z3 = _z3()
    if z3 is None or branch_kind not in {"true", "false"}:
        return SolverResult.UNKNOWN
    result = z3.Int(_symbol_name(result_symbol))
    solver = z3.Solver()
    failure = _failure_constraint(z3, result, check_kind)
    predicate = _predicate(z3, condition, result_symbol, result)
    if failure is None or predicate is None:
        return SolverResult.UNKNOWN
    solver.add(failure)
    solver.add(predicate if branch_kind == "true" else z3.Not(predicate))
    return _check(solver)


def counter_balance_proven(
    deltas: Iterable[tuple[str, str]],
) -> bool:
    """Return true only when visible counter deltas necessarily sum to zero."""

    z3 = _z3()
    if z3 is None:
        return False
    total = z3.IntVal(0)
    for direction, value in deltas:
        term = _counter_term(z3, value)
        if term is None:
            return False
        total += term if direction == "INC" else -term
    solver = z3.Solver()
    solver.add(total != 0)
    return _check(solver) is SolverResult.UNSAT


def _failure_constraint(z3, result, check_kind: str):
    if check_kind in {"nonzero", "!=0", "0!="}:
        return result != 0
    if check_kind in {"negative", "<0", "0>"}:
        return result < 0
    if check_kind in {">0", "0<"}:
        return result > 0
    # Error-pointer checks do not have a portable integer representation in
    # this bounded model. Later direct integer comparisons remain UNKNOWN.
    return None


def _predicate(z3, expression: str, result_symbol: str, result):
    expr = _strip_outer_parens(_compact(expression))
    parts = _split_top_level(expr, "||")
    if len(parts) > 1:
        parsed = [_predicate(z3, item, result_symbol, result) for item in parts]
        return None if any(item is None for item in parsed) else z3.Or(*parsed)
    parts = _split_top_level(expr, "&&")
    if len(parts) > 1:
        parsed = [_predicate(z3, item, result_symbol, result) for item in parts]
        return None if any(item is None for item in parsed) else z3.And(*parsed)
    if expr.startswith("!"):
        inner = _predicate(z3, expr[1:], result_symbol, result)
        return z3.Not(inner) if inner is not None else None
    symbol = re.escape(_compact(result_symbol))
    if re.fullmatch(symbol, expr):
        return result != 0
    for operator, build in (
        ("==", lambda value: result == value),
        ("!=", lambda value: result != value),
        ("<=", lambda value: result <= value),
        (">=", lambda value: result >= value),
        ("<", lambda value: result < value),
        (">", lambda value: result > value),
    ):
        match = re.fullmatch(rf"{symbol}{re.escape(operator)}(-?\d+)", expr)
        if match:
            return build(int(match.group(1)))
        match = re.fullmatch(rf"(-?\d+){re.escape(operator)}{symbol}", expr)
        if match:
            value = int(match.group(1))
            inverse = {
                "==": lambda: result == value,
                "!=": lambda: result != value,
                "<=": lambda: result >= value,
                ">=": lambda: result <= value,
                "<": lambda: result > value,
                ">": lambda: result < value,
            }
            return inverse[operator]()
    return None


def _counter_term(z3, value: str):
    text = _compact(value)
    if re.fullmatch(r"-?\d+", text):
        return z3.IntVal(int(text))
    if re.fullmatch(r"[A-Za-z_]\w*", text):
        return z3.Int(_symbol_name(text))
    return None


def _check(solver) -> SolverResult:
    result = solver.check()
    text = str(result)
    if text == "sat":
        return SolverResult.SAT
    if text == "unsat":
        return SolverResult.UNSAT
    return SolverResult.UNKNOWN


def _compact(value: str) -> str:
    return "".join(value.split())


def _strip_outer_parens(value: str) -> str:
    while value.startswith("(") and value.endswith(")"):
        depth = 0
        wraps_all = True
        for index, char in enumerate(value):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and index != len(value) - 1:
                    wraps_all = False
                    break
        if not wraps_all:
            break
        value = value[1:-1]
    return value


def _split_top_level(value: str, operator: str) -> list[str]:
    depth = 0
    start = 0
    result: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth == 0 and value.startswith(operator, index):
            result.append(value[start:index])
            start = index + len(operator)
            index += len(operator) - 1
        index += 1
    result.append(value[start:])
    return result


def _symbol_name(value: str) -> str:
    return "residual_" + re.sub(r"\W+", "_", _compact(value)).strip("_")
