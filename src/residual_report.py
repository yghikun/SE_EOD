"""JSON and Markdown witness reports for filesystem metadata residual analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from .metadata_residual import MetadataResidualReport, ReportKind, SourceSite


RESIDUAL_WITNESS_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ResidualWitnessReport:
    report: MetadataResidualReport
    source_version: str
    unknown_causes: tuple[str, ...] = ()

    @property
    def kind(self) -> ReportKind:
        return self.report.kind

    @property
    def confidence(self) -> str:
        return self.report.confidence

    def to_dict(self) -> dict[str, object]:
        data = self.report.to_dict()
        data["schema_version"] = RESIDUAL_WITNESS_SCHEMA_VERSION
        data["source_version"] = self.source_version
        data["unknown_causes"] = list(self.unknown_causes)
        return data

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True) + "\n"

    def to_markdown(self) -> str:
        return report_to_markdown(self)


def reports_to_json(
    reports: Iterable[ResidualWitnessReport],
    *,
    indent: int | None = 2,
) -> str:
    payload = [report.to_dict() for report in reports]
    return json.dumps(payload, indent=indent, sort_keys=True) + "\n"


def report_to_markdown(report: ResidualWitnessReport) -> str:
    data = report.report
    residual_slice = data.residual_slice
    lines = [
        f"# {data.kind.value}: {data.function}",
        "",
        f"- Source version: `{report.source_version}`",
        f"- Confidence: `{data.confidence}`",
        f"- Scope: {data.scope_rationale}",
        f"- Failure point: {_site_text(residual_slice.failure_site)}",
        f"- Error exit: {_site_text(residual_slice.exit_site)}",
        f"- State: `{residual_slice.state.value}`",
    ]
    if residual_slice.rationale:
        lines.append(f"- Rationale: {residual_slice.rationale}")
    if report.unknown_causes:
        lines.append(f"- Unknown causes: {'; '.join(report.unknown_causes)}")
    if data.mdr_evidence:
        lines.append(f"- MDR evidence: {data.mdr_evidence}")

    lines.extend(["", "## E_f Reaching Effects", *_effect_lines(residual_slice.reaching_effects)])
    lines.extend(["", "## C_f Cancellations", *_effect_lines(residual_slice.cancellations)])
    lines.extend(["", "## T_f Protections", *_effect_lines(residual_slice.protections)])
    lines.extend(["", "## R_f Residuals", *_effect_lines(residual_slice.residuals)])
    return "\n".join(lines).rstrip() + "\n"


def reports_to_markdown(reports: Iterable[ResidualWitnessReport]) -> str:
    return "\n---\n\n".join(report_to_markdown(report).rstrip() for report in reports) + "\n"


def _site_text(site: SourceSite | None) -> str:
    if site is None:
        return "`unknown`"
    return f"`{site.file}:{site.line}` `{site.expression}`"


def _effect_lines(effects) -> list[str]:
    if not effects:
        return ["- None"]
    return [
        (
            f"- `{effect.plane.value}` `{effect.delta.value}` "
            f"`{effect.root}.{effect.key}` value `{effect.value}` "
            f"at `{effect.site.file}:{effect.site.line}` `{effect.site.expression}`"
        )
        for effect in effects
    ]
