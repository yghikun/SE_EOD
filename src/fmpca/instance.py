from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .dsl import ProtocolSpec
from .model import EvidenceEvent, ProtocolState, instance_key_tuple
from .semantics import ProtocolEngine


class AliasDecision(str, Enum):
    MUST_ALIAS = "MUST_ALIAS"
    MAY_ALIAS = "MAY_ALIAS"
    NO_ALIAS = "NO_ALIAS"
    UNKNOWN_ALIAS = "UNKNOWN_ALIAS"


@dataclass
class ProtocolInstance:
    semantic_key: Tuple[Any, ...]
    generation: int
    state: ProtocolState

    @property
    def instance_id(self) -> Tuple[Any, ...]:
        return self.semantic_key + (self.generation,)


@dataclass
class CandidateInstanceSet:
    candidates: List[ProtocolInstance]
    overflowed: bool = False


@dataclass
class InstanceStore:
    spec: ProtocolSpec
    candidate_budget: int = 8
    instances: Dict[Tuple[Any, ...], List[ProtocolInstance]] = field(default_factory=dict)

    def _anchors(self, event: EvidenceEvent) -> Optional[Dict[str, str]]:
        anchors = {}
        for role in self.spec.roles:
            if not role.get("anchor"):
                continue
            identity = event.roles.get(role["id"])
            if identity is None:
                return None
            anchors[role["id"]] = identity
        return anchors

    def _epoch(self, event: EvidenceEvent) -> Dict[str, Any]:
        return {
            name: event.epoch.get(name)
            for name in self.spec.epoch_policy.get("include", [])
        }

    def select_or_create(self, event: EvidenceEvent) -> CandidateInstanceSet:
        anchors = self._anchors(event)
        if anchors is None:
            return CandidateInstanceSet([], overflowed=True)
        key = instance_key_tuple(self.spec.protocol_id, anchors, self._epoch(event))
        live = self.instances.get(key, [])
        if live:
            return CandidateInstanceSet(list(live))
        engine = ProtocolEngine(self.spec)
        state = engine.initial_state(anchors)
        instance = ProtocolInstance(key, 0, state)
        self.instances[key] = [instance]
        return CandidateInstanceSet([instance])

    def settle(self, instance: ProtocolInstance) -> None:
        if instance.state.phase not in {"SETTLED", "RESTORED"}:
            return
        siblings = self.instances.get(instance.semantic_key, [])
        generation = max((item.generation for item in siblings), default=-1) + 1
        engine = ProtocolEngine(self.spec)
        siblings.append(ProtocolInstance(instance.semantic_key, generation, engine.initial_state()))

    def resolve_alias(
        self,
        left: Optional[str],
        right: Optional[str],
    ) -> AliasDecision:
        if left is None or right is None:
            return AliasDecision.UNKNOWN_ALIAS
        if left == right:
            return AliasDecision.MUST_ALIAS
        return AliasDecision.NO_ALIAS
