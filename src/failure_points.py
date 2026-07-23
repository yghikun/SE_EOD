"""Failure-point discovery for failure-local residual analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .cfg import build_cfg
from .frontend.model import (
    BasicBlockIR,
    CFGEdgeIR,
    ControlFlowGraphIR,
    FrontendNode,
    FunctionIR,
)
from .metadata_residual import SourceSite
from .parser import call_name_and_args, compact_ws, extract_return_expr


ERROR_CHECK_CALLS = {
    "IS_ERR",
    "IS_ERR_OR_NULL",
    "IS_ERR_VALUE",
}
ERROR_CONVERSION_CALLS = {
    "PTR_ERR",
    "ERR_PTR",
}
BOOLEAN_WRAPPERS = {
    "likely",
    "unlikely",
    "__builtin_expect",
}
NON_FAILURE_CALLS = ERROR_CHECK_CALLS | ERROR_CONVERSION_CALLS | BOOLEAN_WRAPPERS


@dataclass(frozen=True)
class ErrorEdge:
    """CFG edge that carries a checked failure result toward an error exit."""

    source_block: int
    target_block: int
    kind: str
    condition: str
    exit_site: SourceSite
    exit_expression: str
    outcome_extension: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "source_block": self.source_block,
            "target_block": self.target_block,
            "kind": self.kind,
            "condition": self.condition,
            "exit_site": self.exit_site.to_dict(),
            "exit_expression": self.exit_expression,
            "outcome_extension": self.outcome_extension,
        }


@dataclass(frozen=True)
class FailurePoint:
    """A fallible call, its error check, and the checked edge to an error exit."""

    call_site: SourceSite
    check_site: SourceSite
    error_edge: ErrorEdge
    result_symbol: str
    callee: str
    check_kind: str

    def to_dict(self) -> dict[str, object]:
        return {
            "call_site": self.call_site.to_dict(),
            "check_site": self.check_site.to_dict(),
            "error_edge": self.error_edge.to_dict(),
            "result_symbol": self.result_symbol,
            "callee": self.callee,
            "check_kind": self.check_kind,
        }


@dataclass(frozen=True)
class _CallBinding:
    result_symbol: str
    callee: str
    call_node: FrontendNode
    statement_node: FrontendNode


@dataclass(frozen=True)
class _ConditionFailure:
    result_symbol: str
    check_kind: str
    error_when_true: bool
    direct_call: _CallBinding | None = None


def find_failure_points(
    function: FunctionIR,
    *,
    include_outcome_success: bool = False,
) -> tuple[FailurePoint, ...]:
    """Discover checked fallible calls that reach an error exit.

    The first M1 implementation is intentionally intraprocedural.  It recognizes
    source-visible call results and verifies that the checked CFG edge reaches a
    return expression that is error-valued for that edge.  When
    ``include_outcome_success`` is enabled, ``return 0`` on an otherwise error
    edge is also reported for the outcome-residual extension.
    """

    if function.body_node is None:
        return ()

    cfg = build_cfg(function)
    bindings = _call_bindings(function.body_node)
    bindings_by_symbol: dict[str, list[_CallBinding]] = {}
    for binding in bindings:
        bindings_by_symbol.setdefault(binding.result_symbol, []).append(binding)
    for items in bindings_by_symbol.values():
        items.sort(key=lambda item: item.call_node.start_byte)

    points: list[FailurePoint] = []
    seen: set[tuple[int, int, str, str]] = set()
    for if_node in _nodes_of_type(function.body_node, "if_statement"):
        condition_node = _if_condition(if_node)
        if condition_node is None:
            continue
        condition = _condition_failure(condition_node, if_node)
        if condition is None:
            continue

        binding = condition.direct_call or _latest_binding_before(
            bindings_by_symbol.get(condition.result_symbol, ()),
            if_node.start_byte,
        )
        if binding is None:
            continue

        branch = "true" if condition.error_when_true else "false"
        cfg_edge = _cfg_branch_edge(cfg, if_node, branch)
        if cfg_edge is None:
            continue

        error_edge = _verified_error_edge(
            function,
            cfg,
            cfg_edge,
            condition,
            include_outcome_success=include_outcome_success,
        )
        if error_edge is None:
            continue

        key = (
            binding.call_node.start_byte,
            if_node.start_byte,
            condition.result_symbol,
            error_edge.exit_expression,
        )
        if key in seen:
            continue
        seen.add(key)
        points.append(
            FailurePoint(
                call_site=_site(function, binding.call_node),
                check_site=_site(function, if_node, condition_node.text),
                error_edge=error_edge,
                result_symbol=condition.result_symbol,
                callee=binding.callee,
                check_kind=condition.check_kind,
            )
        )

    points.sort(
        key=lambda point: (
            point.call_site.line,
            point.check_site.line,
            point.callee,
            point.result_symbol,
        )
    )
    return tuple(points)


def _call_bindings(body: FrontendNode) -> list[_CallBinding]:
    bindings: list[_CallBinding] = []
    for node in body.walk():
        if node.type == "assignment_expression":
            if len(node.children) < 3:
                continue
            result_symbol = compact_ws(node.children[0].text)
            rhs = node.children[-1]
            call = _first_fallible_call(rhs)
            if result_symbol and call is not None:
                bindings.append(
                    _CallBinding(
                        result_symbol=result_symbol,
                        callee=_call_name(call),
                        call_node=call,
                        statement_node=_enclosing_statement(node) or node,
                    )
                )
        elif node.type == "init_declarator":
            if len(node.children) < 3:
                continue
            result_symbol = compact_ws(node.children[0].text)
            rhs = node.children[-1]
            call = _first_fallible_call(rhs)
            if result_symbol and call is not None:
                bindings.append(
                    _CallBinding(
                        result_symbol=result_symbol,
                        callee=_call_name(call),
                        call_node=call,
                        statement_node=_enclosing_statement(node) or node,
                    )
                )
    return bindings


def _enclosing_statement(node: FrontendNode) -> FrontendNode | None:
    # FrontendNode is parentless, so statement_node currently falls back to the
    # nearest binding node.  The field is kept for later same-file summary logic.
    return None


def _condition_failure(
    condition_node: FrontendNode,
    if_node: FrontendNode,
) -> _ConditionFailure | None:
    expr = _unwrap_expression(condition_node)
    wrapper = _unwrap_boolean_wrapper(expr)
    if wrapper is not expr:
        return _condition_failure(wrapper, if_node)

    if expr.type == "call_expression":
        name, args = call_name_and_args(compact_ws(expr.text))
        if name in ERROR_CHECK_CALLS and args:
            arg = compact_ws(args[0])
            direct = _direct_call_binding(expr, if_node, arg)
            return _ConditionFailure(
                result_symbol=arg,
                check_kind=name,
                error_when_true=True,
                direct_call=direct,
            )
        return None

    if expr.type == "identifier":
        return _ConditionFailure(
            result_symbol=compact_ws(expr.text),
            check_kind="nonzero",
            error_when_true=True,
        )

    if expr.type == "binary_expression":
        return _binary_condition_failure(expr, if_node)

    return None


def _binary_condition_failure(
    expr: FrontendNode,
    if_node: FrontendNode,
) -> _ConditionFailure | None:
    if len(expr.children) < 3:
        return None
    left = _unwrap_expression(expr.children[0])
    op = compact_ws(expr.children[1].text)
    right = _unwrap_expression(expr.children[2])

    left_zero = _is_zero(right)
    right_zero = _is_zero(left)
    if op in {"<", "<=", "!=", "=="} and left_zero:
        symbol = _condition_symbol(left)
        if symbol is None:
            return None
        direct = _direct_call_binding(left, if_node, symbol)
        if op in {"<", "!="}:
            return _ConditionFailure(symbol, f"{op}0", True, direct)
        if op == "==":
            return None
        return None

    if op in {">", ">=", "!=", "=="} and right_zero:
        symbol = _condition_symbol(right)
        if symbol is None:
            return None
        direct = _direct_call_binding(right, if_node, symbol)
        if op in {">", "!="}:
            return _ConditionFailure(symbol, f"0{op}", True, direct)
        if op == "==":
            return None
        return None

    return None


def _condition_symbol(node: FrontendNode) -> str | None:
    node = _unwrap_expression(node)
    if node.type == "identifier":
        return compact_ws(node.text)
    if node.type == "call_expression":
        name = _call_name(node)
        if name not in NON_FAILURE_CALLS:
            return compact_ws(node.text)
    return None


def _direct_call_binding(
    node: FrontendNode,
    if_node: FrontendNode,
    result_symbol: str,
) -> _CallBinding | None:
    node = _unwrap_expression(node)
    call: FrontendNode | None = None
    if node.type == "call_expression":
        name = _call_name(node)
        if name in ERROR_CHECK_CALLS:
            _, args = call_name_and_args(compact_ws(node.text))
            if args:
                nested = _first_fallible_call_text(args[0], node)
                call = nested
        elif name not in NON_FAILURE_CALLS:
            call = node
    if call is None:
        return None
    return _CallBinding(
        result_symbol=result_symbol,
        callee=_call_name(call),
        call_node=call,
        statement_node=if_node,
    )


def _first_fallible_call(node: FrontendNode) -> FrontendNode | None:
    for child in node.walk():
        if child.type == "call_expression" and _call_name(child) not in NON_FAILURE_CALLS:
            return child
    return None


def _first_fallible_call_text(
    text: str,
    within: FrontendNode,
) -> FrontendNode | None:
    normalized = compact_ws(text)
    for child in within.walk():
        if (
            child.type == "call_expression"
            and compact_ws(child.text) == normalized
            and _call_name(child) not in NON_FAILURE_CALLS
        ):
            return child
    return None


def _call_name(node: FrontendNode) -> str:
    name, _ = call_name_and_args(compact_ws(node.text))
    return name


def _latest_binding_before(
    bindings: Iterable[_CallBinding],
    byte_offset: int,
) -> _CallBinding | None:
    latest: _CallBinding | None = None
    for binding in bindings:
        if binding.call_node.start_byte < byte_offset:
            latest = binding
        else:
            break
    return latest


def _cfg_branch_edge(
    cfg: ControlFlowGraphIR,
    if_node: FrontendNode,
    branch: str,
) -> CFGEdgeIR | None:
    block = _cfg_block_for_node(cfg, if_node, kind="condition")
    if block is None:
        return None
    for edge in cfg.successors(block.id):
        if edge.kind == branch:
            return edge
    return None


def _verified_error_edge(
    function: FunctionIR,
    cfg: ControlFlowGraphIR,
    edge: CFGEdgeIR,
    condition: _ConditionFailure,
    *,
    include_outcome_success: bool,
) -> ErrorEdge | None:
    for block in _reachable_return_blocks(cfg, edge.target):
        expr = compact_ws(extract_return_expr(block.text) or "")
        outcome_extension = expr == "0" and include_outcome_success
        if _is_error_return(expr, condition) or outcome_extension:
            return ErrorEdge(
                source_block=edge.source,
                target_block=edge.target,
                kind=edge.kind,
                condition=edge.condition,
                exit_site=_site_from_block(function, block, block.text),
                exit_expression=expr,
                outcome_extension=outcome_extension,
            )
    return None


def _reachable_return_blocks(
    cfg: ControlFlowGraphIR,
    start_block: int,
) -> list[BasicBlockIR]:
    pending = [start_block]
    seen: set[int] = set()
    returns: list[BasicBlockIR] = []
    while pending:
        block_id = pending.pop(0)
        if block_id in seen:
            continue
        seen.add(block_id)
        block = cfg.blocks[block_id]
        if block.kind == "return_statement":
            returns.append(block)
            continue
        if block_id == cfg.exit:
            continue
        for edge in cfg.successors(block_id):
            pending.append(edge.target)
    returns.sort(key=lambda item: (item.start_line, item.id))
    return returns


def _is_error_return(expr: str, condition: _ConditionFailure) -> bool:
    if not expr:
        return False
    if expr.startswith("-"):
        return True
    if expr == condition.result_symbol:
        return True
    name, args = call_name_and_args(expr)
    if name == "PTR_ERR" and args and compact_ws(args[0]) == condition.result_symbol:
        return True
    if name == "ERR_PTR":
        return True
    return False


def _unwrap_expression(node: FrontendNode) -> FrontendNode:
    current = node
    while current.type == "parenthesized_expression":
        children = [
            child
            for child in current.children
            if child.type not in {"(", ")"}
        ]
        if len(children) != 1:
            break
        current = children[0]
    return current


def _unwrap_boolean_wrapper(node: FrontendNode) -> FrontendNode:
    node = _unwrap_expression(node)
    if node.type != "call_expression":
        return node
    name, args = call_name_and_args(compact_ws(node.text))
    if name not in BOOLEAN_WRAPPERS or not args:
        return node
    normalized = compact_ws(args[0])
    for child in node.walk():
        if compact_ws(child.text) == normalized:
            return _unwrap_expression(child)
    return node


def _is_zero(node: FrontendNode) -> bool:
    return compact_ws(node.text) in {"0", "0L", "0UL", "NULL"}


def _if_condition(if_node: FrontendNode) -> FrontendNode | None:
    condition = if_node.child_by_field_name("condition")
    if condition is not None:
        return condition
    for child in if_node.children:
        if child.type == "parenthesized_expression":
            return child
    return None


def _cfg_block_for_node(
    cfg: ControlFlowGraphIR,
    node: FrontendNode,
    *,
    kind: str | None = None,
) -> BasicBlockIR | None:
    matches = [
        block
        for block in cfg.blocks.values()
        if block.start_byte == node.start_byte
        and block.end_byte == node.end_byte
        and (kind is None or block.kind == kind)
    ]
    if matches:
        return min(matches, key=lambda block: block.id)
    line_matches = [
        block
        for block in cfg.blocks.values()
        if block.start_line == node.start_line
        and (kind is None or block.kind == kind)
    ]
    return min(line_matches, key=lambda block: block.id) if line_matches else None


def _nodes_of_type(node: FrontendNode, node_type: str) -> Iterable[FrontendNode]:
    return (child for child in node.walk() if child.type == node_type)


def _site(function: FunctionIR, node: FrontendNode, expression: str | None = None) -> SourceSite:
    return SourceSite(
        function.file.as_posix(),
        node.start_line,
        compact_ws(expression if expression is not None else node.text),
    )


def _site_from_block(function: FunctionIR, block: BasicBlockIR, expression: str) -> SourceSite:
    return SourceSite(function.file.as_posix(), block.start_line, compact_ws(expression))
