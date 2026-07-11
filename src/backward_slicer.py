"""Small backward slicer for nearest error-variable source."""

from __future__ import annotations

import re

from .label_resolver import Statement
from .parser import compact_ws, extract_call_expressions


def _assignment_parts(text: str) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    idx = 0
    while idx < len(text):
        eq_idx = text.find("=", idx)
        if eq_idx == -1:
            break
        before = text[eq_idx - 1] if eq_idx > 0 else ""
        after = text[eq_idx + 1] if eq_idx + 1 < len(text) else ""
        if before in {"=", "!", "<", ">"} or after == "=":
            idx = eq_idx + 1
            continue

        left = text[:eq_idx].rstrip()
        var = ""
        match = re.search(
            r"([A-Za-z_]\w*(?:(?:->|\.)[A-Za-z_]\w*)*(?:\[[^\]]+\])?)\s*$",
            left,
        )
        if match:
            var = match.group(1)

        rhs = text[eq_idx + 1 :]
        semi = rhs.find(";")
        if semi != -1:
            rhs = rhs[:semi]
        rhs = rhs.strip()
        if var and rhs:
            parts.append((var, rhs))
        idx = eq_idx + 1
    return parts


def find_error_source(
    statements: list[Statement],
    error_var: str,
    before_line: int,
    parameters: set[str] | None = None,
) -> str:
    if not error_var or error_var == "unknown":
        return "unknown"
    parameters = parameters or set()

    for stmt in reversed([s for s in statements if s.line <= before_line]):
        for var, rhs in reversed(_assignment_parts(stmt.text)):
            if var != error_var:
                continue
            calls = extract_call_expressions(rhs)
            if calls:
                return calls[0]
            return compact_ws(rhs)
    if error_var in parameters:
        return "function_parameter"
    return "unknown"
