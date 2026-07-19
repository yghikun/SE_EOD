"""Function extraction for C files."""

from __future__ import annotations

import bisect
import re
from typing import Any

from .frontend.model import AstPoint, FrontendNode, FunctionIR
from .parser import ParsedFile, compact_ws, mask_comments_and_strings, split_args

AstNode = FrontendNode
Function = FunctionIR


CONTROL_KEYWORDS = {"if", "for", "while", "switch", "return", "sizeof"}


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for idx, ch in enumerate(text):
        if ch == "\n":
            starts.append(idx + 1)
    return starts


def _line_for_pos(starts: list[int], pos: int) -> int:
    return bisect.bisect_right(starts, pos)


def _matching_open_paren(header: str, close_idx: int) -> int:
    depth = 0
    for idx in range(close_idx, -1, -1):
        if header[idx] == ")":
            depth += 1
        elif header[idx] == "(":
            depth -= 1
            if depth == 0:
                return idx
    return -1


def _function_name_from_header(header: str) -> str | None:
    header = "\n".join(
        line for line in header.splitlines() if not line.strip().startswith("#")
    ).strip()
    if not header or header.startswith("#"):
        return None
    close_idx = header.rfind(")")
    if close_idx == -1:
        return None
    open_idx = _matching_open_paren(header, close_idx)
    if open_idx == -1:
        return None

    prefix = header[:open_idx].rstrip()
    match = re.search(r"([A-Za-z_]\w*)$", prefix)
    if not match:
        return None
    name = match.group(1)
    if name in CONTROL_KEYWORDS:
        return None
    if re.search(r"\b(?:if|for|while|switch)\s*$", prefix):
        return None
    if "=" in prefix.splitlines()[-1]:
        return None
    return name


def _parameters_from_signature(signature: str) -> set[str]:
    close_idx = signature.rfind(")")
    if close_idx == -1:
        return set()
    open_idx = _matching_open_paren(signature, close_idx)
    if open_idx == -1:
        return set()
    params: set[str] = set()
    for arg in split_args(signature[open_idx + 1 : close_idx]):
        arg = arg.strip()
        if not arg or arg == "void" or arg == "...":
            continue
        match = re.search(r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?$", arg.replace("*", " "))
        if match and match.group(1) != "void":
            params.add(match.group(1))
    return params


def _find_matching_brace(masked: str, open_idx: int) -> int:
    depth = 0
    for idx in range(open_idx, len(masked)):
        if masked[idx] == "{":
            depth += 1
        elif masked[idx] == "}":
            depth -= 1
            if depth == 0:
                return idx
    return -1


def _previous_top_level_delimiter(masked: str, brace_idx: int) -> int:
    semi = masked.rfind(";", 0, brace_idx)
    close = masked.rfind("}", 0, brace_idx)
    return max(semi, close)


def _node_text(source_bytes: bytes, node: Any) -> str:
    return source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _copy_ast_node(source_bytes: bytes, node: Any, source_file: str = "") -> AstNode:
    copied_children = [
        _copy_ast_node(source_bytes, child, source_file) for child in node.children
    ]
    field_map: dict[str, AstNode] = {}
    for idx, child in enumerate(copied_children):
        try:
            field_name = node.field_name_for_child(idx)
        except Exception:
            field_name = None
        if field_name and field_name not in field_map:
            field_map[field_name] = child
    return AstNode(
        type=node.type,
        text=_node_text(source_bytes, node),
        start_byte=node.start_byte,
        end_byte=node.end_byte,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        start_column=node.start_point.column,
        end_column=node.end_point.column,
        children=copied_children,
        field_map=field_map,
        source_file=source_file,
        normalized_text=compact_ws(_node_text(source_bytes, node)),
    )


def _find_child_type(node: Any | None, node_type: str) -> Any | None:
    if node is None:
        return None
    if node.type == node_type:
        return node
    for child in node.children:
        found = _find_child_type(child, node_type)
        if found is not None:
            return found
    return None


def _function_declarator(node: Any) -> Any | None:
    declarator = node.child_by_field_name("declarator")
    return _find_child_type(declarator, "function_declarator")


def _function_name_from_ast(source_bytes: bytes, node: Any) -> str | None:
    function_declarator = _function_declarator(node)
    if function_declarator is None:
        return None
    name_node = function_declarator.child_by_field_name("declarator")
    if name_node is None:
        name_node = _find_child_type(function_declarator, "identifier")
    if name_node is None:
        return None
    return _node_text(source_bytes, name_node).strip()


def _parameter_name(source_bytes: bytes, parameter_node: Any) -> str | None:
    identifiers: list[Any] = []

    def visit(node: Any) -> None:
        if node.type == "identifier":
            identifiers.append(node)
        for child in node.children:
            visit(child)

    visit(parameter_node)
    if not identifiers:
        return None
    return _node_text(source_bytes, identifiers[-1]).strip()


def _function_parameters(source_bytes: bytes, node: Any) -> set[str]:
    function_declarator = _function_declarator(node)
    params = _find_child_type(function_declarator, "parameter_list")
    if params is None:
        return set()

    names: set[str] = set()
    for child in params.children:
        if child.type not in {"parameter_declaration", "optional_parameter_declaration"}:
            continue
        name = _parameter_name(source_bytes, child)
        if name and name != "void":
            names.add(name)
    return names


def _extract_functions_from_ast(parsed: ParsedFile) -> list[Function]:
    if parsed.tree is None:
        return []

    source_bytes = parsed.text.encode("utf-8", errors="replace")
    functions: list[Function] = []

    def visit(node: Any) -> None:
        if node.type == "function_definition":
            name = _function_name_from_ast(source_bytes, node)
            body_node = node.child_by_field_name("body") or _find_child_type(
                node, "compound_statement"
            )
            if name and body_node is not None:
                ast_node = _copy_ast_node(source_bytes, node, parsed.path.as_posix())
                copied_body_node = ast_node.child_by_field_name("body") or _find_child_type(
                    ast_node, "compound_statement"
                )
                source = _node_text(source_bytes, node)
                body = _node_text(source_bytes, body_node)
                if body.startswith("{") and body.endswith("}"):
                    body = body[1:-1]
                signature = source_bytes[node.start_byte : body_node.start_byte].decode(
                    "utf-8", errors="replace"
                )
                functions.append(
                    Function(
                        file=parsed.path,
                        name=name,
                        signature=compact_ws(signature),
                        source=source,
                        body=body,
                        start_line=node.start_point.row + 1,
                        end_line=node.end_point.row + 1,
                        body_start_line=body_node.start_point.row + 1,
                        ast_node=ast_node,
                        body_node=copied_body_node,
                        source_start_byte=node.start_byte,
                        body_start_byte=body_node.start_byte,
                        file_bytes=source_bytes,
                        parameters=_function_parameters(source_bytes, node),
                        analysis_quality=parsed.parser_kind,
                    )
                )
            return

        for child in node.children:
            visit(child)

    visit(parsed.tree.root_node)
    return functions


def extract_functions(parsed: ParsedFile) -> list[Function]:
    ast_functions = _extract_functions_from_ast(parsed)
    if ast_functions:
        return ast_functions

    text = parsed.text
    masked = mask_comments_and_strings(text)
    source_bytes = text.encode("utf-8", errors="replace")
    starts = _line_starts(text)
    functions: list[Function] = []

    idx = 0
    while idx < len(masked):
        brace_idx = masked.find("{", idx)
        if brace_idx == -1:
            break

        delimiter = _previous_top_level_delimiter(masked, brace_idx)
        header_start = delimiter + 1
        header = masked[header_start:brace_idx]
        name = _function_name_from_header(header)
        if not name:
            idx = brace_idx + 1
            continue

        close_idx = _find_matching_brace(masked, brace_idx)
        if close_idx == -1:
            idx = brace_idx + 1
            continue

        real_header = text[header_start:brace_idx]
        non_ws = re.search(r"\S", real_header)
        start_pos = header_start + (non_ws.start() if non_ws else 0)
        signature = compact_ws(real_header)
        source = text[start_pos : close_idx + 1]
        body = text[brace_idx + 1 : close_idx]
        functions.append(
            Function(
                file=parsed.path,
                name=name,
                signature=signature,
                source=source,
                body=body,
                start_line=_line_for_pos(starts, start_pos),
                end_line=_line_for_pos(starts, close_idx),
                body_start_line=_line_for_pos(starts, brace_idx + 1),
                source_start_byte=len(text[:start_pos].encode("utf-8", errors="replace")),
                body_start_byte=len(text[: brace_idx + 1].encode("utf-8", errors="replace")),
                file_bytes=source_bytes,
                parameters=_parameters_from_signature(real_header),
                analysis_quality="degraded-text",
            )
        )
        idx = close_idx + 1

    return functions
