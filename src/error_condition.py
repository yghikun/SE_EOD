"""Error-condition classification."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .parser import compact_ws


@dataclass
class ConditionInfo:
    condition: str
    condition_type: str
    error_var: str
    confidence: str
    reason: str


ERRNO_RE = re.compile(r"^-\s*E[A-Z0-9_]+$")
ERROR_VAR_NAMES = {"ret", "err", "error", "errno", "rc", "retval", "status"}


def strip_outer_parens(expr: str) -> str:
    expr = compact_ws(expr)
    changed = True
    while changed and expr.startswith("(") and expr.endswith(")"):
        changed = False
        depth = 0
        for idx, ch in enumerate(expr):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and idx != len(expr) - 1:
                    return expr
        if depth == 0:
            expr = expr[1:-1].strip()
            changed = True
    return compact_ws(expr)


def _first_identifier(expr: str) -> str:
    match = re.search(r"\b([A-Za-z_]\w*)\b", expr)
    return match.group(1) if match else "unknown"


RESOURCE_EXPR_RE = r"[A-Za-z_]\w*(?:\s*(?:->|\.)\s*[A-Za-z_]\w*)*(?:\s*\[[^\]]+\])?"


def is_error_return_expr(expr: str, error_var: str = "") -> bool:
    expr = compact_ws(expr)
    if not expr:
        return False
    if ERRNO_RE.match(expr):
        return True
    if re.match(r"^-\s*[A-Za-z_]\w+$", expr):
        return True
    if expr in {"NULL"}:
        return True
    if re.match(r"^(PTR_ERR|ERR_PTR)\s*\(", expr):
        return True
    if expr in ERROR_VAR_NAMES:
        return True
    if error_var and expr == error_var:
        return True
    return False


def return_expr_type(expr: str) -> str:
    expr = compact_ws(expr)
    if expr == "NULL":
        return "pointer_null_return"
    if re.match(r"^ERR_PTR\s*\(", expr):
        return "err_ptr_return"
    if re.match(r"^PTR_ERR\s*\(", expr):
        return "ptr_err_propagation"
    if ERRNO_RE.match(expr) or re.match(r"^-\s*[A-Za-z_]\w+$", expr):
        return "negative_errno_return"
    if expr in ERROR_VAR_NAMES:
        return "error_var_return"
    return "return"


def is_errorish_label(label: str) -> bool:
    return bool(re.match(r"^(out|err|error|fail|failed|cleanup)(?:_|$)", label))


def classify_condition(
    condition: str,
    final_return_expr: str = "",
    target_label: str = "",
) -> ConditionInfo:
    cond = strip_outer_parens(condition)

    match = re.match(rf"^IS_ERR_OR_NULL\s*\(\s*({RESOURCE_EXPR_RE})\s*\)$", cond)
    if match:
        return ConditionInfo(
            cond,
            "err_ptr_check",
            compact_ws(match.group(1)),
            "high",
            "IS_ERR_OR_NULL pointer failure check",
        )

    match = re.match(rf"^IS_ERR\s*\(\s*({RESOURCE_EXPR_RE})\s*\)$", cond)
    if match:
        return ConditionInfo(
            cond,
            "err_ptr_check",
            compact_ws(match.group(1)),
            "high",
            "IS_ERR pointer failure check",
        )

    match = re.match(rf"^!\s*({RESOURCE_EXPR_RE})$", cond)
    if match:
        return ConditionInfo(
            cond,
            "null_check",
            compact_ws(match.group(1)),
            "high",
            "NULL pointer failure check",
        )

    match = re.match(rf"^({RESOURCE_EXPR_RE})\s*==\s*NULL$", cond) or re.match(
        rf"^NULL\s*==\s*({RESOURCE_EXPR_RE})$", cond
    )
    if match:
        return ConditionInfo(
            cond,
            "null_check",
            compact_ws(match.group(1)),
            "high",
            "NULL pointer failure check",
        )

    if re.search(r">\s*end\b", cond) or re.search(r"\bend\s*<", cond):
        return ConditionInfo(
            cond,
            "bounds_check",
            _first_identifier(cond),
            "high",
            "pointer or buffer bounds validation check",
        )

    match = re.match(r"^([A-Za-z_]\w*)\s*<\s*sizeof\s*\(", cond)
    if match:
        return ConditionInfo(
            cond,
            "invalid_size",
            match.group(1),
            "high",
            "size is smaller than required structure",
        )

    match = re.match(r"^([A-Za-z_]\w*)\s*<\s*0$", cond)
    if match:
        return ConditionInfo(
            cond,
            "negative_error",
            match.group(1),
            "high",
            "negative value indicates an error",
        )

    match = re.match(r"^([A-Za-z_]\w*)\s*==\s*0$", cond)
    if match:
        var = match.group(1)
        condition_type = "invalid_count" if var in {"count", "n"} else "state_or_validation_error"
        return ConditionInfo(
            cond,
            condition_type,
            var,
            "medium",
            "zero value validation check",
        )

    match = re.match(r"^([A-Za-z_]\w*)\s*(?:!=|==)\s*0$", cond)
    if match:
        var = match.group(1)
        if var in ERROR_VAR_NAMES:
            return ConditionInfo(
                cond,
                "ret_nonzero",
                var,
                "high",
                "canonical non-zero error variable check",
            )

    match = re.match(r"^(.+?)\s*!=\s*(.+)$", cond)
    if match:
        left, right = match.group(1), match.group(2)
        condition_type = "invalid_version" if "version" in cond.lower() else "state_or_validation_error"
        confidence = "high" if is_error_return_expr(final_return_expr) or is_errorish_label(target_label) else "medium"
        return ConditionInfo(
            cond,
            condition_type,
            _first_identifier(left),
            confidence,
            "mismatch validation check",
        )

    match = re.match(r"^([A-Za-z_]\w*)\s*(<|!=|==)\s*(-?\d+|0)$", cond)
    if match:
        var, op, rhs = match.group(1), match.group(2), match.group(3)
        if op in {"<", "!="}:
            return ConditionInfo(
                cond,
                "negative_error",
                var,
                "high",
                "integer error variable comparison",
            )
        if op == "==" and rhs != "0":
            return ConditionInfo(
                cond,
                "specific_error_code",
                var,
                "medium",
                "specific non-zero comparison may represent an error",
            )

    match = re.match(r"^([A-Za-z_]\w*)$", cond)
    if match:
        var = match.group(1)
        if var in ERROR_VAR_NAMES:
            return ConditionInfo(
                cond,
                "ret_nonzero",
                var,
                "high",
                "canonical non-zero error variable check",
            )
        if is_error_return_expr(final_return_expr, var) or is_errorish_label(target_label):
            return ConditionInfo(
                cond,
                "state_or_validation_error",
                var,
                "medium",
                "non-zero condition flows to an error-like exit",
            )
        return ConditionInfo(
            cond,
            "nonzero_condition",
            var,
            "low",
            "non-zero condition may be ordinary control flow",
        )

    if is_errorish_label(target_label) or is_error_return_expr(final_return_expr):
        return ConditionInfo(
            cond,
            "unknown_error_like",
            _first_identifier(cond),
            "medium",
            "compound condition flows to an error-like exit",
        )

    return ConditionInfo(
        cond,
        "unknown_error_like",
        _first_identifier(cond),
        "low",
        "condition does not match a known error-path pattern",
    )


def classify_direct_return(expr: str) -> ConditionInfo:
    expr = compact_ws(expr)
    expr_type = return_expr_type(expr)
    if expr_type in {"negative_errno_return", "err_ptr_return", "ptr_err_propagation"}:
        return ConditionInfo(
            "",
            expr_type,
            "unknown",
            "high",
            f"direct {expr_type}",
        )
    if expr_type == "pointer_null_return":
        return ConditionInfo(
            "",
            "pointer_null_return",
            "unknown",
            "medium",
            "direct NULL return may represent a pointer error path",
        )
    return ConditionInfo(
        "",
        "direct_return",
        "unknown",
        "low",
        "direct return is not obviously an error",
    )
