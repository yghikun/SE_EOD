"""Bounded source proof that a residual owner remains live after failure."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Iterable

from .effect_extractor import extract_metadata_effects
from .failure_domain_primitives import (
    failure_domain_kind,
    transaction_cancel_owner_index,
)
from .failure_points import find_failure_points
from .frontend.model import FrontendNode, FunctionIR
from .metadata_residual import (
    MetadataEffect,
    OwnerLivenessProof,
    ResidualState,
    SourceSite,
)
from .parser import call_name_and_args, compact_ws
from .residual_slicer import (
    ResidualSlicingResult,
    _conditional_shutdown_review_blockers,
)


def refine_source_visible_owner_liveness(
    functions: Iterable[FunctionIR],
    slicings: dict[str, ResidualSlicingResult],
) -> dict[str, ResidualSlicingResult]:
    """Promote only residuals followed by source-visible normal continuation."""

    function_tuple = tuple(functions)
    callers_by_target = _direct_callers(function_tuple)
    result = dict(slicings)
    for target in function_tuple:
        slicing = result.get(target.function_id)
        if slicing is None or not any(
            item.state is ResidualState.EXPOSED and item.residuals
            for item in slicing.slices
        ):
            continue
        parameters = _ordered_parameters(target)
        if not parameters:
            continue
        refined = []
        for residual_slice in slicing.slices:
            if residual_slice.state is not ResidualState.EXPOSED:
                refined.append(residual_slice)
                continue
            proofs: list[OwnerLivenessProof] = []
            for residual in residual_slice.residuals:
                proofs.extend(
                    _residual_liveness_proofs(
                        target,
                        residual,
                        residual,
                        callers_by_target,
                        max_depth=2,
                        visited=(),
                        chain=(),
                        origin_site=None,
                    )
                )
            covered = {
                effect for proof in proofs for effect in proof.covered_effects
            }
            state = (
                ResidualState.LIVE
                if residual_slice.residuals
                and all(effect in covered for effect in residual_slice.residuals)
                else residual_slice.state
            )
            blockers = tuple(
                blocker
                for blocker in residual_slice.semantic_blockers
                if blocker != "owner_liveness_unproven"
            )
            blockers = tuple(
                dict.fromkeys(
                    (
                        *blockers,
                        *_conditional_shutdown_review_blockers(
                            tuple(
                                dict.fromkeys(
                                    (
                                        *residual_slice.reaching_effects,
                                        *residual_slice.protections,
                                    )
                                )
                            ),
                            residual_slice.cancellations,
                            residual_slice.residuals,
                        ),
                    )
                )
            )
            if state is ResidualState.EXPOSED and not proofs:
                blockers = tuple(dict.fromkeys((*blockers, "owner_liveness_unproven")))
            refined.append(
                replace(
                    residual_slice,
                    state=state,
                    rationale=(
                        "source-visible caller handles the failure, continues metadata "
                        "work on the same owner, and returns success"
                        if state is ResidualState.LIVE
                        else residual_slice.rationale
                    ),
                    owner_liveness_proofs=tuple(dict.fromkeys(proofs)),
                    semantic_blockers=blockers,
                )
            )
        result[target.function_id] = replace(slicing, slices=tuple(refined))
    return result


def _direct_callers(
    functions: tuple[FunctionIR, ...],
) -> dict[str, tuple[tuple[FunctionIR, FrontendNode], ...]]:
    collected: dict[str, list[tuple[FunctionIR, FrontendNode]]] = {}
    names = {function.name for function in functions}
    for caller in functions:
        if caller.body_node is None:
            continue
        for node in caller.body_node.walk():
            if node.type != "call_expression":
                continue
            callee_node = node.child_by_field_name("function")
            callee, _ = call_name_and_args(compact_ws(node.text))
            if (
                callee in names
                and callee_node is not None
                and callee_node.type == "identifier"
            ):
                collected.setdefault(callee, []).append((caller, node))
    return {name: tuple(items) for name, items in collected.items()}


def _residual_liveness_proofs(
    target: FunctionIR,
    residual: MetadataEffect,
    original_residual: MetadataEffect,
    callers_by_target: dict[str, tuple[tuple[FunctionIR, FrontendNode], ...]],
    *,
    max_depth: int,
    visited: tuple[tuple[str, str], ...],
    chain: tuple[str, ...],
    origin_site: SourceSite | None,
) -> tuple[OwnerLivenessProof, ...]:
    parameters = _ordered_parameters(target)
    target_owner = _leading_symbol(residual.root)
    visit_key = (target.function_id, residual.root)
    if (
        max_depth <= 0
        or target_owner not in parameters
        or visit_key in visited
    ):
        return ()
    proofs: list[OwnerLivenessProof] = []
    next_visited = (*visited, visit_key)
    for caller, call in callers_by_target.get(target.name, ()):
        if caller.body_node is None:
            continue
        _, args = call_name_and_args(compact_ws(call.text))
        mapping = {
            parameter: compact_ws(args[index]).strip("&() ")
            for index, parameter in enumerate(parameters)
            if index < len(args)
        }
        caller_owner = mapping.get(target_owner, "")
        if not caller_owner:
            continue
        caller_residual = replace(
            residual,
            root=_replace_leading_owner(
                residual.root,
                target_owner,
                caller_owner,
            ),
        )
        result_name = _call_result_lvalue(caller, call)
        branch = _failure_handling_branch(caller, call, result_name)
        if branch is None:
            continue
        success_return = _success_return(branch)
        branch_effects = tuple(
            effect
            for effect in extract_metadata_effects(caller)
            if success_return is not None
            and branch.start_line <= effect.site.line <= success_return.start_line
            and effect.site.line >= call.start_line
        )
        continuation = next(
            (
                effect
                for effect in branch_effects
                if _same_owner(caller_owner, effect.root)
            ),
            None,
        )
        call_site = SourceSite(
            caller.file.as_posix(), call.start_line, compact_ws(call.text)
        )
        first_site = origin_site or call_site
        next_chain = (*chain, caller.name)
        if continuation is not None and success_return is not None:
            proofs.append(
                OwnerLivenessProof(
                    owner=caller_owner,
                    site=first_site,
                    continuation_site=continuation.site,
                    covered_effects=(original_residual,),
                    via_function=" -> ".join(next_chain),
                    evidence=(
                        f"{' -> '.join(next_chain)} handles the propagated failure, "
                        f"performs {continuation.site.expression} on the same owner, "
                        "and returns success"
                    ),
                )
            )
            continue
        if (
            max_depth <= 1
            or not _propagates_failure(caller, call)
            or _owner_destroyed_or_terminal(caller, call, caller_owner)
        ):
            continue
        caller_parameter = _leading_symbol(caller_owner)
        if caller_parameter not in _ordered_parameters(caller):
            continue
        proofs.extend(
            _residual_liveness_proofs(
                caller,
                caller_residual,
                original_residual,
                callers_by_target,
                max_depth=max_depth - 1,
                visited=next_visited,
                chain=next_chain,
                origin_site=first_site,
            )
        )
    return tuple(proofs)


def _failure_handling_branch(
    caller: FunctionIR,
    call: FrontendNode,
    result_name: str,
) -> FrontendNode | None:
    if caller.body_node is None:
        return None
    call_text = compact_ws(call.text)
    candidates = sorted(
        (
            node
            for node in caller.body_node.walk()
            if node.type == "if_statement" and node.start_line >= call.start_line
        ),
        key=lambda item: (item.start_line, item.end_line),
    )
    for node in candidates:
        condition = node.child_by_field_name("condition")
        consequence = node.child_by_field_name("consequence")
        alternative = node.child_by_field_name("alternative")
        if condition is None or consequence is None:
            continue
        text = compact_ws(condition.text).strip("() ")
        if result_name:
            failure_on_true = _result_failure_on_true(text, result_name)
        else:
            failure_on_true = call_text in text and not text.startswith("!")
        if failure_on_true is True:
            return consequence
        if failure_on_true is False and alternative is not None:
            return alternative
    return None


def _result_failure_on_true(condition: str, result: str) -> bool | None:
    token = re.escape(result)
    if re.fullmatch(rf"{token}", condition):
        return True
    if re.fullmatch(rf"!\s*{token}", condition):
        return False
    if re.fullmatch(rf"{token}\s*(?:!=|<|<=)\s*0", condition):
        return True
    if re.fullmatch(rf"{token}\s*(?:==|>=|>)\s*0", condition):
        return False if "==" in condition else None
    if re.fullmatch(rf"(?:IS_ERR|IS_ERR_OR_NULL)\s*\(\s*{token}\s*\)", condition):
        return True
    return None


def _success_return(branch: FrontendNode) -> FrontendNode | None:
    returns = sorted(
        (node for node in branch.walk() if node.type == "return_statement"),
        key=lambda item: item.start_line,
    )
    for node in returns:
        value = compact_ws(node.text).removeprefix("return").rstrip(";").strip()
        if value in {"0", "NULL", "false"}:
            return node
    return None


def _call_result_lvalue(function: FunctionIR, call: FrontendNode) -> str:
    if function.body_node is None:
        return ""
    containers = sorted(
        (
            node
            for node in function.body_node.walk()
            if node.type in {"assignment_expression", "init_declarator"}
            and node.start_byte <= call.start_byte
            and call.end_byte <= node.end_byte
        ),
        key=lambda item: item.end_byte - item.start_byte,
    )
    for node in containers:
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            if left is not None:
                return compact_ws(left.text)
        declarator = node.child_by_field_name("declarator")
        if declarator is not None:
            identifiers = [
                item.text for item in declarator.walk() if item.type == "identifier"
            ]
            if identifiers:
                return compact_ws(identifiers[-1])
    return ""


def _ordered_parameters(function: FunctionIR) -> tuple[str, ...]:
    indexed = sorted(
        (
            symbol.parameter_index,
            symbol.name,
        )
        for symbol in function.symbols
        if symbol.kind == "parameter" and symbol.parameter_index is not None
    )
    return tuple(name for _, name in indexed)


def _leading_symbol(text: str) -> str:
    match = re.match(r"[&*()\s]*([A-Za-z_]\w*)", compact_ws(text))
    return match.group(1) if match else ""


def _same_owner(expected: str, actual: str) -> bool:
    expected_value = compact_ws(expected).strip("&*() ")
    actual_value = compact_ws(actual).strip("&*() ")
    return actual_value == expected_value or actual_value.startswith(
        (f"{expected_value}->", f"{expected_value}.")
    )


def _replace_leading_owner(text: str, source: str, target: str) -> str:
    return re.sub(
        rf"\b{re.escape(source)}\b",
        compact_ws(target).strip("&() "),
        compact_ws(text),
        count=1,
    )


def _propagates_failure(caller: FunctionIR, call: FrontendNode) -> bool:
    expression = compact_ws(call.text)
    return any(
        point.call_site.line == call.start_line
        and compact_ws(point.call_site.expression) == expression
        for point in find_failure_points(caller)
    )


def _owner_destroyed_or_terminal(
    caller: FunctionIR,
    call: FrontendNode,
    owner: str,
) -> bool:
    if caller.body_node is None:
        return True
    matching = tuple(
        point
        for point in find_failure_points(caller)
        if point.call_site.line == call.start_line
        and compact_ws(point.call_site.expression) == compact_ws(call.text)
    )
    if not matching:
        return True
    last_line = max(point.error_edge.exit_site.line for point in matching)
    deallocators = {
        "free_percpu": 0,
        "kfree": 0,
        "kmem_cache_free": 1,
        "kvfree": 0,
        "vfree": 0,
    }
    for node in caller.body_node.walk():
        if (
            node.type != "call_expression"
            or node.start_line <= call.start_line
            or node.start_line > last_line
        ):
            continue
        name, args = call_name_and_args(compact_ws(node.text))
        if failure_domain_kind(name) is not None:
            return True
        owner_index = deallocators.get(name)
        if owner_index is None:
            owner_index = transaction_cancel_owner_index(name)
        if (
            owner_index is not None
            and owner_index < len(args)
            and _same_owner(owner, args[owner_index])
        ):
            return True
    return False
