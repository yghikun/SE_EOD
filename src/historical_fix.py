"""Reviewed cross-version fix evidence for ranked candidates."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
                evidence = {key: value for key, value in fix.items() if key != "line_mappings"}
                evidence.update(mapping)
                evidence["type"] = "historical_fix"
                evidence["confidence"] = "high"
                matched.append(evidence)
        return matched
