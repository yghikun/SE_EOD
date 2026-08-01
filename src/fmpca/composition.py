from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .dsl import load_protocol
from .model import AnalysisResult, EvidenceEvent, Precision, ProtocolState
from .proof import AnalysisReport, analyze_state
from .report import write_json, write_markdown
from .semantics import ProtocolEngine


@dataclass(frozen=True)
class CompositionSpec:
    raw: Dict[str, Any]
    path: Optional[Path] = None

    def __getattr__(self, name: str) -> Any:
        try:
            return self.raw[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def load_composition_spec(path: str) -> CompositionSpec:
    spec_path = Path(path)
    raw = json.loads(spec_path.read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "composition_id",
        "composition_version",
        "components",
        "shared_identity_roles",
        "clauses",
        "semantic_footprint",
    }
    if set(raw) != required:
        raise ValueError(
            f"invalid composition keys: missing={sorted(required - set(raw))}, "
            f"extra={sorted(set(raw) - required)}"
        )
    if raw["schema_version"] != 1:
        raise ValueError("composition schema_version must be 1")
    if set(raw["clauses"]) != {"eligibility", "contribution", "release"}:
        raise ValueError("composition must declare eligibility, contribution and release clauses")
    return CompositionSpec(raw, spec_path)


def _default_composition_spec() -> CompositionSpec:
    return CompositionSpec(
        {
            "components": {
                "topology_protocol_id": "fmpca.device_topology_rollback",
                "capacity_protocol_id": "fmpca.writable_device_capacity_contribution",
            },
            "shared_identity_roles": ["operation", "device"],
            "clauses": {
                "eligibility": {
                    "id": "DTC-C1",
                    "topology_membership_relation": "topology.device_membership",
                    "member_value": "PRESENT",
                    "capacity_writable_relation": "capacity.writable",
                    "capacity_allocation_relation": "capacity.allocation_eligible",
                    "capacity_eligible_relation": "capacity.eligible",
                },
                "contribution": {
                    "id": "DTC-C2",
                    "capacity_eligible_relation": "capacity.eligible",
                    "capacity_contribution_relation": "capacity.contributing",
                    "present_value": "PRESENT",
                    "absent_value": "ABSENT",
                },
                "release": {
                    "id": "DTC-C3",
                    "deadline": "BEFORE_RELEASE",
                    "topology_membership_relation": "topology.device_membership",
                    "capacity_contribution_relation": "capacity.contributing",
                    "detached_value": "ABSENT",
                },
            },
        }
    )


@dataclass(frozen=True)
class CompositionReport:
    result: AnalysisResult
    rules: List[str]
    reasons: List[str]
    component_results: Dict[str, str]
    shared_identity: Dict[str, Optional[str]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "result": self.result.value,
            "rules": list(self.rules),
            "reasons": list(self.reasons),
            "component_results": dict(self.component_results),
            "shared_identity": dict(self.shared_identity),
        }


def _fact(state: ProtocolState, name: str) -> Tuple[Any, Optional[Precision]]:
    value = state.relation_facts.get(name)
    if value is None:
        return None, None
    return value.value, value.precision


def _is_precise(precision: Optional[Precision]) -> bool:
    return precision is not None and precision.rank >= Precision.JOIN_PRESERVED.rank


def compose_device_topology_capacity(
    topology: AnalysisReport,
    capacity: AnalysisReport,
    spec: Optional[CompositionSpec] = None,
) -> CompositionReport:
    """Close topology and capacity components for one shared operation/device epoch."""
    spec = spec or _default_composition_spec()
    topology_state = topology.state
    capacity_state = capacity.state
    components = spec.components
    if topology_state.protocol_id != components["topology_protocol_id"]:
        raise ValueError("topology component protocol_id does not match composition spec")
    if capacity_state.protocol_id != components["capacity_protocol_id"]:
        raise ValueError("capacity component protocol_id does not match composition spec")
    identity: Dict[str, Optional[str]] = {}
    for role in spec.shared_identity_roles:
        topology_identity = topology_state.role_bindings.get(role)
        capacity_identity = capacity_state.role_bindings.get(role)
        identity[role] = (
            topology_identity
            if topology_identity is not None and topology_identity == capacity_identity
            else None
        )
    component_results = {
        "device_topology_rollback": topology.result.value,
        "writable_device_capacity_contribution": capacity.result.value,
    }
    if any(value is None for value in identity.values()):
        return CompositionReport(
            AnalysisResult.INCOMPLETE,
            ["DTC-ID"],
            ["component instances do not share an exact operation and device identity"],
            component_results,
            identity,
        )

    eligibility_clause = spec.clauses["eligibility"]
    contribution_clause = spec.clauses["contribution"]
    release_clause = spec.clauses["release"]
    member, member_precision = _fact(
        topology_state, eligibility_clause["topology_membership_relation"]
    )
    writable, writable_precision = _fact(
        capacity_state, eligibility_clause["capacity_writable_relation"]
    )
    allocation_eligible, allocation_precision = _fact(
        capacity_state, eligibility_clause["capacity_allocation_relation"]
    )
    eligible, eligible_precision = _fact(
        capacity_state, eligibility_clause["capacity_eligible_relation"]
    )
    contributing, contributing_precision = _fact(
        capacity_state, contribution_clause["capacity_contribution_relation"]
    )
    cross_facts = [
        member_precision,
        writable_precision,
        allocation_precision,
        eligible_precision,
        contributing_precision,
    ]
    rules: List[str] = []
    reasons: List[str] = []
    precise = all(_is_precise(item) for item in cross_facts)
    if precise:
        expected_eligible = (
            member == eligibility_clause["member_value"]
            and writable is True
            and allocation_eligible is True
        )
        if eligible is not expected_eligible:
            rules.append(eligibility_clause["id"])
            reasons.append(
                "capacity eligibility disagrees with topology membership and writable allocation state"
            )
        expected_contribution = (
            contribution_clause["present_value"]
            if eligible is True
            else contribution_clause["absent_value"]
        )
        if contributing != expected_contribution:
            rules.append(contribution_clause["id"])
            reasons.append("capacity contribution disagrees with terminal eligibility")
        release_reached = (
            release_clause["deadline"] in topology_state.reached_deadlines
            or release_clause["deadline"] in capacity_state.reached_deadlines
        )
        if release_reached and (
            member != release_clause["detached_value"]
            or contributing != release_clause["detached_value"]
        ):
            rules.append(release_clause["id"])
            reasons.append(
                "device release occurred before topology membership and capacity contribution were detached"
            )
    else:
        reasons.append("one or more cross-protocol relation facts are missing or imprecise")

    component_violations = [
        name
        for name, report in (("DTR", topology), ("WDC", capacity))
        if report.result == AnalysisResult.VIOLATION
    ]
    if rules or component_violations:
        return CompositionReport(
            AnalysisResult.VIOLATION,
            sorted(set(rules + component_violations)),
            reasons or ["a component protocol has a closed violation"],
            component_results,
            identity,
        )
    if topology.result == AnalysisResult.POSSIBLE_VIOLATION or capacity.result == AnalysisResult.POSSIBLE_VIOLATION:
        return CompositionReport(
            AnalysisResult.POSSIBLE_VIOLATION,
            [],
            reasons + ["a component violation lacks complete proof closure"],
            component_results,
            identity,
        )
    if not precise or topology.result != AnalysisResult.CONFORMANT or capacity.result != AnalysisResult.CONFORMANT:
        return CompositionReport(
            AnalysisResult.INCOMPLETE,
            [],
            reasons + ["universal component or cross-protocol closure is incomplete"],
            component_results,
            identity,
        )
    return CompositionReport(
        AnalysisResult.CONFORMANT,
        [],
        ["both component protocols and all cross-protocol clauses close"],
        component_results,
        identity,
    )


def _run_fixture(protocol_path: str, fixture_path: str) -> AnalysisReport:
    protocol = load_protocol(protocol_path)
    fixture = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    state = ProtocolEngine(protocol).run(
        EvidenceEvent.from_dict(item) for item in fixture["events"]
    )
    closure = fixture.get("closure", {})
    return analyze_state(
        state,
        path_model_closed=closure.get("path_model_closed", True),
        all_paths_closed=closure.get("all_paths_closed", False),
        repair_slice_closed=closure.get("repair_slice_closed", True),
        alias_closed=closure.get("alias_closed", True),
    )


def _verify_freeze(path: str) -> None:
    freeze = json.loads(Path(path).read_text(encoding="utf-8"))
    for artifact, expected in freeze["artifacts"].items():
        actual = hashlib.sha256(Path(artifact).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(
                f"semantic freeze mismatch for {artifact}: {actual} != {expected}"
            )


def run_composition_manifest(path: str) -> Dict[str, Any]:
    manifest_path = Path(path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _verify_freeze(manifest["semantic_freeze"])
    composition_spec = load_composition_spec(manifest["composition_spec"])
    cases: List[Dict[str, Any]] = []
    for case in manifest["cases"]:
        if case["type"] == "capacity":
            report = _run_fixture(case["protocol"], case["events"])
            actual = report.result.value
            details = report.to_dict()
        elif case["type"] == "composition":
            topology = _run_fixture(
                case["topology_protocol"], case["topology_events"]
            )
            capacity = _run_fixture(
                case["capacity_protocol"], case["capacity_events"]
            )
            composed = compose_device_topology_capacity(
                topology, capacity, composition_spec
            )
            actual = composed.result.value
            details = composed.to_dict()
        else:
            raise ValueError(f"unknown v0.4 case type: {case['type']}")
        cases.append(
            {
                "id": case["id"],
                "role": case.get("role", "UNSPECIFIED"),
                "expected": case["expected"],
                "actual": actual,
                "passed": actual == case["expected"],
                "details": details,
            }
        )
    return {
        "schema_version": 1,
        "manifest": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "semantic_freeze": manifest["semantic_freeze"],
        "total": len(cases),
        "passed": sum(item["passed"] for item in cases),
        "failed": sum(not item["passed"] for item in cases),
        "held_out_operation_families": manifest.get(
            "held_out_operation_families", []
        ),
        "cases": cases,
    }


def _markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# FMPCA Device Composition Evaluation",
        "",
        f"Passed: {summary['passed']} / {summary['total']}",
        "",
        "| Case | Role | Expected | Actual | Pass |",
        "|---|---|---|---|---|",
    ]
    for case in summary["cases"]:
        lines.append(
            f"| {case['id']} | {case['role']} | `{case['expected']}` | "
            f"`{case['actual']}` | {'PASS' if case['passed'] else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "No held-out or cross-filesystem generalization claim is made.",
            "",
        ]
    )
    return "\n".join(lines)


def run_and_write(manifest: str, json_out: str, markdown_out: str) -> Dict[str, Any]:
    summary = run_composition_manifest(manifest)
    write_json(json_out, summary)
    write_markdown(markdown_out, _markdown(summary))
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.composition")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    args = parser.parse_args(argv)
    summary = run_and_write(args.manifest, args.json_out, args.markdown_out)
    print(f"{summary['passed']}/{summary['total']} cases passed")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
