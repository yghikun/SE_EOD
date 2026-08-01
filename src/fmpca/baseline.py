from __future__ import annotations

from typing import Dict, Iterable, List

from .model import EvidenceEvent


def api_pairing_baseline(events: Iterable[EvidenceEvent]) -> str:
    """B1: check only explicit AcquireResource/ReleaseResource pairs."""
    balance: Dict[str, int] = {}
    applicable = False
    for event in events:
        if event.event not in {"AcquireResource", "ReleaseResource"}:
            continue
        applicable = True
        resource = str(event.data.get("resource", "unknown"))
        balance[resource] = balance.get(resource, 0) + (
            1 if event.event == "AcquireResource" else -1
        )
    if not applicable:
        return "NO_APPLICABLE_CHECK"
    return "FINDING" if any(value != 0 for value in balance.values()) else "HANDLED"


def local_field_restoration_baseline(events: Iterable[EvidenceEvent]) -> str:
    """B2: consider an error handled once any changed field is restored."""
    updated: List[str] = []
    restored: List[str] = []
    failed = False
    for event in events:
        if event.event == "RelationUpdate":
            updated.append(str(event.data.get("relation")))
        elif event.event == "RestoreRelation":
            restored.append(str(event.data.get("relation")))
        elif event.event == "FailureObserved":
            failed = True
    if not failed or not updated:
        return "NO_APPLICABLE_CHECK"
    return "HANDLED" if set(updated).intersection(restored) else "FINDING"


def single_object_typestate_baseline(events: Iterable[EvidenceEvent]) -> str:
    """B3: track only one object's valid/invalid terminal state."""
    states: Dict[str, bool] = {}
    applicable = False
    for event in events:
        if event.event != "MarkTargetInvalid":
            continue
        applicable = True
        relation = str(event.data.get("relation", "target"))
        states[relation] = bool(event.data.get("value"))
    if not applicable:
        return "NO_APPLICABLE_CHECK"
    return "FINDING" if any(value is False for value in states.values()) else "HANDLED"


def run_baselines(events: Iterable[EvidenceEvent]) -> Dict[str, str]:
    materialized = list(events)
    return {
        "B1_API_PAIRING": api_pairing_baseline(materialized),
        "B2_LOCAL_FIELD_RESTORATION": local_field_restoration_baseline(materialized),
        "B3_SINGLE_OBJECT_TYPESTATE": single_object_typestate_baseline(materialized),
    }
