from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, List, Optional

from .dsl import ProtocolSpec
from .formulas import FormulaResult, evaluate_formula
from .model import (
    AuthorityClaim,
    ClauseCheck,
    Delta,
    EscapeClosure,
    EvidenceEvent,
    Fact,
    Obligation,
    ObligationStatus,
    Outcome,
    Precision,
    ProtocolState,
    Truth,
)


EVENT_DEADLINES = {
    "LiveExposure": ("BEFORE_EXPOSURE",),
    "ReleaseDevice": ("BEFORE_RELEASE",),
    "TransactionCommit": ("BEFORE_COMMIT",),
    "OperationReturn": ("AT_SETTLEMENT",),
    "ProtocolComplete": ("AT_SETTLEMENT",),
    "OwnerTermination": ("BEFORE_OWNER_TERMINATION", "AT_SETTLEMENT"),
}


class ProtocolEngine:
    def __init__(self, spec: ProtocolSpec):
        self.spec = spec

    def initial_state(self, role_bindings: Optional[Dict[str, str]] = None) -> ProtocolState:
        return ProtocolState.initial(
            self.spec.protocol_id,
            self.spec.protocol_version,
            self.spec.initial_phase,
            role_bindings,
        )

    def run(
        self,
        events: Iterable[EvidenceEvent],
        *,
        state: Optional[ProtocolState] = None,
    ) -> ProtocolState:
        current = state or self.initial_state()
        for event in events:
            current = self.apply_event(current, event)
        return current

    def apply_event(self, state: ProtocolState, event: EvidenceEvent) -> ProtocolState:
        next_state = copy.deepcopy(state)
        self._merge_roles(next_state, event)
        if not next_state.event_history:
            entry = evaluate_formula(self.spec.entry_formula, next_state)
            if entry.truth == Truth.TRUE:
                next_state.applicable = True
            elif entry.truth == Truth.UNKNOWN:
                next_state.applicable = True
                next_state.assumptions.append("entry_formula_unknown")
                next_state.precision_provenance["entry_formula"] = entry.precision
        event_index = len(next_state.event_history)
        next_state.event_history.append(event)
        transitions = [
            transition
            for transition in self.spec.transitions
            if transition["event"] == event.event
            and ("*" in transition.get("from", []) or next_state.phase in transition.get("from", []))
        ]
        applied = False
        for transition in transitions:
            guard = evaluate_formula(transition.get("guard", {"op": "literal", "value": True}), next_state)
            if guard.truth == Truth.FALSE:
                continue
            if guard.truth == Truth.UNKNOWN:
                next_state.assumptions.append(f"unknown_guard:{event.event}")
                next_state.precision_provenance[f"guard:{event_index}"] = guard.precision
            for action in transition.get("actions", []):
                self._apply_action(next_state, event, event_index, action)
            next_state.phase = transition["to"]
            applied = True
            break
        if not applied and event.event not in self.spec.events:
            next_state.unhandled_events.append(event.event)
        if event.event in self.spec.events:
            next_state.applicable = True
        self._evaluate_deadline(next_state, "ALWAYS", event_index)
        for reached in EVENT_DEADLINES.get(event.event, ()):
            next_state.reached_deadlines.add(reached)
            self._settle_due_obligations(next_state, reached, event_index)
            self._evaluate_deadline(next_state, reached, event_index)
        if event.event in self.spec.terminal_events:
            self._evaluate_acceptance(next_state, "AT_SETTLEMENT", event_index)
        return next_state

    def _merge_roles(self, state: ProtocolState, event: EvidenceEvent) -> None:
        for role, identity in event.roles.items():
            prior = state.role_bindings.get(role)
            if prior is not None and prior != identity:
                state.alias_closed = False
                state.assumptions.append(f"role_identity_conflict:{role}:{prior}:{identity}")
            else:
                state.role_bindings[role] = identity

    @staticmethod
    def _source(event: EvidenceEvent) -> str:
        file_name = event.source.get("file", "<events>")
        line = event.source.get("line", "?")
        return f"{file_name}:{line}:{event.event}"

    @staticmethod
    def _event_value(value: Any, event: EvidenceEvent) -> Any:
        if isinstance(value, dict) and "from_event" in value:
            return event.data.get(value["from_event"])
        return value

    def _apply_action(
        self,
        state: ProtocolState,
        event: EvidenceEvent,
        event_index: int,
        action: Dict[str, Any],
    ) -> None:
        op = action["op"]
        source = self._source(event)
        if op == "set_relation":
            name = action["name"]
            value = self._event_value(action.get("value"), event)
            precision = Precision(action.get("precision", event.precision.value))
            state.relation_facts[name] = Fact(value, precision, [source])
            state.precision_provenance[name] = precision
        elif op == "set_relation_from_event":
            name = event.data[action.get("name_key", "relation")]
            value = event.data[action.get("value_key", "value")]
            state.relation_facts[name] = Fact(value, event.precision, [source])
            state.precision_provenance[name] = event.precision
        elif op == "snapshot_relation_from_event":
            name = event.data[action.get("name_key", "relation")]
            value = event.data[action.get("value_key", "value")]
            fact = Fact(value, event.precision, [source])
            state.symbolic_prestate[name] = fact
            state.relation_facts[name] = copy.deepcopy(fact)
        elif op == "update_relation_from_event":
            name = event.data[action.get("name_key", "relation")]
            value = event.data[action.get("value_key", "value")]
            before_fact = state.relation_facts.get(name) or state.symbolic_prestate.get(name)
            before = before_fact.value if before_fact else event.data.get("before", "UNKNOWN")
            state.relation_facts[name] = Fact(value, event.precision, [source])
            state.precision_provenance[name] = event.precision
            state.operation_local_deltas.append(
                Delta(
                    relation=name,
                    before=before,
                    after=value,
                    precision=event.precision,
                    deadline=event.data.get("deadline", "AT_SETTLEMENT"),
                    source=source,
                )
            )
        elif op == "restore_relation_from_event":
            name = event.data[action.get("name_key", "relation")]
            pre = state.symbolic_prestate.get(name)
            if pre is None:
                state.precision_provenance[name] = Precision.UNKNOWN
                state.assumptions.append(f"missing_prestate:{name}")
            else:
                state.relation_facts[name] = Fact(pre.value, event.precision, [source])
                self._discharge(state, action.get("template"), name, event_index)
        elif op == "copy_prestate":
            name = action["name"]
            fact = state.relation_facts.get(name)
            if fact:
                state.symbolic_prestate[name] = copy.deepcopy(fact)
        elif op == "add_delta":
            name = action["relation"]
            state.operation_local_deltas.append(
                Delta(
                    name,
                    self._event_value(action.get("before"), event),
                    self._event_value(action.get("after"), event),
                    event.precision,
                    action.get("deadline", "AT_SETTLEMENT"),
                    source,
                )
            )
        elif op == "set_outcome":
            state.outcome = Outcome(self._event_value(action["value"], event))
            state.precision_provenance["outcome"] = event.precision
        elif op == "set_isolation":
            state.isolation_evidence = str(self._event_value(action["value"], event))
        elif op == "set_escape_closure":
            state.escape_closure = EscapeClosure(self._event_value(action["value"], event))
        elif op == "activate_obligation":
            relation = action.get("relation")
            if relation == "$event.relation":
                relation = event.data.get("relation")
            completion_deadline = (
                event.data.get("deadline") if action.get("deadline_from_event") else None
            )
            self._activate(
                state,
                action["template"],
                relation,
                event_index,
                completion_deadline=completion_deadline,
            )
        elif op == "activate_obligations_for_deltas":
            template = action["template"]
            seen = set()
            for delta in state.operation_local_deltas:
                if delta.before == delta.after or delta.relation in seen:
                    continue
                seen.add(delta.relation)
                self._activate(
                    state,
                    template,
                    delta.relation,
                    event_index,
                    completion_deadline=delta.deadline,
                )
        elif op == "discharge_obligation":
            relation = action.get("relation")
            if relation == "$event.relation":
                relation = event.data.get("relation")
            self._discharge(state, action["template"], relation, event_index)
        elif op == "delegate_obligation":
            relation = action.get("relation")
            if relation == "$event.relation":
                relation = event.data.get("relation")
            authority = self._event_value(action["authority"], event)
            self._delegate(state, action["template"], relation, authority, event_index)
        elif op == "delegate_relation_from_event":
            self._delegate(
                state,
                action["template"],
                event.data.get("relation"),
                event.data.get("authority"),
                event_index,
            )
        elif op == "complete_authority":
            authority = self._event_value(action["authority"], event)
            relation = event.data.get("relation") if action.get("relation") == "$event.relation" else action.get("relation")
            for claim in state.authority_claims:
                if claim.authority == authority and (relation is None or claim.relation == relation):
                    claim.completed = True
            for obligation in state.obligations.values():
                if obligation.authority == authority and (relation is None or obligation.relation == relation):
                    obligation.status = ObligationStatus.DISCHARGED
                    obligation.discharge_event = event_index
        elif op == "record_irreversible_violation":
            state.irreversible_violation_evidence.append(
                {
                    "code": action["code"],
                    "relation": self._event_value(action.get("relation"), event),
                    "event_index": event_index,
                    "source": source,
                }
            )
        elif op == "record_irreversible_if_false":
            name = self._event_value(action["relation"], event)
            fact = state.relation_facts.get(name)
            if fact is not None and fact.value is False:
                state.irreversible_violation_evidence.append(
                    {
                        "code": action["code"],
                        "relation": name,
                        "event_index": event_index,
                        "source": source,
                    }
                )
        elif op == "mark_precision":
            name = action["relation"]
            precision = Precision(action["precision"])
            state.precision_provenance[name] = precision
            if name in state.relation_facts:
                state.relation_facts[name].precision = precision
        else:
            raise ValueError(f"unsupported action op: {op}")

    def _activate(
        self,
        state: ProtocolState,
        template_id: str,
        relation: Optional[str],
        event_index: int,
        *,
        completion_deadline: Optional[str] = None,
    ) -> None:
        template = self.spec.obligation_map[template_id]
        obligation = Obligation(
            template_id=template_id,
            required_formula=copy.deepcopy(template["required_formula"]),
            status=ObligationStatus.OPEN,
            activation_horizon=template["activation_horizon"],
            deadline_policy=template["deadline_policy"],
            delegation_deadline=template.get("delegation_deadline"),
            completion_deadline=completion_deadline or template["completion_deadline"],
            allowed_authorities=list(template.get("allowed_authorities", [])),
            relation=relation,
            activation_event=event_index,
        )
        prior = state.obligations.get(obligation.key)
        if prior is None or prior.status == ObligationStatus.DISCHARGED:
            state.obligations[obligation.key] = obligation

    @staticmethod
    def _discharge(
        state: ProtocolState,
        template_id: Optional[str],
        relation: Optional[str],
        event_index: int,
    ) -> None:
        for obligation in state.obligations.values():
            if template_id and obligation.template_id != template_id:
                continue
            if relation is not None and obligation.relation != relation:
                continue
            obligation.status = ObligationStatus.DISCHARGED
            obligation.discharge_event = event_index

    def _delegate(
        self,
        state: ProtocolState,
        template_id: str,
        relation: Optional[str],
        authority: Optional[str],
        event_index: int,
    ) -> None:
        if authority is None:
            state.assumptions.append("delegation_without_authority")
            return
        key = f"{template_id}:{relation or '*'}"
        obligation = state.obligations.get(key)
        if obligation is None:
            state.assumptions.append(f"delegation_without_obligation:{key}")
            return
        allowed = authority in obligation.allowed_authorities and authority in self.spec.allowed_authorities
        state.authority_claims.append(AuthorityClaim(authority, relation, allowed, False, event_index))
        obligation.status = ObligationStatus.DELEGATED
        obligation.authority = authority

    def _settle_due_obligations(self, state: ProtocolState, deadline: str, event_index: int) -> None:
        for obligation in state.obligations.values():
            if obligation.completion_deadline != deadline or obligation.status == ObligationStatus.DISCHARGED:
                continue
            result = evaluate_formula(
                obligation.required_formula,
                state,
                deadline=deadline,
                obligation_relation=obligation.relation,
            )
            if result.truth == Truth.TRUE:
                obligation.status = ObligationStatus.DISCHARGED
                obligation.discharge_event = event_index
            state.checks.append(
                ClauseCheck(
                    obligation.template_id,
                    deadline,
                    result.truth,
                    result.precision,
                    result.dependencies,
                    event_index,
                )
            )

    def _evaluate_deadline(self, state: ProtocolState, deadline: str, event_index: int) -> None:
        for invariant in self.spec.invariants:
            if invariant["deadline"] != deadline:
                continue
            result = evaluate_formula(invariant["formula"], state, deadline=deadline)
            state.checks.append(
                ClauseCheck(
                    invariant["id"],
                    deadline,
                    result.truth,
                    result.precision,
                    result.dependencies,
                    event_index,
                )
            )

    def _evaluate_acceptance(self, state: ProtocolState, deadline: str, event_index: int) -> None:
        formula = evaluate_formula(self.spec.acceptance_formula, state, deadline=deadline)
        due_open = [
            item
            for item in state.obligations.values()
            if item.completion_deadline == deadline and item.status != ObligationStatus.DISCHARGED
        ]
        invalid_delegation = any(
            item.status == ObligationStatus.DELEGATED
            and not any(
                claim.authority == item.authority
                and claim.relation == item.relation
                and claim.allowed
                for claim in state.authority_claims
            )
            for item in due_open
        )
        truth = formula.truth
        dependencies = list(formula.dependencies)
        precision = formula.precision
        if due_open or invalid_delegation or state.irreversible_violation_evidence:
            truth = Truth.FALSE
            dependencies.extend([f"open:{item.key}" for item in due_open])
            if state.irreversible_violation_evidence:
                dependencies.append("irreversible_evidence")
        always_false = any(
            check.deadline == "ALWAYS" and check.truth == Truth.FALSE for check in state.checks
        )
        if always_false:
            truth = Truth.FALSE
            dependencies.append("always_invariant")
        state.checks.append(
            ClauseCheck(
                f"ACCEPTANCE@{deadline}",
                deadline,
                truth,
                precision,
                sorted(set(dependencies)),
                event_index,
            )
        )
