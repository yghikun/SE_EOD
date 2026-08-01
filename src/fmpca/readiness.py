from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def evaluate_readiness(path: str) -> Dict[str, Any]:
    manifest_path = Path(path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = set(manifest["required_gates"])
    declared = set(manifest["gates"])
    missing = required - declared
    if missing:
        raise ValueError(f"missing readiness gates: {sorted(missing)}")
    families = [item["family_id"] for item in manifest["operation_families"]]
    if len(families) != len(set(families)):
        raise ValueError("operation families must be unique")
    failed = sorted(name for name in required if not manifest["gates"][name])
    generalization_required = set(manifest.get("generalization_required_gates", []))
    generalization_failed = sorted(
        name
        for name in generalization_required
        if not manifest["gates"].get(name, False)
    )
    derived_eligible = not failed
    if bool(manifest["freeze_eligible"]) != derived_eligible:
        raise ValueError("freeze_eligible disagrees with required gate values")
    return {
        "readiness_id": manifest["readiness_id"],
        "protocol_id": manifest["protocol_id"],
        "freeze_eligible": derived_eligible,
        "failed_required_gates": failed,
        "operation_family_count": len(families),
        "held_out_family_available": bool(manifest["held_out_family_available"]),
        "generalization_eligible": not generalization_failed,
        "failed_generalization_gates": generalization_failed,
    }
