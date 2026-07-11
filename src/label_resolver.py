"""Function-local statement and label helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .function_extractor import Function
from .parser import compact_ws, extract_call_expressions, extract_return_expr


@dataclass
class Statement:
    text: str
    line: int
    kind: str = "stmt"
    label: str | None = None


@dataclass
class LabelResolution:
    label: str
    cleanup_calls: list[str]
    final_return_expr: str
    reason: str


LABEL_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*:\s*(.*)$")


def parse_statements(function: Function) -> tuple[list[Statement], dict[str, int]]:
    statements: list[Statement] = []
    labels: dict[str, int] = {}

    for offset, raw_line in enumerate(function.body.splitlines()):
        line_no = function.body_start_line + offset
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        while True:
            match = LABEL_RE.match(line)
            if not match or match.group(1) in {"case", "default"}:
                break
            label = match.group(1)
            labels[label] = len(statements)
            statements.append(Statement(f"{label}:", line_no, "label", label))
            line = match.group(2).strip()
            if not line:
                break
        if not line:
            continue

        statements.append(Statement(compact_ws(line), line_no))

    return statements, labels


def resolve_label(
    statements: list[Statement], labels: dict[str, int], label: str
) -> LabelResolution:
    if label not in labels:
        return LabelResolution(label, [], "unknown", "target label not found")

    cleanup_calls: list[str] = []
    final_return_expr = "unknown"
    current_label = label
    visited: set[str] = set()

    while current_label in labels and current_label not in visited:
        visited.add(current_label)
        start_idx = labels[current_label] + 1
        jumped = False

        for stmt in statements[start_idx:]:
            if stmt.kind == "label":
                continue
            return_expr = extract_return_expr(stmt.text)
            if return_expr is not None:
                return_idx = stmt.text.find("return")
                if return_idx > 0:
                    cleanup_calls.extend(extract_call_expressions(stmt.text[:return_idx]))
                final_return_expr = return_expr
                jumped = False
                break
            goto_match = re.search(r"\bgoto\s+([A-Za-z_]\w*)\s*;", stmt.text)
            if goto_match:
                goto_idx = stmt.text.find("goto")
                if goto_idx > 0:
                    cleanup_calls.extend(extract_call_expressions(stmt.text[:goto_idx]))
                current_label = goto_match.group(1)
                jumped = True
                break
            cleanup_calls.extend(extract_call_expressions(stmt.text))

        if final_return_expr != "unknown" or not jumped:
            break

    reason = "resolved label cleanup until return"
    if final_return_expr == "unknown":
        reason = "label found but no return reached"
    return LabelResolution(label, cleanup_calls, final_return_expr, reason)
