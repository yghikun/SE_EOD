"""tree-sitter adapter for the shared frontend IR."""

from __future__ import annotations

import re
from pathlib import Path

from .base import Frontend
from .model import (
    FRONTEND_IR_SCHEMA_VERSION,
    AccessPathIR,
    CallIR,
    FrontendDiagnostic,
    FrontendNode,
    FunctionIR,
    SourceRange,
    SymbolIR,
    TranslationUnitIR,
    _stable_id,
)
from ..function_extractor import extract_functions
from ..parser import call_name_and_args, compact_ws, parse_c_file


def _nodes(root: FrontendNode | None):
    if root is None:
        return
    yield from root.walk()


def _nodes_with_parent(root: FrontendNode | None):
    if root is None:
        return
    pending: list[tuple[FrontendNode, FrontendNode | None]] = [(root, None)]
    while pending:
        node, parent = pending.pop()
        yield node, parent
        pending.extend((child, node) for child in reversed(node.children))


def _last_identifier(node: FrontendNode) -> FrontendNode | None:
    identifiers = [candidate for candidate in node.walk() if candidate.type == "identifier"]
    return identifiers[-1] if identifiers else None


def _declarator_identifier(node: FrontendNode | None) -> FrontendNode | None:
    current = node
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if current.type in {"identifier", "field_identifier"}:
            return current
        nested = current.child_by_field_name("declarator")
        if nested is not None:
            current = nested
            continue
        direct = [
            child
            for child in current.children
            if child.type in {
                "identifier",
                "pointer_declarator",
                "array_declarator",
                "function_declarator",
                "parenthesized_declarator",
            }
        ]
        current = direct[0] if direct else None
    return None


def _type_without_identifier(node: FrontendNode, identifier: FrontendNode) -> str:
    start = max(0, identifier.start_byte - node.start_byte)
    end = max(start, identifier.end_byte - node.start_byte)
    return compact_ws(node.text[:start] + node.text[end:])


def _set_source_file(node: FrontendNode | None, source_file: str) -> None:
    if node is None:
        return
    for candidate in node.walk():
        candidate.source_file = source_file


def _callee_kind(node: FrontendNode | None) -> str:
    if node is None:
        return "unknown"
    if node.type == "identifier":
        return "direct"
    if node.type == "field_expression":
        return "field"
    if node.type == "subscript_expression":
        return "table"
    return "indirect"


def _function_return_type(function: FunctionIR) -> str:
    if function.ast_node is not None:
        type_node = function.ast_node.child_by_field_name("type")
        if type_node is not None:
            return compact_ws(type_node.text)
    signature = function.signature
    index = signature.find(function.name)
    return compact_ws(signature[:index]) if index > 0 else ""


def _extract_calls(function: FunctionIR) -> list[CallIR]:
    calls: list[CallIR] = []
    value_symbols = {
        symbol.name
        for symbol in function.symbols
        if symbol.kind in {"parameter", "local"}
    }
    for node in _nodes(function.body_node):
        if node.type != "call_expression":
            continue
        callee_node = node.child_by_field_name("function")
        arguments_node = node.child_by_field_name("arguments")
        callee = compact_ws(callee_node.text) if callee_node is not None else ""
        _, fallback_args = call_name_and_args(compact_ws(node.text))
        arguments = tuple(fallback_args)
        if arguments_node is not None:
            named = [
                child.text.strip()
                for child in arguments_node.children
                if child.type not in {"(", ")", ","}
            ]
            if named:
                arguments = tuple(named)
        kind = _callee_kind(callee_node)
        if kind == "direct" and callee in value_symbols:
            kind = "indirect"
        possible_targets = (callee,) if kind == "direct" and callee else ()
        calls.append(
            CallIR(
                call_id=_stable_id(
                    "call", function.function_id, node.start_byte, node.end_byte
                ),
                callee_spelling=callee,
                callee_kind=kind,
                arguments=arguments,
                possible_targets=possible_targets,
                source_range=node.source_range,
            )
        )
    return calls


def _extract_symbols(function: FunctionIR) -> list[SymbolIR]:
    symbols: list[SymbolIR] = []
    parameter_index = 0

    def visit(node: FrontendNode, scope_id: str) -> None:
        nonlocal parameter_index
        current_scope = scope_id
        if node.type == "compound_statement":
            current_scope = _stable_id("scope", function.function_id, node.start_byte)
        if node.type in {"parameter_declaration", "optional_parameter_declaration"}:
            declarator = node.child_by_field_name("declarator")
            identifier = _declarator_identifier(declarator) or _last_identifier(node)
            if identifier is not None:
                symbols.append(
                    SymbolIR(
                        symbol_id=_stable_id(
                            "sym", function.function_id, identifier.start_byte, identifier.text
                        ),
                        name=identifier.text,
                        kind="parameter",
                        type_spelling=_type_without_identifier(node, identifier),
                        scope_id=_stable_id("scope", function.function_id, "function"),
                        declaration_range=identifier.source_range,
                        parameter_index=parameter_index,
                    )
                )
                parameter_index += 1
        elif node.type == "declaration":
            declarators = []
            direct_declarator = node.child_by_field_name("declarator")
            if direct_declarator is not None:
                declarators.append(direct_declarator)
            declarators.extend(
                candidate.child_by_field_name("declarator") or candidate
                for candidate in node.children
                if candidate.type == "init_declarator"
            )
            for declarator in declarators:
                identifier = _declarator_identifier(declarator)
                if identifier is None:
                    continue
                symbols.append(
                    SymbolIR(
                        symbol_id=_stable_id(
                            "sym", function.function_id, identifier.start_byte, identifier.text
                        ),
                        name=identifier.text,
                        kind="local",
                        type_spelling=(
                            _type_without_identifier(node, identifier)
                            .split("=", 1)[0]
                            .strip()
                        ),
                        scope_id=current_scope,
                        declaration_range=identifier.source_range,
                    )
                )
        for child in node.children:
            visit(child, current_scope)

    if function.ast_node is not None:
        visit(function.ast_node, _stable_id("scope", function.function_id, "function"))
    unique = {symbol.symbol_id: symbol for symbol in symbols}
    return sorted(unique.values(), key=lambda symbol: symbol.declaration_range.start_byte)


def _extract_access_paths(function: FunctionIR) -> list[AccessPathIR]:
    paths: list[AccessPathIR] = []
    seen: set[tuple[int, int]] = set()
    symbol_names = {symbol.name: symbol.symbol_id for symbol in function.symbols}
    for node, parent in _nodes_with_parent(function.body_node):
        if node.type not in {"field_expression", "subscript_expression", "pointer_expression"}:
            continue
        identity = (node.start_byte, node.end_byte)
        if identity in seen:
            continue
        seen.add(identity)
        spelling = compact_ws(node.text)
        root_match = re.match(r"[*&\s(]*([A-Za-z_]\w*)", spelling)
        root = root_match.group(1) if root_match else ""
        fields = tuple(re.findall(r"(?:->|\.)\s*([A-Za-z_]\w*)", spelling))
        index_match = re.search(r"\[([^\]]+)\]", spelling)
        index = compact_ws(index_match.group(1)) if index_match else ""
        precision = "exact"
        if index and not re.fullmatch(r"\d+", index):
            precision = "bounded"
        if not root:
            precision = "unknown"
        role = "rvalue"
        if parent is not None and parent.child_by_field_name("left") is node:
            role = "lvalue"
        elif parent is not None and parent.type == "pointer_expression" and "&" in parent.text[:2]:
            role = "address"
        paths.append(
            AccessPathIR(
                spelling=spelling,
                root_kind="symbol" if root in symbol_names else "unknown",
                root_id=symbol_names.get(root, root),
                dereference_depth=spelling.count("*") + spelling.count("->"),
                fields=fields,
                index=index,
                precision=precision,
                source_range=node.source_range,
                role=role,
            )
        )
    return paths


class TreeSitterFrontend(Frontend):
    name = "tree-sitter"

    def __init__(self, source_root: str | Path | None = None):
        self.source_root = Path(source_root).resolve() if source_root else None

    def parse(self, path: str | Path) -> TranslationUnitIR:
        parsed = parse_c_file(path)
        functions = extract_functions(parsed)
        identity_path = parsed.path.as_posix()
        if self.source_root is not None:
            try:
                identity_path = parsed.path.resolve().relative_to(
                    self.source_root
                ).as_posix()
            except ValueError:
                identity_path = parsed.path.name
        diagnostics = [
            FrontendDiagnostic(
                code="tree_sitter_diagnostic",
                message=warning,
                severity="warning",
                recoverable=True,
            )
            for warning in parsed.warnings
        ]
        unit = TranslationUnitIR(
            path=parsed.path,
            source_text=parsed.text,
            frontend_name=self.name,
            frontend_mode=parsed.parser_kind,
            functions=functions,
            diagnostics=diagnostics,
            schema_version=FRONTEND_IR_SCHEMA_VERSION,
            identity_path=identity_path,
        )
        for function in unit.functions:
            _set_source_file(function.ast_node, identity_path)
            _set_source_file(function.body_node, identity_path)
            function.return_type = _function_return_type(function)
            function.symbols = _extract_symbols(function)
            function.calls = _extract_calls(function)
            function.access_paths = _extract_access_paths(function)
            function.diagnostics = list(diagnostics)
            error_nodes = [
                node for node in _nodes(function.ast_node) if node.type == "ERROR"
            ]
            for error_node in error_nodes:
                diagnostic = FrontendDiagnostic(
                    code="tree_sitter_error_node",
                    message="tree-sitter produced an ERROR node",
                    severity="warning",
                    recoverable=True,
                    source_range=error_node.source_range,
                )
                function.diagnostics.append(diagnostic)
                unit.diagnostics.append(diagnostic)
            if error_nodes:
                function.unsupported_features.append("tree_sitter_error_node")
            if function.body_node is None:
                diagnostic = FrontendDiagnostic(
                    code="text_fallback_no_syntax_tree",
                    message="function was recovered without a syntax tree",
                    severity="warning",
                    recoverable=True,
                    source_range=function.source_range,
                )
                function.diagnostics.append(diagnostic)
                unit.diagnostics.append(diagnostic)
                function.unsupported_features.append("no_syntax_tree")
        return unit
