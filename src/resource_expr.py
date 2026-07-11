"""Helpers for comparing resource expressions conservatively."""

from __future__ import annotations

import re


def norm_resource_expr(value: object) -> str:
    expr = re.sub(r"\s+", "", str(value or ""))
    expr = _strip_balanced_outer_parens(expr)
    expr = _strip_casts(expr)
    expr = _strip_balanced_outer_parens(expr)
    if expr.startswith("&"):
        expr = "&" + _strip_balanced_outer_parens(expr[1:])
    return expr


def same_resource_expr(left: object, right: object) -> bool:
    left_norm = norm_resource_expr(left)
    right_norm = norm_resource_expr(right)
    if left_norm == right_norm:
        return True
    if not left_norm or not right_norm:
        return False

    left_no_index = _strip_trailing_indices(left_norm)
    right_no_index = _strip_trailing_indices(right_norm)
    if left_no_index == right_no_index:
        return True

    left_tail = _tail_name(left_no_index)
    right_tail = _tail_name(right_no_index)
    if (
        left_tail
        and left_tail == right_no_index
        and _has_field_access(left_no_index)
        and not _has_index_access(left_no_index)
    ):
        return True
    if (
        right_tail
        and right_tail == left_no_index
        and _has_field_access(right_no_index)
        and not _has_index_access(right_no_index)
    ):
        return True
    return False


def _strip_balanced_outer_parens(expr: str) -> str:
    changed = True
    while changed and expr.startswith("(") and expr.endswith(")"):
        changed = False
        depth = 0
        balanced = True
        for index, ch in enumerate(expr):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and index != len(expr) - 1:
                    balanced = False
                    break
        if balanced and depth == 0:
            expr = expr[1:-1]
            changed = True
    return expr


def _strip_casts(expr: str) -> str:
    while True:
        match = re.match(r"^\([^()]*\*[^()]*\)(.+)$", expr)
        if not match:
            return expr
        expr = match.group(1)


def _strip_trailing_indices(expr: str) -> str:
    while re.search(r"\[[^\[\]]+\]$", expr):
        expr = re.sub(r"\[[^\[\]]+\]$", "", expr)
    return expr


def _tail_name(expr: str) -> str:
    expr = _strip_trailing_indices(expr)
    if "->" in expr:
        return expr.rsplit("->", 1)[1].split(".", 1)[-1]
    if "." in expr:
        return expr.rsplit(".", 1)[1]
    return expr


def _has_field_access(expr: str) -> bool:
    return "->" in expr or "." in expr


def _has_index_access(expr: str) -> bool:
    return "[" in expr and "]" in expr
