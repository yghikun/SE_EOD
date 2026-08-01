from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .model import ObligationStatus, Precision, ProtocolState, Truth


@dataclass
class FormulaResult:
    truth: Truth
    precision: Precision
    dependencies: List[str]


def _combine_precision(results: List[FormulaResult]) -> Precision:
    return Precision.minimum([result.precision for result in results])


def _resolve_relation(name: Optional[str], obligation_relation: Optional[str]) -> Optional[str]:
    if name == "$obligation.relation":
        return obligation_relation
    return name


def evaluate_formula(
    formula: Dict[str, Any],
    state: ProtocolState,
    *,
    deadline: Optional[str] = None,
    obligation_relation: Optional[str] = None,
) -> FormulaResult:
    op = formula["op"]
    if op == "literal":
        value = formula.get("value")
        truth = Truth.TRUE if value is True else Truth.FALSE if value is False else Truth.UNKNOWN
        return FormulaResult(truth, Precision.EXACT, [])
    if op in {"all", "any"}:
        results = [
            evaluate_formula(
                item,
                state,
                deadline=deadline,
                obligation_relation=obligation_relation,
            )
            for item in formula.get("items", [])
        ]
        dependencies = sorted({dep for result in results for dep in result.dependencies})
        precision = _combine_precision(results)
        truths = [result.truth for result in results]
        if op == "all":
            truth = Truth.FALSE if Truth.FALSE in truths else Truth.UNKNOWN if Truth.UNKNOWN in truths else Truth.TRUE
        else:
            truth = Truth.TRUE if Truth.TRUE in truths else Truth.UNKNOWN if Truth.UNKNOWN in truths else Truth.FALSE
        return FormulaResult(truth, precision, dependencies)
    if op == "not":
        result = evaluate_formula(
            formula["item"],
            state,
            deadline=deadline,
            obligation_relation=obligation_relation,
        )
        truth = {
            Truth.TRUE: Truth.FALSE,
            Truth.FALSE: Truth.TRUE,
            Truth.UNKNOWN: Truth.UNKNOWN,
        }[result.truth]
        return FormulaResult(truth, result.precision, result.dependencies)
    if op in {"relation_equals", "relation_in", "relation_matches_prestate", "precision_at_least"}:
        name = _resolve_relation(formula.get("name"), obligation_relation)
        if not name:
            return FormulaResult(Truth.UNKNOWN, Precision.UNKNOWN, ["relation:<missing>"])
        fact = state.relation_facts.get(name)
        if fact is None:
            return FormulaResult(Truth.UNKNOWN, Precision.UNKNOWN, [f"relation:{name}"])
        if op == "relation_equals":
            truth = Truth.TRUE if fact.value == formula.get("value") else Truth.FALSE
        elif op == "relation_in":
            truth = Truth.TRUE if fact.value in formula.get("values", []) else Truth.FALSE
        elif op == "relation_matches_prestate":
            pre = state.symbolic_prestate.get(name)
            if pre is None:
                return FormulaResult(Truth.UNKNOWN, Precision.UNKNOWN, [f"prestate:{name}"])
            truth = Truth.TRUE if fact.value == pre.value else Truth.FALSE
            return FormulaResult(
                truth,
                Precision.minimum([fact.precision, pre.precision]),
                [f"relation:{name}", f"prestate:{name}"],
            )
        else:
            minimum = Precision(formula.get("minimum", "JOIN_PRESERVED"))
            truth = Truth.TRUE if fact.precision.rank >= minimum.rank else Truth.FALSE
        return FormulaResult(truth, fact.precision, [f"relation:{name}"])
    if op == "phase_in":
        return FormulaResult(
            Truth.TRUE if state.phase in formula.get("values", []) else Truth.FALSE,
            Precision.EXACT,
            ["phase"],
        )
    if op == "outcome_in":
        if state.outcome.value == "UNKNOWN":
            return FormulaResult(Truth.UNKNOWN, Precision.UNKNOWN, ["outcome"])
        return FormulaResult(
            Truth.TRUE if state.outcome.value in formula.get("values", []) else Truth.FALSE,
            state.precision_provenance.get("outcome", Precision.EXACT),
            ["outcome"],
        )
    if op == "obligation_status":
        template = formula["template"]
        relation = _resolve_relation(formula.get("relation"), obligation_relation)
        statuses = {ObligationStatus(value) for value in formula.get("statuses", [])}
        matches = [
            obligation
            for obligation in state.obligations.values()
            if obligation.template_id == template and (relation is None or obligation.relation == relation)
        ]
        if not matches:
            return FormulaResult(Truth.UNKNOWN, Precision.UNKNOWN, [f"obligation:{template}:{relation or '*'}"])
        truth = Truth.TRUE if all(item.status in statuses for item in matches) else Truth.FALSE
        return FormulaResult(truth, Precision.EXACT, [f"obligation:{template}:{relation or '*'}"])
    if op == "no_due_obligations":
        target = formula.get("deadline") or deadline
        due = [
            obligation
            for obligation in state.obligations.values()
            if obligation.completion_deadline == target and obligation.status != ObligationStatus.DISCHARGED
        ]
        return FormulaResult(
            Truth.FALSE if due else Truth.TRUE,
            Precision.EXACT,
            [f"due:{target}"],
        )
    if op == "no_irreversible_violation":
        return FormulaResult(
            Truth.FALSE if state.irreversible_violation_evidence else Truth.TRUE,
            Precision.EXACT,
            ["irreversible_evidence"],
        )
    if op == "role_bound":
        role = formula["role"]
        return FormulaResult(
            Truth.TRUE if role in state.role_bindings else Truth.FALSE,
            Precision.EXACT,
            [f"role:{role}"],
        )
    if op == "authority_allowed":
        authority = formula["authority"]
        claims = [claim for claim in state.authority_claims if claim.authority == authority]
        if not claims:
            return FormulaResult(Truth.FALSE, Precision.EXACT, [f"authority:{authority}"])
        return FormulaResult(
            Truth.TRUE if all(claim.allowed for claim in claims) else Truth.FALSE,
            Precision.EXACT,
            [f"authority:{authority}"],
        )
    raise ValueError(f"unsupported formula op: {op}")
