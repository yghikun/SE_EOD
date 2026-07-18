"""Tree-sitter based function-local control-flow graph."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .function_extractor import Function


@dataclass(frozen=True)
class CFGEdge:
    source: int
    target: int
    kind: str = "fallthrough"
    condition: str = ""
    scope_unwind: int = 0

    @property
    def edge_id(self) -> str:
        return f"e{self.source}_{self.target}_{self.kind}_u{self.scope_unwind}"


@dataclass
class BasicBlock:
    id: int
    kind: str
    text: str = ""
    start_line: int = 0
    end_line: int = 0
    label: str = ""
    start_byte: int = 0
    end_byte: int = 0
    condition_start_byte: int = 0
    condition_end_byte: int = 0
    scope_depth: int = 0


@dataclass
class ControlFlowGraph:
    blocks: dict[int, BasicBlock]
    edges: list[CFGEdge]
    entry: int
    exit: int
    labels: dict[str, int] = field(default_factory=dict)
    unsupported_nodes: list[str] = field(default_factory=list)
    unsupported_blocks: dict[int, list[str]] = field(default_factory=dict)
    unsupported_ranges: list[dict[str, int | str]] = field(default_factory=list)

    def successors(self, block_id: int) -> list[CFGEdge]:
        return [edge for edge in self.edges if edge.source == block_id]

    def predecessors(self, block_id: int) -> list[CFGEdge]:
        return [edge for edge in self.edges if edge.target == block_id]

    def block_at_line(self, line: int) -> BasicBlock | None:
        matches = [
            block
            for block in self.blocks.values()
            if block.start_line <= line <= block.end_line and block.start_line
        ]
        return min(matches, key=lambda block: (block.end_line - block.start_line, block.id)) if matches else None


@dataclass
class _Fragment:
    entry: int
    exits: list[tuple[int, str]]


class _CFGBuilder:
    def __init__(self, function: Function):
        self.function = function
        self.blocks: dict[int, BasicBlock] = {}
        self.edges: list[CFGEdge] = []
        self.labels: dict[str, int] = {}
        self.pending_gotos: list[tuple[int, str]] = []
        self.unsupported: list[str] = []
        self.unsupported_blocks: dict[int, list[str]] = {}
        self.unsupported_ranges: list[dict[str, int | str]] = []
        self.next_id = 0
        self.scope_depth = 0
        self.entry = self._block("entry")
        self.exit = self._block("exit")

    def _block(
        self,
        kind: str,
        node: Any | None = None,
        label: str = "",
        text: str | None = None,
        condition_node: Any | None = None,
    ) -> int:
        block_id = self.next_id
        self.next_id += 1
        self.blocks[block_id] = BasicBlock(
            id=block_id,
            kind=kind,
            text=text if text is not None else (node.text.strip() if node is not None else ""),
            start_line=node.start_line if node is not None else 0,
            end_line=node.end_line if node is not None else 0,
            label=label,
            start_byte=node.start_byte if node is not None else 0,
            end_byte=node.end_byte if node is not None else 0,
            condition_start_byte=(
                condition_node.start_byte if condition_node is not None else 0
            ),
            condition_end_byte=(
                condition_node.end_byte if condition_node is not None else 0
            ),
            scope_depth=self.scope_depth,
        )
        return block_id

    def _edge(self, source: int, target: int, kind: str = "fallthrough", condition: str = "") -> None:
        scope_unwind = 0
        if kind in {"goto", "backedge", "break", "continue", "return"}:
            scope_unwind = max(
                0,
                self.blocks[source].scope_depth
                - self.blocks[target].scope_depth,
            )
        edge = CFGEdge(source, target, kind, condition, scope_unwind)
        if edge not in self.edges:
            self.edges.append(edge)

    def _mark_unsupported(
        self, block_id: int, node_type: str, node: Any | None = None
    ) -> None:
        self.unsupported.append(node_type)
        self.unsupported_blocks.setdefault(block_id, []).append(node_type)
        block = self.blocks[block_id]
        self.unsupported_ranges.append(
            {
                "type": node_type,
                "block": block_id,
                "start_byte": node.start_byte if node is not None else block.start_byte,
                "end_byte": node.end_byte if node is not None else block.end_byte,
                "start_line": node.start_line if node is not None else block.start_line,
                "end_line": node.end_line if node is not None else block.end_line,
            }
        )

    def build(self) -> ControlFlowGraph:
        if self.function.body_node is None:
            return ControlFlowGraph(self.blocks, self.edges, self.entry, self.exit)
        body = self._sequence(self._named_statements(self.function.body_node), None, None)
        self._edge(self.entry, body.entry)
        for source, kind in body.exits:
            self._edge(source, self.exit, kind)
        for source, label in self.pending_gotos:
            target = self.labels.get(label)
            if target is not None:
                kind = "backedge" if self.blocks[target].start_line <= self.blocks[source].start_line else "goto"
                self._edge(source, target, kind)
            else:
                self._mark_unsupported(source, f"unresolved_goto:{label}")
                self._edge(source, self.exit, "unknown")
        return ControlFlowGraph(
            self.blocks,
            self.edges,
            self.entry,
            self.exit,
            self.labels,
            sorted(set(self.unsupported)),
            {
                block_id: sorted(set(nodes))
                for block_id, nodes in self.unsupported_blocks.items()
            },
            list(self.unsupported_ranges),
        )

    @staticmethod
    def _named_statements(node: Any) -> list[Any]:
        ignored = {"{", "}", ";", ":"}
        return [child for child in node.children if child.type not in ignored]

    def _sequence(self, nodes: list[Any], break_target: int | None, continue_target: int | None) -> _Fragment:
        if not nodes:
            empty = self._block("empty")
            return _Fragment(empty, [(empty, "fallthrough")])
        first: int | None = None
        exits: list[tuple[int, str]] = []
        for node in nodes:
            fragment = self._statement(node, break_target, continue_target)
            if first is None:
                first = fragment.entry
            for source, kind in exits:
                if kind == "fallthrough":
                    self._edge(source, fragment.entry, kind)
            exits = [item for item in exits if item[1] != "fallthrough"] + fragment.exits
        return _Fragment(first if first is not None else self.exit, exits)

    def _statement(self, node: Any, break_target: int | None, continue_target: int | None) -> _Fragment:
        if node.type == "else_clause":
            children = self._named_statements(node)
            if not children:
                empty = self._block("empty", node, text="")
                return _Fragment(empty, [(empty, "fallthrough")])
            return self._statement(children[-1], break_target, continue_target)
        if node.type == "compound_statement":
            enter = self._block("scope_enter", node, text="")
            self.scope_depth += 1
            body = self._sequence(
                self._named_statements(node), break_target, continue_target
            )
            self.scope_depth -= 1
            leave = self._block("scope_exit", node, text="")
            self._edge(enter, body.entry)
            remaining: list[tuple[int, str]] = []
            for source, kind in body.exits:
                if kind == "fallthrough":
                    self._edge(source, leave)
                else:
                    remaining.append((source, kind))
            return _Fragment(enter, [*remaining, (leave, "fallthrough")])
        if node.type == "labeled_statement":
            label_node = node.child_by_field_name("label")
            label = label_node.text.strip() if label_node is not None else ""
            block = self._block("label", node, label)
            if label:
                self.labels[label] = block
            body_nodes = [child for child in node.children if child is not label_node and child.type not in {":", ";"}]
            if not body_nodes:
                return _Fragment(block, [(block, "fallthrough")])
            body = self._sequence(body_nodes, break_target, continue_target)
            self._edge(block, body.entry)
            return _Fragment(block, body.exits)
        if node.type == "if_statement":
            condition_node = node.child_by_field_name("condition")
            condition = condition_node.text.strip() if condition_node is not None else "unknown"
            block = self._block(
                "condition", node, text=condition, condition_node=condition_node
            )
            consequence = self._statement(node.child_by_field_name("consequence"), break_target, continue_target)
            alternative_node = node.child_by_field_name("alternative")
            if alternative_node is not None:
                alternative = self._statement(alternative_node, break_target, continue_target)
            else:
                false_block = self._block("empty")
                alternative = _Fragment(false_block, [(false_block, "fallthrough")])
            self._edge(block, consequence.entry, "true", condition)
            self._edge(block, alternative.entry, "false", condition)
            return _Fragment(block, consequence.exits + alternative.exits)
        if node.type in {"while_statement", "for_statement", "do_statement"}:
            condition_node = node.child_by_field_name("condition")
            condition = condition_node.text.strip() if condition_node is not None else "1"
            header = self._block(
                "loop_condition", node, text=condition, condition_node=condition_node
            )
            after = self._block("loop_exit")
            body_node = node.child_by_field_name("body")
            body = self._statement(body_node, after, header)
            self._edge(header, body.entry, "true", condition)
            self._edge(header, after, "false", condition)
            for source, kind in body.exits:
                if kind == "fallthrough":
                    self._edge(source, header, "backedge")
            return _Fragment(header, [(after, "fallthrough")])
        block = self._block(node.type, node)
        if node.type == "goto_statement":
            label_node = node.child_by_field_name("label")
            self.pending_gotos.append((block, label_node.text.strip() if label_node else ""))
            return _Fragment(block, [])
        if node.type == "return_statement":
            self._edge(block, self.exit, "return")
            return _Fragment(block, [])
        if node.type == "break_statement":
            self._edge(block, break_target or self.exit, "break")
            return _Fragment(block, [])
        if node.type == "continue_statement":
            self._edge(block, continue_target or self.exit, "continue")
            return _Fragment(block, [])
        if node.type in {"switch_statement", "case_statement"}:
            self._mark_unsupported(block, node.type, node)
        return _Fragment(block, [(block, "fallthrough")])


def build_cfg(function: Function) -> ControlFlowGraph:
    return _CFGBuilder(function).build()
