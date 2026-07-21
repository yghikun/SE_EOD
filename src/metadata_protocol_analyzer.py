"""CFG-backed Protocol A analysis over the version-neutral frontend IR."""

from __future__ import annotations

import re
import argparse
import json
from collections import deque
from dataclasses import dataclass
from typing import Any, Iterable

from .cfg import build_cfg
from .frontend.model import BasicBlockIR, CFGEdgeIR, FunctionIR, ControlFlowGraphIR
from .metadata_candidate_rules import AnalysisUnknown, MetadataCandidate, generate_candidates
from .metadata_event import MetadataEvent, EventStrength, extract_metadata_events
from .metadata_protocol import (
    CompletionMode,
    EffectStatus,
    LegalExitKind,
    MetadataProtocol,
    ReturnContract,
    ReturnOutcome,
)
from .metadata_tracker import (
    AccountingObligation,
    EffectRecord,
    FailureResolution,
    MetadataOperationInstance,
    WitnessStep,
)
from .frontend.tree_sitter_frontend import TreeSitterFrontend


@dataclass(frozen=True)
class ReturnObservation:
    block_id: int
    text: str
    line: int
    path: tuple[int, ...]


@dataclass(frozen=True)
class ProtocolAnalysisResult:
    protocol_id: str
    operation_id: str
    function: str
    source_file: str
    source_version: str
    events: tuple[dict[str, Any], ...]
    candidates: tuple[MetadataCandidate, ...]
    unknown: tuple[AnalysisUnknown, ...]
    cfg_snapshot: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "operation_id": self.operation_id,
            "function": self.function,
            "source_file": self.source_file,
            "source_version": self.source_version,
            "events": list(self.events),
            "candidates": [item.to_dict() for item in self.candidates],
            "unknown": [item.to_dict() for item in self.unknown],
            "cfg_snapshot": self.cfg_snapshot,
        }


def analyze_function(
    function: FunctionIR,
    protocol: MetadataProtocol,
    *,
    operation_id: str = "",
    source_version: str = "",
    max_paths_per_event: int = 32,
) -> ProtocolAnalysisResult | None:
    operation = next(
        (
            item
            for item in protocol.operations
            if (
                item.operation_id == operation_id
                if operation_id
                else function.name in item.entry_functions
            )
        ),
        None,
    )
    if operation is None:
        return None
    events = extract_metadata_events(
        function,
        protocol,
        operation_id=operation.operation_id,
    )
    cfg = build_cfg(function)
    candidates: list[MetadataCandidate] = []
    unknown: list[AnalysisUnknown] = []
    for event in events:
        if not event.necessary or not event.callee_role_id:
            continue
        if event.strength is not EventStrength.MUST:
            unknown.append(
                AnalysisUnknown(
                    protocol.protocol_id,
                    operation.operation_id,
                    LegalExitKind.SUCCESS,
                    "",
                    tuple(sorted(set(event.uncertainty_causes) | {"event_not_proven_must"})),
                    (),
                )
            )
            continue
        contracts = [
            contract
            for contract in protocol.return_contracts
            if contract.contract_id in event.return_contract_ids
        ]
        if not contracts:
            unknown.append(
                AnalysisUnknown(
                    protocol.protocol_id,
                    operation.operation_id,
                    LegalExitKind.SUCCESS,
                    "",
                    ("callee_role_has_no_return_contract",),
                    (),
                )
            )
            continue
        for contract in contracts:
            if contract.outcome in {
                ReturnOutcome.SUCCESS_CHANGED,
                ReturnOutcome.SUCCESS_NO_CHANGE,
            }:
                observations = _observations_for_contract(
                    function,
                    cfg,
                    event,
                    contract,
                    contracts,
                    events,
                    max_paths=max_paths_per_event,
                )
                for observation in observations:
                    state = MetadataOperationInstance(operation.operation_id, protocol.protocol_id)
                    state.completion_mode = CompletionMode.COMMITTED
                    attempt_id = state.start_attempt(event.callee_role_id, event)
                    state.return_outcome = contract.outcome.value
                    state.return_value = observation.text.strip()
                    state.return_attempt_id = attempt_id
                    state.return_provenance = f"contract:{contract.contract_id}"
                    state.witness.append(
                        WitnessStep(
                            "branch",
                            event.source_location.file,
                            f"contract {contract.contract_id}: {contract.guard}",
                            event.source_location.start_line,
                            event.event_id,
                        )
                    )
                    _apply_path_events(state, protocol, events, observation, cfg)
                    _evaluate_accounting_constraints(state, protocol, operation.operation_id)
                    state.witness.append(
                        WitnessStep(
                            "exit",
                            function.file.as_posix(),
                            observation.text.strip(),
                            observation.line,
                        )
                    )
                    generated, unresolved = generate_candidates(
                        state,
                        protocol,
                        phase="SUCCESS",
                        outcome=contract.outcome,
                        exit_kind=LegalExitKind.SUCCESS,
                    )
                    candidates.extend(generated)
                    unknown.extend(unresolved)
                continue
            if contract.outcome not in {
                ReturnOutcome.FAILURE,
                ReturnOutcome.RETRYABLE_FAILURE,
                ReturnOutcome.EXPECTED_SENTINEL,
            }:
                continue
            if not _supported_guard(contract.guard):
                unknown.append(
                    AnalysisUnknown(
                        protocol.protocol_id,
                        operation.operation_id,
                        LegalExitKind.SUCCESS,
                        "",
                        ("return_guard_unknown", contract.contract_id),
                        (),
                    )
                )
                continue
            observations = _observations_for_contract(
                function,
                cfg,
                event,
                contract,
                contracts,
                events,
                max_paths=max_paths_per_event,
            )
            if not observations:
                unknown.append(
                    AnalysisUnknown(
                        protocol.protocol_id,
                        operation.operation_id,
                        LegalExitKind.SUCCESS,
                        "",
                        ("failure_exit_not_reached_or_guard_unresolved",),
                        (),
                    )
                )
                continue
            for observation in observations:
                state = MetadataOperationInstance(operation.operation_id, protocol.protocol_id)
                state.completion_mode = CompletionMode.COMMITTED
                _apply_path_events(
                    state,
                    protocol,
                    events,
                    observation,
                    cfg,
                    max_start_byte=event.source_location.start_byte,
                )
                attempt_id = state.start_attempt(event.callee_role_id, event)
                state.return_value = observation.text.strip()
                state.return_outcome = contract.outcome.value
                state.return_attempt_id = attempt_id
                state.return_provenance = f"contract:{contract.contract_id}"
                state.witness.append(
                    WitnessStep(
                        "branch",
                        event.source_location.file,
                        f"contract {contract.contract_id}: {contract.guard}",
                        event.source_location.start_line,
                        event.event_id,
                    )
                )
                if contract.outcome is ReturnOutcome.EXPECTED_SENTINEL:
                    state.witness.append(
                        WitnessStep(
                            "handler",
                            event.source_location.file,
                            "allowed sentinel handling; fallback/create remains responsible",
                            event.source_location.start_line,
                            event.event_id,
                        )
                    )
                    continue
                state.record_failure(event, attempt_id, contract.guard, "return_contract")
                _apply_path_events(
                    state,
                    protocol,
                    events,
                    observation,
                    cfg,
                    min_start_byte=event.source_location.start_byte + 1,
                )
                _evaluate_accounting_constraints(state, protocol, operation.operation_id)
                handler = _handler_on_path(protocol, events, observation, cfg)
                if handler is not None:
                    resolution = {
                        "ABORTED": FailureResolution.ABORTED,
                        "RECOVERY_DELEGATED": FailureResolution.RECOVERY_DELEGATED,
                        "DEFERRED": FailureResolution.RECOVERY_DELEGATED,
                    }[handler.completion_mode.value]
                    for failure_id in list(state.failure_tokens):
                        state.resolve_failure(
                            failure_id,
                            resolution,
                            f"{handler.handler_id} owns failure completion",
                            source=function.file.as_posix(),
                            line=observation.line,
                        )
                    state.completion_mode = handler.completion_mode
                    if not any(
                        effect.required
                        and effect.status in {EffectStatus.OPEN, EffectStatus.UNKNOWN}
                        for effect in state.effect_ledger.values()
                    ):
                        continue
                retry = _successful_retry_on_path(events, event, observation, cfg, contracts)
                if retry is not None:
                    retry_attempt = state.start_attempt(event.callee_role_id, retry)
                    state.resolve_prior_attempts(event.callee_role_id, retry_attempt)
                    state.witness.append(
                        WitnessStep(
                            "retry_success",
                            retry.source_location.file,
                            f"{retry.callee} succeeds as {retry_attempt}",
                            retry.source_location.start_line,
                            retry.event_id,
                        )
                    )
                    state.completion_mode = CompletionMode.COMMITTED
                    continue
                if _effect_after_failure_on_path(state, event, events, observation, cfg):
                    state.phase_facts.add("stale_result_provenance")
                    state.return_provenance = "stale_result_provenance"
                    state.witness.append(
                        WitnessStep(
                            "stale_result",
                            event.source_location.file,
                            f"metadata changed after {attempt_id}, but the returned symbol still carries its failure",
                            observation.line,
                            event.event_id,
                        )
                    )
                state.witness.append(
                    WitnessStep("exit", function.file.as_posix(), observation.text.strip(), observation.line)
                )
                if _return_propagates_failure(observation.text, event.result_symbol):
                    for failure_id in list(state.failure_tokens):
                        state.resolve_failure(
                            failure_id,
                            FailureResolution.PROPAGATED,
                            "failure reaches function return",
                            source=function.file.as_posix(),
                            line=observation.line,
                        )
                    if state.return_provenance != "stale_result_provenance":
                        state.return_provenance = "propagated_failure"
                    if state.completion_mode is CompletionMode.COMMITTED:
                        state.completion_mode = CompletionMode.ROLLED_BACK
                    generated, unresolved = generate_candidates(
                        state,
                        protocol,
                        phase="FAILURE",
                        outcome=ReturnOutcome.FAILURE,
                        exit_kind=LegalExitKind.FAILURE,
                    )
                    candidates.extend(generated)
                    unknown.extend(unresolved)
                    continue
                outcome = ReturnOutcome.SUCCESS if _return_is_success(observation.text) else None
                if outcome is None:
                    unknown.append(
                        AnalysisUnknown(
                            protocol.protocol_id,
                            operation.operation_id,
                            LegalExitKind.SUCCESS,
                            "",
                            ("return_outcome_unknown",),
                            tuple(item.to_dict() for item in state.witness),
                        )
                    )
                    continue
                generated, unresolved = generate_candidates(
                    state,
                    protocol,
                    phase="SUCCESS",
                    outcome=outcome,
                    exit_kind=LegalExitKind.SUCCESS,
                )
                candidates.extend(generated)
                unknown.extend(unresolved)
    return ProtocolAnalysisResult(
        protocol.protocol_id,
        operation.operation_id,
        function.name,
        function.file.as_posix(),
        source_version,
        tuple(item.to_dict() for item in events),
        tuple(_dedupe_candidates(candidates)),
        tuple(_dedupe_unknown(unknown)),
        _cfg_snapshot(cfg),
    )


def _evaluate_accounting_constraints(
    state: MetadataOperationInstance,
    protocol: MetadataProtocol,
    operation_id: str,
) -> None:
    records = tuple(state.effect_ledger.values())
    for constraint in protocol.accounting_constraints:
        if constraint.operation_id != operation_id or not constraint.trigger_effect_ids:
            continue
        triggers = [
            item for item in records if item.spec_effect_id in constraint.trigger_effect_ids
        ]
        if not triggers:
            continue
        satisfying = [
            item for item in records if item.spec_effect_id in constraint.satisfying_effect_ids
        ]
        subject = triggers[0].object_ref
        satisfied: bool | None
        observed: str
        if any(item.status is EffectStatus.UNKNOWN for item in (*triggers, *satisfying)):
            satisfied = None
            observed = "unknown"
        elif satisfying:
            satisfied = True
            observed = "reserved"
        else:
            satisfied = False
            observed = "pending_without_reservation"
        state.accounting_obligations[constraint.constraint_id] = AccountingObligation(
            constraint.constraint_id,
            subject,
            constraint.expression,
            observed,
            satisfied,
        )
        state.witness.append(
            WitnessStep(
                "accounting_check",
                triggers[0].object_ref.expression,
                f"{constraint.constraint_id}: {observed}",
            )
        )


def _effect_after_failure_on_path(
    state: MetadataOperationInstance,
    failed_event: MetadataEvent,
    events: tuple[MetadataEvent, ...],
    observation: ReturnObservation,
    cfg: ControlFlowGraphIR,
) -> bool:
    by_id = {item.event_id: item for item in events}
    path_positions = {block_id: index for index, block_id in enumerate(observation.path)}
    for effect in state.effect_ledger.values():
        source = by_id.get(effect.source_event)
        if (
            effect.status is not EffectStatus.OPEN
            or source is None
            or source.source_location.start_byte <= failed_event.source_location.start_byte
        ):
            continue
        effect_block = _block_for_byte(cfg, source.source_location.start_byte)
        if effect_block not in path_positions:
            continue
        suffix = observation.path[path_positions[effect_block] + 1 :]
        if any(
            cfg.blocks[block_id].kind != "return_statement"
            and _block_redefines_symbol(cfg.blocks[block_id], failed_event.result_symbol)
            for block_id in suffix
        ):
            continue
        return True
    return False


def analyze_source_file(
    source_path: str,
    protocol: MetadataProtocol,
    *,
    source_version: str = "",
    function_names: Iterable[str] = (),
) -> tuple[ProtocolAnalysisResult, ...]:
    selected = set(function_names)
    unit = TreeSitterFrontend().parse(source_path)
    results: list[ProtocolAnalysisResult] = []
    for function in unit.functions:
        if selected and function.name not in selected:
            continue
        result = analyze_function(function, protocol, source_version=source_version)
        if result is not None:
            results.append(result)
    return tuple(results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run MOCC-SE metadata protocols")
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--source-version", default="")
    parser.add_argument("--function", action="append", default=[])
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    protocol = MetadataProtocol.read_json(args.protocol)
    results = analyze_source_file(
        args.source,
        protocol,
        source_version=args.source_version,
        function_names=args.function,
    )
    payload = json.dumps([item.to_dict() for item in results], indent=2) + "\n"
    if args.out:
        from pathlib import Path

        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


def _observations_for_contract(
    function: FunctionIR,
    cfg: ControlFlowGraphIR,
    event: MetadataEvent,
    contract: ReturnContract,
    contracts: list[ReturnContract],
    events: tuple[MetadataEvent, ...],
    *,
    max_paths: int,
) -> tuple[ReturnObservation, ...]:
    start = _block_for_byte(cfg, event.source_location.start_byte)
    if start is None:
        return ()
    later_redefinitions = {
        block_id
        for other in events
        if other.callee_role_id == event.callee_role_id
        and other.result_symbol == event.result_symbol
        and other.source_location.start_byte > event.source_location.start_byte
        if (block_id := _block_for_byte(cfg, other.source_location.start_byte)) is not None
    }
    queue: deque[tuple[int, tuple[int, ...], bool, bool]] = deque(
        [(start, (start,), True, False)]
    )
    seen: set[tuple[int, bool, bool]] = set()
    observations: list[ReturnObservation] = []
    while queue and len(observations) < max_paths:
        block_id, path, guarded, used_backedge = queue.popleft()
        key = (block_id, guarded, used_backedge)
        if key in seen:
            continue
        seen.add(key)
        block = cfg.blocks[block_id]
        active_here = guarded and block_id not in later_redefinitions
        if block.kind == "return_statement":
            observations.append(ReturnObservation(block_id, block.text, block.start_line, path))
            continue
        if block_id == cfg.exit:
            observations.append(ReturnObservation(block_id, "<implicit return>", function.end_line, path))
            continue
        for edge in cfg.successors(block_id):
            target = cfg.blocks.get(edge.target)
            if target is None:
                continue
            next_used_backedge = used_backedge or edge.kind == "backedge"
            if used_backedge and edge.kind == "backedge":
                continue
            next_guarded = active_here
            if active_here and block.kind == "condition" and _condition_mentions(block.text, event.result_symbol):
                possible = _branch_possible(
                    contract, contracts, block.text, edge.kind, event.result_symbol
                )
                if not possible:
                    continue
                next_guarded = True
            queue.append(
                (edge.target, path + (edge.target,), next_guarded, next_used_backedge)
            )
    effect_blocks = tuple(
        block_id
        for block_id in (
            _block_for_byte(cfg, item.source_location.start_byte)
            for item in events
            if item.effect_spec_id
            and item.source_location.start_byte <= event.source_location.start_byte
        )
        if block_id is not None
    )
    prefix = _representative_prefix(cfg, cfg.entry, start, effect_blocks)
    if not prefix:
        prefixed = tuple(observations)
    else:
        prefixed = tuple(
        ReturnObservation(
            item.block_id,
            item.text,
            item.line,
            prefix[:-1] + item.path,
        )
        for item in observations
    )
    stale_observations = _stale_effect_observations(
        function,
        cfg,
        event,
        contract,
        contracts,
        events,
        max_paths=max_paths,
    )
    if stale_observations:
        prefixed = tuple(
            item
            for item in prefixed
            if not (_return_is_success(item.text) and _path_uses_backedge(cfg, item.path))
        )
    return _dedupe_observations((*prefixed, *stale_observations))


def _stale_effect_observations(
    function: FunctionIR,
    cfg: ControlFlowGraphIR,
    event: MetadataEvent,
    contract: ReturnContract,
    contracts: list[ReturnContract],
    events: tuple[MetadataEvent, ...],
    *,
    max_paths: int,
) -> tuple[ReturnObservation, ...]:
    if contract.outcome is not ReturnOutcome.FAILURE or not event.result_symbol:
        return ()
    start = _block_for_byte(cfg, event.source_location.start_byte)
    if start is None:
        return ()
    effect_blocks = tuple(
        block_id
        for candidate in events
        if candidate.effect_spec_id
        and candidate.source_location.start_byte > event.source_location.start_byte
        if (block_id := _block_for_byte(cfg, candidate.source_location.start_byte)) is not None
    )
    observations: list[ReturnObservation] = []
    for effect_block in effect_blocks:
        path_to_effect = _path_to_block_after_failure(
            cfg,
            start,
            effect_block,
            event.result_symbol,
            contract,
            contracts,
            max_paths=max_paths,
        )
        if not path_to_effect or not _path_uses_backedge(cfg, path_to_effect):
            continue
        path_to_return = _path_to_return_preserving_symbol(
            cfg,
            effect_block,
            event.result_symbol,
        )
        if not path_to_return:
            continue
        full_path = path_to_effect + path_to_return[1:]
        block = cfg.blocks[full_path[-1]]
        observations.append(
            ReturnObservation(block.id, block.text, block.start_line, full_path)
        )
        if len(observations) >= max_paths:
            break
    return tuple(observations)


def _path_to_block_after_failure(
    cfg: ControlFlowGraphIR,
    source: int,
    target: int,
    symbol: str,
    contract: ReturnContract,
    contracts: list[ReturnContract],
    *,
    max_paths: int,
) -> tuple[int, ...]:
    queue: deque[tuple[int, tuple[int, ...], bool, bool]] = deque(
        [(source, (source,), True, False)]
    )
    seen: set[tuple[int, bool, bool, tuple[int, ...]]] = set()
    while queue and len(seen) < max_paths * 64:
        block_id, path, guarded, used_backedge = queue.popleft()
        if block_id == target:
            return path
        key = (block_id, guarded, used_backedge, path[-6:])
        if key in seen:
            continue
        seen.add(key)
        block = cfg.blocks[block_id]
        active_here = guarded and not used_backedge
        for edge in cfg.successors(block_id):
            if used_backedge and edge.kind == "backedge":
                continue
            if active_here and block.kind == "condition" and _condition_mentions(block.text, symbol):
                if not _branch_possible(contract, contracts, block.text, edge.kind, symbol):
                    continue
            next_used_backedge = used_backedge or edge.kind == "backedge"
            queue.append(
                (
                    edge.target,
                    path + (edge.target,),
                    active_here and not next_used_backedge,
                    next_used_backedge,
                )
            )
    return ()


def _path_to_return_preserving_symbol(
    cfg: ControlFlowGraphIR,
    source: int,
    symbol: str,
) -> tuple[int, ...]:
    queue: deque[tuple[int, ...]] = deque([(source,)])
    seen: set[int] = set()
    while queue:
        path = queue.popleft()
        block = cfg.blocks[path[-1]]
        if block.kind == "return_statement":
            return path if _return_propagates_failure(block.text, symbol) else ()
        if path[-1] in seen:
            continue
        seen.add(path[-1])
        for edge in cfg.successors(path[-1]):
            target = cfg.blocks.get(edge.target)
            if target is None or target.id in path:
                continue
            if target.kind != "return_statement" and _block_redefines_symbol(target, symbol):
                continue
            queue.append(path + (target.id,))
    return ()


def _successful_retry_on_path(
    events: tuple[MetadataEvent, ...],
    failed_event: MetadataEvent,
    observation: ReturnObservation,
    cfg: ControlFlowGraphIR,
    contracts: list[ReturnContract],
) -> MetadataEvent | None:
    if not _return_is_success(observation.text):
        return None
    path_positions = {block_id: index for index, block_id in enumerate(observation.path)}
    for event in events:
        if (
            event.callee_role_id != failed_event.callee_role_id
            or event.source_location.start_byte <= failed_event.source_location.start_byte
        ):
            continue
        block_id = _block_for_byte(cfg, event.source_location.start_byte)
        if block_id not in path_positions:
            continue
        relevant = [
            item
            for item in contracts
            if item.contract_id in event.return_contract_ids
            and item.outcome in {ReturnOutcome.SUCCESS, ReturnOutcome.SUCCESS_CHANGED, ReturnOutcome.SUCCESS_NO_CHANGE}
        ]
        if not relevant:
            # A conventional failure-only contract implies that reaching a zero return
            # after the redefinition took its non-failure branch.
            relevant = [
                ReturnContract("implicit.success", event.operation_id, "ret == 0", ReturnOutcome.SUCCESS)
            ]
        suffix = observation.path[path_positions[block_id] :]
        if any(_path_supports_contract(cfg, suffix, event.result_symbol, item, contracts) for item in relevant):
            return event
    return None


def _path_supports_contract(
    cfg: ControlFlowGraphIR,
    path: tuple[int, ...],
    symbol: str,
    contract: ReturnContract,
    contracts: list[ReturnContract],
) -> bool:
    checked = False
    for source, target in zip(path, path[1:]):
        block = cfg.blocks[source]
        if block.kind != "condition" or not _condition_mentions(block.text, symbol):
            continue
        edge = next((item for item in cfg.successors(source) if item.target == target), None)
        if edge is None:
            continue
        checked = True
        if not _branch_possible(contract, contracts, block.text, edge.kind, symbol):
            return False
    return checked


def _handler_on_path(
    protocol: MetadataProtocol,
    events: tuple[MetadataEvent, ...],
    observation: ReturnObservation,
    cfg: ControlFlowGraphIR,
):
    path = set(observation.path)
    for event in events:
        if not event.handler_spec_id or event.strength is not EventStrength.MUST:
            continue
        block_id = _block_for_byte(cfg, event.source_location.start_byte)
        if block_id not in path:
            continue
        return next(
            (item for item in protocol.handlers if item.handler_id == event.handler_spec_id),
            None,
        )
    return None


def _apply_path_events(
    state: MetadataOperationInstance,
    protocol: MetadataProtocol,
    events: tuple[MetadataEvent, ...],
    observation: ReturnObservation,
    cfg: ControlFlowGraphIR,
    *,
    min_start_byte: int | None = None,
    max_start_byte: int | None = None,
) -> None:
    path = set(observation.path)
    effects = {item.effect_id: item for item in protocol.effects}
    compensations = {item.compensation_id: item for item in protocol.compensations}
    handlers = {item.handler_id: item for item in protocol.handlers}
    for event in events:
        if min_start_byte is not None and event.source_location.start_byte < min_start_byte:
            continue
        if max_start_byte is not None and event.source_location.start_byte >= max_start_byte:
            continue
        block_id = _block_for_byte(cfg, event.source_location.start_byte)
        if block_id not in path:
            continue
        if event.effect_spec_id:
            spec = effects[event.effect_spec_id]
            if not _event_guard_holds_on_path(event, spec.guard, observation.path, cfg, events):
                continue
            instance_id = f"{spec.effect_id}@{event.event_id}"
            status = EffectStatus.OPEN
            if event.strength is not EventStrength.MUST:
                status = EffectStatus.UNKNOWN
                state.uncertainty_causes.update(event.uncertainty_causes)
                state.uncertainty_causes.add("effect_event_not_proven_must")
            state.add_effect(
                EffectRecord(
                    instance_id,
                    spec.kind,
                    event.object_ref,
                    spec.scope,
                    spec.owner,
                    status,
                    event.event_id,
                    spec.required,
                    spec.effect_id,
                )
            )
            state.witness.append(
                WitnessStep("effect_created", event.source_location.file, spec.effect_id, event.source_location.start_line, event.event_id)
            )
        elif event.compensation_spec_id:
            spec = compensations[event.compensation_spec_id]
            if event.strength is not EventStrength.MUST:
                state.uncertainty_causes.update(event.uncertainty_causes)
                state.uncertainty_causes.add("compensation_event_not_proven_must")
                continue
            if state.compensate(spec.target_effect_id, event.object_ref):
                state.witness.append(
                    WitnessStep("effect_compensated", event.source_location.file, spec.target_effect_id, event.source_location.start_line, event.event_id)
                )
        elif event.handler_spec_id:
            spec = handlers[event.handler_spec_id]
            if event.strength is not EventStrength.MUST:
                state.uncertainty_causes.update(event.uncertainty_causes)
                state.uncertainty_causes.add("handler_event_not_proven_must")
                continue
            state.transfer(
                spec.handles_effect_ids,
                event.object_ref,
                spec.completion_mode,
                spec.owner,
                spec.guard,
            )


def _condition_mentions(condition: str, symbol: str) -> bool:
    if not symbol:
        return False
    return re.search(rf"\b{re.escape(symbol)}\b", condition) is not None


def _block_redefines_symbol(block: BasicBlockIR, symbol: str) -> bool:
    if not symbol or block.kind == "return_statement":
        return False
    return (
        re.search(rf"(?<![=!<>])\b{re.escape(symbol)}\s*=(?!=)", block.text)
        is not None
    )


def _path_uses_backedge(cfg: ControlFlowGraphIR, path: tuple[int, ...]) -> bool:
    return any(
        edge.kind == "backedge"
        for source, target in zip(path, path[1:])
        for edge in cfg.successors(source)
        if edge.target == target
    )


def _representative_prefix(
    cfg: ControlFlowGraphIR,
    source: int,
    target: int,
    preferred_targets: Iterable[int] = (),
) -> tuple[int, ...]:
    baseline = _simple_path(cfg, source, target)
    paths = [baseline] if baseline else []
    for preferred in dict.fromkeys(preferred_targets):
        if preferred in {source, target}:
            continue
        left = _simple_path(cfg, source, preferred)
        right = _simple_path(cfg, preferred, target) if left else ()
        if left and right:
            paths.append(left + right[1:])
    if paths:
        preferred_set = set(preferred_targets)
        return max(
            paths,
            key=lambda path: (
                sum(block_id in preferred_set for block_id in path),
                -len(path),
            ),
        )
    return ()


def _simple_path(
    cfg: ControlFlowGraphIR,
    source: int,
    target: int,
    blocked: set[int] | None = None,
) -> tuple[int, ...]:
    queue: deque[tuple[int, ...]] = deque([(source,)])
    blocked = blocked or set()
    seen: set[int] = set()
    while queue:
        path = queue.popleft()
        current = path[-1]
        if current == target:
            return path
        if current in seen:
            continue
        seen.add(current)
        for edge in cfg.successors(current):
            if edge.target not in path and edge.target not in blocked:
                queue.append(path + (edge.target,))
    return ()


def _event_guard_holds_on_path(
    event: MetadataEvent,
    guard: str,
    path: tuple[int, ...],
    cfg: ControlFlowGraphIR,
    events: tuple[MetadataEvent, ...],
) -> bool:
    if guard == "always":
        return True
    block_id = _block_for_byte(cfg, event.source_location.start_byte)
    if block_id not in path or not event.result_symbol:
        return False
    start_index = path.index(block_id)
    later_redefinitions = {
        _block_for_byte(cfg, item.source_location.start_byte)
        for item in events
        if item.result_symbol == event.result_symbol
        and item.source_location.start_byte > event.source_location.start_byte
    }
    contract = ReturnContract(
        "effect.guard", event.operation_id, guard, ReturnOutcome.SUCCESS
    )
    for index in range(start_index, len(path) - 1):
        current = path[index]
        if index > start_index and current in later_redefinitions:
            break
        block = cfg.blocks[current]
        if block.kind != "condition" or not _condition_mentions(block.text, event.result_symbol):
            continue
        target = path[index + 1]
        edge = next((item for item in cfg.successors(current) if item.target == target), None)
        if edge is not None:
            return _branch_possible(contract, [contract], block.text, edge.kind, event.result_symbol)
    return False


def _branch_possible(
    contract: ReturnContract,
    contracts: list[ReturnContract],
    condition: str,
    edge_kind: str,
    symbol: str,
) -> bool:
    if edge_kind not in {"true", "false"}:
        return True
    labels = [
        "negative", "enoent", "enospc", "zero", "positive", "err_ptr", "normal_ptr"
    ]
    return any(
        _contract_applies(contract, contracts, label)
        and _condition_holds(condition, symbol, label) is (edge_kind == "true")
        for label in labels
    )


def _contract_applies(
    contract: ReturnContract, contracts: list[ReturnContract], label: str
) -> bool:
    if not _guard_holds(contract.guard, label):
        return False
    priority = contract.priority if contract.priority is not None else 0
    return not any(
        other.contract_id != contract.contract_id
        and (other.priority if other.priority is not None else 0) > priority
        and _guard_holds(other.guard, label)
        for other in contracts
    )


def _guard_holds(guard: str, label: str) -> bool:
    guard = _strip_parens(guard)
    if "&&" in guard:
        return all(_guard_holds(part, label) for part in guard.split("&&"))
    if re.search(r"IS_ERR(?:_OR_NULL)?\s*\(", guard):
        return label == "err_ptr"
    match = re.search(r"(?:ret|return)\s*(==|!=|<=|>=|<|>)\s*(-?\d+|-?[A-Z][A-Z0-9_]*)", guard, re.IGNORECASE)
    if not match:
        return True
    operator, raw = match.groups()
    expected = _guard_value(raw)
    actual = _label_value(label)
    return _compare(actual, operator, expected)


def _supported_guard(guard: str) -> bool:
    value = _strip_parens(guard)
    if "&&" in value:
        return all(_supported_guard(part) for part in value.split("&&"))
    if re.search(r"IS_ERR(?:_OR_NULL)?\s*\(", value):
        return True
    return re.search(
        r"(?:ret|return)\s*(==|!=|<=|>=|<|>)\s*(-?\d+|-?[A-Z][A-Z0-9_]*)",
        value,
        re.IGNORECASE,
    ) is not None


def _condition_holds(condition: str, symbol: str, label: str) -> bool:
    value = _strip_parens(condition).replace(symbol, "ret")
    if "&&" in value:
        return all(_condition_holds(part, "ret", label) for part in value.split("&&"))
    if re.search(r"IS_ERR(?:_OR_NULL)?\s*\(", value):
        result = label == "err_ptr"
        return not result if "!IS_ERR" in value.replace(" ", "") else result
    match = re.search(r"(?:ret|return)\s*(==|!=|<=|>=|<|>)\s*(-?\d+|-?[A-Z][A-Z0-9_]*)", value, re.IGNORECASE)
    if match:
        operator, raw = match.groups()
        expected = _guard_value(raw)
        actual = _label_value(label)
        return _compare(actual, operator, expected)
    if re.fullmatch(r"!?ret", value.strip()):
        result = label not in {"zero", "normal_ptr"}
        return not result if value.strip().startswith("!") else result
    return True


def _compare(actual: int, operator: str, expected: int) -> bool:
    return {
        "==": actual == expected,
        "!=": actual != expected,
        "<": actual < expected,
        "<=": actual <= expected,
        ">": actual > expected,
        ">=": actual >= expected,
    }[operator]


def _guard_value(raw: str) -> int:
    errno_values = {"-ENOENT": -2, "-EIO": -5, "-ENOMEM": -12, "-ENOSPC": -28}
    return errno_values.get(raw.upper(), -4095) if raw.startswith("-") and not raw[1:].isdigit() else int(raw)


def _label_value(label: str) -> int:
    return {
        "negative": -5,
        "enoent": -2,
        "enospc": -28,
        "zero": 0,
        "positive": 2,
    }.get(label, 0)


def _return_is_success(text: str) -> bool:
    match = re.search(r"\breturn\s+(.+?);?$", text.strip(), re.DOTALL)
    if not match:
        return False
    expression = match.group(1).strip().rstrip(";").strip()
    return expression in {"0", "NULL", "false"}


def _return_propagates_failure(text: str, result_symbol: str) -> bool:
    match = re.search(r"\breturn\s+(.+?);?$", text.strip(), re.DOTALL)
    if not match:
        return False
    expression = match.group(1).strip().rstrip(";").strip()
    if expression in {"0", "NULL", "false"}:
        return False
    if result_symbol and re.search(rf"\b{re.escape(result_symbol)}\b", expression):
        return True
    if expression.startswith("-") or expression.startswith("PTR_ERR"):
        return True
    return "(" in expression or expression.startswith("ERR")


def _block_for_byte(cfg: ControlFlowGraphIR, byte: int) -> int | None:
    matches = [
        block.id
        for block in cfg.blocks.values()
        if block.start_byte <= byte <= max(block.end_byte, block.start_byte)
    ]
    return min(matches, key=lambda item: cfg.blocks[item].end_byte - cfg.blocks[item].start_byte) if matches else None


def _cfg_snapshot(cfg: ControlFlowGraphIR) -> dict[str, Any]:
    return {
        "entry": cfg.entry,
        "exit": cfg.exit,
        "blocks": len(cfg.blocks),
        "edges": len(cfg.edges),
        "unsupported_nodes": list(cfg.unsupported_nodes),
        "unsupported_blocks": {str(key): value for key, value in cfg.unsupported_blocks.items()},
        "complete": not cfg.unsupported_nodes and not cfg.unsupported_blocks,
    }


def _strip_parens(value: str) -> str:
    result = value.strip()
    while result.startswith("(") and result.endswith(")"):
        result = result[1:-1].strip()
    return result


def _dedupe_candidates(items: Iterable[MetadataCandidate]) -> list[MetadataCandidate]:
    result: dict[str, MetadataCandidate] = {}
    for item in items:
        result[item.candidate_id] = item
    return list(result.values())


def _dedupe_observations(items: Iterable[ReturnObservation]) -> tuple[ReturnObservation, ...]:
    result: dict[tuple[int, str, tuple[int, ...]], ReturnObservation] = {}
    for item in items:
        result[(item.block_id, item.text, item.path)] = item
    return tuple(result.values())


def _dedupe_unknown(items: Iterable[AnalysisUnknown]) -> list[AnalysisUnknown]:
    result: dict[tuple[str, str, str, tuple[str, ...]], AnalysisUnknown] = {}
    for item in items:
        result[(item.operation_id, item.exit_id, item.exit_kind.value, item.reasons)] = item
    return list(result.values())


if __name__ == "__main__":
    raise SystemExit(main())
