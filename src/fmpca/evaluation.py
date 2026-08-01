from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from .baseline import run_baselines
from .dsl import load_protocol
from .frontend import analyze_source, load_binding
from .model import EvidenceEvent
from .proof import analyze_state
from .report import count_bug_specific_conditions, evaluation_markdown, write_json, write_markdown
from .semantics import ProtocolEngine


def _load_events(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_case(case: Dict[str, Any]) -> Dict[str, Any]:
    spec = load_protocol(case["protocol"])
    engine = ProtocolEngine(spec)
    source_evidence: List[Dict[str, Any]] = []
    if case["type"] == "events":
        fixture = _load_events(case["events"])
        events = [EvidenceEvent.from_dict(item) for item in fixture["events"]]
        closure = fixture.get("closure", {})
        state = engine.run(events)
        report = analyze_state(
            state,
            path_model_closed=closure.get("path_model_closed", True),
            all_paths_closed=closure.get("all_paths_closed", False),
            repair_slice_closed=closure.get("repair_slice_closed", True),
            alias_closed=closure.get("alias_closed", True),
        )
    elif case["type"] == "source":
        binding = load_binding(case["binding"])
        if binding.protocol_id != spec.protocol_id:
            raise ValueError(f"binding/protocol mismatch in {case['id']}")
        analysis = analyze_source(
            binding,
            case["source"],
            case["function"],
            case["source_version"],
        )
        state = engine.run(analysis.events)
        state.assumptions.extend(analysis.assumptions)
        report = analyze_state(
            state,
            path_model_closed=analysis.path_model_closed,
            all_paths_closed=analysis.all_paths_closed,
            repair_slice_closed=analysis.repair_slice_closed,
            alias_closed=True,
        )
        source_evidence = analysis.evidence
    elif case["type"] == "revision_source":
        from .frontend_extensions import (
            analyze_revision_source,
            load_revision_binding,
            require_protocol_scope,
        )

        binding = load_revision_binding(case["binding"])
        if binding.protocol_id != spec.protocol_id:
            raise ValueError(f"binding/protocol mismatch in {case['id']}")
        require_protocol_scope(binding, spec)
        analysis = analyze_revision_source(
            binding,
            case["repo"],
            case["revision"],
            case["source_path"],
            case["function"],
            case["source_version"],
        )
        state = engine.run(analysis.events)
        state.assumptions.extend(analysis.assumptions)
        report = analyze_state(
            state,
            path_model_closed=analysis.path_model_closed,
            all_paths_closed=analysis.all_paths_closed,
            repair_slice_closed=analysis.repair_slice_closed,
            alias_closed=True,
        )
        source_evidence = analysis.evidence
    else:
        raise ValueError(f"unknown case type: {case['type']}")
    actual = report.result.value
    return {
        "id": case["id"],
        "role": case.get("role", "UNSPECIFIED"),
        "expected": case["expected"],
        "actual": actual,
        "passed": actual == case["expected"],
        "protocol_sha256": spec.sha256,
        "baselines": run_baselines(events if case["type"] == "events" else analysis.events),
        "source_evidence": source_evidence,
        "report": report.to_dict(),
    }


def run_manifest(path: str) -> Dict[str, Any]:
    manifest_path = Path(path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    freeze_path = Path(manifest["semantic_freeze"])
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    for artifact, expected_hash in freeze["artifacts"].items():
        actual_hash = hashlib.sha256(Path(artifact).read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(
                f"semantic freeze mismatch for {artifact}: {actual_hash} != {expected_hash}"
            )
    for artifact in freeze.get("git_artifacts", []):
        revision = subprocess.run(
            ["git", "-C", artifact["repo"], "rev-parse", artifact["revision"]],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        if revision != artifact["revision"]:
            raise ValueError(
                f"git revision mismatch for {artifact['repo']}: {revision} != {artifact['revision']}"
            )
        object_id = subprocess.run(
            [
                "git",
                "-C",
                artifact["repo"],
                "rev-parse",
                f"{artifact['revision']}:{artifact['path']}",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        if object_id != artifact["object_id"]:
            raise ValueError(
                f"git object mismatch for {artifact['path']}: {object_id} != {artifact['object_id']}"
            )
    cases = [run_case(case) for case in manifest["cases"]]
    catalog = Path(manifest["catalog"])
    catalog_hash = hashlib.sha256(catalog.read_bytes()).hexdigest()
    config_values = []
    for protocol_path in sorted({case["protocol"] for case in manifest["cases"]}):
        config_values.append(json.loads(Path(protocol_path).read_text(encoding="utf-8")))
    for binding_path in sorted({case.get("binding") for case in manifest["cases"] if case.get("binding")}):
        config_values.append(json.loads(Path(binding_path).read_text(encoding="utf-8")))
    return {
        "schema_version": 1,
        "manifest": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "semantic_freeze": str(freeze_path),
        "semantic_freeze_sha256": hashlib.sha256(freeze_path.read_bytes()).hexdigest(),
        "catalog_sha256": catalog_hash,
        "total": len(cases),
        "passed": sum(1 for case in cases if case["passed"]),
        "failed": sum(1 for case in cases if not case["passed"]),
        "bug_specific_condition_count": count_bug_specific_conditions(config_values),
        "git_artifact_count": len(freeze.get("git_artifacts", [])),
        "held_out_operation_families": list(
            manifest.get("held_out_operation_families", [])
        ),
        "screening_rejections": list(manifest.get("screening_rejections", [])),
        "held_out_checker_modifications": 0,
        "cases": cases,
    }


def run_and_write(manifest: str, json_out: str, markdown_out: str) -> Dict[str, Any]:
    summary = run_manifest(manifest)
    write_json(json_out, summary)
    write_markdown(markdown_out, evaluation_markdown(summary))
    return summary
