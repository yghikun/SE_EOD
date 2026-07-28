"""Indirect call target-set discovery for function summaries."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Iterable

from ..frontend.model import FrontendNode, FunctionIR
from ..metadata_residual import IndirectTargetSet, SourceSite
from ..parser import call_name_and_args, compact_ws
from .model import FunctionSummary
from .syntax import (
    declarator_name as _declarator_name,
    ordered_parameters as _ordered_parameters,
)


def _attach_indirect_target_sets(
    summaries: dict[str, FunctionSummary],
    functions: Iterable[FunctionIR],
    *,
    max_targets: int = 4,
) -> dict[str, FunctionSummary]:
    """Serialize exact visible target sets even when their semantics differ."""

    function_map = {function.name: function for function in functions}
    result = dict(summaries)
    for name, summary in summaries.items():
        function = function_map.get(name)
        if function is None or function.body_node is None:
            continue
        sets: list[IndirectTargetSet] = []
        resolved = _local_indirect_call_targets(function, summaries)
        pointer_parameters = _called_function_pointer_parameters(function)
        for node in function.body_node.walk():
            if node.type != "call_expression":
                continue
            call_text = compact_ws(node.text)
            callee, _ = call_name_and_args(call_text)
            targets = resolved.get(call_text, ())
            if not targets and callee in pointer_parameters:
                targets = _visible_callback_targets(
                    function.name,
                    pointer_parameters[callee],
                    tuple(functions),
                    summaries,
                )
            has_indirect_cause = (
                f"indirect_call: {call_text}" in summary.unknown_causes
                or f"function_pointer_parameter_call: {callee}" in summary.unknown_causes
            )
            if not targets and not has_indirect_cause:
                continue
            callee_node = node.child_by_field_name("function")
            expression = compact_ws(callee_node.text) if callee_node is not None else callee
            target_tuple = tuple(sorted(set(targets)))
            site = SourceSite(function.file.as_posix(), node.start_line, call_text)
            sets.append(
                IndirectTargetSet(
                    call_site=site,
                    receiver_type=_receiver_type(function, expression),
                    ops_table=expression,
                    possible_targets=target_tuple,
                    complete=(
                        bool(target_tuple)
                        and len(target_tuple) <= max_targets
                        and all(target in summaries for target in target_tuple)
                    ),
                    source_evidence=(site,),
                )
            )
        if sets:
            result[name] = replace(
                summary,
                indirect_target_sets=tuple(dict.fromkeys(sets)),
            )
    return result


def _receiver_type(function: FunctionIR, expression: str) -> str:
    match = re.match(r"[&*()\s]*([A-Za-z_]\w*)", expression)
    if not match:
        return ""
    root = match.group(1)
    symbol = next((item for item in function.symbols if item.name == root), None)
    return compact_ws(symbol.type_spelling) if symbol is not None else ""


def _called_function_pointer_parameters(function: FunctionIR) -> dict[str, int]:
    if function.body_node is None:
        return {}
    parameters = _ordered_parameters(function)
    parameter_index = {parameter: index for index, parameter in enumerate(parameters)}
    result: dict[str, int] = {}
    for node in function.body_node.walk():
        if node.type != "call_expression":
            continue
        name, _ = call_name_and_args(compact_ws(node.text))
        if name in parameter_index:
            result[name] = parameter_index[name]
    return result


def _visible_callback_targets(
    callee_name: str,
    parameter_index: int,
    functions: tuple[FunctionIR, ...],
    summaries: dict[str, FunctionSummary],
) -> tuple[str, ...]:
    targets: set[str] = set()
    saw_call = False
    for function in functions:
        if function.body_node is None:
            continue
        for node in function.body_node.walk():
            if node.type != "call_expression":
                continue
            name, args = call_name_and_args(compact_ws(node.text))
            if name != callee_name:
                continue
            saw_call = True
            if parameter_index >= len(args):
                return ()
            target = compact_ws(args[parameter_index]).strip("&()")
            if not re.fullmatch(r"[A-Za-z_]\w*", target):
                return ()
            if target not in summaries:
                return ()
            targets.add(target)
    return tuple(sorted(targets)) if saw_call else ()


def _local_indirect_call_targets(
    function: FunctionIR,
    summaries: dict[str, FunctionSummary],
) -> dict[str, tuple[str, ...]]:
    if function.body_node is None:
        return {}
    assignments = _local_function_pointer_assignments(function, summaries)
    result: dict[str, tuple[str, ...]] = {}
    for node in function.body_node.walk():
        if node.type != "call_expression":
            continue
        callee = node.child_by_field_name("function")
        if callee is None:
            continue
        expression = compact_ws(callee.text)
        targets = assignments.get(expression, ())
        if targets:
            result[compact_ws(node.text)] = targets
            continue
        targets = _ops_initializer_targets(function, expression, summaries)
        if targets:
            result[compact_ws(node.text)] = targets
    return result


def _local_function_pointer_assignments(
    function: FunctionIR,
    summaries: dict[str, FunctionSummary],
) -> dict[str, tuple[str, ...]]:
    if function.body_node is None:
        return {}
    direct: dict[str, set[str]] = {}
    aliases: list[tuple[str, str]] = []
    unresolved: set[str] = set()
    for node in function.body_node.walk():
        if node.type == "init_declarator":
            declarator = node.child_by_field_name("declarator")
            value = node.child_by_field_name("value")
            name = _declarator_name(declarator) if declarator is not None else None
            if name and value is not None:
                _record_function_pointer_binding(
                    name,
                    value,
                    summaries,
                    direct,
                    aliases,
                    unresolved,
                )
        elif node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is None or right is None:
                continue
            _record_function_pointer_binding(
                compact_ws(left.text),
                right,
                summaries,
                direct,
                aliases,
                unresolved,
            )
    changed = True
    while changed:
        changed = False
        for left, right in aliases:
            targets = direct.get(right, set())
            if targets - direct.setdefault(left, set()):
                direct[left].update(targets)
                changed = True
    unresolved.update(
        left for left, right in aliases if not direct.get(right)
    )
    return {
        expression: tuple(sorted(targets))
        for expression, targets in direct.items()
        if targets and expression not in unresolved
    }


def _record_function_pointer_binding(
    left: str,
    right: FrontendNode,
    summaries: dict[str, FunctionSummary],
    direct: dict[str, set[str]],
    aliases: list[tuple[str, str]],
    unresolved: set[str],
) -> None:
    text = compact_ws(right.text).strip("&() ")
    if text in summaries:
        direct.setdefault(left, set()).add(text)
        return
    if right.type == "conditional_expression":
        targets = {
            compact_ws(node.text)
            for node in right.walk()
            if node.type == "identifier" and compact_ws(node.text) in summaries
        }
        if targets:
            direct.setdefault(left, set()).update(targets)
            return
    if re.fullmatch(r"[A-Za-z_]\w*(?:(?:->|\.)[A-Za-z_]\w*)*", text):
        aliases.append((left, text))
        return
    if any(node.type == "call_expression" for node in right.walk()):
        unresolved.add(left)


def _ops_initializer_targets(
    function: FunctionIR,
    expression: str,
    summaries: dict[str, FunctionSummary],
) -> tuple[str, ...]:
    match = re.search(r"(?:->|\.)\s*([A-Za-z_]\w*)$", compact_ws(expression))
    if not match:
        return ()
    field = match.group(1)
    try:
        text = function.file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ()
    tables = _bound_ops_tables(function, expression)
    matches: list[str] = []
    if tables:
        for table in tables:
            initializer = re.search(
                rf"\b{re.escape(table)}\b\s*=\s*\{{(?P<body>.*?)\}}\s*;",
                text,
                re.DOTALL,
            )
            if initializer is None:
                return ()
            matches.extend(
                re.findall(
                    rf"\.\s*{re.escape(field)}\s*=\s*&?\s*([A-Za-z_]\w*)",
                    initializer.group("body"),
                )
            )
    else:
        matches.extend(
            re.findall(
                rf"\.\s*{re.escape(field)}\s*=\s*&?\s*([A-Za-z_]\w*)",
                text,
            )
        )
    if not matches or any(item not in summaries for item in matches):
        return ()
    return tuple(sorted(set(matches)))


def _bound_ops_tables(
    function: FunctionIR,
    expression: str,
) -> tuple[str, ...]:
    receiver = re.sub(
        r"(?:->|\.)\s*[A-Za-z_]\w*$",
        "",
        compact_ws(expression),
    )
    if not receiver or function.body_node is None:
        return ()
    tables: set[str] = set()
    for node in function.body_node.walk():
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            target = compact_ws(left.text) if left is not None else ""
        elif node.type == "init_declarator":
            declarator = node.child_by_field_name("declarator")
            right = node.child_by_field_name("value")
            target = _declarator_name(declarator) or ""
        else:
            continue
        if target != receiver or right is None:
            continue
        table = compact_ws(right.text).strip("&() ")
        if re.fullmatch(r"[A-Za-z_]\w*", table):
            tables.add(table)
    return tuple(sorted(tables))
