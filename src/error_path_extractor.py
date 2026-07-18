"""Extract function-local error paths."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .backward_slicer import find_error_source
from .error_condition import (
    ConditionInfo,
    classify_condition,
    classify_direct_return,
    is_error_return_expr,
    return_expr_type,
    strip_outer_parens,
)
from .function_extractor import Function
from .label_resolver import Statement, parse_statements, resolve_label
from .parser import (
    compact_ws,
    extract_call_expressions,
    extract_return_expr,
    find_matching_paren,
    mask_comments_and_strings,
)
from .resource_release import cleanup_call_releases_resource
from .resource_tracker import HeldResource, ResourceTracker


@dataclass
class ErrorPath:
    file: str
    function: str
    function_start_line: int
    function_end_line: int
    path_id: str
    error_line: int
    condition: str
    condition_type: str
    branch_taken: str
    condition_start_byte: int
    condition_end_byte: int
    cfg_edge_id: str
    cfg_source_block: int | str
    cfg_target_block: int | str
    cfg_edge_kind: str
    cfg_witness: dict[str, Any]
    error_var: str
    error_source_expr: str
    exit_type: str
    target_label: str
    cleanup_calls: list[str]
    final_return_expr: str
    held_resources: list[dict]
    missing_cleanup_candidates: list[str]
    released_cleanup_candidates: list[str]
    partial_cleanup: bool
    resource_analysis: str
    confidence: str
    reason: str
    linux_git_commit: str = ""
    linux_git_tag: str = ""


@dataclass
class BranchExit:
    exit_type: str
    target_label: str = ""
    return_expr: str = "unknown"
    cleanup_calls: list[str] = field(default_factory=list)
    end_index: int = -1
    exit_node: Any | None = None
    exit_line: int = 0


def _parse_if(text: str) -> tuple[str, str] | None:
    match = re.search(r"\bif\s*\(", text)
    if not match:
        return None
    open_idx = text.find("(", match.start())
    close_idx = find_matching_paren(text, open_idx)
    if close_idx == -1:
        return None
    condition = text[open_idx + 1 : close_idx]
    action = text[close_idx + 1 :].strip()
    return compact_ws(condition), action


def _goto_label(text: str) -> str:
    match = re.search(r"\bgoto\s+([A-Za-z_]\w*)\s*;", text)
    return match.group(1) if match else ""


def _branch_exit_from_text(text: str, stmt_index: int = -1) -> BranchExit | None:
    cleanup_calls: list[str] = []
    goto_label = _goto_label(text)
    return_expr = extract_return_expr(text)

    if return_expr is not None:
        before_return = text[: text.find("return")]
        cleanup_calls.extend(extract_call_expressions(before_return))
        return BranchExit(
            "return",
            return_expr=return_expr,
            cleanup_calls=cleanup_calls,
            end_index=stmt_index,
        )

    if goto_label:
        before_goto = text[: text.find("goto")]
        cleanup_calls.extend(extract_call_expressions(before_goto))
        return BranchExit(
            "goto",
            target_label=goto_label,
            cleanup_calls=cleanup_calls,
            end_index=stmt_index,
        )

    return None


def _collect_branch_exit(statements: list[Statement], idx: int, action: str) -> BranchExit | None:
    direct = _branch_exit_from_text(action, idx)
    if direct:
        return direct

    if action and "{" not in action and action != "{":
        return None

    cleanup_calls: list[str] = []
    max_scan = min(len(statements), idx + 8)
    for next_idx in range(idx + 1, max_scan):
        stmt = statements[next_idx]
        if stmt.kind == "label":
            break
        text = stmt.text
        direct = _branch_exit_from_text(text, next_idx)
        if direct:
            direct.cleanup_calls = cleanup_calls + direct.cleanup_calls
            return direct
        cleanup_calls.extend(extract_call_expressions(text))
        if "}" in text and "{" not in text:
            break
    return None


def _merge_confidence(base: str, final_return_expr: str, condition: ConditionInfo) -> str:
    if base == "high" and final_return_expr not in {"unknown", ""}:
        if is_error_return_expr(final_return_expr, condition.error_var):
            return "high"
        if condition.condition_type in {
            "is_err",
            "is_err_or_null",
            "null_pointer",
            "err_ptr_check",
            "null_check",
        }:
            return "high"
        return "medium"
    return base


def _lower_confidence(confidence: str) -> str:
    return {
        "high": "medium",
        "medium": "low",
        "low": "low",
        "uncertain": "uncertain",
    }.get(confidence, confidence)


def _condition_implies_cycle(condition: str, cycle_condition: str) -> bool:
    cycle = compact_ws(strip_outer_parens(cycle_condition))
    original = compact_ws(strip_outer_parens(condition))
    if cycle == "always" or original == cycle:
        return True

    conjunction = _split_top_level(cycle, "&&")
    if len(conjunction) > 1:
        return all(_condition_implies_cycle(original, term) for term in conjunction)
    disjunction = _split_top_level(cycle, "||")
    if len(disjunction) > 1:
        return any(_condition_implies_cycle(original, term) for term in disjunction)

    match = re.fullmatch(r"([A-Za-z_]\w*)\s*(?:!=\s*0)?", original)
    if not match:
        return False
    variable = match.group(1)
    return bool(
        re.fullmatch(rf"{re.escape(variable)}\s*(?:!=\s*0)?", cycle)
    )


def _goto_targets_prior_label(
    statements: list[Statement], labels: dict[str, int], branch_exit: BranchExit
) -> bool:
    if branch_exit.exit_type != "goto" or not branch_exit.exit_line:
        return False
    label_index = labels.get(branch_exit.target_label)
    if label_index is None:
        return False
    return statements[label_index].line <= branch_exit.exit_line


def _split_top_level(expression: str, operator: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    index = 0
    while index < len(expression):
        char = expression[index]
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        elif depth == 0 and expression.startswith(operator, index):
            parts.append(expression[start:index].strip())
            start = index + len(operator)
            index += len(operator) - 1
        index += 1
    parts.append(expression[start:].strip())
    return parts


def _node_text(function: Function, node: Any) -> str:
    return function.file_bytes[node.start_byte : node.end_byte].decode(
        "utf-8", errors="replace"
    )


def _condition_text(function: Function, condition_node: Any) -> str:
    return strip_outer_parens(_node_text(function, condition_node))


def _goto_label_from_node(function: Function, node: Any) -> str:
    for child in node.children:
        if child.type == "statement_identifier":
            return _node_text(function, child).strip()
    return _goto_label(_node_text(function, node))


def _return_expr_from_node(function: Function, node: Any) -> str:
    return extract_return_expr(_node_text(function, node)) or "unknown"


def _cleanup_before_exit(function: Function, branch_node: Any, exit_node: Any) -> list[str]:
    if branch_node.start_byte >= exit_node.start_byte:
        return []
    before = function.file_bytes[branch_node.start_byte : exit_node.start_byte].decode(
        "utf-8", errors="replace"
    )
    return extract_call_expressions(before)


def _collect_branch_exits(function: Function, branch_node: Any | None) -> list[BranchExit]:
    if branch_node is None:
        return []

    exits: list[BranchExit] = []

    def visit(node: Any) -> None:
        if node.type == "return_statement":
            exits.append(
                BranchExit(
                    "return",
                    return_expr=_return_expr_from_node(function, node),
                    cleanup_calls=_cleanup_before_exit(function, branch_node, node),
                    exit_node=node,
                    exit_line=node.start_point.row + 1,
                )
            )
            return
        if node.type == "goto_statement":
            exits.append(
                BranchExit(
                    "goto",
                    target_label=_goto_label_from_node(function, node),
                    cleanup_calls=_cleanup_before_exit(function, branch_node, node),
                    exit_node=node,
                    exit_line=node.start_point.row + 1,
                )
            )
            return
        if node is not branch_node and node.type == "if_statement":
            return
        for child in node.children:
            visit(child)

    visit(branch_node)
    return exits


def _return_phrase(expr: str) -> str:
    kind = return_expr_type(expr)
    if kind == "pointer_null_return":
        return "return NULL"
    if kind == "err_ptr_return":
        return "ERR_PTR return"
    if kind == "ptr_err_propagation":
        return "PTR_ERR propagation"
    if kind == "negative_errno_return":
        return "negative errno return"
    return f"return {expr}"


def _path_reason(
    condition: ConditionInfo,
    exit_type: str,
    target_label: str,
    final_return_expr: str,
    label_reason: str = "",
) -> str:
    if exit_type == "goto":
        reason = (
            f"goto {target_label} under {condition.condition_type} condition, "
            f"final return {final_return_expr}"
        )
    else:
        reason = f"{_return_phrase(final_return_expr)} under {condition.condition_type} condition"
    if label_reason:
        reason = f"{reason}; {label_reason}"
    return reason


def _is_ident_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _is_word_at(text: str, pos: int, word: str) -> bool:
    if not text.startswith(word, pos):
        return False
    before = text[pos - 1] if pos > 0 else ""
    after_idx = pos + len(word)
    after = text[after_idx] if after_idx < len(text) else ""
    return not _is_ident_char(before) and not _is_ident_char(after)


def _skip_ws(text: str, pos: int, end: int | None = None) -> int:
    end = len(text) if end is None else end
    while pos < end and text[pos].isspace():
        pos += 1
    return pos


def _find_matching_delim(text: str, open_idx: int, open_ch: str, close_ch: str) -> int:
    depth = 0
    for idx in range(open_idx, len(text)):
        if text[idx] == open_ch:
            depth += 1
        elif text[idx] == close_ch:
            depth -= 1
            if depth == 0:
                return idx
    return -1


def _find_statement_end(masked: str, start: int, limit: int) -> int:
    depth_paren = 0
    depth_bracket = 0
    for idx in range(start, limit):
        ch = masked[idx]
        if ch == "(":
            depth_paren += 1
        elif ch == ")" and depth_paren > 0:
            depth_paren -= 1
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]" and depth_bracket > 0:
            depth_bracket -= 1
        elif ch == ";" and depth_paren == 0 and depth_bracket == 0:
            return idx + 1
    return limit


def _parse_statement_range(masked: str, start: int, limit: int) -> tuple[int, int]:
    start = _skip_ws(masked, start, limit)
    if start >= limit:
        return start, start
    if masked[start] == "{":
        close = _find_matching_delim(masked, start, "{", "}")
        return start, (close + 1 if close != -1 else limit)
    if _is_word_at(masked, start, "if"):
        parsed = _parse_if_ranges(masked, start, limit)
        if parsed is not None:
            return start, parsed["end"]
    return start, _find_statement_end(masked, start, limit)


def _parse_if_ranges(masked: str, if_pos: int, limit: int) -> dict[str, Any] | None:
    pos = _skip_ws(masked, if_pos + 2, limit)
    if pos >= limit or masked[pos] != "(":
        return None
    cond_close = _find_matching_delim(masked, pos, "(", ")")
    if cond_close == -1 or cond_close >= limit:
        return None
    consequence = _parse_statement_range(masked, cond_close + 1, limit)
    end = consequence[1]
    alternative = None
    else_pos = _skip_ws(masked, end, limit)
    if _is_word_at(masked, else_pos, "else"):
        alternative = _parse_statement_range(masked, else_pos + 4, limit)
        end = alternative[1]
    return {
        "condition": (pos + 1, cond_close),
        "consequence": consequence,
        "alternative": alternative,
        "end": end,
    }


def _line_for_source_pos(function: Function, pos: int) -> int:
    return function.start_line + function.source[:pos].count("\n")


def _collect_text_exits(
    source: str, masked: str, start: int, end: int
) -> list[BranchExit]:
    exits: list[BranchExit] = []
    pos = start
    while pos < end:
        if _is_word_at(masked, pos, "return"):
            stmt_end = _find_statement_end(masked, pos, end)
            return_expr = extract_return_expr(source[pos:stmt_end]) or "unknown"
            exits.append(
                BranchExit(
                    "return",
                    return_expr=return_expr,
                    cleanup_calls=extract_call_expressions(source[start:pos]),
                    end_index=pos,
                )
            )
            pos = stmt_end
            continue
        if _is_word_at(masked, pos, "goto"):
            stmt_end = _find_statement_end(masked, pos, end)
            label = _goto_label(source[pos:stmt_end])
            exits.append(
                BranchExit(
                    "goto",
                    target_label=label,
                    cleanup_calls=extract_call_expressions(source[start:pos]),
                    end_index=pos,
                )
            )
            pos = stmt_end
            continue
        if _is_word_at(masked, pos, "if"):
            nested = _parse_if_ranges(masked, pos, end)
            if nested is not None:
                pos = nested["end"]
                continue
        pos += 1
    return exits


def _iter_structured_if_paths(function: Function) -> list[tuple[int, str, BranchExit]]:
    source = function.source
    masked = mask_comments_and_strings(source)
    body_start = masked.find("{")
    if body_start == -1:
        return []
    body_end = _find_matching_delim(masked, body_start, "{", "}")
    if body_end == -1:
        body_end = len(masked)

    paths: list[tuple[int, str, BranchExit]] = []
    pos = body_start + 1
    while pos < body_end:
        if not _is_word_at(masked, pos, "if"):
            pos += 1
            continue
        parsed = _parse_if_ranges(masked, pos, body_end)
        if parsed is None:
            pos += 1
            continue
        cond_start, cond_end = parsed["condition"]
        condition = compact_ws(source[cond_start:cond_end])
        for branch_range in [parsed["consequence"], parsed["alternative"]]:
            if branch_range is None:
                continue
            branch_start, branch_end = branch_range
            for branch_exit in _collect_text_exits(
                source, masked, branch_start, branch_end
            ):
                branch_exit.exit_line = _line_for_source_pos(function, branch_exit.end_index)
                paths.append((_line_for_source_pos(function, pos), condition, branch_exit))
        pos += 1
    return paths


class ErrorPathExtractor:
    def __init__(self, resource_tracker: ResourceTracker):
        self.resource_tracker = resource_tracker

    def extract(self, function: Function) -> list[ErrorPath]:
        statements, labels = parse_statements(function)
        if function.body_node is not None:
            paths = self._extract_from_ast(function, statements, labels)
            for num, path in enumerate(paths, 1):
                path.path_id = f"{function.name}#{num:03d}"
            return paths

        paths = self._extract_from_text(function, statements, labels)
        for num, path in enumerate(paths, 1):
            path.path_id = f"{function.name}#{num:03d}"
        return paths

    def _extract_from_text(
        self, function: Function, statements: list[Statement], labels: dict[str, int]
    ) -> list[ErrorPath]:
        paths: list[ErrorPath] = []
        seen: set[tuple[int, str, str, str, str]] = set()
        consumed_return_lines: set[int] = set()

        for error_line, condition_text, branch_exit in _iter_structured_if_paths(function):
            label_cleanup: list[str] = []
            final_return_expr = branch_exit.return_expr
            label_reason = ""
            if branch_exit.exit_type == "goto":
                if _goto_targets_prior_label(statements, labels, branch_exit):
                    continue
                resolution = resolve_label(statements, labels, branch_exit.target_label)
                if resolution.cycles and _condition_implies_cycle(
                    condition_text, resolution.cycle_condition
                ):
                    continue
                label_cleanup = resolution.cleanup_calls
                final_return_expr = resolution.final_return_expr
                label_reason = resolution.reason

            condition = classify_condition(
                condition_text, final_return_expr, branch_exit.target_label
            )
            confidence = _merge_confidence(condition.confidence, final_return_expr, condition)
            cleanup_calls = branch_exit.cleanup_calls + label_cleanup
            key = (
                error_line,
                condition.condition,
                branch_exit.exit_type,
                branch_exit.target_label,
                final_return_expr,
            )
            if key in seen:
                continue
            seen.add(key)
            if branch_exit.exit_line:
                consumed_return_lines.add(branch_exit.exit_line)
            paths.append(
                self._build_path(
                    function,
                    statements,
                    error_line,
                    condition,
                    branch_exit.exit_type,
                    branch_exit.target_label,
                    cleanup_calls,
                    final_return_expr,
                    confidence,
                    _path_reason(
                        condition,
                        branch_exit.exit_type,
                        branch_exit.target_label,
                        final_return_expr,
                        label_reason,
                    ),
                )
            )

        for stmt in statements:
            if stmt.kind == "label" or stmt.line in consumed_return_lines:
                continue
            if any(label_stmt.kind == "label" and label_stmt.line <= stmt.line for label_stmt in statements):
                continue
            return_expr = extract_return_expr(stmt.text)
            if return_expr is None:
                continue
            condition = classify_direct_return(return_expr)
            if condition.confidence == "low":
                continue
            key = (stmt.line, "", "return", "", return_expr)
            if key in seen:
                continue
            seen.add(key)
            paths.append(
                self._build_path(
                    function,
                    statements,
                    stmt.line,
                    condition,
                    "return",
                    "",
                    extract_call_expressions(stmt.text[: stmt.text.find("return")]),
                    return_expr,
                    condition.confidence,
                    condition.reason,
                )
            )

        return paths

    def _extract_from_ast(
        self, function: Function, statements: list[Statement], labels: dict[str, int]
    ) -> list[ErrorPath]:
        paths: list[ErrorPath] = []
        seen: set[tuple[int, str, str, str, str]] = set()

        def handle_if(node: Any) -> None:
            condition_node = node.child_by_field_name("condition")
            if condition_node is None:
                return
            condition_text = _condition_text(function, condition_node)
            branches = [
                (node.child_by_field_name("consequence"), True),
                (node.child_by_field_name("alternative"), False),
            ]
            for branch, branch_truth in branches:
                for branch_exit in _collect_branch_exits(function, branch):
                    label_cleanup: list[str] = []
                    final_return_expr = branch_exit.return_expr
                    label_reason = ""
                    if branch_exit.exit_type == "goto":
                        if _goto_targets_prior_label(statements, labels, branch_exit):
                            continue
                        resolution = resolve_label(
                            statements, labels, branch_exit.target_label
                        )
                        if resolution.cycles and _condition_implies_cycle(
                            condition_text, resolution.cycle_condition
                        ):
                            continue
                        label_cleanup = resolution.cleanup_calls
                        final_return_expr = resolution.final_return_expr
                        label_reason = resolution.reason

                    branch_condition = (
                        condition_text
                        if branch_truth
                        else f"!({condition_text})"
                    )
                    condition = classify_condition(
                        branch_condition,
                        final_return_expr,
                        branch_exit.target_label,
                    )
                    confidence = _merge_confidence(
                        condition.confidence, final_return_expr, condition
                    )
                    cleanup_calls = branch_exit.cleanup_calls + label_cleanup
                    key = (
                        node.start_point.row + 1,
                        condition.condition,
                        branch_exit.exit_type,
                        branch_exit.target_label,
                        final_return_expr,
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    paths.append(
                        self._build_path(
                            function,
                            statements,
                            node.start_point.row + 1,
                            condition,
                            branch_exit.exit_type,
                            branch_exit.target_label,
                            cleanup_calls,
                            final_return_expr,
                            confidence,
                            _path_reason(
                                condition,
                                branch_exit.exit_type,
                                branch_exit.target_label,
                                final_return_expr,
                                label_reason,
                            ),
                            "true" if branch_truth else "false",
                            condition_node.start_byte,
                            condition_node.end_byte,
                        )
                    )

        def handle_direct_return(node: Any) -> None:
            return_expr = _return_expr_from_node(function, node)
            condition = classify_direct_return(return_expr)
            if condition.confidence == "low":
                return
            if any(stmt.kind == "label" and stmt.line <= node.start_point.row + 1 for stmt in statements):
                return
            key = (node.start_point.row + 1, "", "return", "", return_expr)
            if key in seen:
                return
            seen.add(key)
            paths.append(
                self._build_path(
                    function,
                    statements,
                    node.start_point.row + 1,
                    condition,
                    "return",
                    "",
                    [],
                    return_expr,
                    condition.confidence,
                    condition.reason,
                )
            )

        def visit(node: Any, in_if: bool = False) -> None:
            if node.type == "if_statement":
                handle_if(node)
                for child in node.children:
                    visit(child, True)
                return
            if node.type == "return_statement" and not in_if:
                handle_direct_return(node)
                return
            for child in node.children:
                visit(child, in_if)

        visit(function.body_node)
        return paths

    def _build_path(
        self,
        function: Function,
        statements: list[Statement],
        error_line: int,
        condition: ConditionInfo,
        exit_type: str,
        target_label: str,
        cleanup_calls: list[str],
        final_return_expr: str,
        confidence: str,
        reason: str,
        branch_taken: str = "direct",
        condition_start_byte: int = 0,
        condition_end_byte: int = 0,
    ) -> ErrorPath:
        error_source = find_error_source(
            statements, condition.error_var, error_line, function.parameters
        )
        held = self.resource_tracker.held_before_cfg(
            function, error_line, condition, error_source
        )
        resource_analysis = "cfg"
        if held is None:
            resource_analysis = "linear-degraded"
            held = self.resource_tracker.held_before(
                statements, error_line, condition, error_source, function.name
            )
        outcome = self.resource_tracker.cleanup_outcome_cfg(
            function, error_line, condition, target_label, held
        )
        if outcome is None:
            if resource_analysis == "cfg":
                resource_analysis = "linear-fallback"
                confidence = "low"
            missing = self.resource_tracker.missing_cleanup_candidates(
                held, cleanup_calls
            )
            released_cleanup_candidates: list[str] = []
            partial_cleanup = False
        else:
            missing = outcome.missing
            released_cleanup_candidates = outcome.released
            partial_cleanup = outcome.partial
        uncertain_ownership = any(
            resource.ownership_state == "MAY_ACQUIRED" for resource in held
        )
        if function.analysis_quality != "tree-sitter":
            confidence = "low"
            reason = (
                f"{reason}; degraded analysis quality: "
                f"{function.analysis_quality}"
            )
        if missing:
            reason = f"{reason}; suspicious missing cleanup candidates"
            if uncertain_ownership:
                confidence = _lower_confidence(confidence)
                reason = f"{reason}; ownership may still be held"
        release_reasons = self._release_reasons(
            held, cleanup_calls, target_label, set(missing)
        )
        if release_reasons:
            reason = f"{reason}; {'; '.join(release_reasons)}"

        cfg_witness = self.resource_tracker.cfg_edge_witness(
            function,
            error_line,
            branch_taken,
            condition_start_byte,
            condition_end_byte,
        )
        if (
            missing
            and resource_analysis == "cfg"
            and cfg_witness
            and cfg_witness.get("cfg_slice_complete") is False
        ):
            confidence = "low"
            unsupported = cfg_witness.get("unsupported_nodes_on_reachable_slice", [])
            reason = (
                f"{reason}; incomplete CFG on candidate slice"
                + (f": {unsupported}" if unsupported else "")
            )

        return ErrorPath(
            file=str(function.file),
            function=function.name,
            function_start_line=function.start_line,
            function_end_line=function.end_line,
            path_id="",
            error_line=error_line,
            condition=condition.condition,
            condition_type=condition.condition_type,
            branch_taken=branch_taken,
            condition_start_byte=condition_start_byte,
            condition_end_byte=condition_end_byte,
            cfg_edge_id=str(cfg_witness.get("edge_id", "")),
            cfg_source_block=cfg_witness.get("source_block", ""),
            cfg_target_block=cfg_witness.get("target_block", ""),
            cfg_edge_kind=str(cfg_witness.get("edge_kind", "")),
            cfg_witness=cfg_witness,
            error_var=condition.error_var,
            error_source_expr=error_source,
            exit_type=exit_type,
            target_label=target_label,
            cleanup_calls=cleanup_calls,
            final_return_expr=final_return_expr or "unknown",
            held_resources=[res.to_csv_dict() for res in held],
            missing_cleanup_candidates=missing,
            released_cleanup_candidates=released_cleanup_candidates,
            partial_cleanup=partial_cleanup,
            resource_analysis=resource_analysis,
            confidence=confidence,
            reason=reason,
        )

    def _release_reasons(
        self,
        held: list[HeldResource],
        cleanup_calls: list[str],
        target_label: str,
        missing: set[str],
    ) -> list[str]:
        reasons: list[str] = []
        for res in held:
            if res.release_suggestion in missing:
                continue
            for call in cleanup_calls:
                if not cleanup_call_releases_resource(call, res):
                    continue
                location = f" in {target_label} label" if target_label else ""
                reasons.append(
                    f"resource {res.var} acquired by {res.acquire_func} before path, "
                    f"released by {call}{location}"
                )
                break
        return reasons
