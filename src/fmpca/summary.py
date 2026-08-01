from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .formulas import evaluate_formula
from .model import EvidenceEvent, Precision, ProtocolState, Truth, join_facts
from .semantics import ProtocolEngine


@dataclass
class SummaryRow:
    guard: Dict[str, Any]
    outcome: str
    events: List[EvidenceEvent]
    footprint: List[str]
    precision: Precision = Precision.EXACT


@dataclass
class GuardedSummary:
    name: str
    rows: List[SummaryRow] = field(default_factory=list)


def apply_summary(
    engine: ProtocolEngine,
    state: ProtocolState,
    summary: GuardedSummary,
) -> List[ProtocolState]:
    outputs: List[ProtocolState] = []
    for row in summary.rows:
        guard = evaluate_formula(row.guard, state)
        if guard.truth == Truth.FALSE:
            continue
        projected = copy.deepcopy(state)
        if guard.truth == Truth.UNKNOWN or row.precision.rank < Precision.JOIN_PRESERVED.rank:
            projected.assumptions.append(f"summary_uncertain:{summary.name}")
            for relation in row.footprint:
                projected.precision_provenance[relation] = row.precision
                if relation in projected.relation_facts:
                    projected.relation_facts[relation].precision = row.precision
        outputs.append(engine.run(row.events, state=projected))
    return outputs


def join_states(left: ProtocolState, right: ProtocolState) -> ProtocolState:
    result = copy.deepcopy(left)
    for name, fact in right.relation_facts.items():
        if name in result.relation_facts:
            result.relation_facts[name] = join_facts(result.relation_facts[name], fact)
        else:
            result.relation_facts[name] = copy.deepcopy(fact)
    result.irreversible_violation_evidence.extend(
        item for item in right.irreversible_violation_evidence
        if item not in result.irreversible_violation_evidence
    )
    for key, obligation in right.obligations.items():
        if key not in result.obligations:
            result.obligations[key] = copy.deepcopy(obligation)
        elif result.obligations[key].status.value != obligation.status.value:
            result.obligations[key].status = min(
                [result.obligations[key].status, obligation.status],
                key=lambda status: {"OPEN": 0, "DELEGATED": 1, "DISCHARGED": 2}[status.value],
            )
    result.alias_closed = left.alias_closed and right.alias_closed
    result.repair_closed = left.repair_closed and right.repair_closed
    return result
