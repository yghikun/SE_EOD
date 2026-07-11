"""Load lightweight cleanup wrapper summaries."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WrapperSummary:
    function: str
    releases: tuple[str, ...]
    resource_kinds: tuple[str, ...]
    aliases: tuple[str, ...] = ()
    confidence: str = "medium"
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WrapperSummary":
        releases = data.get("releases", [])
        resource_kinds = data.get("resource_kinds", [])
        aliases = data.get("aliases", [])
        if isinstance(releases, str):
            releases = [releases]
        if isinstance(resource_kinds, str):
            resource_kinds = [resource_kinds]
        if isinstance(aliases, str):
            aliases = [aliases]

        return cls(
            function=str(data.get("function", "")).strip(),
            releases=tuple(str(item).strip() for item in releases if str(item).strip()),
            resource_kinds=tuple(
                str(item).strip() for item in resource_kinds if str(item).strip()
            ),
            aliases=tuple(str(item).strip() for item in aliases if str(item).strip()),
            confidence=str(data.get("confidence", "medium")),
            description=str(data.get("description", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "function": self.function,
            "releases": list(self.releases),
            "resource_kinds": list(self.resource_kinds),
            "aliases": list(self.aliases),
            "confidence": self.confidence,
            "description": self.description,
        }

    def names(self) -> tuple[str, ...]:
        return (self.function, *self.aliases)


@dataclass
class WrapperSummaryDB:
    summaries: list[WrapperSummary] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def load_from_file(cls, path: str | Path) -> "WrapperSummaryDB":
        source = Path(path)
        db = cls()
        if not source.exists() or not source.is_file():
            db.warnings.append(f"wrapper_summaries_missing: {source}")
            return db

        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            db.warnings.append(f"{source}: {type(exc).__name__}: {exc}")
            return db
        if not isinstance(raw, list):
            db.warnings.append(f"{source}: expected a JSON list of wrapper summaries")
            return db

        for index, item in enumerate(raw):
            if not isinstance(item, dict):
                db.warnings.append(f"{source}:{index}: expected wrapper object")
                continue
            try:
                summary = WrapperSummary.from_dict(item)
            except Exception as exc:
                db.warnings.append(f"{source}:{index}: {type(exc).__name__}: {exc}")
                continue
            if not summary.function:
                db.warnings.append(f"{source}:{index}: missing function")
                continue
            db.summaries.append(summary)
        return db

    def find(self, function_name: str) -> WrapperSummary | None:
        name = str(function_name or "").strip()
        for summary in self.summaries:
            if name in summary.names():
                return summary
        return None

    def releases_resource_kind(self, function_name: str, resource_kind: str) -> bool:
        summary = self.find(function_name)
        if not summary:
            return False
        return _normalize_kind(resource_kind) in {
            _normalize_kind(kind) for kind in summary.resource_kinds
        }

    def release_actions_for(self, function_name: str) -> list[str]:
        summary = self.find(function_name)
        return list(summary.releases) if summary else []


def _normalize_kind(kind: str) -> str:
    aliases = {
        "journal": "journal_handle",
        "lock": "lock",
        "posix_acl": "posix_acl",
    }
    value = str(kind or "").strip()
    return aliases.get(value, value)
