from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


class ProtocolValidationError(ValueError):
    pass


REQUIRED_KEYS = {
    "schema_version",
    "protocol_id",
    "protocol_version",
    "semantic_intent",
    "roles",
    "epoch_policy",
    "entry_formula",
    "initial_phase",
    "phases",
    "events",
    "transitions",
    "invariants",
    "obligation_templates",
    "allowed_authorities",
    "deadlines",
    "checkpoint_events",
    "terminal_events",
    "acceptance_formula",
    "frame_relations",
    "semantic_footprint",
    "evidence_references",
}

OPTIONAL_KEYS = {
    "deadline_events",
}

FORMULA_OPS = {
    "literal",
    "all",
    "any",
    "not",
    "relation_equals",
    "relation_in",
    "relation_matches_prestate",
    "phase_in",
    "outcome_in",
    "obligation_status",
    "no_due_obligations",
    "no_irreversible_violation",
    "precision_at_least",
    "role_bound",
    "authority_allowed",
}

ACTION_OPS = {
    "set_relation",
    "set_relation_from_event",
    "snapshot_relation_from_event",
    "update_relation_from_event",
    "restore_relation_from_event",
    "copy_prestate",
    "add_delta",
    "set_outcome",
    "set_isolation",
    "set_escape_closure",
    "activate_obligation",
    "activate_obligations_for_deltas",
    "discharge_obligation",
    "delegate_obligation",
    "delegate_relation_from_event",
    "complete_authority",
    "record_irreversible_violation",
    "record_irreversible_if_false",
    "mark_precision",
}

FORBIDDEN_PREDICATE_KEYS = {
    "bug_id",
    "target_function",
    "source_line",
    "patch_id",
}


@dataclass(frozen=True)
class ProtocolSpec:
    raw: Dict[str, Any]
    path: Path
    sha256: str

    def __getattr__(self, name: str) -> Any:
        try:
            return self.raw[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    @property
    def role_map(self) -> Dict[str, Dict[str, Any]]:
        return {role["id"]: role for role in self.roles}

    @property
    def obligation_map(self) -> Dict[str, Dict[str, Any]]:
        return {item["id"]: item for item in self.obligation_templates}


def _duplicates(values: List[str]) -> List[str]:
    seen = set()
    dupes = set()
    for value in values:
        if value in seen:
            dupes.add(value)
        seen.add(value)
    return sorted(dupes)


def _validate_formula(formula: Any, location: str) -> None:
    if not isinstance(formula, dict) or "op" not in formula:
        raise ProtocolValidationError(f"{location}: formula must be an object with op")
    op = formula["op"]
    if op not in FORMULA_OPS:
        raise ProtocolValidationError(f"{location}: unknown formula op {op!r}")
    if any(key in formula for key in FORBIDDEN_PREDICATE_KEYS):
        raise ProtocolValidationError(f"{location}: forbidden bug-specific predicate key")
    if op in {"all", "any"}:
        items = formula.get("items")
        if not isinstance(items, list):
            raise ProtocolValidationError(f"{location}: {op} requires items")
        for index, item in enumerate(items):
            _validate_formula(item, f"{location}.items[{index}]")
    elif op == "not":
        _validate_formula(formula.get("item"), f"{location}.item")


def validate_protocol(raw: Dict[str, Any]) -> None:
    if not isinstance(raw, dict):
        raise ProtocolValidationError("protocol root must be an object")
    missing = REQUIRED_KEYS - set(raw)
    extra = set(raw) - REQUIRED_KEYS - OPTIONAL_KEYS
    if missing:
        raise ProtocolValidationError(f"missing keys: {sorted(missing)}")
    if extra:
        raise ProtocolValidationError(f"unknown keys: {sorted(extra)}")
    if raw["schema_version"] != 1:
        raise ProtocolValidationError("schema_version must be 1")
    phases = raw["phases"]
    events = raw["events"]
    if _duplicates(phases):
        raise ProtocolValidationError(f"duplicate phases: {_duplicates(phases)}")
    if _duplicates(events):
        raise ProtocolValidationError(f"duplicate events: {_duplicates(events)}")
    if raw["initial_phase"] not in phases:
        raise ProtocolValidationError("initial_phase is not declared")
    roles = [role["id"] for role in raw["roles"]]
    if _duplicates(roles):
        raise ProtocolValidationError(f"duplicate roles: {_duplicates(roles)}")
    if not any(role.get("anchor") for role in raw["roles"]):
        raise ProtocolValidationError("at least one anchor role is required")
    _validate_formula(raw["entry_formula"], "entry_formula")
    _validate_formula(raw["acceptance_formula"], "acceptance_formula")
    rule_ids: List[str] = []
    for index, transition in enumerate(raw["transitions"]):
        if transition.get("event") not in events:
            raise ProtocolValidationError(f"transition[{index}] uses undeclared event")
        if any(phase not in phases and phase != "*" for phase in transition.get("from", [])):
            raise ProtocolValidationError(f"transition[{index}] uses undeclared source phase")
        if transition.get("to") not in phases:
            raise ProtocolValidationError(f"transition[{index}] uses undeclared target phase")
        _validate_formula(transition.get("guard", {"op": "literal", "value": True}), f"transition[{index}].guard")
        for action_index, action in enumerate(transition.get("actions", [])):
            if action.get("op") not in ACTION_OPS:
                raise ProtocolValidationError(
                    f"transition[{index}].actions[{action_index}]: unknown action op"
                )
    for index, invariant in enumerate(raw["invariants"]):
        rule_ids.append(invariant["id"])
        if invariant["deadline"] not in raw["deadlines"]:
            raise ProtocolValidationError(f"invariant[{index}] uses undeclared deadline")
        _validate_formula(invariant["formula"], f"invariant[{index}].formula")
    authority_set = set(raw["allowed_authorities"])
    for index, obligation in enumerate(raw["obligation_templates"]):
        rule_ids.append(obligation["id"])
        _validate_formula(obligation["required_formula"], f"obligation[{index}].required_formula")
        if obligation["completion_deadline"] not in raw["deadlines"]:
            raise ProtocolValidationError(f"obligation[{index}] uses undeclared deadline")
        if not set(obligation.get("allowed_authorities", [])).issubset(authority_set):
            raise ProtocolValidationError(f"obligation[{index}] uses undeclared authority")
    if _duplicates(rule_ids):
        raise ProtocolValidationError(f"duplicate rule ids: {_duplicates(rule_ids)}")
    if not set(raw["checkpoint_events"]).issubset(set(events)):
        raise ProtocolValidationError("checkpoint_events must be declared events")
    if not set(raw["terminal_events"]).issubset(set(events)):
        raise ProtocolValidationError("terminal_events must be declared events")
    deadline_events = raw.get("deadline_events", {})
    if not isinstance(deadline_events, dict):
        raise ProtocolValidationError("deadline_events must be an object")
    for event, deadlines in deadline_events.items():
        if event not in events:
            raise ProtocolValidationError(
                f"deadline_events uses undeclared event: {event}"
            )
        if not isinstance(deadlines, list) or not deadlines:
            raise ProtocolValidationError(
                f"deadline_events[{event!r}] must be a non-empty list"
            )
        undeclared = set(deadlines) - set(raw["deadlines"])
        if undeclared:
            raise ProtocolValidationError(
                f"deadline_events[{event!r}] uses undeclared deadlines: "
                f"{sorted(undeclared)}"
            )
        if _duplicates(deadlines):
            raise ProtocolValidationError(
                f"deadline_events[{event!r}] has duplicate deadlines: "
                f"{_duplicates(deadlines)}"
            )


def load_protocol(path: str) -> ProtocolSpec:
    protocol_path = Path(path)
    content = protocol_path.read_bytes()
    raw = json.loads(content.decode("utf-8"))
    validate_protocol(raw)
    return ProtocolSpec(raw=raw, path=protocol_path, sha256=hashlib.sha256(content).hexdigest())
