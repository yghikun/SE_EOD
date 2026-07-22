"""Validate independent reviewer labels and adjudication for frozen samples."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .metadata_validation_manifest import (
    DEFAULT_FREEZE,
    DEFAULT_MANIFEST,
    MetadataValidationManifestError,
    ProtocolFreeze,
    ValidationManifest,
    validate_validation_manifest,
)


LABEL_SCHEMA_VERSION = 1
ADJUDICATION_SCHEMA_VERSION = 1
UNLABELED = "unlabeled"
VERDICTS = {"legal", "violation", "analysis_unknown", "out_of_scope"}


class MetadataValidationLabelError(ValueError):
    """A reviewer label set or adjudication file violates validation policy."""

    def __init__(self, path: str, message: str) -> None:
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


@dataclass(frozen=True)
class ReviewerLabelEntry:
    sample_id: str
    reviewer_slot: str
    verdict: str
    rationale: str
    evidence_notes: str
    analysis_limitations: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], path: str) -> "ReviewerLabelEntry":
        value = _mapping(data, path)
        _known_keys(
            value,
            {
                "sample_id",
                "reviewer_slot",
                "verdict",
                "rationale",
                "evidence_notes",
                "analysis_limitations",
            },
            path,
        )
        verdict = _text(value, "verdict", path)
        if verdict not in VERDICTS | {UNLABELED}:
            raise MetadataValidationLabelError(f"{path}.verdict", "unsupported verdict")
        return cls(
            sample_id=_identifier(value, "sample_id", path),
            reviewer_slot=_identifier(value, "reviewer_slot", path),
            verdict=verdict,
            rationale=_optional_text(value, "rationale", path),
            evidence_notes=_optional_text(value, "evidence_notes", path),
            analysis_limitations=_optional_text(value, "analysis_limitations", path),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "reviewer_slot": self.reviewer_slot,
            "verdict": self.verdict,
            "rationale": self.rationale,
            "evidence_notes": self.evidence_notes,
            "analysis_limitations": self.analysis_limitations,
        }


@dataclass(frozen=True)
class ReviewerLabelSet:
    schema_version: int
    label_set_id: str
    manifest_id: str
    freeze_id: str
    reviewer_slot: str
    label_visibility: str
    status: str
    entries: tuple[ReviewerLabelEntry, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReviewerLabelSet":
        value = _mapping(data, "label_set")
        _known_keys(
            value,
            {
                "schema_version",
                "label_set_id",
                "manifest_id",
                "freeze_id",
                "reviewer_slot",
                "label_visibility",
                "status",
                "entries",
            },
            "label_set",
        )
        schema_version = _positive_integer(value, "schema_version", "label_set")
        if schema_version != LABEL_SCHEMA_VERSION:
            raise MetadataValidationLabelError(
                "label_set.schema_version", f"expected {LABEL_SCHEMA_VERSION}"
            )
        return cls(
            schema_version=schema_version,
            label_set_id=_identifier(value, "label_set_id", "label_set"),
            manifest_id=_identifier(value, "manifest_id", "label_set"),
            freeze_id=_identifier(value, "freeze_id", "label_set"),
            reviewer_slot=_identifier(value, "reviewer_slot", "label_set"),
            label_visibility=_choice(
                value, "label_visibility", "label_set", {"independent"}
            ),
            status=_choice(value, "status", "label_set", {"template", "complete"}),
            entries=tuple(
                ReviewerLabelEntry.from_dict(item, f"label_set.entries[{index}]")
                for index, item in enumerate(_object_list(value, "entries", "label_set"))
            ),
        )

    @classmethod
    def read_json(cls, path: str | Path) -> "ReviewerLabelSet":
        return cls.from_dict(_read_json(path))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "label_set_id": self.label_set_id,
            "manifest_id": self.manifest_id,
            "freeze_id": self.freeze_id,
            "reviewer_slot": self.reviewer_slot,
            "label_visibility": self.label_visibility,
            "status": self.status,
            "entries": [entry.to_dict() for entry in self.entries],
        }


@dataclass(frozen=True)
class AdjudicationEntry:
    sample_id: str
    final_verdict: str
    adjudicator: str
    rationale: str
    reviewer_verdicts: dict[str, str]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], path: str) -> "AdjudicationEntry":
        value = _mapping(data, path)
        _known_keys(
            value,
            {
                "sample_id",
                "final_verdict",
                "adjudicator",
                "rationale",
                "reviewer_verdicts",
            },
            path,
        )
        final_verdict = _text(value, "final_verdict", path)
        if final_verdict not in VERDICTS | {UNLABELED}:
            raise MetadataValidationLabelError(
                f"{path}.final_verdict", "unsupported verdict"
            )
        reviewer_verdicts = _string_mapping(value, "reviewer_verdicts", path)
        unsupported = sorted(set(reviewer_verdicts.values()) - VERDICTS - {UNLABELED})
        if unsupported:
            raise MetadataValidationLabelError(
                f"{path}.reviewer_verdicts", "unsupported reviewer verdict"
            )
        return cls(
            sample_id=_identifier(value, "sample_id", path),
            final_verdict=final_verdict,
            adjudicator=_optional_identifier(value, "adjudicator", path),
            rationale=_optional_text(value, "rationale", path),
            reviewer_verdicts=reviewer_verdicts,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "final_verdict": self.final_verdict,
            "adjudicator": self.adjudicator,
            "rationale": self.rationale,
            "reviewer_verdicts": dict(self.reviewer_verdicts),
        }


@dataclass(frozen=True)
class AdjudicationSet:
    schema_version: int
    adjudication_id: str
    manifest_id: str
    freeze_id: str
    status: str
    label_set_ids: tuple[str, ...]
    entries: tuple[AdjudicationEntry, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AdjudicationSet":
        value = _mapping(data, "adjudication")
        _known_keys(
            value,
            {
                "schema_version",
                "adjudication_id",
                "manifest_id",
                "freeze_id",
                "status",
                "label_set_ids",
                "entries",
            },
            "adjudication",
        )
        schema_version = _positive_integer(value, "schema_version", "adjudication")
        if schema_version != ADJUDICATION_SCHEMA_VERSION:
            raise MetadataValidationLabelError(
                "adjudication.schema_version",
                f"expected {ADJUDICATION_SCHEMA_VERSION}",
            )
        return cls(
            schema_version=schema_version,
            adjudication_id=_identifier(value, "adjudication_id", "adjudication"),
            manifest_id=_identifier(value, "manifest_id", "adjudication"),
            freeze_id=_identifier(value, "freeze_id", "adjudication"),
            status=_choice(value, "status", "adjudication", {"template", "complete"}),
            label_set_ids=_identifier_tuple(
                value, "label_set_ids", "adjudication", nonempty=True
            ),
            entries=tuple(
                AdjudicationEntry.from_dict(
                    item, f"adjudication.entries[{index}]"
                )
                for index, item in enumerate(
                    _object_list(value, "entries", "adjudication")
                )
            ),
        )

    @classmethod
    def read_json(cls, path: str | Path) -> "AdjudicationSet":
        return cls.from_dict(_read_json(path))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adjudication_id": self.adjudication_id,
            "manifest_id": self.manifest_id,
            "freeze_id": self.freeze_id,
            "status": self.status,
            "label_set_ids": list(self.label_set_ids),
            "entries": [entry.to_dict() for entry in self.entries],
        }


def make_reviewer_label_template(
    manifest: ValidationManifest, reviewer_slot: str
) -> ReviewerLabelSet:
    _ensure_manifest_reviewer_slot(manifest, reviewer_slot)
    return ReviewerLabelSet(
        schema_version=LABEL_SCHEMA_VERSION,
        label_set_id=f"{manifest.manifest_id}.{reviewer_slot}.labels",
        manifest_id=manifest.manifest_id,
        freeze_id=manifest.freeze_id,
        reviewer_slot=reviewer_slot,
        label_visibility="independent",
        status="template",
        entries=tuple(
            ReviewerLabelEntry(
                sample_id=sample.sample_id,
                reviewer_slot=reviewer_slot,
                verdict=UNLABELED,
                rationale="",
                evidence_notes="",
                analysis_limitations="",
            )
            for sample in manifest.samples
        ),
    )


def make_adjudication_template(
    manifest: ValidationManifest, label_sets: tuple[ReviewerLabelSet, ...]
) -> AdjudicationSet:
    slots = tuple(label_set.reviewer_slot for label_set in label_sets)
    return AdjudicationSet(
        schema_version=ADJUDICATION_SCHEMA_VERSION,
        adjudication_id=f"{manifest.manifest_id}.adjudication",
        manifest_id=manifest.manifest_id,
        freeze_id=manifest.freeze_id,
        status="template",
        label_set_ids=tuple(label_set.label_set_id for label_set in label_sets),
        entries=tuple(
            AdjudicationEntry(
                sample_id=sample.sample_id,
                final_verdict=UNLABELED,
                adjudicator="",
                rationale="",
                reviewer_verdicts={slot: UNLABELED for slot in slots},
            )
            for sample in manifest.samples
        ),
    )


def validate_reviewer_label_set(
    label_set: ReviewerLabelSet,
    manifest: ValidationManifest,
    freeze: ProtocolFreeze,
    workspace: str | Path,
    *,
    require_complete: bool = False,
) -> None:
    validate_validation_manifest(manifest, freeze, workspace)
    if label_set.manifest_id != manifest.manifest_id:
        raise MetadataValidationLabelError(
            "label_set.manifest_id", "does not match validation manifest"
        )
    if label_set.freeze_id != freeze.freeze_id:
        raise MetadataValidationLabelError(
            "label_set.freeze_id", "does not match protocol freeze"
        )
    _ensure_manifest_reviewer_slot(manifest, label_set.reviewer_slot)
    if require_complete and label_set.status != "complete":
        raise MetadataValidationLabelError("label_set.status", "expected complete")

    samples = {sample.sample_id: sample for sample in manifest.samples}
    entries = {entry.sample_id: entry for entry in label_set.entries}
    _require_exact_keys(entries, samples, "label_set.entries")
    for entry in label_set.entries:
        path = f"label_set.entries.{entry.sample_id}"
        sample = samples[entry.sample_id]
        if entry.reviewer_slot != label_set.reviewer_slot:
            raise MetadataValidationLabelError(
                f"{path}.reviewer_slot", "does not match label_set reviewer_slot"
            )
        if entry.reviewer_slot not in sample.reviewer_slots:
            raise MetadataValidationLabelError(
                f"{path}.reviewer_slot", "not authorized for this sample"
            )
        if entry.verdict == UNLABELED:
            if label_set.status == "complete" or require_complete:
                raise MetadataValidationLabelError(
                    f"{path}.verdict", "complete label sets cannot contain unlabeled"
                )
            continue
        if entry.verdict not in sample.allowed_verdicts:
            raise MetadataValidationLabelError(
                f"{path}.verdict", "not allowed by sample manifest"
            )
        if not entry.rationale:
            raise MetadataValidationLabelError(
                f"{path}.rationale", "labeled entries require rationale"
            )


def validate_adjudication_set(
    adjudication: AdjudicationSet,
    manifest: ValidationManifest,
    freeze: ProtocolFreeze,
    label_sets: tuple[ReviewerLabelSet, ...],
    workspace: str | Path,
    *,
    require_complete: bool = False,
) -> None:
    validate_validation_manifest(manifest, freeze, workspace)
    if adjudication.manifest_id != manifest.manifest_id:
        raise MetadataValidationLabelError(
            "adjudication.manifest_id", "does not match validation manifest"
        )
    if adjudication.freeze_id != freeze.freeze_id:
        raise MetadataValidationLabelError(
            "adjudication.freeze_id", "does not match protocol freeze"
        )
    if require_complete and adjudication.status != "complete":
        raise MetadataValidationLabelError("adjudication.status", "expected complete")
    if tuple(label_set.label_set_id for label_set in label_sets) != adjudication.label_set_ids:
        raise MetadataValidationLabelError(
            "adjudication.label_set_ids", "does not match supplied label sets"
        )
    for label_set in label_sets:
        validate_reviewer_label_set(
            label_set,
            manifest,
            freeze,
            workspace,
            require_complete=adjudication.status == "complete" or require_complete,
        )

    samples = {sample.sample_id: sample for sample in manifest.samples}
    entries = {entry.sample_id: entry for entry in adjudication.entries}
    _require_exact_keys(entries, samples, "adjudication.entries")
    labels_by_sample = {
        sample_id: {
            label_set.reviewer_slot: next(
                entry.verdict for entry in label_set.entries if entry.sample_id == sample_id
            )
            for label_set in label_sets
        }
        for sample_id in samples
    }
    for entry in adjudication.entries:
        path = f"adjudication.entries.{entry.sample_id}"
        sample = samples[entry.sample_id]
        expected = labels_by_sample[entry.sample_id]
        if entry.reviewer_verdicts != expected:
            raise MetadataValidationLabelError(
                f"{path}.reviewer_verdicts", "does not mirror supplied reviewer labels"
            )
        if entry.final_verdict == UNLABELED:
            if adjudication.status == "complete" or require_complete:
                raise MetadataValidationLabelError(
                    f"{path}.final_verdict", "complete adjudication cannot be unlabeled"
                )
            continue
        if entry.final_verdict not in sample.allowed_verdicts:
            raise MetadataValidationLabelError(
                f"{path}.final_verdict", "not allowed by sample manifest"
            )
        if not entry.adjudicator or not entry.rationale:
            raise MetadataValidationLabelError(
                path, "completed adjudication requires adjudicator and rationale"
            )


def _ensure_manifest_reviewer_slot(
    manifest: ValidationManifest, reviewer_slot: str
) -> None:
    missing = [
        sample.sample_id
        for sample in manifest.samples
        if reviewer_slot not in sample.reviewer_slots
    ]
    if missing:
        raise MetadataValidationLabelError(
            "reviewer_slot",
            f"reviewer slot {reviewer_slot!r} is not available for every sample",
        )


def _require_exact_keys(
    actual: Mapping[str, Any], expected: Mapping[str, Any], path: str
) -> None:
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    details = []
    if missing:
        details.append("missing=" + ",".join(missing))
    if extra:
        details.append("extra=" + ",".join(extra))
    if details:
        raise MetadataValidationLabelError(path, "; ".join(details))


def _load_manifest_and_freeze(
    workspace: Path, manifest_path: str, freeze_path: str
) -> tuple[ValidationManifest, ProtocolFreeze]:
    return (
        ValidationManifest.read_json(workspace / manifest_path),
        ProtocolFreeze.read_json(workspace / freeze_path),
    )


def _write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _read_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        payload = json.loads(
            source.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
        )
    except OSError as exc:
        raise MetadataValidationLabelError(str(source), f"cannot read JSON: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise MetadataValidationLabelError(
            str(source), f"invalid JSON at line {exc.lineno}: {exc.msg}"
        ) from exc
    if not isinstance(payload, dict):
        raise MetadataValidationLabelError(str(source), "expected a JSON object")
    return payload


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MetadataValidationLabelError("json", f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _mapping(data: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise MetadataValidationLabelError(path, "expected an object")
    return data


def _known_keys(data: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise MetadataValidationLabelError(
            path, "unknown field(s): " + ", ".join(unknown)
        )


def _required(data: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in data:
        raise MetadataValidationLabelError(f"{path}.{key}", "required field missing")
    return data[key]


def _text(data: Mapping[str, Any], key: str, path: str) -> str:
    value = _required(data, key, path)
    if not isinstance(value, str) or not value.strip():
        raise MetadataValidationLabelError(f"{path}.{key}", "expected non-empty text")
    return value.strip()


def _optional_text(data: Mapping[str, Any], key: str, path: str) -> str:
    value = data.get(key, "")
    if not isinstance(value, str):
        raise MetadataValidationLabelError(f"{path}.{key}", "expected text")
    return value.strip()


def _identifier(data: Mapping[str, Any], key: str, path: str) -> str:
    value = _text(data, key, path)
    if not value[0].isalpha() or not all(
        item.isalnum() or item in "_.-" for item in value
    ):
        raise MetadataValidationLabelError(f"{path}.{key}", "invalid identifier")
    return value


def _optional_identifier(data: Mapping[str, Any], key: str, path: str) -> str:
    value = _optional_text(data, key, path)
    if value and (not value[0].isalpha() or not all(
        item.isalnum() or item in "_.-" for item in value
    )):
        raise MetadataValidationLabelError(f"{path}.{key}", "invalid identifier")
    return value


def _positive_integer(data: Mapping[str, Any], key: str, path: str) -> int:
    value = _required(data, key, path)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise MetadataValidationLabelError(
            f"{path}.{key}", "expected a positive integer"
        )
    return value


def _choice(
    data: Mapping[str, Any], key: str, path: str, allowed: set[str]
) -> str:
    value = _text(data, key, path)
    if value not in allowed:
        raise MetadataValidationLabelError(
            f"{path}.{key}", "expected one of: " + ", ".join(sorted(allowed))
        )
    return value


def _object_list(data: Mapping[str, Any], key: str, path: str) -> list[Mapping[str, Any]]:
    value = _required(data, key, path)
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise MetadataValidationLabelError(f"{path}.{key}", "expected an object array")
    return value


def _identifier_tuple(
    data: Mapping[str, Any], key: str, path: str, *, nonempty: bool = False
) -> tuple[str, ...]:
    raw = _required(data, key, path)
    if not isinstance(raw, list):
        raise MetadataValidationLabelError(f"{path}.{key}", "expected an array")
    values = tuple(_identifier({key: item}, key, f"{path}.{key}[{index}]") for index, item in enumerate(raw))
    if nonempty and not values:
        raise MetadataValidationLabelError(f"{path}.{key}", "must not be empty")
    if len(values) != len(set(values)):
        raise MetadataValidationLabelError(f"{path}.{key}", "duplicate value")
    return values


def _string_mapping(data: Mapping[str, Any], key: str, path: str) -> dict[str, str]:
    raw = _required(data, key, path)
    if not isinstance(raw, Mapping):
        raise MetadataValidationLabelError(f"{path}.{key}", "expected an object")
    result = {}
    for item_key, item_value in raw.items():
        if not isinstance(item_key, str) or not item_key:
            raise MetadataValidationLabelError(f"{path}.{key}", "invalid key")
        if not isinstance(item_value, str) or not item_value.strip():
            raise MetadataValidationLabelError(f"{path}.{key}.{item_key}", "expected text")
        result[item_key] = item_value.strip()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate or generate MOCC-SE validation reviewer/adjudication files."
    )
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--freeze", default=str(DEFAULT_FREEZE))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--emit-reviewer-template", choices=["reviewer_a", "reviewer_b"])
    parser.add_argument("--emit-adjudication-template", action="store_true")
    parser.add_argument("--out")
    parser.add_argument("--labels", action="append", default=[])
    parser.add_argument("--adjudication")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.workspace).resolve()
    manifest, freeze = _load_manifest_and_freeze(root, args.manifest, args.freeze)

    if args.emit_reviewer_template:
        if not args.out:
            parser.error("--out is required with --emit-reviewer-template")
        label_set = make_reviewer_label_template(manifest, args.emit_reviewer_template)
        _write_json(root / args.out, label_set.to_dict())
        return 0

    label_sets = tuple(ReviewerLabelSet.read_json(root / item) for item in args.labels)
    if args.emit_adjudication_template:
        if not args.out:
            parser.error("--out is required with --emit-adjudication-template")
        adjudication = make_adjudication_template(manifest, label_sets)
        _write_json(root / args.out, adjudication.to_dict())
        return 0

    for label_set in label_sets:
        validate_reviewer_label_set(
            label_set,
            manifest,
            freeze,
            root,
            require_complete=args.require_complete,
        )
    if args.adjudication:
        validate_adjudication_set(
            AdjudicationSet.read_json(root / args.adjudication),
            manifest,
            freeze,
            label_sets,
            root,
            require_complete=args.require_complete,
        )
    print(
        json.dumps(
            {
                "manifest_id": manifest.manifest_id,
                "label_sets": len(label_sets),
                "adjudication": bool(args.adjudication),
                "require_complete": args.require_complete,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
