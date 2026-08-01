from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class Truth(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


class Precision(str, Enum):
    UNKNOWN = "UNKNOWN"
    WIDENED = "WIDENED"
    JOIN_PRESERVED = "JOIN_PRESERVED"
    EXACT = "EXACT"

    @property
    def rank(self) -> int:
        return {
            Precision.UNKNOWN: 0,
            Precision.WIDENED: 1,
            Precision.JOIN_PRESERVED: 2,
            Precision.EXACT: 3,
        }[self]

    @classmethod
    def minimum(cls, values: List["Precision"]) -> "Precision":
        if not values:
            return cls.EXACT
        return min(values, key=lambda item: item.rank)


class Outcome(str, Enum):
    UNKNOWN = "UNKNOWN"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    RETRY = "RETRY"
    DEFERRED = "DEFERRED"


class ObligationStatus(str, Enum):
    OPEN = "OPEN"
    DELEGATED = "DELEGATED"
    DISCHARGED = "DISCHARGED"


class EscapeClosure(str, Enum):
    CLOSED = "CLOSED"
    ESCAPED = "ESCAPED"
    INCOMPLETE = "INCOMPLETE"


class AnalysisResult(str, Enum):
    VIOLATION = "VIOLATION_UNDER_LOADED_SPEC"
    POSSIBLE_VIOLATION = "POSSIBLE_VIOLATION_REVIEW"
    INCOMPLETE = "INCOMPLETE_UNDER_LOADED_SPEC"
    CONFORMANT = "CONFORMANT_UNDER_LOADED_SPEC"
    NO_APPLICABLE_PROTOCOL = "NO_APPLICABLE_PROTOCOL"


@dataclass
class Fact:
    value: Any
    precision: Precision = Precision.EXACT
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "precision": self.precision.value,
            "sources": list(self.sources),
        }


@dataclass
class Delta:
    relation: str
    before: Any
    after: Any
    precision: Precision = Precision.EXACT
    deadline: str = "AT_SETTLEMENT"
    source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relation": self.relation,
            "before": self.before,
            "after": self.after,
            "precision": self.precision.value,
            "deadline": self.deadline,
            "source": self.source,
        }


@dataclass
class Obligation:
    template_id: str
    required_formula: Dict[str, Any]
    status: ObligationStatus
    activation_horizon: str
    deadline_policy: str
    delegation_deadline: Optional[str]
    completion_deadline: str
    allowed_authorities: List[str]
    relation: Optional[str] = None
    authority: Optional[str] = None
    activation_event: Optional[int] = None
    discharge_event: Optional[int] = None

    @property
    def key(self) -> str:
        return f"{self.template_id}:{self.relation or '*'}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "relation": self.relation,
            "status": self.status.value,
            "activation_horizon": self.activation_horizon,
            "deadline_policy": self.deadline_policy,
            "delegation_deadline": self.delegation_deadline,
            "completion_deadline": self.completion_deadline,
            "allowed_authorities": list(self.allowed_authorities),
            "authority": self.authority,
            "activation_event": self.activation_event,
            "discharge_event": self.discharge_event,
        }


@dataclass
class AuthorityClaim:
    authority: str
    relation: Optional[str]
    allowed: bool
    completed: bool = False
    source_event: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "authority": self.authority,
            "relation": self.relation,
            "allowed": self.allowed,
            "completed": self.completed,
            "source_event": self.source_event,
        }


@dataclass
class EvidenceEvent:
    event: str
    roles: Dict[str, str]
    epoch: Dict[str, Any]
    data: Dict[str, Any] = field(default_factory=dict)
    source: Dict[str, Any] = field(default_factory=dict)
    precision: Precision = Precision.EXACT

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "EvidenceEvent":
        return cls(
            event=value["event"],
            roles=dict(value.get("roles", {})),
            epoch=dict(value.get("epoch", {})),
            data=dict(value.get("data", {})),
            source=dict(value.get("source", {})),
            precision=Precision(value.get("precision", "EXACT")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event,
            "roles": dict(self.roles),
            "epoch": dict(self.epoch),
            "data": dict(self.data),
            "source": dict(self.source),
            "precision": self.precision.value,
        }


@dataclass
class ClauseCheck:
    rule_id: str
    deadline: str
    truth: Truth
    precision: Precision
    dependencies: List[str]
    event_index: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "deadline": self.deadline,
            "truth": self.truth.value,
            "precision": self.precision.value,
            "dependencies": list(self.dependencies),
            "event_index": self.event_index,
        }


@dataclass
class ProtocolState:
    protocol_id: str
    protocol_version: str
    symbolic_prestate: Dict[str, Fact]
    phase: str
    role_bindings: Dict[str, str]
    relation_facts: Dict[str, Fact]
    operation_local_deltas: List[Delta]
    obligations: Dict[str, Obligation]
    authority_claims: List[AuthorityClaim]
    transaction_context: Dict[str, Any]
    isolation_evidence: str
    escape_closure: EscapeClosure
    observability: Set[str]
    outcome: Outcome
    irreversible_violation_evidence: List[Dict[str, Any]]
    precision_provenance: Dict[str, Precision]
    event_history: List[EvidenceEvent]
    checks: List[ClauseCheck]
    reached_deadlines: Set[str]
    unhandled_events: List[str]
    assumptions: List[str]
    applicable: bool = False
    path_feasible: bool = True
    alias_closed: bool = True
    repair_closed: bool = True

    @classmethod
    def initial(
        cls,
        protocol_id: str,
        protocol_version: str,
        phase: str,
        role_bindings: Optional[Dict[str, str]] = None,
    ) -> "ProtocolState":
        return cls(
            protocol_id=protocol_id,
            protocol_version=protocol_version,
            symbolic_prestate={},
            phase=phase,
            role_bindings=dict(role_bindings or {}),
            relation_facts={},
            operation_local_deltas=[],
            obligations={},
            authority_claims=[],
            transaction_context={},
            isolation_evidence="UNKNOWN",
            escape_closure=EscapeClosure.INCOMPLETE,
            observability=set(),
            outcome=Outcome.UNKNOWN,
            irreversible_violation_evidence=[],
            precision_provenance={},
            event_history=[],
            checks=[],
            reached_deadlines=set(),
            unhandled_events=[],
            assumptions=[],
        )

    def fact_precision(self, name: str) -> Precision:
        fact = self.relation_facts.get(name)
        return fact.precision if fact else Precision.UNKNOWN

    def has_low_precision(self) -> bool:
        if any(p.rank < Precision.JOIN_PRESERVED.rank for p in self.precision_provenance.values()):
            return True
        return any(f.precision.rank < Precision.JOIN_PRESERVED.rank for f in self.relation_facts.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "symbolic_prestate": {k: v.to_dict() for k, v in self.symbolic_prestate.items()},
            "phase": self.phase,
            "role_bindings": dict(self.role_bindings),
            "relation_facts": {k: v.to_dict() for k, v in self.relation_facts.items()},
            "operation_local_deltas": [d.to_dict() for d in self.operation_local_deltas],
            "obligations": {k: v.to_dict() for k, v in self.obligations.items()},
            "authority_claims": [c.to_dict() for c in self.authority_claims],
            "transaction_context": dict(self.transaction_context),
            "isolation_evidence": self.isolation_evidence,
            "escape_closure": self.escape_closure.value,
            "observability": sorted(self.observability),
            "outcome": self.outcome.value,
            "irreversible_violation_evidence": list(self.irreversible_violation_evidence),
            "precision_provenance": {k: v.value for k, v in self.precision_provenance.items()},
            "event_history": [e.to_dict() for e in self.event_history],
            "checks": [c.to_dict() for c in self.checks],
            "reached_deadlines": sorted(self.reached_deadlines),
            "unhandled_events": list(self.unhandled_events),
            "assumptions": list(self.assumptions),
            "applicable": self.applicable,
            "path_feasible": self.path_feasible,
            "alias_closed": self.alias_closed,
            "repair_closed": self.repair_closed,
        }


def join_facts(left: Fact, right: Fact) -> Fact:
    sources = sorted(set(left.sources + right.sources))
    if left.value == right.value:
        precision = Precision.minimum([left.precision, right.precision])
        if precision == Precision.EXACT:
            precision = Precision.JOIN_PRESERVED
        return Fact(left.value, precision, sources)
    return Fact("TOP", Precision.WIDENED, sources)


def instance_key_tuple(
    protocol_id: str,
    anchors: Dict[str, str],
    base_epoch: Dict[str, Any],
) -> Tuple[Any, ...]:
    return (
        protocol_id,
        tuple(sorted(anchors.items())),
        tuple(sorted(base_epoch.items())),
    )
