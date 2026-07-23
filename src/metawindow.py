"""Lightweight data model for MetaWindow metadata failure-window analysis."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class MetadataPlane(str, Enum):
    STRUCTURAL = "STRUCTURAL"
    ACCOUNTING = "ACCOUNTING"
    RECOVERY = "RECOVERY"


class MetadataDelta(str, Enum):
    ADD = "ADD"
    REMOVE = "REMOVE"
    SET = "SET"
    CLEAR = "CLEAR"
    INC = "INC"
    DEC = "DEC"
    RESERVE = "RESERVE"
    RELEASE = "RELEASE"
    PROTECT = "PROTECT"
    CLOSE = "CLOSE"
    UNKNOWN = "UNKNOWN"


class WindowState(str, Enum):
    EXPOSED = "EXPOSED"
    PROTECTED = "PROTECTED"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


class ReportKind(str, Enum):
    UNCLOSED_METADATA_FAILURE_WINDOW = "UNCLOSED_METADATA_FAILURE_WINDOW"
    METADATA_WINDOW_UNKNOWN = "METADATA_WINDOW_UNKNOWN"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


@dataclass(frozen=True)
class SourceSite:
    file: str
    line: int
    expression: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "expression": self.expression,
        }


@dataclass(frozen=True)
class MetadataEffect:
    root: str
    key: str
    plane: MetadataPlane
    delta: MetadataDelta
    site: SourceSite

    def identity(self) -> tuple[str, str, MetadataPlane]:
        return (self.root, self.key, self.plane)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "key": self.key,
            "plane": self.plane.value,
            "delta": self.delta.value,
            "site": self.site.to_dict(),
        }


@dataclass(frozen=True)
class FailureWindow:
    effect: MetadataEffect
    state: WindowState
    fallible_site: SourceSite
    exit_site: SourceSite | None = None
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "effect": self.effect.to_dict(),
            "state": self.state.value,
            "fallible_site": self.fallible_site.to_dict(),
            "exit_site": self.exit_site.to_dict() if self.exit_site else None,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class MetaWindowReport:
    kind: ReportKind
    function: str
    window: FailureWindow
    scope_rationale: str
    mdr_evidence: str = ""
    confidence: str = "review"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "function": self.function,
            "window": self.window.to_dict(),
            "scope_rationale": self.scope_rationale,
            "mdr_evidence": self.mdr_evidence,
            "confidence": self.confidence,
        }


def error_exit_report(
    *,
    function: str,
    window: FailureWindow,
    scope_rationale: str,
    mdr_evidence: str = "",
) -> MetaWindowReport:
    kind = (
        ReportKind.UNCLOSED_METADATA_FAILURE_WINDOW
        if window.state is WindowState.EXPOSED
        else ReportKind.METADATA_WINDOW_UNKNOWN
        if window.state is WindowState.UNKNOWN
        else ReportKind.OUT_OF_SCOPE
    )
    confidence = "candidate" if kind is ReportKind.UNCLOSED_METADATA_FAILURE_WINDOW else "review"
    return MetaWindowReport(
        kind=kind,
        function=function,
        window=window,
        scope_rationale=scope_rationale,
        mdr_evidence=mdr_evidence,
        confidence=confidence,
    )
