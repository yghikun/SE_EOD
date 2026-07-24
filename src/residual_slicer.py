"""Failure-anchored residual slicing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .cancellation import normalize_residuals
from .cfg import build_cfg
from .effect_extractor import (
    effect_targets_transient_object,
    extract_metadata_effects,
    looks_like_metadata_reader,
)
from .failure_points import FailurePoint, find_failure_points
from .frontend.model import BasicBlockIR, ControlFlowGraphIR, FrontendNode, FunctionIR
from .function_summary import FunctionSummary, apply_same_file_summary
from .metadata_residual import (
    MetadataDelta,
    MetadataEffect,
    ResidualSlice,
    ResidualState,
    SourceSite,
)
from .parser import call_name_and_args, compact_ws


@dataclass(frozen=True)
class ResidualSlicingResult:
    function: str
    slices: tuple[ResidualSlice, ...]
    unknown_causes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "function": self.function,
            "slices": [item.to_dict() for item in self.slices],
            "unknown_causes": list(self.unknown_causes),
        }


def slice_function_residuals(
    function: FunctionIR,
    *,
    summaries: dict[str, FunctionSummary] | None = None,
    failure_points: tuple[FailurePoint, ...] | None = None,
) -> ResidualSlicingResult:
    """Compute M5 residual slices for one function.

    This pass is intraprocedural with optional same-file helper summaries.  It
    collects effects that can reach each failure point, then walks the verified
    error edge to collect cancellation and protection effects before the error
    exit.
    """

    if function.body_node is None:
        return ResidualSlicingResult(function.name, (), ("missing function body",))

    cfg = build_cfg(function)
    summaries = summaries or {}
    failure_points = failure_points if failure_points is not None else find_failure_points(function)
    local_effects = tuple(_LocatedEffect(effect, _block_for_site(cfg, effect.site)) for effect in extract_metadata_effects(function))
    known_error_path_effect_sites = _known_error_path_effect_sites(local_effects)
    call_apps = tuple(_summary_applications(function, cfg, summaries))

    slices: list[ResidualSlice] = []
    all_unknown_causes: list[str] = []
    for point in failure_points:
        reaching_blocks = _reverse_reachable(cfg, point.error_edge.source_block)
        error_blocks = _forward_reachable_until_returns(cfg, point.error_edge.target_block)
        reaching_effects: list[MetadataEffect] = []
        cancellations: list[MetadataEffect] = []
        protections: list[MetadataEffect] = []
        unknown_causes: list[str] = []
        error_path_unknown_causes: list[str] = []

        for item in local_effects:
            if item.block_id not in reaching_blocks or not _effect_before_failure(item.effect, point):
                continue
            if item.effect.delta in _CANCEL_DELTAS:
                cancellations.append(item.effect)
            elif item.effect.delta in _PROTECT_DELTAS:
                protections.append(item.effect)
            else:
                reaching_effects.append(item.effect)

        for item in local_effects:
            if item.block_id not in error_blocks:
                continue
            if item.effect.site.line < point.check_site.line:
                continue
            if item.effect.delta in _CANCEL_DELTAS:
                cancellations.append(item.effect)
            elif item.effect.delta in _PROTECT_DELTAS:
                protections.append(item.effect)

        for app in call_apps:
            is_failure_call = _is_failure_call_application(app, point)
            transfer_order_unknown = (
                is_failure_call
                and app.has_ownership_transfer
                and not app.failure_effects_complete
            )
            if (
                is_failure_call
                and app.block_id in reaching_blocks
                and app.site.line <= point.call_site.line
                and (app.failure_effects_complete or app.has_ownership_transfer)
            ):
                reaching_effects.extend(app.error_opens)
                cancellations.extend(app.error_cancels)
                protections.extend(app.error_protects)
                if app.failure_unknown:
                    unknown_causes.extend(app.failure_unknown_causes)
                continue
            if (
                app.block_id in reaching_blocks
                and app.site.line <= point.call_site.line
                and not transfer_order_unknown
            ):
                reaching_effects.extend(app.opens)
                cancellations.extend(app.cancels_before_failure)
                protections.extend(app.protects_before_failure)
            if app.block_id in error_blocks and app.site.line >= point.check_site.line:
                cancellations.extend(app.cancels)
                protections.extend(app.protects)
            if app.unknown and (
                app.block_id in reaching_blocks and app.site.line <= point.call_site.line
            ):
                unknown_causes.extend(app.unknown_causes)
            elif transfer_order_unknown and (
                app.opens or app.cancels or app.protects
            ):
                unknown_causes.append(
                    f"{app.function_name}: callee_failure_effect_order_unknown"
                )
            elif app.unknown and app.block_id in error_blocks:
                error_path_unknown_causes.extend(app.unknown_causes)

        normalized = normalize_residuals(tuple(reaching_effects), tuple(cancellations), tuple(protections))
        if reaching_effects:
            error_path_unknown_causes.extend(
                _unknown_calls_on_path(
                    function,
                    cfg,
                    summaries,
                    error_blocks,
                    point.check_site.line,
                    known_error_path_effect_sites,
                )
            )
            unknown_causes.extend(error_path_unknown_causes)
        residuals = normalized.residuals
        state = (
            ResidualState.UNKNOWN
            if unknown_causes
            else ResidualState.EXPOSED
            if residuals
            else ResidualState.PROTECTED
            if normalized.protected
            else ResidualState.CLOSED
        )
        exit_site = point.error_edge.exit_site
        slices.append(
            ResidualSlice(
                failure_site=point.call_site,
                reaching_effects=tuple(reaching_effects),
                cancellations=tuple(cancellations),
                protections=tuple(protections),
                residuals=tuple(residuals),
                state=state,
                exit_site=exit_site,
                rationale=_rationale(state, residuals, unknown_causes),
            )
        )
        all_unknown_causes.extend(unknown_causes)

    return ResidualSlicingResult(
        function=function.name,
        slices=tuple(slices),
        unknown_causes=tuple(sorted(set(all_unknown_causes))),
    )


_CANCEL_DELTAS = {
    MetadataDelta.REMOVE,
    MetadataDelta.CLEAR,
    MetadataDelta.DEC,
    MetadataDelta.RELEASE,
    MetadataDelta.CLOSE,
}
_PROTECT_DELTAS = {MetadataDelta.PROTECT}


@dataclass(frozen=True)
class _LocatedEffect:
    effect: MetadataEffect
    block_id: int | None


@dataclass(frozen=True)
class _SummaryApp:
    function_name: str
    block_id: int | None
    site: SourceSite
    opens: tuple[MetadataEffect, ...]
    cancels: tuple[MetadataEffect, ...]
    protects: tuple[MetadataEffect, ...]
    error_opens: tuple[MetadataEffect, ...]
    error_cancels: tuple[MetadataEffect, ...]
    error_protects: tuple[MetadataEffect, ...]
    unknown: bool
    unknown_causes: tuple[str, ...]
    failure_unknown: bool
    failure_unknown_causes: tuple[str, ...]
    failure_effects_complete: bool
    may_fail: bool
    has_ownership_transfer: bool

    @property
    def cancels_before_failure(self) -> tuple[MetadataEffect, ...]:
        return self.cancels

    @property
    def protects_before_failure(self) -> tuple[MetadataEffect, ...]:
        return self.protects


def _summary_applications(
    function: FunctionIR,
    cfg: ControlFlowGraphIR,
    summaries: dict[str, FunctionSummary],
) -> Iterable[_SummaryApp]:
    if function.body_node is None:
        return
    for node in function.body_node.walk():
        if node.type != "call_expression":
            continue
        app = apply_same_file_summary(
            summaries,
            node,
            return_lvalue=_return_lvalue_for_call(function, node),
        )
        if app is None:
            continue
        block = _block_for_node(cfg, node)
        site = SourceSite(function.file.as_posix(), node.start_line, compact_ws(node.text))
        unknown_causes: list[str] = []
        unknown_causes.extend(
            f"{app.summary.function_name}: {cause}"
            for cause in app.summary.unknown_causes
        )
        unknown_causes.extend(
            f"{app.summary.function_name}: unresolved_identity: {item}"
            for item in app.unresolved_identities
        )
        failure_unknown_causes: list[str] = []
        failure_unknown_causes.extend(
            f"{app.summary.function_name}: unresolved_identity: {item}"
            for item in app.unresolved_identities
        )
        if app.summary.has_ownership_transfer:
            failure_unknown_causes.extend(
                f"{app.summary.function_name}: {cause}"
                for cause in app.summary.error_unknown_causes
            )
        if not app.failure_effects_complete and app.summary.has_ownership_transfer:
            failure_unknown_causes.append(
                f"{app.summary.function_name}: callee_failure_effect_order_unknown"
            )
        transfer_is_caller_owned = _transfer_roots_are_caller_owned(
            function,
            app.ownership_transfer_roots,
        )
        opens = _in_scope_summary_effects(function, app.opens)
        cancels = _in_scope_summary_effects(function, app.cancels)
        protects = _in_scope_summary_effects(function, app.protects)
        error_opens = _in_scope_summary_effects(function, app.error_opens)
        error_cancels = _in_scope_summary_effects(function, app.error_cancels)
        error_protects = _in_scope_summary_effects(function, app.error_protects)
        error_opens = _drop_unexposed_fresh_error_effects(error_opens)
        error_cancels = _drop_unexposed_fresh_error_effects(error_cancels)
        error_protects = _drop_unexposed_fresh_error_effects(error_protects)
        if app.ownership_transfer_roots and not transfer_is_caller_owned:
            opens = ()
            cancels = ()
            protects = ()
            error_opens = ()
            error_cancels = ()
            error_protects = ()
        yield _SummaryApp(
            function_name=app.summary.function_name,
            block_id=block.id if block is not None else None,
            site=site,
            opens=opens,
            cancels=cancels,
            protects=protects,
            error_opens=error_opens,
            error_cancels=error_cancels,
            error_protects=error_protects,
            unknown=app.unknown,
            unknown_causes=tuple(unknown_causes),
            failure_unknown=bool(failure_unknown_causes),
            failure_unknown_causes=tuple(failure_unknown_causes),
            failure_effects_complete=app.failure_effects_complete,
            may_fail=app.summary.may_fail,
            has_ownership_transfer=(
                app.summary.has_ownership_transfer and transfer_is_caller_owned
            ),
        )


def _is_failure_call_application(app: _SummaryApp, point: FailurePoint) -> bool:
    return (
        app.site.line == point.call_site.line
        and compact_ws(app.site.expression) == compact_ws(point.call_site.expression)
    )


def _drop_unexposed_fresh_error_effects(
    effects: tuple[MetadataEffect, ...],
) -> tuple[MetadataEffect, ...]:
    exposed = _fresh_identities_exposed_by_effects(effects)
    return tuple(
        effect
        for effect in effects
        if not _fresh_identity_tokens(effect) - exposed
    )


def _fresh_identities_exposed_by_effects(
    effects: tuple[MetadataEffect, ...],
) -> set[str]:
    exposed: set[str] = set()
    for effect in effects:
        if effect.delta is MetadataDelta.ADD:
            root_tokens = _fresh_tokens(effect.root)
            value_tokens = _fresh_tokens(effect.value)
            if value_tokens and not root_tokens:
                exposed.update(value_tokens)
        elif effect.delta is MetadataDelta.SET:
            root_tokens = _fresh_tokens(effect.root)
            value_tokens = _fresh_tokens(effect.value)
            if value_tokens and not root_tokens:
                exposed.update(value_tokens)
    return exposed


def _fresh_identity_tokens(effect: MetadataEffect) -> set[str]:
    return (
        _fresh_tokens(effect.root)
        | _fresh_tokens(effect.key)
        | _fresh_tokens(effect.value)
    )


def _fresh_tokens(text: str) -> set[str]:
    return set(re.findall(r"\b__fresh_[A-Za-z0-9_]+__\b", text))


def _in_scope_summary_effects(
    function: FunctionIR,
    effects: tuple[MetadataEffect, ...],
) -> tuple[MetadataEffect, ...]:
    return tuple(
        effect
        for effect in effects
        if not effect_targets_transient_object(function, effect)
    )


def _transfer_roots_are_caller_owned(
    function: FunctionIR,
    roots: tuple[str, ...],
) -> bool:
    if not roots:
        return True
    local_symbols = _caller_local_symbols(function)
    return all(
        (symbol := _leading_symbol(root)) and symbol not in local_symbols
        for root in roots
    )


def _caller_local_symbols(function: FunctionIR) -> set[str]:
    if function.body_node is None:
        return set()
    symbols: set[str] = set()
    declarator_types = {
        "array_declarator",
        "attributed_declarator",
        "identifier",
        "init_declarator",
        "parenthesized_declarator",
        "pointer_declarator",
    }
    for node in function.body_node.walk():
        if node.type == "declaration":
            declarators = tuple(
                child
                for child in node.children
                if child.type in declarator_types
            )
            if not declarators:
                declarator = node.child_by_field_name("declarator")
                declarators = (declarator,) if declarator is not None else ()
            for declarator in declarators:
                name = _declarator_name(declarator)
                if name:
                    symbols.add(name)
        elif node.type == "call_expression":
            name, args = call_name_and_args(compact_ws(node.text))
            if name in {"LIST_HEAD", "HLIST_HEAD"} and args:
                symbol = compact_ws(args[0])
                if re.fullmatch(r"[A-Za-z_]\w*", symbol):
                    symbols.add(symbol)
    return symbols - set(function.parameters)


def _leading_symbol(path: str) -> str:
    match = re.match(r"^([A-Za-z_]\w*)", compact_ws(path).lstrip("&*()"))
    return match.group(1) if match else ""


def _unknown_calls_on_path(
    function: FunctionIR,
    cfg: ControlFlowGraphIR,
    summaries: dict[str, FunctionSummary],
    block_ids: set[int],
    min_line: int,
    known_error_path_effect_sites: set[tuple[int, str]],
) -> tuple[str, ...]:
    if function.body_node is None:
        return ()
    causes: list[str] = []
    for node in function.body_node.walk():
        if node.type != "call_expression":
            continue
        block = _block_for_node(cfg, node)
        if block is None or block.id not in block_ids or node.start_line < min_line:
            continue
        site_key = (node.start_line, compact_ws(node.text))
        if site_key in known_error_path_effect_sites:
            continue
        name, _ = call_name_and_args(compact_ws(node.text))
        if name in summaries:
            continue
        callee_node = node.child_by_field_name("function")
        if callee_node is not None and callee_node.type != "identifier":
            causes.append(f"indirect call on error path: {compact_ws(node.text)}")
        elif _looks_like_metadata_helper(name):
            causes.append(f"unresolved metadata helper on error path: {name}")
    return tuple(causes)


def _return_lvalue_for_call(function: FunctionIR, node: FrontendNode) -> str:
    if function.body_node is None:
        return ""
    for parent in function.body_node.walk():
        if parent.type == "assignment_expression":
            right = parent.child_by_field_name("right")
            left = parent.child_by_field_name("left")
            if (
                left is not None
                and right is not None
                and _node_contains(right, node)
            ):
                return compact_ws(left.text)
        if parent.type == "init_declarator":
            value = parent.child_by_field_name("value")
            declarator = parent.child_by_field_name("declarator")
            if value is not None and declarator is not None and _node_contains(value, node):
                name = _declarator_name(declarator)
                if name:
                    return name
    return ""


def _node_contains(parent: FrontendNode, child: FrontendNode) -> bool:
    return parent.start_byte <= child.start_byte and child.end_byte <= parent.end_byte


def _declarator_name(node: FrontendNode | None) -> str:
    if node is None:
        return ""
    if node.type == "identifier":
        return compact_ws(node.text)
    nested = node.child_by_field_name("declarator")
    if nested is not None:
        return _declarator_name(nested)
    identifiers = [child for child in node.walk() if child.type == "identifier"]
    return compact_ws(identifiers[-1].text) if identifiers else ""


def _reverse_reachable(cfg: ControlFlowGraphIR, target: int) -> set[int]:
    pending = [target]
    seen: set[int] = set()
    while pending:
        block_id = pending.pop(0)
        if block_id in seen:
            continue
        seen.add(block_id)
        pending.extend(edge.source for edge in cfg.predecessors(block_id))
    return seen


def _forward_reachable_until_returns(cfg: ControlFlowGraphIR, start: int) -> set[int]:
    pending = [start]
    seen: set[int] = set()
    while pending:
        block_id = pending.pop(0)
        if block_id in seen:
            continue
        seen.add(block_id)
        block = cfg.blocks[block_id]
        if block.kind == "return_statement" or block_id == cfg.exit:
            continue
        pending.extend(edge.target for edge in cfg.successors(block_id))
    return seen


def _block_for_site(cfg: ControlFlowGraphIR, site: SourceSite) -> int | None:
    matches = [
        block
        for block in cfg.blocks.values()
        if block.start_line <= site.line <= block.end_line and block.start_line
    ]
    if not matches:
        return None
    exact = [block for block in matches if compact_ws(site.expression) in compact_ws(block.text)]
    chosen = exact or matches
    return min(chosen, key=lambda block: (block.end_line - block.start_line, block.id)).id


def _block_for_node(cfg: ControlFlowGraphIR, node: FrontendNode) -> BasicBlockIR | None:
    matches = [
        block
        for block in cfg.blocks.values()
        if block.start_byte <= node.start_byte and node.end_byte <= block.end_byte and block.start_byte
    ]
    if matches:
        return min(matches, key=lambda block: (block.end_byte - block.start_byte, block.id))
    return cfg.block_at_line(node.start_line)


def _effect_before_failure(effect: MetadataEffect, point: FailurePoint) -> bool:
    return effect.site.line <= point.call_site.line


def _known_error_path_effect_sites(
    local_effects: tuple[_LocatedEffect, ...],
) -> set[tuple[int, str]]:
    return {
        (item.effect.site.line, compact_ws(item.effect.site.expression))
        for item in local_effects
        if item.effect.delta in _CANCEL_DELTAS or item.effect.delta in _PROTECT_DELTAS
    }


def _looks_like_metadata_helper(name: str) -> bool:
    if looks_like_metadata_reader(name):
        return False
    lowered = name.lower()
    return any(
        token in lowered
        for token in (
            "inode",
            "dquot",
            "quota",
            "qgroup",
            "trans",
            "journal",
            "orphan",
            "block_rsv",
            "reserv",
            "reloc",
            "root",
            "extent",
            "chunk",
            "device",
        )
    )


def _rationale(
    state: ResidualState,
    residuals: tuple[MetadataEffect, ...],
    unknown_causes: list[str],
) -> str:
    if state is ResidualState.UNKNOWN:
        return "; ".join(sorted(set(unknown_causes)))
    if state is ResidualState.EXPOSED:
        return f"{len(residuals)} metadata effect(s) remain after error-path normalization"
    if state is ResidualState.PROTECTED:
        return "all reaching metadata effects are explicitly protected"
    return "all reaching metadata effects are cancelled on the error path"
