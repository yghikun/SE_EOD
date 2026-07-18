"""Reviewed cross-version fix evidence for ranked candidates."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .parser import call_name_and_first_arg
from .resource_expr import same_resource_expr


@dataclass
class HistoricalFixDB:
    fixes: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def load_from_file(cls, path: str | Path | None) -> "HistoricalFixDB":
        db = cls()
        if not path:
            return db
        source = Path(path)
        if not source.exists():
            return db
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            db.warnings.append(f"historical_fixes_invalid:{source}:{exc}")
            return db
        raw_fixes = payload.get("fixes", []) if isinstance(payload, dict) else []
        if not isinstance(raw_fixes, list):
            db.warnings.append(f"historical_fixes_invalid:{source}:fixes must be a list")
            return db
        db.fixes = [fix for fix in raw_fixes if isinstance(fix, dict)]
        return db

    def match(self, row: dict[str, str]) -> list[dict[str, Any]]:
        matched: list[dict[str, Any]] = []
        try:
            error_line = int(row.get("error_line", 0))
        except (TypeError, ValueError):
            error_line = 0
        for fix in self.fixes:
            if fix.get("file") not in {None, "", row.get("file", "")}:
                continue
            if fix.get("function") not in {None, "", row.get("function", "")}:
                continue
            if fix.get("candidate_type") not in {
                None,
                "",
                row.get("candidate_type", ""),
            }:
                continue
            for mapping in fix.get("line_mappings", []):
                if not isinstance(mapping, dict):
                    continue
                if int(mapping.get("affected_line", 0)) != error_line:
                    continue
                if not _selectors_match(row, fix, mapping):
                    continue
                evidence = {key: value for key, value in fix.items() if key != "line_mappings"}
                evidence.update(mapping)
                evidence["type"] = "historical_fix"
                evidence["confidence"] = "high"
                matched.append(evidence)
        return matched


def _selectors_match(
    row: dict[str, str], fix: dict[str, Any], mapping: dict[str, Any]
) -> bool:
    selectors = [fix, mapping]
    obligation_id = str(row.get("obligation_id", "") or row.get("candidate_id", ""))
    resource_id = str(row.get("resource_id", ""))
    missing_cleanup = str(row.get("missing_cleanup", ""))
    missing_action, missing_arg = call_name_and_first_arg(missing_cleanup)

    for selector in selectors:
        expected_obligation = str(selector.get("obligation_id", "")).strip()
        if expected_obligation and expected_obligation != obligation_id:
            return False

        expected_resource_id = str(selector.get("resource_id", "")).strip()
        if expected_resource_id and expected_resource_id != resource_id:
            return False

        resource_id_pattern = str(selector.get("resource_id_pattern", "")).strip()
        if resource_id_pattern and resource_id_pattern not in resource_id:
            return False

        expected_missing_cleanup = str(selector.get("missing_cleanup", "")).strip()
        if expected_missing_cleanup and not same_resource_expr(
            expected_missing_cleanup, missing_cleanup
        ):
            return False

        expected_action = str(
            selector.get("missing_action") or selector.get("required_action") or ""
        ).strip()
        if expected_action and expected_action != missing_action:
            return False

        expected_arg = str(selector.get("missing_arg", "")).strip()
        if expected_arg and not same_resource_expr(expected_arg, missing_arg):
            return False

        expected_type = str(selector.get("resource_type", "")).strip()
        if expected_type:
            row_type = str(row.get("resource_type", "")).strip()
            if not row_type:
                row_type = _resource_field(row, "resource_type")
            if expected_type != row_type:
                return False

        expected_acquire = str(selector.get("acquire_func", "")).strip()
        if expected_acquire:
            row_acquire = str(row.get("acquire_func", "")).strip()
            if not row_acquire:
                row_acquire = _resource_field(row, "acquire_func")
            if expected_acquire != row_acquire:
                return False
    return True


def _resource_field(row: dict[str, str], field: str) -> str:
    import json

    candidates = []
    for key in ("held_resources", "evidence"):
        raw = row.get(key, "")
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if key == "evidence" and isinstance(parsed, dict):
            parsed = parsed.get("acquired_resources", [])
        if isinstance(parsed, list):
            candidates.extend(item for item in parsed if isinstance(item, dict))
    resource_id = str(row.get("resource_id", ""))
    for resource in candidates:
        if resource_id and str(resource.get("resource_id", "")) != resource_id:
            continue
        value = str(resource.get(field, "")).strip()
        if value:
            return value
    return ""
