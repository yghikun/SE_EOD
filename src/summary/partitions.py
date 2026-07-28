"""Exit-sensitive effects and exact error partition construction."""

from __future__ import annotations

import re
from typing import Iterable

from ..semantics.cancellation import normalize_residuals
from ..cfg import build_cfg
from ..semantics.failure_domain_primitives import (
    covered_effects_for_action,
    failure_domain_guard,
    failure_domain_key,
    is_failure_domain_key,
)
from ..failure_points import find_failure_points
from ..frontend.model import BasicBlockIR, FrontendNode, FunctionIR
from ..metadata_residual import (
    EffectEvidence,
    MetadataDelta,
    MetadataEffect,
    MetadataPlane,
    SourceSite,
)
from ..parser import call_name_and_args, compact_ws
from .control_flow import (
    block_for_effect_site as _block_for_effect_site,
    block_for_return_node as _block_for_return_node,
    can_reach_block as _can_reach_block,
    containing_cfg_block as _containing_cfg_block,
    dominators as _dominators,
)
from .model import (
    ErrorExitPartition,
    ExitSensitiveEffects,
    LifecycleEvent,
    LifecycleFact,
)
from .syntax import (
    bare_owner_symbol as _bare_owner_symbol,
    declarator_name as _declarator_name,
    local_pointer_symbols as _local_pointer_symbols,
    ordered_parameters as _ordered_parameters,
    return_expression as _return_expression,
    success_return_symbols as _success_return_symbols,
)


OPEN_DELTAS = {
    MetadataDelta.ADD,
    MetadataDelta.SET,
    MetadataDelta.INC,
    MetadataDelta.RESERVE,
}
CANCEL_DELTAS = {
    MetadataDelta.REMOVE,
    MetadataDelta.CLEAR,
    MetadataDelta.DEC,
    MetadataDelta.RELEASE,
    MetadataDelta.CLOSE,
}
PROTECT_DELTAS = {MetadataDelta.PROTECT}


def _exit_sensitive_effects(
    function: FunctionIR,
    effects: tuple[MetadataEffect, ...],
) -> ExitSensitiveEffects:
    if function.body_node is None:
        return ExitSensitiveEffects(unknown_causes=("missing_function_body",))
    exits = _classified_return_nodes(function)
    success_returns = tuple(node for node, kind in exits if kind == "success")
    error_returns = tuple(node for node, kind in exits if kind == "error")
    unknown_returns = tuple(node for node, kind in exits if kind == "unknown")
    cfg = build_cfg(function)
    success_blocks = _exit_blocks(cfg, success_returns)
    error_blocks = _exit_blocks(cfg, error_returns)
    causes: list[str] = []
    if unknown_returns:
        causes.append("unclassified_return_exit")
    if len(success_blocks) != len(success_returns):
        causes.append("unclassified_success_exit_block")
    if len(error_blocks) != len(error_returns):
        causes.append("unclassified_error_exit_block")
    success_must, success_may = _effects_for_exit_blocks(
        cfg,
        effects,
        success_blocks,
    )
    error_must, error_may = _effects_for_exit_blocks(cfg, effects, error_blocks)
    return ExitSensitiveEffects(
        success_must=success_must,
        success_may=success_may,
        error_must=error_must,
        error_may=error_may,
        error_complete=bool(error_returns) and not causes,
        unknown_causes=tuple(causes),
    )


def _error_exit_partitions(
    function: FunctionIR,
    effects: tuple[MetadataEffect, ...],
    lifecycle_facts: tuple[LifecycleFact, ...] = (),
) -> tuple[ErrorExitPartition, ...]:
    """Keep effect correlation for each classified source error return."""

    if function.body_node is None:
        return ()
    cfg = build_cfg(function)
    partitions: list[ErrorExitPartition] = []
    for return_node, kind in _classified_return_nodes(function):
        if kind != "error":
            continue
        block = _block_for_return_node(cfg, return_node)
        expression = compact_ws(_return_expression(return_node))
        site = SourceSite(
            function.file.as_posix(),
            return_node.start_line,
            expression,
        )
        if block is None:
            partitions.append(
                ErrorExitPartition(
                    exit_site=site,
                    return_expression=expression,
                    complete=False,
                    unknown_causes=("unclassified_error_exit_block",),
                )
            )
            continue
        must, _ = _effects_for_exit_blocks(cfg, effects, (block,))
        must = tuple(dict.fromkeys((
            *must,
            *_failure_domain_guard_actions_for_return(function, cfg, block),
        )))
        terminal_actions = tuple(
            effect for effect in must if is_failure_domain_key(effect.key)
        )
        ordinary = tuple(
            effect for effect in must if not is_failure_domain_key(effect.key)
        )
        opens = tuple(effect for effect in ordinary if effect.delta in OPEN_DELTAS)
        cancels = tuple(effect for effect in ordinary if effect.delta in CANCEL_DELTAS)
        protects = tuple(effect for effect in ordinary if effect.delta in PROTECT_DELTAS)
        normalized = normalize_residuals(opens, cancels, protects)
        destructions = tuple(
            fact
            for fact in lifecycle_facts
            if fact.event is LifecycleEvent.RELEASED
            and any(fact.site == effect.site for effect in must)
        )
        partitions.append(
            ErrorExitPartition(
                exit_site=site,
                return_expression=expression,
                return_constraint=_return_constraint_for_exit(
                    function,
                    return_node,
                    expression,
                    cfg,
                ),
                opens=opens,
                cancels=cancels,
                protects=protects,
                ordered_effects=_ordered_effects(must),
                residuals=normalized.residuals,
                terminal_actions=terminal_actions,
                failed_owner_destructions=destructions,
                path=(site,),
                complete=True,
            )
        )
    partitions.extend(
        _conditional_error_exit_partitions(
            function,
            cfg,
            effects,
            lifecycle_facts,
        )
    )
    return tuple(dict.fromkeys(partitions))


def _conditional_error_exit_partitions(
    function: FunctionIR,
    cfg,
    effects: tuple[MetadataEffect, ...],
    lifecycle_facts: tuple[LifecycleFact, ...],
) -> tuple[ErrorExitPartition, ...]:
    """Split a shared return by a source-visible checked error outcome."""

    partitions: list[ErrorExitPartition] = []
    for point in find_failure_points(function):
        if point.check_kind not in {"IS_ERR", "IS_ERR_OR_NULL", "IS_ERR_VALUE"}:
            continue
        exit_block = next(
            (
                block
                for block in cfg.blocks.values()
                if block.kind == "return_statement"
                and block.start_line == point.error_edge.exit_site.line
            ),
            None,
        )
        if exit_block is None:
            continue
        reachable = _reachable_blocks_without(
            cfg,
            point.error_edge.target_block,
            forbidden={point.error_edge.source_block},
        )
        if exit_block.id not in reachable:
            continue
        dominators = _subset_dominators(
            cfg,
            point.error_edge.target_block,
            reachable,
        )
        must_effects = tuple(
            effect
            for effect in effects
            if (block_id := _block_for_effect_site(cfg, effect)) is not None
            and block_id in dominators.get(exit_block.id, set())
            and effect.site.line >= point.check_site.line
        )
        terminal_actions = tuple(
            effect for effect in must_effects if is_failure_domain_key(effect.key)
        )
        if not terminal_actions:
            continue
        ordinary = tuple(
            effect for effect in must_effects if not is_failure_domain_key(effect.key)
        )
        opens = tuple(effect for effect in ordinary if effect.delta in OPEN_DELTAS)
        cancels = tuple(effect for effect in ordinary if effect.delta in CANCEL_DELTAS)
        protects = tuple(effect for effect in ordinary if effect.delta in PROTECT_DELTAS)
        normalized = normalize_residuals(opens, cancels, protects)
        destructions = tuple(
            fact
            for fact in lifecycle_facts
            if fact.event is LifecycleEvent.RELEASED
            and any(fact.site == effect.site for effect in must_effects)
        )
        partitions.append(
            ErrorExitPartition(
                exit_site=point.error_edge.exit_site,
                return_expression=point.error_edge.exit_expression,
                return_constraint=point.check_kind,
                opens=opens,
                cancels=cancels,
                protects=protects,
                ordered_effects=_ordered_effects(must_effects),
                residuals=normalized.residuals,
                terminal_actions=terminal_actions,
                failed_owner_destructions=destructions,
                path=tuple(dict.fromkeys((
                    point.check_site,
                    *(effect.site for effect in terminal_actions),
                    point.error_edge.exit_site,
                ))),
                complete=True,
            )
        )
    return tuple(partitions)


def _failure_domain_guard_actions_for_return(
    function: FunctionIR,
    cfg,
    return_block: BasicBlockIR,
) -> tuple[MetadataEffect, ...]:
    if function.body_node is None:
        return ()
    parameter_index = {
        name: index for index, name in enumerate(_ordered_parameters(function))
    }
    actions: list[MetadataEffect] = []
    for if_node in function.body_node.walk():
        if if_node.type != "if_statement":
            continue
        condition = if_node.child_by_field_name("condition")
        if condition is None:
            continue
        condition_block = next(
            (
                block
                for block in cfg.blocks.values()
                if block.kind == "condition" and block.start_line == if_node.start_line
            ),
            None,
        )
        if condition_block is None:
            continue
        true_targets = [
            edge.target for edge in cfg.successors(condition_block.id) if edge.kind == "true"
        ]
        false_targets = [
            edge.target for edge in cfg.successors(condition_block.id) if edge.kind == "false"
        ]
        if not true_targets or not false_targets:
            continue
        true_reaches = any(
            _can_reach_block(cfg, target, return_block.id) for target in true_targets
        )
        false_reaches = any(
            _can_reach_block(cfg, target, return_block.id) for target in false_targets
        )
        if not true_reaches or false_reaches:
            continue
        for call in condition.walk():
            if call.type != "call_expression":
                continue
            name, args = call_name_and_args(compact_ws(call.text))
            guard = failure_domain_guard(name)
            if guard is None:
                continue
            owner_index, kind = guard
            if owner_index >= len(args):
                continue
            owner = compact_ws(args[owner_index]).strip("() ")
            if owner not in parameter_index:
                continue
            actions.append(
                MetadataEffect(
                    root=f"arg{parameter_index[owner]}",
                    key=failure_domain_key(kind),
                    plane=MetadataPlane.RECOVERY,
                    delta=MetadataDelta.PROTECT,
                    value=kind.value,
                    site=SourceSite(
                        function.file.as_posix(),
                        call.start_line,
                        compact_ws(call.text),
                    ),
                    evidence=EffectEvidence.EXPLICIT_PRIMITIVE,
                )
            )
    return tuple(dict.fromkeys(actions))


def _reachable_blocks_without(
    cfg,
    start: int,
    *,
    forbidden: set[int],
) -> set[int]:
    pending = [start]
    seen: set[int] = set()
    while pending:
        block_id = pending.pop()
        if block_id in seen or block_id in forbidden:
            continue
        seen.add(block_id)
        pending.extend(edge.target for edge in cfg.successors(block_id))
    return seen


def _subset_dominators(cfg, start: int, nodes: set[int]) -> dict[int, set[int]]:
    dominators = {node: set(nodes) for node in nodes}
    dominators[start] = {start}
    changed = True
    while changed:
        changed = False
        for node in sorted(nodes - {start}):
            predecessors = [
                edge.source
                for edge in cfg.predecessors(node)
                if edge.source in nodes
            ]
            new = (
                set.intersection(*(dominators[item] for item in predecessors))
                if predecessors
                else set()
            )
            new.add(node)
            if new != dominators[node]:
                dominators[node] = new
                changed = True
    return dominators


def _return_constraint(expression: str) -> str:
    value = compact_ws(expression).strip()
    name, args = call_name_and_args(value)
    if name == "ERR_PTR" and len(args) == 1:
        inner = compact_ws(args[0]).strip("() ")
        if re.fullmatch(r"-?(?:[A-Z_]\w*|\d+)", inner):
            return f"EXACT:{inner}"
        return "IS_ERR"
    if name == "PTR_ERR" and len(args) == 1:
        return "NEGATIVE"
    if re.fullmatch(r"-?(?:[A-Z_]\w*|\d+)", value):
        return f"EXACT:{value}"
    return ""


def _return_constraint_for_exit(
    function: FunctionIR,
    return_node: FrontendNode,
    expression: str,
    cfg,
) -> str:
    """Resolve constants and checked result predicates reaching one return."""

    literal = _return_constraint(expression)
    if literal:
        return literal
    symbol = _bare_owner_symbol(expression)
    return_block = _block_for_return_node(cfg, return_node)
    if symbol and return_block is not None and function.body_node is not None:
        dominators = _dominators(cfg)
        bindings: list[tuple[int, str]] = []
        for node in function.body_node.walk():
            if node.start_byte >= return_node.start_byte:
                continue
            value = None
            target = ""
            if node.type == "assignment_expression":
                left = node.child_by_field_name("left")
                right = node.child_by_field_name("right")
                target = compact_ws(left.text) if left is not None else ""
                value = right
            elif node.type == "init_declarator":
                declarator = node.child_by_field_name("declarator")
                target = _declarator_name(declarator) or ""
                value = node.child_by_field_name("value")
            if target != symbol or value is None:
                continue
            block = _containing_cfg_block(cfg, node)
            if (
                block is not None
                and block.id in dominators.get(return_block.id, set())
            ):
                bindings.append((node.start_byte, compact_ws(value.text)))
        if bindings:
            bound = _return_constraint(max(bindings)[1])
            if bound:
                return bound

    constraints = {
        _constraint_from_failure_point(point)
        for point in find_failure_points(function)
        if point.error_edge.exit_site.line == return_node.start_line
        and (not symbol or point.result_symbol == symbol)
    }
    constraints.discard("")
    return next(iter(constraints)) if len(constraints) == 1 else ""


def _constraint_from_failure_point(point) -> str:
    check = point.check_kind
    if check.startswith("eq:"):
        return f"EXACT:{check[3:]}"
    if check in {"<0", "0>"}:
        return "NEGATIVE"
    if check in {">0", "0<"}:
        return "POSITIVE"
    if check in {"<=0", "0>="}:
        return "NONPOSITIVE"
    if check in {">=0", "0<="}:
        return "NONNEGATIVE"
    if check == "nonzero" or check == "ne:0":
        return "NONZERO"
    if check in {"IS_ERR", "IS_ERR_OR_NULL", "IS_ERR_VALUE"}:
        return check
    return ""


def _ordered_effects(
    effects: Iterable[MetadataEffect],
) -> tuple[MetadataEffect, ...]:
    unique = tuple(dict.fromkeys(effects))
    return tuple(
        sorted(
            unique,
            key=lambda effect: (
                effect.site.file,
                effect.site.line,
                effect.site.expression,
                effect.root,
                effect.key,
                effect.delta.value,
            ),
        )
    )


def _partitions_cover_error_outcomes(
    function: FunctionIR,
    partitions: tuple[ErrorExitPartition, ...],
) -> bool:
    if not partitions or not all(partition.complete for partition in partitions):
        return False
    covered_lines = {partition.exit_site.line for partition in partitions}
    return all(
        kind == "success" or node.start_line in covered_lines
        for node, kind in _classified_return_nodes(function)
    )


def _failure_effect_projection(
    partitions: tuple[ErrorExitPartition, ...],
    exit_effects: ExitSensitiveEffects,
) -> tuple[
    tuple[MetadataEffect, ...],
    tuple[MetadataEffect, ...],
    tuple[MetadataEffect, ...],
]:
    """Project exact alternatives without mixing branch-local cleanup proofs."""

    # Keep the established MUST projection until the caller slicer can analyze
    # alternatives independently.  Unioning partition residuals here would
    # discard their cleanup/terminal correlation and inflate Candidates.
    common_opens = tuple(
        effect
        for effect in exit_effects.error_must
        if effect.delta in OPEN_DELTAS
    )
    common_cancels = tuple(
        effect
        for effect in exit_effects.error_must
        if effect.delta in CANCEL_DELTAS
    )
    common_protects = tuple(
        effect
        for effect in exit_effects.error_must
        if effect.delta in PROTECT_DELTAS
    )
    terminal_actions: tuple[MetadataEffect, ...] = ()
    complete = partitions and all(partition.complete for partition in partitions)
    if complete and all(partition.terminal_actions for partition in partitions):
        terminal_actions = tuple(dict.fromkeys(
            action
            for partition in partitions
            for action in partition.terminal_actions
        ))
    return (
        common_opens,
        common_cancels,
        tuple(dict.fromkeys((*common_protects, *terminal_actions))),
    )


def _live_partition_residuals(
    partition: ErrorExitPartition,
) -> tuple[MetadataEffect, ...]:
    terminally_covered = {
        effect
        for action in partition.terminal_actions
        for effect in covered_effects_for_action(action, partition.residuals)
    }
    return tuple(
        effect
        for effect in partition.residuals
        if effect not in terminally_covered
        and not any(
            _destruction_covers_effect(destruction, effect)
            for destruction in partition.failed_owner_destructions
        )
    )


def _destruction_covers_effect(
    destruction: LifecycleFact,
    effect: MetadataEffect,
) -> bool:
    subject = compact_ws(destruction.subject)
    root = compact_ws(effect.root)
    return bool(subject) and (
        root == subject
        or root.startswith(f"{subject}->")
        or root.startswith(f"{subject}.")
    )


def _exit_blocks(cfg, returns: tuple[FrontendNode, ...]) -> tuple[BasicBlockIR, ...]:
    return tuple(
        block
        for node in returns
        if (block := _block_for_return_node(cfg, node)) is not None
    )


def _effects_for_exit_blocks(
    cfg,
    effects: tuple[MetadataEffect, ...],
    exit_blocks: tuple[BasicBlockIR, ...],
) -> tuple[tuple[MetadataEffect, ...], tuple[MetadataEffect, ...]]:
    if not exit_blocks:
        return (), ()
    dominators = _dominators(cfg)
    must: list[MetadataEffect] = []
    may: list[MetadataEffect] = []
    for effect in effects:
        block_id = _block_for_effect_site(cfg, effect)
        if block_id is None:
            continue
        reaches_exit = tuple(
            _can_reach_block(cfg, block_id, exit_block.id)
            and effect.site.line <= exit_block.start_line
            for exit_block in exit_blocks
        )
        if not any(reaches_exit):
            continue
        may.append(effect)
        if all(
            block_id in dominators.get(exit_block.id, set())
            and effect.site.line <= exit_block.start_line
            for exit_block in exit_blocks
        ):
            must.append(effect)
    return tuple(must), tuple(may)


def _has_error_return(function: FunctionIR) -> bool:
    return any(kind == "error" for _, kind in _classified_return_nodes(function))


def _classified_return_nodes(
    function: FunctionIR,
) -> tuple[tuple[FrontendNode, str], ...]:
    if function.body_node is None:
        return ()
    pointer_locals = _local_pointer_symbols(function)
    success_symbols = _success_return_symbols(function, pointer_locals)
    known_error_expressions = {
        compact_ws(point.error_edge.exit_expression)
        for point in find_failure_points(function)
    }
    result: list[tuple[FrontendNode, str]] = []
    for node in function.body_node.walk():
        if node.type != "return_statement":
            continue
        expr = _return_expression(node)
        kind = _return_kind(expr, success_symbols, known_error_expressions)
        result.append((node, kind))
    return tuple(result)


def _return_kind(
    expression: str,
    success_symbols: set[str],
    known_error_expressions: set[str],
) -> str:
    expr = compact_ws(expression)
    if not expr:
        return "unknown"
    if expr in {"0", "NULL", "false", "FALSE"} or expr in success_symbols:
        return "success"
    if expr.startswith("-") or expr in known_error_expressions:
        return "error"
    name, _ = call_name_and_args(expr)
    if name in {"ERR_PTR", "PTR_ERR"}:
        return "error"
    return "unknown"
