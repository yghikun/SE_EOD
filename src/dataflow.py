"""Generic bounded forward dataflow solver for function CFGs."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Generic, TypeVar

from .cfg import BasicBlock, ControlFlowGraph


StateT = TypeVar("StateT")


@dataclass
class DataflowResult(Generic[StateT]):
    in_states: dict[int, StateT] = field(default_factory=dict)
    out_states: dict[int, StateT] = field(default_factory=dict)
    iterations: int = 0
    truncated: bool = False


@dataclass
class DisjunctiveDataflowResult(Generic[StateT]):
    in_states: dict[int, list[StateT]] = field(default_factory=dict)
    out_states: dict[int, list[StateT]] = field(default_factory=dict)
    iterations: int = 0
    truncated: bool = False
    widened_blocks: set[int] = field(default_factory=set)


def solve_forward(
    cfg: ControlFlowGraph,
    initial: StateT,
    transfer: Callable[[BasicBlock, StateT], StateT],
    join: Callable[[StateT, StateT], StateT],
    clone: Callable[[StateT], StateT],
    max_iterations: int = 10000,
) -> DataflowResult[StateT]:
    result: DataflowResult[StateT] = DataflowResult(in_states={cfg.entry: clone(initial)})
    queue = deque([cfg.entry])
    queued = {cfg.entry}

    while queue and result.iterations < max_iterations:
        block_id = queue.popleft()
        queued.discard(block_id)
        result.iterations += 1
        incoming = result.in_states[block_id]
        outgoing = transfer(cfg.blocks[block_id], clone(incoming))
        if result.out_states.get(block_id) == outgoing:
            continue
        result.out_states[block_id] = clone(outgoing)
        for edge in cfg.successors(block_id):
            previous = result.in_states.get(edge.target)
            merged = clone(outgoing) if previous is None else join(previous, outgoing)
            if previous == merged:
                continue
            result.in_states[edge.target] = merged
            if edge.target not in queued:
                queue.append(edge.target)
                queued.add(edge.target)

    result.truncated = bool(queue)
    return result


def solve_forward_disjunctive(
    cfg: ControlFlowGraph,
    initial: StateT,
    transfer: Callable[[BasicBlock, StateT], StateT],
    join: Callable[[StateT, StateT], StateT],
    clone: Callable[[StateT], StateT],
    edge_transfer: Callable[[object, StateT], StateT | None] | None = None,
    max_states_per_block: int = 16,
    max_iterations: int = 20000,
) -> DisjunctiveDataflowResult[StateT]:
    result: DisjunctiveDataflowResult[StateT] = DisjunctiveDataflowResult(
        in_states={cfg.entry: [clone(initial)]}
    )
    queue = deque([cfg.entry])
    queued = {cfg.entry}

    while queue and result.iterations < max_iterations:
        block_id = queue.popleft()
        queued.discard(block_id)
        result.iterations += 1
        outgoing = _unique_states(
            [transfer(cfg.blocks[block_id], clone(state)) for state in result.in_states[block_id]]
        )
        if result.out_states.get(block_id) == outgoing:
            continue
        result.out_states[block_id] = [clone(state) for state in outgoing]
        for edge in cfg.successors(block_id):
            propagated = [clone(state) for state in outgoing]
            if edge_transfer is not None:
                propagated = [
                    candidate
                    for state in propagated
                    if (candidate := edge_transfer(edge, state)) is not None
                ]
            if not propagated:
                continue
            combined = _unique_states(
                [*result.in_states.get(edge.target, []), *propagated]
            )
            if len(combined) > max_states_per_block:
                widened = clone(combined[0])
                for state in combined[1:]:
                    widened = join(widened, state)
                combined = [widened]
                result.widened_blocks.add(edge.target)
            if result.in_states.get(edge.target) == combined:
                continue
            result.in_states[edge.target] = combined
            if edge.target not in queued:
                queue.append(edge.target)
                queued.add(edge.target)

    result.truncated = bool(queue)
    return result


def _unique_states(states: list[StateT]) -> list[StateT]:
    unique: list[StateT] = []
    for state in states:
        if state not in unique:
            unique.append(state)
    return unique
