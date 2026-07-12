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
    cycles: bool = False
    cycle_condition: str = ""


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
    backedge_condition = ""
    pending_condition = ""
    pending_loop_entry_decrements: set[str] = set()

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
                goto_condition = _goto_condition(stmt.text[:goto_idx])
                if goto_condition == "always" and pending_condition:
                    goto_condition = pending_condition
                next_label = goto_match.group(1)
                if next_label in labels and labels[next_label] <= labels[current_label]:
                    backedge_condition = goto_condition
                    current_label = next_label
                    jumped = False
                    break
                current_label = next_label
                jumped = True
                break
            loop_entry_decrements = _loop_entry_decrements(stmt.text)
            calls = extract_call_expressions(stmt.text)
            if pending_loop_entry_decrements and calls:
                calls = [
                    _mark_loop_entry_decrements(call, pending_loop_entry_decrements)
                    for call in calls
                ]
                pending_loop_entry_decrements.clear()
            cleanup_calls.extend(calls)
            if loop_entry_decrements:
                pending_loop_entry_decrements = loop_entry_decrements
            pending_condition = _standalone_if_condition(stmt.text)

        if final_return_expr != "unknown" or not jumped or backedge_condition:
            break

    cycles = bool(backedge_condition)
    reason = "resolved label cleanup until return"
    if cycles:
        reason = "label chain forms a control-flow cycle"
    elif final_return_expr == "unknown":
        reason = "label found but no return reached"
    return LabelResolution(
        label,
        cleanup_calls,
        final_return_expr,
        reason,
        cycles,
        backedge_condition,
    )


def _goto_condition(prefix: str) -> str:
    match = re.search(r"\bif\s*\((.*)\)\s*\{?\s*$", prefix.strip())
    return match.group(1).strip() if match else "always"


def _standalone_if_condition(text: str) -> str:
    match = re.fullmatch(r"\s*if\s*\((.*)\)\s*\{?\s*", text)
    return match.group(1).strip() if match else ""


def _loop_entry_decrements(text: str) -> set[str]:
    match = re.match(r"\s*for\s*\(\s*([^;]+);", text)
    if not match:
        return set()
    return set(re.findall(r"\b([A-Za-z_]\w*)\s*--", match.group(1)))


def _mark_loop_entry_decrements(call: str, variables: set[str]) -> str:
    for variable in variables:
        call = re.sub(
            rf"\[\s*{re.escape(variable)}\s*\]",
            f"[{variable}--]",
            call,
        )
    return call
