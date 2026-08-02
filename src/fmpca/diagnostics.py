from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, Tuple

from .dsl import ProtocolSpec, load_protocol


class DiagnosticValidationError(ValueError):
    pass


REQUIRED_KEYS = {
    "schema_version",
    "extension_id",
    "extension_version",
    "protocol_id",
    "base_protocol",
    "evidence_levels",
    "failure_causes",
    "repair_obligations",
    "diagnostic_mappings",
    "applicability_policy",
    "heldout_policy",
}

SAFE_ALTERNATIVE_KINDS = {
    "PROPAGATE_FAILURE",
    "PROVE_ABORT_OR_ROLLBACK",
    "ENTER_FAILSTOP",
    "ENTER_CONTAINMENT",
    "PROVE_SAFE_DELEGATION",
}


@dataclass(frozen=True)
class DiagnosticExtension:
    raw: Dict[str, Any]
    path: Path
    sha256: str
    base_protocol: ProtocolSpec

    @property
    def cause_map(self) -> Dict[str, Dict[str, Any]]:
        return {item["id"]: item for item in self.raw["failure_causes"]}

    @property
    def repair_map(self) -> Dict[str, Dict[str, Any]]:
        return {item["id"]: item for item in self.raw["repair_obligations"]}

    @property
    def evidence_level_map(self) -> Dict[str, Dict[str, Any]]:
        return {item["id"]: item for item in self.raw["evidence_levels"]}


@dataclass(frozen=True)
class DiagnosticFinding:
    rule: str
    cause: str
    stage: str
    unsafe_checkpoint: str
    repair_obligation: str
    forbidden_outcome: str
    safe_alternatives: Tuple[Dict[str, Any], ...]
    evidence_level: str
    supplied_evidence: FrozenSet[str]
    missing_evidence: FrozenSet[str]
    trigger_facts_present: bool

    @property
    def evidence_complete(self) -> bool:
        return not self.missing_evidence

    @property
    def diagnostic_closed(self) -> bool:
        return self.trigger_facts_present and self.evidence_complete

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule": self.rule,
            "cause": self.cause,
            "stage": self.stage,
            "unsafe_checkpoint": self.unsafe_checkpoint,
            "repair_obligation": self.repair_obligation,
            "forbidden_outcome": self.forbidden_outcome,
            "safe_alternatives": list(self.safe_alternatives),
            "evidence_level": self.evidence_level,
            "supplied_evidence": sorted(self.supplied_evidence),
            "missing_evidence": sorted(self.missing_evidence),
            "trigger_facts_present": self.trigger_facts_present,
            "evidence_complete": self.evidence_complete,
            "diagnostic_closed": self.diagnostic_closed,
        }


def _duplicates(values: Tuple[str, ...]) -> Tuple[str, ...]:
    seen = set()
    duplicates = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return tuple(sorted(duplicates))


def _canonical_hash(value: Any) -> str:
    content = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def validate_diagnostic_extension(raw: Dict[str, Any], base: ProtocolSpec) -> None:
    if not isinstance(raw, dict):
        raise DiagnosticValidationError("diagnostic extension root must be an object")
    missing = REQUIRED_KEYS - set(raw)
    extra = set(raw) - REQUIRED_KEYS
    if missing:
        raise DiagnosticValidationError(f"missing keys: {sorted(missing)}")
    if extra:
        raise DiagnosticValidationError(f"unknown keys: {sorted(extra)}")
    if raw["schema_version"] != 1:
        raise DiagnosticValidationError("schema_version must be 1")
    if raw["protocol_id"] != base.protocol_id:
        raise DiagnosticValidationError("diagnostic protocol_id does not match base")
    if raw["base_protocol"]["sha256"] != base.sha256:
        raise DiagnosticValidationError("base protocol hash mismatch")
    if not raw["base_protocol"]["normative_outcomes_preserved"]:
        raise DiagnosticValidationError("normative outcomes must remain preserved")

    base_obligations = base.obligation_map
    for rule, expected in raw["base_protocol"]["obligation_hashes"].items():
        if rule not in base_obligations or _canonical_hash(base_obligations[rule]) != expected:
            raise DiagnosticValidationError(f"base obligation hash mismatch: {rule}")

    evidence_ids = tuple(item["id"] for item in raw["evidence_levels"])
    cause_ids = tuple(item["id"] for item in raw["failure_causes"])
    repair_ids = tuple(item["id"] for item in raw["repair_obligations"])
    for label, values in (
        ("evidence level", evidence_ids),
        ("failure cause", cause_ids),
        ("repair obligation", repair_ids),
    ):
        duplicates = _duplicates(values)
        if duplicates:
            raise DiagnosticValidationError(f"duplicate {label} ids: {duplicates}")

    evidence_set = set(evidence_ids)
    cause_map = {item["id"]: item for item in raw["failure_causes"]}
    repair_map = {item["id"]: item for item in raw["repair_obligations"]}
    if not evidence_set:
        raise DiagnosticValidationError("at least one evidence level is required")
    for cause in cause_map.values():
        if cause["rule"] not in base_obligations:
            raise DiagnosticValidationError(f"unknown cause rule: {cause['rule']}")
        if cause["repair_obligation"] not in repair_map:
            raise DiagnosticValidationError(f"unknown cause repair: {cause['repair_obligation']}")
        if not cause["trigger_facts"]:
            raise DiagnosticValidationError(f"cause has no trigger facts: {cause['id']}")
    for repair in repair_map.values():
        if repair["preserved_violation_rule"] not in base_obligations:
            raise DiagnosticValidationError(
                f"unknown preserved rule: {repair['preserved_violation_rule']}"
            )
        alternatives = repair["safe_alternatives"]
        if len(alternatives) < 3:
            raise DiagnosticValidationError(f"repair needs three alternatives: {repair['id']}")
        alternative_ids = tuple(item["id"] for item in alternatives)
        if _duplicates(alternative_ids):
            raise DiagnosticValidationError(f"duplicate safe alternative: {repair['id']}")
        for alternative in alternatives:
            if alternative["kind"] not in SAFE_ALTERNATIVE_KINDS:
                raise DiagnosticValidationError(
                    f"unknown safe alternative kind: {alternative['kind']}"
                )
            if not alternative["required_facts"]:
                raise DiagnosticValidationError(
                    f"safe alternative lacks required facts: {alternative['id']}"
                )

    seen_mappings = set()
    for mapping in raw["diagnostic_mappings"]:
        key = (mapping["rule"], mapping["cause"])
        if key in seen_mappings:
            raise DiagnosticValidationError(f"duplicate diagnostic mapping: {key}")
        seen_mappings.add(key)
        cause = cause_map.get(mapping["cause"])
        repair = repair_map.get(mapping["repair_obligation"])
        if not cause or not repair:
            raise DiagnosticValidationError(f"unresolved diagnostic mapping: {key}")
        if cause["rule"] != mapping["rule"]:
            raise DiagnosticValidationError(f"cause/rule mismatch: {key}")
        if cause["repair_obligation"] != repair["id"]:
            raise DiagnosticValidationError(f"cause/repair mismatch: {key}")
    if seen_mappings != {(item["rule"], item["id"]) for item in cause_map.values()}:
        raise DiagnosticValidationError("every failure cause requires exactly one mapping")

    applicability = raw["applicability_policy"]
    if not applicability["base_scope_preserved"]:
        raise DiagnosticValidationError("base applicability scope must be preserved")
    if applicability["new_applicability_predicates"]:
        raise DiagnosticValidationError("v0.2 diagnostic extension cannot add applicability predicates")
    heldout = raw["heldout_policy"]
    if heldout["heldout_validation_allowed"] or heldout["common_v0_2_validated"]:
        raise DiagnosticValidationError("held-out claims are not enabled in Phase 14")


def load_diagnostic_extension(path: str) -> DiagnosticExtension:
    extension_path = Path(path)
    content = extension_path.read_bytes()
    raw = json.loads(content.decode("utf-8"))
    base_path = raw.get("base_protocol", {}).get("path")
    if not base_path:
        raise DiagnosticValidationError("base protocol path is required")
    base = load_protocol(base_path)
    validate_diagnostic_extension(raw, base)
    return DiagnosticExtension(
        raw=raw,
        path=extension_path,
        sha256=hashlib.sha256(content).hexdigest(),
        base_protocol=base,
    )


def diagnose_failure(
    extension: DiagnosticExtension,
    *,
    rule: str,
    cause: str,
    evidence_level: str,
    trigger_facts: Tuple[str, ...],
    evidence_facts: Tuple[str, ...],
) -> DiagnosticFinding:
    cause_value = extension.cause_map.get(cause)
    if not cause_value or cause_value["rule"] != rule:
        raise DiagnosticValidationError(f"unmapped rule/cause pair: {rule}/{cause}")
    level = extension.evidence_level_map.get(evidence_level)
    if not level:
        raise DiagnosticValidationError(f"unknown evidence level: {evidence_level}")
    repair = extension.repair_map[cause_value["repair_obligation"]]
    supplied = frozenset(evidence_facts)
    required = frozenset(level["requires"])
    return DiagnosticFinding(
        rule=rule,
        cause=cause,
        stage=cause_value["stage"],
        unsafe_checkpoint=cause_value["unsafe_checkpoint"],
        repair_obligation=repair["id"],
        forbidden_outcome=repair["forbidden_outcome"],
        safe_alternatives=tuple(repair["safe_alternatives"]),
        evidence_level=evidence_level,
        supplied_evidence=supplied,
        missing_evidence=required - supplied,
        trigger_facts_present=set(cause_value["trigger_facts"]).issubset(trigger_facts),
    )
