from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def analyze_patch_evidence(path: str) -> Dict[str, Any]:
    evidence_path = Path(path)
    raw = json.loads(evidence_path.read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "fixed_commit",
        "bug_revision",
        "source_path",
        "function",
        "bug_blob",
        "fixed_blob",
        "removed_fragments",
        "added_fragments",
        "bug_rollback_shape",
        "fixed_rollback_shape",
        "confirmation",
    }
    missing = required - set(raw)
    if missing:
        raise ValueError(f"missing patch evidence keys: {sorted(missing)}")
    removed = "\n".join(raw["removed_fragments"])
    added = "\n".join(raw["added_fragments"])
    bug_uses_total_size_diff = "atomic64_sub(diff" in removed
    bug_rollback_uses_total_size_diff = (
        "atomic64_add(diff" in removed
        and "if (device_is_writeable) total_rw_bytes += diff; atomic64_add(diff"
        in raw["bug_rollback_shape"]
    )
    fixed_computes_free_delta = all(
        fragment in added
        for fragment in (
            "u64 free_diff = 0;",
            "if (device->bytes_used < new_size)",
            "free_diff = (old_size - device->bytes_used) - (new_size - device->bytes_used);",
            "free_diff = old_size - device->bytes_used;",
            "atomic64_sub(free_diff",
        )
    )
    fixed_reuses_free_delta = (
        "atomic64_add(free_diff" in added
        and "if (device_is_writeable) {" in raw["fixed_rollback_shape"]
        and "atomic64_add(free_diff, free_chunk_space); }"
        in raw["fixed_rollback_shape"]
    )
    return {
        "provenance": {
            "bug_revision": raw["bug_revision"],
            "fixed_commit": raw["fixed_commit"],
            "bug_blob": raw["bug_blob"],
            "fixed_blob": raw["fixed_blob"],
            "source_path": raw["source_path"],
        },
        "bug": {
            "delta_valid": not bug_uses_total_size_diff,
            "rollback_guard_valid": not bug_rollback_uses_total_size_diff,
        },
        "fixed": {
            "delta_valid": fixed_computes_free_delta,
            "rollback_guard_valid": fixed_reuses_free_delta,
        },
    }
