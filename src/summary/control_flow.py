"""Control-flow queries shared by summary analysis stages."""

from __future__ import annotations

from ..frontend.model import BasicBlockIR, FrontendNode
from ..metadata_residual import MetadataEffect
from ..parser import compact_ws


def containing_cfg_block(cfg, node: FrontendNode) -> BasicBlockIR | None:
    matches = [
        block
        for block in cfg.blocks.values()
        if block.kind not in {"entry", "exit"}
        and block.start_byte <= node.start_byte
        and node.end_byte <= block.end_byte
    ]
    return min(
        matches,
        key=lambda block: (block.end_byte - block.start_byte, block.id),
    ) if matches else None


def can_reach_block(cfg, start: int, target: int) -> bool:
    pending = [start]
    seen: set[int] = set()
    while pending:
        block_id = pending.pop()
        if block_id in seen:
            continue
        if block_id == target:
            return True
        seen.add(block_id)
        pending.extend(edge.target for edge in cfg.successors(block_id))
    return False


def dominators(cfg) -> dict[int, set[int]]:
    nodes = set(cfg.blocks)
    result = {block_id: set(nodes) for block_id in nodes}
    result[cfg.entry] = {cfg.entry}
    changed = True
    while changed:
        changed = False
        for block_id in sorted(nodes - {cfg.entry}):
            predecessors = [edge.source for edge in cfg.predecessors(block_id)]
            if not predecessors:
                new = {block_id}
            else:
                new = set.intersection(*(result[item] for item in predecessors))
                new.add(block_id)
            if new != result[block_id]:
                result[block_id] = new
                changed = True
    return result


def block_for_return_node(cfg, node: FrontendNode):
    matches = [
        block
        for block in cfg.blocks.values()
        if block.kind == "return_statement"
        and block.start_byte == node.start_byte
        and block.end_byte == node.end_byte
    ]
    if matches:
        return min(matches, key=lambda block: block.id)
    return cfg.block_at_line(node.start_line)


def block_for_effect_site(cfg, effect: MetadataEffect) -> int | None:
    matches = [
        block
        for block in cfg.blocks.values()
        if block.start_line <= effect.site.line <= block.end_line and block.start_line
    ]
    if not matches:
        return None
    exact = [
        block
        for block in matches
        if compact_ws(effect.site.expression) in compact_ws(block.text)
    ]
    chosen = exact or matches
    return min(
        chosen,
        key=lambda block: (block.end_line - block.start_line, block.id),
    ).id
