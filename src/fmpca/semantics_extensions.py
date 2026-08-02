from __future__ import annotations

import copy

from .formulas import evaluate_formula
from .model import EvidenceEvent, ProtocolState, Truth
from .semantics import EVENT_DEADLINES, ProtocolEngine


class ProtocolDeadlineEngine(ProtocolEngine):
    """Protocol engine extension for spec-declared event/deadline mappings.

    The v0.2 semantic kernel remains hash-frozen for historical evaluations.
    New candidate protocols opt into this extension without changing those
    frozen evaluation semantics.
    """

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
            and (
                "*" in transition.get("from", [])
                or next_state.phase in transition.get("from", [])
            )
        ]
        applied = False
        for transition in transitions:
            guard = evaluate_formula(
                transition.get("guard", {"op": "literal", "value": True}),
                next_state,
            )
            if guard.truth == Truth.FALSE:
                continue
            if guard.truth == Truth.UNKNOWN:
                next_state.assumptions.append(f"unknown_guard:{event.event}")
                next_state.precision_provenance[f"guard:{event_index}"] = (
                    guard.precision
                )
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
        protocol_deadlines = self.spec.raw.get("deadline_events", {}).get(
            event.event, ()
        )
        reached_deadlines = dict.fromkeys(
            (*EVENT_DEADLINES.get(event.event, ()), *protocol_deadlines)
        )
        for reached in reached_deadlines:
            next_state.reached_deadlines.add(reached)
            self._settle_due_obligations(next_state, reached, event_index)
            self._evaluate_deadline(next_state, reached, event_index)
        if event.event in self.spec.terminal_events:
            self._evaluate_acceptance(next_state, "AT_SETTLEMENT", event_index)
        return next_state
