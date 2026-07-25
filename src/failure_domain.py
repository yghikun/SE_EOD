"""Source-proven caller containment for function-boundary residuals."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Iterable

from .failure_points import FailurePoint, find_failure_points
from .frontend.model import FrontendNode, FunctionIR
from .function_summary import FunctionSummary, instantiate_summary
from .metadata_residual import (
    FailureDomainKind,
    FailureDomainProof,
    MetadataEffect,
    ResidualSlice,
    ResidualState,
)
from .parser import call_name_and_args, compact_ws
from .residual_slicer import ResidualSlicingResult


@dataclass(frozen=True)
class _CallContext:
    caller: FunctionIR
    point: FailurePoint
    residual_slice: ResidualSlice
    propagated_effects: tuple[MetadataEffect, ...]


def refine_static_callee_containment(
    functions: Iterable[FunctionIR],
    slicings: dict[str, ResidualSlicingResult],
    summaries: dict[str, FunctionSummary],
) -> dict[str, ResidualSlicingResult]:
    """Contain a static callee only when every visible failure call is sealed."""

    function_tuple = tuple(functions)
    by_name = {function.name: function for function in function_tuple}
    contexts = _call_contexts(function_tuple, slicings, summaries)
    externally_contained: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, function in by_name.items():
            if name in externally_contained or not _is_static(function):
                continue
            call_contexts = contexts.get(name, ())
            if not call_contexts:
                continue
            if all(
                _context_is_contained(context, externally_contained)
                for context in call_contexts
            ):
                externally_contained.add(name)
                changed = True

    result = dict(slicings)
    for name in sorted(externally_contained):
        function = by_name[name]
        slicing = result.get(function.function_id)
        if slicing is None:
            continue
        proofs = tuple(
            _proof_for_context(context)
            for context in contexts[name]
        )
        refined = tuple(
            replace(
                item,
                state=ResidualState.CONTAINED,
                rationale=(
                    f"{len(item.residuals)} metadata effect(s) remain at this "
                    "static function boundary, but every source-visible failure "
                    "caller contains the propagated effects"
                ),
                containment_proofs=tuple(dict.fromkeys(item.containment_proofs + proofs)),
            )
            if item.state is ResidualState.EXPOSED and item.residuals
            else item
            for item in slicing.slices
        )
        result[function.function_id] = replace(slicing, slices=refined)
    return result


def _call_contexts(
    functions: tuple[FunctionIR, ...],
    slicings: dict[str, ResidualSlicingResult],
    summaries: dict[str, FunctionSummary],
) -> dict[str, tuple[_CallContext, ...]]:
    static_names = {function.name for function in functions if _is_static(function)}
    collected: dict[str, list[_CallContext]] = {name: [] for name in static_names}
    blocked: set[str] = set()
    for caller in functions:
        if caller.body_node is None:
            continue
        slicing = slicings.get(caller.function_id)
        if slicing is None:
            continue
        points = find_failure_points(caller)
        slice_by_point = {
            _point_key(point): residual_slice
            for point, residual_slice in zip(points, slicing.slices)
        }
        for node in caller.body_node.walk():
            if node.type != "call_expression":
                continue
            callee, _ = call_name_and_args(compact_ws(node.text))
            if callee not in static_names:
                continue
            point = next(
                (
                    item
                    for item in points
                    if item.callee == callee
                    and item.call_site.line == node.start_line
                    and compact_ws(item.call_site.expression) == compact_ws(node.text)
                ),
                None,
            )
            summary = summaries.get(callee)
            if point is None or summary is None or not summary.failure_effects_complete:
                blocked.add(callee)
                continue
            residual_slice = slice_by_point.get(_point_key(point))
            application = instantiate_summary(summary, node)
            propagated = application.error_opens
            if residual_slice is None or not propagated or not all(
                _effect_reaches(effect, residual_slice.reaching_effects)
                for effect in propagated
            ):
                blocked.add(callee)
                continue
            collected[callee].append(
                _CallContext(caller, point, residual_slice, propagated)
            )
    return {
        name: tuple(items)
        for name, items in collected.items()
        if name not in blocked
    }


def _context_is_contained(
    context: _CallContext,
    externally_contained: set[str],
) -> bool:
    if context.residual_slice.state in {
        ResidualState.CLOSED,
        ResidualState.PROTECTED,
        ResidualState.CONTAINED,
    }:
        return all(
            not _effect_reaches(effect, context.residual_slice.residuals)
            or context.residual_slice.state is ResidualState.CONTAINED
            for effect in context.propagated_effects
        )
    return (
        context.residual_slice.state is ResidualState.EXPOSED
        and context.caller.name in externally_contained
    )


def _proof_for_context(context: _CallContext) -> FailureDomainProof:
    inherited = context.residual_slice.containment_proofs
    kind = (
        inherited[0].kind
        if inherited
        else FailureDomainKind.CALLER_CONTAINMENT
    )
    return FailureDomainProof(
        kind=kind,
        site=context.point.call_site,
        via_function=context.caller.name,
        evidence=(
            f"{context.caller.name} checks this static callee failure; "
            f"{len(context.propagated_effects)} complete error effect(s) reach a "
            f"{context.residual_slice.state.value} caller path"
        ),
    )


def _effect_reaches(effect: MetadataEffect, effects: tuple[MetadataEffect, ...]) -> bool:
    return any(
        effect.root == candidate.root
        and effect.key == candidate.key
        and effect.plane is candidate.plane
        and effect.delta is candidate.delta
        and effect.value == candidate.value
        for candidate in effects
    )


def _point_key(point: FailurePoint) -> tuple[int, int, str, str]:
    return (
        point.call_site.line,
        point.check_site.line,
        point.callee,
        point.error_edge.exit_expression,
    )


def _is_static(function: FunctionIR) -> bool:
    return bool(re.search(r"\bstatic\b", function.signature))
