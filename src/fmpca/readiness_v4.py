from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def _failed(required: List[str], gates: Dict[str, bool]) -> List[str]:
    missing = set(required) - set(gates)
    if missing:
        raise ValueError(f"missing readiness gates: {sorted(missing)}")
    return sorted(name for name in required if not gates[name])


def evaluate_v4_readiness(path: str) -> Dict[str, Any]:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    gates = manifest["gates"]
    freeze_failed = _failed(manifest["freeze_required_gates"], gates)
    cross_family_failed = _failed(
        manifest["cross_family_required_gates"], gates
    )
    held_out_failed = _failed(manifest["held_out_required_gates"], gates)
    derived = {
        "freeze_eligible": not freeze_failed,
        "cross_operation_family_validated": not cross_family_failed,
        "held_out_generalization_eligible": not held_out_failed,
    }
    for name, value in derived.items():
        if bool(manifest[name]) != value:
            raise ValueError(f"{name} disagrees with required gate values")
    families = [item["family_id"] for item in manifest["operation_families"]]
    if len(families) != len(set(families)):
        raise ValueError("operation families must be unique")
    return {
        "readiness_id": manifest["readiness_id"],
        **derived,
        "failed_freeze_gates": freeze_failed,
        "failed_cross_family_gates": cross_family_failed,
        "failed_held_out_gates": held_out_failed,
        "operation_family_count": len(families),
    }
