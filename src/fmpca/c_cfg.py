from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Dict, Iterable, List, Optional, Set, Tuple

from tree_sitter import Language, Node, Parser
import tree_sitter_c

from .frontend import ExtractedFunction, SourceBindingError, extract_function


@dataclass(frozen=True)
class CCall:
    name: str
    arguments: Tuple[str, ...]


@dataclass(frozen=True)
class CFGNode:
    node_id: int
    kind: str
    text: str
    line: int
    calls: Tuple[CCall, ...] = ()


@dataclass
class FunctionCFG:
    function_name: str
    source_path: str
    entry: int
    exit: int
    nodes: Dict[int, CFGNode]
    edges: Dict[int, Set[int]]
    edge_labels: Dict[Tuple[int, int], str]
    labels: Dict[str, int]
    unresolved_gotos: List[Tuple[int, str]]
    parse_has_error: bool
    normalized_attributes: Tuple[str, ...] = ()

    def successors(self, node_id: int) -> Set[int]:
        return set(self.edges.get(node_id, set()))

    def predecessors(self, node_id: int, allowed: Optional[Set[int]] = None) -> Set[int]:
        return {
            source
            for source, targets in self.edges.items()
            if node_id in targets and (allowed is None or source in allowed)
        }

    def reachable(self, root: Optional[int] = None) -> Set[int]:
        start = self.entry if root is None else root
        seen: Set[int] = set()
        work = [start]
        while work:
            current = work.pop()
            if current in seen:
                continue
            seen.add(current)
            work.extend(self.edges.get(current, ()))
        return seen

    def can_reach(self, source: int, target: int) -> bool:
        return target in self.reachable(source)

    def dominators(self, root: Optional[int] = None) -> Dict[int, Set[int]]:
        start = self.entry if root is None else root
        reachable = self.reachable(start)
        dominators = {
            node: ({node} if node == start else set(reachable)) for node in reachable
        }
        changed = True
        while changed:
            changed = False
            for node in reachable - {start}:
                predecessors = self.predecessors(node, reachable)
                if not predecessors:
                    updated = {node}
                else:
                    common = set(reachable)
                    for predecessor in predecessors:
                        common &= dominators[predecessor]
                    updated = {node} | common
                if updated != dominators[node]:
                    dominators[node] = updated
                    changed = True
        return dominators

    def dominates(self, dominator: int, node: int, root: Optional[int] = None) -> bool:
        return dominator in self.dominators(root).get(node, set())

    def find_calls(self, names: Iterable[str]) -> List[int]:
        wanted = set(names)
        return [
            node_id
            for node_id, node in self.nodes.items()
            if any(call.name in wanted for call in node.calls)
        ]

    def find_text(self, markers: Iterable[str]) -> List[int]:
        values = tuple(markers)
        return [
            node_id
            for node_id, node in self.nodes.items()
            if any(marker in node.text for marker in values)
        ]

    def branch_successor(self, node_id: int, label: str) -> Optional[int]:
        return next(
            (
                target
                for target in self.edges.get(node_id, ())
                if self.edge_labels.get((node_id, target)) == label
            ),
            None,
        )


def _node_text(source: bytes, node: Node) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _call_name(source: bytes, node: Node) -> str:
    function = node.child_by_field_name("function")
    return _node_text(source, function).strip() if function else "<unknown>"


def _calls(source: bytes, node: Node) -> Tuple[CCall, ...]:
    result: List[CCall] = []

    def visit(current: Node) -> None:
        if current.type == "call_expression":
            arguments = current.child_by_field_name("arguments")
            values = tuple(
                _node_text(source, child).strip()
                for child in (arguments.named_children if arguments else [])
            )
            result.append(CCall(_call_name(source, current), values))
        for child in current.named_children:
            visit(child)

    visit(node)
    return tuple(result)


def _is_constant_true(source: bytes, condition: Optional[Node], loop: Node) -> bool:
    if loop.type == "for_statement" and condition is None:
        return True
    if condition is None:
        return False
    value = _node_text(source, condition).strip()
    while value.startswith("(") and value.endswith(")"):
        value = value[1:-1].strip()
    return value == "1"


class _CFGBuilder:
    def __init__(
        self,
        source: bytes,
        function: ExtractedFunction,
        source_path: str,
        normalized_attributes: Tuple[str, ...] = (),
    ):
        self.source = source
        self.function = function
        self.source_path = source_path
        self.normalized_attributes = normalized_attributes
        self.nodes: Dict[int, CFGNode] = {}
        self.edges: Dict[int, Set[int]] = {}
        self.edge_labels: Dict[Tuple[int, int], str] = {}
        self.labels: Dict[str, int] = {}
        self.unresolved_gotos: List[Tuple[int, str]] = []
        self._next_id = 0

    def add_node(self, kind: str, syntax: Optional[Node] = None, text: str = "") -> int:
        node_id = self._next_id
        self._next_id += 1
        if syntax is not None:
            value = _node_text(self.source, syntax)
            line = self.function.start_line + syntax.start_point[0]
            calls = _calls(self.source, syntax)
        else:
            value = text
            line = self.function.start_line
            calls = ()
        self.nodes[node_id] = CFGNode(node_id, kind, value, line, calls)
        self.edges[node_id] = set()
        return node_id

    def connect(self, source: int, target: int, label: str = "next") -> None:
        self.edges[source].add(target)
        self.edge_labels[(source, target)] = label

    def build_statement(
        self,
        node: Node,
        next_node: int,
        *,
        break_target: Optional[int] = None,
        continue_target: Optional[int] = None,
    ) -> int:
        kind = node.type
        if kind == "compound_statement":
            current = next_node
            for child in reversed(node.named_children):
                current = self.build_statement(
                    child,
                    current,
                    break_target=break_target,
                    continue_target=continue_target,
                )
            return current
        if kind == "if_statement":
            condition = node.child_by_field_name("condition")
            consequence = node.child_by_field_name("consequence")
            alternative = node.child_by_field_name("alternative")
            condition_id = self.add_node("condition", condition or node)
            true_entry = (
                self.build_statement(
                    consequence,
                    next_node,
                    break_target=break_target,
                    continue_target=continue_target,
                )
                if consequence
                else next_node
            )
            false_entry = next_node
            if alternative:
                alternative_body = (
                    alternative.named_children[-1]
                    if alternative.type == "else_clause" and alternative.named_children
                    else alternative
                )
                false_entry = self.build_statement(
                    alternative_body,
                    next_node,
                    break_target=break_target,
                    continue_target=continue_target,
                )
            self.connect(condition_id, true_entry, "true")
            self.connect(condition_id, false_entry, "false")
            return condition_id
        if kind in {"while_statement", "for_statement"}:
            condition = node.child_by_field_name("condition")
            condition_id = self.add_node("loop_condition", condition or node)
            body = node.child_by_field_name("body")
            body_entry = (
                self.build_statement(
                    body,
                    condition_id,
                    break_target=next_node,
                    continue_target=condition_id,
                )
                if body
                else condition_id
            )
            self.connect(condition_id, body_entry, "true")
            if not _is_constant_true(self.source, condition, node):
                self.connect(condition_id, next_node, "false")
            return condition_id
        if kind == "do_statement":
            condition = node.child_by_field_name("condition")
            condition_id = self.add_node("loop_condition", condition or node)
            body = node.child_by_field_name("body")
            body_entry = (
                self.build_statement(
                    body,
                    condition_id,
                    break_target=next_node,
                    continue_target=condition_id,
                )
                if body
                else condition_id
            )
            self.connect(condition_id, body_entry, "true")
            if not _is_constant_true(self.source, condition, node):
                self.connect(condition_id, next_node, "false")
            return body_entry
        if kind == "labeled_statement":
            # The label itself is a control-transfer target.  Do not attach the
            # whole labeled subtree, otherwise calls in its body are duplicated
            # on the label node and distort dominance queries.
            label_syntax = node.child(0) if node.child_count else node
            label_node = self.add_node("label", label_syntax)
            label_text = _node_text(self.source, label_syntax).rstrip(":").strip()
            self.labels[label_text] = label_node
            statement = node.named_children[-1] if node.named_children else None
            entry = (
                self.build_statement(
                    statement,
                    next_node,
                    break_target=break_target,
                    continue_target=continue_target,
                )
                if statement and statement != node.child(0)
                else next_node
            )
            self.connect(label_node, entry)
            return label_node
        if kind == "goto_statement":
            node_id = self.add_node("goto", node)
            label = next(
                (
                    _node_text(self.source, child).strip()
                    for child in node.named_children
                    if child.type == "statement_identifier"
                ),
                "",
            )
            self.unresolved_gotos.append((node_id, label))
            return node_id
        if kind == "return_statement":
            node_id = self.add_node("return", node)
            self.connect(node_id, 1, "return")
            return node_id
        if kind == "break_statement":
            node_id = self.add_node("break", node)
            self.connect(node_id, break_target or next_node, "break")
            return node_id
        if kind == "continue_statement":
            node_id = self.add_node("continue", node)
            self.connect(node_id, continue_target or next_node, "continue")
            return node_id
        if kind in {"preproc_if", "preproc_ifdef", "preproc_elif", "preproc_else"}:
            node_id = self.add_node("preprocessor", node)
            self.connect(node_id, next_node)
            return node_id
        node_id = self.add_node("statement", node)
        self.connect(node_id, next_node)
        return node_id

    def finish(self, body: Node, parse_has_error: bool) -> FunctionCFG:
        entry = self.add_node("entry", text="<entry>")
        exit_node = self.add_node("exit", text="<exit>")
        if (entry, exit_node) != (0, 1):
            raise AssertionError("CFG entry/exit allocation order changed")
        body_entry = self.build_statement(body, exit_node)
        self.connect(entry, body_entry)
        for source, label in self.unresolved_gotos:
            target = self.labels.get(label)
            if target is not None:
                self.connect(source, target, "goto")
        return FunctionCFG(
            function_name=self.function.name,
            source_path=self.source_path,
            entry=entry,
            exit=exit_node,
            nodes=self.nodes,
            edges=self.edges,
            edge_labels=self.edge_labels,
            labels=self.labels,
            unresolved_gotos=[
                item for item in self.unresolved_gotos if item[1] not in self.labels
            ],
            parse_has_error=parse_has_error,
            normalized_attributes=self.normalized_attributes,
        )


_GNU_ATTRIBUTES = ("__cold", "__maybe_unused")


def _normalize_gnu_attributes(text: str) -> Tuple[str, Tuple[str, ...]]:
    normalized = text
    applied: List[str] = []
    for attribute in _GNU_ATTRIBUTES:
        if re.search(r"\b" + re.escape(attribute) + r"\b", normalized):
            normalized = re.sub(r"\b" + re.escape(attribute) + r"\b", " " * len(attribute), normalized)
            applied.append(attribute)
    return normalized, tuple(applied)


def build_function_cfg(source_path: str, function_name: str) -> FunctionCFG:
    source_text = Path(source_path).read_text(encoding="utf-8")
    function = extract_function(source_text, function_name)
    normalized_text, normalized_attributes = _normalize_gnu_attributes(function.text)
    source = normalized_text.encode("utf-8")
    parser = Parser(Language(tree_sitter_c.language()))
    tree = parser.parse(source)
    definition = next(
        (child for child in tree.root_node.named_children if child.type == "function_definition"),
        None,
    )
    if definition is None:
        raise SourceBindingError(f"tree-sitter function parse failed: {function_name}")
    body = definition.child_by_field_name("body")
    if body is None:
        raise SourceBindingError(f"tree-sitter function body missing: {function_name}")
    return _CFGBuilder(
        source,
        function,
        source_path,
        normalized_attributes,
    ).finish(
        body, tree.root_node.has_error
    )
