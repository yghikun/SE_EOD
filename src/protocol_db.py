"""Load API resource lifecycle protocols from JSON config files."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ResourceProtocol:
    protocol_id: str
    resource_kind: str
    acquire_functions: tuple[str, ...]
    release_functions: tuple[str, ...]
    success_condition: str
    resource_expr: str
    required_action: str
    exceptions: tuple[str, ...]
    evidence_type: str
    evidence_level: str
    confidence: str
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResourceProtocol":
        acquire_functions = data.get("acquire_functions", [])
        release_functions = data.get("release_functions", [])
        exceptions = data.get("exceptions", [])
        if isinstance(acquire_functions, str):
            acquire_functions = [acquire_functions]
        if isinstance(release_functions, str):
            release_functions = [release_functions]
        if isinstance(exceptions, str):
            exceptions = [exceptions]

        return cls(
            protocol_id=str(data.get("protocol_id", "")).strip(),
            resource_kind=str(data.get("resource_kind", "")).strip(),
            acquire_functions=tuple(str(item) for item in acquire_functions),
            release_functions=tuple(str(item) for item in release_functions),
            success_condition=str(data.get("success_condition", "")),
            resource_expr=str(data.get("resource_expr", "")),
            required_action=str(data.get("required_action", "")).strip(),
            exceptions=tuple(str(item) for item in exceptions),
            evidence_type=str(data.get("evidence_type", "api_lifecycle")),
            evidence_level=str(data.get("evidence_level", "E2_API_PROTOCOL")),
            confidence=str(data.get("confidence", "medium")),
            description=str(data.get("description", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "resource_kind": self.resource_kind,
            "acquire_functions": list(self.acquire_functions),
            "release_functions": list(self.release_functions),
            "success_condition": self.success_condition,
            "resource_expr": self.resource_expr,
            "required_action": self.required_action,
            "exceptions": list(self.exceptions),
            "evidence_type": self.evidence_type,
            "evidence_level": self.evidence_level,
            "confidence": self.confidence,
            "description": self.description,
        }


@dataclass
class ResourceProtocolDB:
    protocols: list[ResourceProtocol] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def load_from_dir(cls, protocols_dir: str | Path) -> "ResourceProtocolDB":
        root = Path(protocols_dir)
        db = cls()
        roots: list[Path]
        if root.exists() and root.is_dir():
            roots = [root]
        elif root.name == "resource_protocols":
            # Older callers use one aggregate directory. Keep that API working
            # after protocol files were split by filesystem.
            roots = sorted(
                path
                for path in root.parent.glob("*_resource_protocols")
                if path.is_dir()
            )
            if not roots:
                db.warnings.append(f"protocols_dir_missing: {root}")
                return db
        else:
            db.warnings.append(f"protocols_dir_missing: {root}")
            return db

        for protocol_root in roots:
            for path in sorted(protocol_root.glob("*.json")):
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    db.warnings.append(f"{path}: {type(exc).__name__}: {exc}")
                    continue
                if not isinstance(raw, list):
                    db.warnings.append(f"{path}: expected a JSON list of protocols")
                    continue
                for index, item in enumerate(raw):
                    if not isinstance(item, dict):
                        db.warnings.append(f"{path}:{index}: expected protocol object")
                        continue
                    try:
                        protocol = ResourceProtocol.from_dict(item)
                    except Exception as exc:
                        db.warnings.append(f"{path}:{index}: {type(exc).__name__}: {exc}")
                        continue
                    if not protocol.protocol_id:
                        db.warnings.append(f"{path}:{index}: missing protocol_id")
                        continue
                    db.protocols.append(protocol)
        return db

    def find_by_resource_kind(self, kind: str) -> list[ResourceProtocol]:
        normalized = _normalize_kind(kind)
        return [
            protocol
            for protocol in self.protocols
            if _normalize_kind(protocol.resource_kind) == normalized
        ]

    def find_by_required_action(self, action: str) -> list[ResourceProtocol]:
        return [
            protocol
            for protocol in self.protocols
            if protocol.required_action == action
        ]

    def find_by_acquire_function(self, function_name: str) -> list[ResourceProtocol]:
        return [
            protocol
            for protocol in self.protocols
            if function_name in protocol.acquire_functions
        ]

    def find_by_release_function(self, function_name: str) -> list[ResourceProtocol]:
        return [
            protocol
            for protocol in self.protocols
            if function_name in protocol.release_functions
        ]


def _normalize_kind(kind: str) -> str:
    aliases = {
        "journal": "journal_handle",
        "lock": "lock",
        "posix_acl": "posix_acl",
    }
    value = str(kind or "").strip()
    return aliases.get(value, value)
