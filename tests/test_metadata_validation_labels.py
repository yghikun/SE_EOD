import json
from pathlib import Path

import pytest

from src.metadata_validation_labels import (
    AdjudicationSet,
    MetadataValidationLabelError,
    ReviewerLabelSet,
    make_adjudication_template,
    make_reviewer_label_template,
    validate_adjudication_set,
    validate_reviewer_label_set,
)
from src.metadata_validation_manifest import ProtocolFreeze, ValidationManifest


ROOT = Path(__file__).parents[1]
FREEZE_PATH = ROOT / "configs" / "validation" / "protocol_freeze_v1.json"
MANIFEST_PATH = ROOT / "configs" / "validation" / "validation_manifest_v1.json"
REVIEWER_A_PATH = ROOT / "configs" / "validation" / "reviewer_a_labels_v1.json"
REVIEWER_B_PATH = ROOT / "configs" / "validation" / "reviewer_b_labels_v1.json"
ADJUDICATION_PATH = ROOT / "configs" / "validation" / "adjudication_v1.json"


def _manifest() -> ValidationManifest:
    return ValidationManifest.read_json(MANIFEST_PATH)


def _freeze() -> ProtocolFreeze:
    return ProtocolFreeze.read_json(FREEZE_PATH)


def _label_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_current_label_templates_validate_as_incomplete():
    manifest = _manifest()
    freeze = _freeze()
    reviewer_a = ReviewerLabelSet.read_json(REVIEWER_A_PATH)
    reviewer_b = ReviewerLabelSet.read_json(REVIEWER_B_PATH)
    adjudication = AdjudicationSet.read_json(ADJUDICATION_PATH)

    validate_reviewer_label_set(reviewer_a, manifest, freeze, ROOT)
    validate_reviewer_label_set(reviewer_b, manifest, freeze, ROOT)
    validate_adjudication_set(
        adjudication, manifest, freeze, (reviewer_a, reviewer_b), ROOT
    )

    assert reviewer_a.status == "template"
    assert reviewer_b.status == "template"
    assert adjudication.status == "template"


def test_templates_are_rejected_when_complete_labels_are_required():
    manifest = _manifest()
    freeze = _freeze()
    reviewer_a = ReviewerLabelSet.read_json(REVIEWER_A_PATH)

    with pytest.raises(MetadataValidationLabelError, match="expected complete"):
        validate_reviewer_label_set(
            reviewer_a, manifest, freeze, ROOT, require_complete=True
        )


def test_reviewer_template_generation_tracks_manifest_samples():
    manifest = _manifest()

    label_set = make_reviewer_label_template(manifest, "reviewer_a")

    assert [entry.sample_id for entry in label_set.entries] == [
        sample.sample_id for sample in manifest.samples
    ]
    assert all(entry.verdict == "unlabeled" for entry in label_set.entries)


def test_completed_label_requires_rationale():
    manifest = _manifest()
    freeze = _freeze()
    payload = _label_payload(REVIEWER_A_PATH)
    payload["status"] = "complete"
    payload["entries"][0]["verdict"] = "legal"
    payload["entries"][0]["rationale"] = "reviewed source path and protocol obligation"

    with pytest.raises(MetadataValidationLabelError, match="cannot contain unlabeled"):
        validate_reviewer_label_set(
            ReviewerLabelSet.from_dict(payload),
            manifest,
            freeze,
            ROOT,
        )

    for entry in payload["entries"]:
        entry["verdict"] = "legal"
        entry["rationale"] = "reviewed source path and protocol obligation"
    payload["entries"][0]["rationale"] = ""

    with pytest.raises(MetadataValidationLabelError, match="require rationale"):
        validate_reviewer_label_set(
            ReviewerLabelSet.from_dict(payload),
            manifest,
            freeze,
            ROOT,
        )


def test_wrong_reviewer_slot_is_rejected():
    manifest = _manifest()
    freeze = _freeze()
    payload = _label_payload(REVIEWER_A_PATH)
    payload["entries"][0]["reviewer_slot"] = "reviewer_b"

    with pytest.raises(MetadataValidationLabelError, match="does not match"):
        validate_reviewer_label_set(
            ReviewerLabelSet.from_dict(payload), manifest, freeze, ROOT
        )


def test_adjudication_template_generation_mirrors_reviewer_slots():
    manifest = _manifest()
    reviewer_a = make_reviewer_label_template(manifest, "reviewer_a")
    reviewer_b = make_reviewer_label_template(manifest, "reviewer_b")

    adjudication = make_adjudication_template(manifest, (reviewer_a, reviewer_b))

    assert adjudication.label_set_ids == (
        reviewer_a.label_set_id,
        reviewer_b.label_set_id,
    )
    assert adjudication.entries[0].reviewer_verdicts == {
        "reviewer_a": "unlabeled",
        "reviewer_b": "unlabeled",
    }


def test_adjudication_reviewer_verdict_drift_is_rejected():
    manifest = _manifest()
    freeze = _freeze()
    reviewer_a = ReviewerLabelSet.read_json(REVIEWER_A_PATH)
    reviewer_b = ReviewerLabelSet.read_json(REVIEWER_B_PATH)
    payload = _label_payload(ADJUDICATION_PATH)
    payload["entries"][0]["reviewer_verdicts"]["reviewer_a"] = "legal"

    with pytest.raises(MetadataValidationLabelError, match="does not mirror"):
        validate_adjudication_set(
            AdjudicationSet.from_dict(payload),
            manifest,
            freeze,
            (reviewer_a, reviewer_b),
            ROOT,
        )


def test_duplicate_json_fields_are_rejected(tmp_path):
    target = tmp_path / "labels.json"
    target.write_text(
        '{"schema_version": 1, "schema_version": 1}',
        encoding="utf-8",
    )

    with pytest.raises(MetadataValidationLabelError, match="duplicate JSON field"):
        ReviewerLabelSet.read_json(target)
