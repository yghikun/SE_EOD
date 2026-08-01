from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .model import AnalysisResult, Precision, ProtocolState, Truth


@dataclass
class AnalysisReport:
    result: AnalysisResult
    protocol_id: str
    protocol_version: str
    reasons: List[str]
    violation_rules: List[str]
    unknown_rules: List[str]
    coverage: Dict[str, Any]
    state: ProtocolState

    def to_dict(self) -> Dict[str, Any]:
        return {
            "result": self.result.value,
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "reasons": list(self.reasons),
            "violation_rules": list(self.violation_rules),
            "unknown_rules": list(self.unknown_rules),
            "coverage": dict(self.coverage),
            "state": self.state.to_dict(),
        }


def _latest_checks(state: ProtocolState) -> Dict[str, Any]:
    latest = {}
    for check in state.checks:
        latest[(check.rule_id, check.deadline)] = check
    return latest


def _proof_relevant_checks(state: ProtocolState) -> List[Any]:
    latest = list(_latest_checks(state).values())
    sticky = [
        check
        for check in state.checks
        if check.truth != Truth.TRUE
        and (
            check.deadline == "ALWAYS"
            or check.deadline in state.reached_deadlines
        )
    ]
    result = []
    seen = set()
    for check in sticky + latest:
        key = (
            check.rule_id,
            check.deadline,
            check.truth.value,
            check.event_index,
        )
        if key not in seen:
            seen.add(key)
            result.append(check)
    return result


def analyze_state(
    state: ProtocolState,
    *,
    path_model_closed: bool = True,
    all_paths_closed: bool = False,
    repair_slice_closed: bool = True,
    alias_closed: bool = True,
) -> AnalysisReport:
    coverage = {
        "events": len(state.event_history),
        "handled_events": len(state.event_history) - len(state.unhandled_events),
        "unhandled_events": list(state.unhandled_events),
        "reached_deadlines": sorted(state.reached_deadlines),
        "path_model_closed": path_model_closed,
        "all_paths_closed": all_paths_closed,
        "repair_slice_closed": repair_slice_closed,
        "alias_closed": alias_closed and state.alias_closed,
        "escape_closure": state.escape_closure.value,
        "assumptions": list(state.assumptions),
    }
    if not state.applicable or not state.event_history:
        return AnalysisReport(
            AnalysisResult.NO_APPLICABLE_PROTOCOL,
            state.protocol_id,
            state.protocol_version,
            ["no typed event matched the protocol entry/footprint"],
            [],
            [],
            coverage,
            state,
        )
    latest = _proof_relevant_checks(state)
    false_checks = [check for check in latest if check.truth == Truth.FALSE]
    unknown_checks = [check for check in latest if check.truth == Truth.UNKNOWN]
    exact_false = [
        check
        for check in false_checks
        if check.precision.rank >= Precision.JOIN_PRESERVED.rank
    ]
    violation_rules = sorted({check.rule_id for check in false_checks})
    unknown_rules = sorted({check.rule_id for check in unknown_checks})
    closure = (
        state.path_feasible
        and path_model_closed
        and repair_slice_closed
        and state.repair_closed
        and alias_closed
        and state.alias_closed
    )
    if exact_false and closure:
        return AnalysisReport(
            AnalysisResult.VIOLATION,
            state.protocol_id,
            state.protocol_version,
            ["an exact due clause is false and the witness/repair slice is closed"],
            violation_rules,
            unknown_rules,
            coverage,
            state,
        )
    if false_checks:
        return AnalysisReport(
            AnalysisResult.POSSIBLE_VIOLATION,
            state.protocol_id,
            state.protocol_version,
            ["a due clause is false but precision or proof closure is incomplete"],
            violation_rules,
            unknown_rules,
            coverage,
            state,
        )
    acceptance_checks = [
        check for check in latest if check.rule_id.startswith("ACCEPTANCE@")
    ]
    acceptance_true = bool(acceptance_checks) and all(
        check.truth == Truth.TRUE for check in acceptance_checks
    )
    conformance_closed = (
        acceptance_true
        and all_paths_closed
        and path_model_closed
        and alias_closed
        and state.alias_closed
        and not state.unhandled_events
        and not state.has_low_precision()
        and not unknown_checks
    )
    if conformance_closed:
        return AnalysisReport(
            AnalysisResult.CONFORMANT,
            state.protocol_id,
            state.protocol_version,
            ["all represented relevant paths and due clauses close under the loaded spec"],
            [],
            [],
            coverage,
            state,
        )
    reasons = ["no closed violation exists, but universal conformance is not closed"]
    if unknown_checks:
        reasons.append("one or more clauses are unknown")
    if not all_paths_closed:
        reasons.append("all relevant paths are not closed")
    if state.has_low_precision():
        reasons.append("state depends on widened or unknown facts")
    return AnalysisReport(
        AnalysisResult.INCOMPLETE,
        state.protocol_id,
        state.protocol_version,
        reasons,
        [],
        unknown_rules,
        coverage,
        state,
    )
