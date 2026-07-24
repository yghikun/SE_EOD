"""Lightweight data model for failure-path filesystem metadata residual analysis."""

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


class ResidualState(str, Enum):
    EXPOSED = "EXPOSED"
    PROTECTED = "PROTECTED"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


class ReportKind(str, Enum):
    UNCLOSED_METADATA_RESIDUAL = "UNCLOSED_METADATA_RESIDUAL"
    METADATA_RESIDUAL_UNKNOWN = "METADATA_RESIDUAL_UNKNOWN"
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
    value: str
    site: SourceSite

    def identity(self) -> tuple[str, str, MetadataPlane]:
        return (self.root, self.key, self.plane)

    def cancellation_key(self) -> tuple[str, str, MetadataPlane, str]:
        return (self.root, self.key, self.plane, self.value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "key": self.key,
            "plane": self.plane.value,
            "delta": self.delta.value,
            "value": self.value,
            "site": self.site.to_dict(),
        }


@dataclass(frozen=True)
class ResidualSlice:
    failure_site: SourceSite
    reaching_effects: tuple[MetadataEffect, ...]
    cancellations: tuple[MetadataEffect, ...]
    protections: tuple[MetadataEffect, ...]
    residuals: tuple[MetadataEffect, ...]
    state: ResidualState
    exit_site: SourceSite | None = None
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_site": self.failure_site.to_dict(),
            "reaching_effects": [item.to_dict() for item in self.reaching_effects],
            "cancellations": [item.to_dict() for item in self.cancellations],
            "protections": [item.to_dict() for item in self.protections],
            "residuals": [item.to_dict() for item in self.residuals],
            "state": self.state.value,
            "exit_site": self.exit_site.to_dict() if self.exit_site else None,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class MetadataResidualReport:
    kind: ReportKind
    function: str
    residual_slice: ResidualSlice
    scope_rationale: str
    mdr_evidence: str = ""
    confidence: str = "review"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "function": self.function,
            "residual_slice": self.residual_slice.to_dict(),
            "scope_rationale": self.scope_rationale,
            "mdr_evidence": self.mdr_evidence,
            "confidence": self.confidence,
        }


def residual_report(
    *,
    function: str,
    residual_slice: ResidualSlice,
    scope_rationale: str,
    mdr_evidence: str = "",
) -> MetadataResidualReport:
    kind = (
        ReportKind.UNCLOSED_METADATA_RESIDUAL
        if residual_slice.residuals and residual_slice.state is ResidualState.EXPOSED
        else ReportKind.METADATA_RESIDUAL_UNKNOWN
        if residual_slice.state is ResidualState.UNKNOWN
        else ReportKind.OUT_OF_SCOPE
    )
    confidence = "candidate" if kind is ReportKind.UNCLOSED_METADATA_RESIDUAL else "review"
    return MetadataResidualReport(
        kind=kind,
        function=function,
        residual_slice=residual_slice,
        scope_rationale=scope_rationale,
        mdr_evidence=mdr_evidence,
        confidence=confidence,
    )
