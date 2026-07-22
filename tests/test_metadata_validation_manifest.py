import json
from pathlib import Path

import pytest

from src.metadata_validation_manifest import (
    ProtocolFreeze,
    ValidationManifest,
    MetadataValidationManifestError,
    _frozen_artifact_sha256,
    _version_applies,
    validate_validation_manifest,
)


ROOT = Path(__file__).parents[1]
FREEZE_PATH = ROOT / "configs" / "validation" / "protocol_freeze_v1.json"
MANIFEST_PATH = ROOT / "configs" / "validation" / "validation_manifest_v1.json"


def _freeze_payload() -> dict:
    return json.loads(FREEZE_PATH.read_text(encoding="utf-8"))


def _manifest_payload() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _validate(freeze_payload: dict, manifest_payload: dict):
    freeze = ProtocolFreeze.from_dict(freeze_payload)
    manifest = ValidationManifest.from_dict(manifest_payload)
    return validate_validation_manifest(manifest, freeze, ROOT)


def test_current_freeze_and_manifest_validate():
    coverage = validate_validation_manifest(
        ValidationManifest.read_json(MANIFEST_PATH),
        ProtocolFreeze.read_json(FREEZE_PATH),
        ROOT,
    )

    assert coverage.frozen_artifacts == 14
    assert coverage.samples == 10
    assert coverage.functions == 10
    assert coverage.protocols == 5
    assert coverage.filesystems == 3
    assert coverage.near_neighbor_samples == 10
    assert coverage.construction_overlaps == 0


def test_frozen_artifact_hash_drift_is_rejected():
    freeze = _freeze_payload()
    freeze["artifacts"][0]["content_sha256"] = "0" * 64

    with pytest.raises(
        MetadataValidationManifestError,
        match="frozen configuration differs",
    ):
        _validate(freeze, _manifest_payload())


def test_construction_function_reuse_is_rejected():
    manifest = _manifest_payload()
    manifest["samples"][0]["functions"] = ["ext4_fc_replay_inode"]

    with pytest.raises(
        MetadataValidationManifestError,
        match="construction overlap detected",
    ):
        _validate(_freeze_payload(), manifest)


def test_source_hash_drift_is_rejected():
    manifest = _manifest_payload()
    manifest["samples"][0]["source_sha256"] = "0" * 64

    with pytest.raises(
        MetadataValidationManifestError,
        match="source file digest has drifted",
    ):
        _validate(_freeze_payload(), manifest)


def test_missing_active_protocol_sample_is_rejected():
    manifest = _manifest_payload()
    manifest["samples"] = [
        sample
        for sample in manifest["samples"]
        if sample["protocol_id"] != "mocc.protocol_e.allocation_lifecycle"
    ]

    with pytest.raises(
        MetadataValidationManifestError,
        match="does not cover active protocol",
    ):
        _validate(_freeze_payload(), manifest)


def test_blind_manifest_cannot_contain_labeled_sample():
    manifest = _manifest_payload()
    manifest["samples"][0]["label_status"] = "independently_labeled"

    with pytest.raises(
        MetadataValidationManifestError,
        match="blind manifests may only contain unlabeled",
    ):
        ValidationManifest.from_dict(manifest)


def test_duplicate_json_fields_are_rejected(tmp_path):
    target = tmp_path / "freeze.json"
    target.write_text(
        '{"schema_version": 1, "schema_version": 1}',
        encoding="utf-8",
    )

    with pytest.raises(
        MetadataValidationManifestError,
        match="duplicate JSON field",
    ):
        ProtocolFreeze.read_json(target)


def test_frozen_artifact_hash_is_line_ending_stable(tmp_path):
    lf = tmp_path / "lf.json"
    crlf = tmp_path / "crlf.json"
    lf.write_bytes(b'{\n  "key": "value"\n}\n')
    crlf.write_bytes(b'{\r\n  "key": "value"\r\n}\r\n')

    assert _frozen_artifact_sha256(lf) == _frozen_artifact_sha256(crlf)


def test_freeze_and_manifest_round_trip():
    freeze = ProtocolFreeze.read_json(FREEZE_PATH)
    manifest = ValidationManifest.read_json(MANIFEST_PATH)

    assert ProtocolFreeze.from_dict(freeze.to_dict()).to_dict() == freeze.to_dict()
    assert (
        ValidationManifest.from_dict(manifest.to_dict()).to_dict()
        == manifest.to_dict()
    )


def test_protocol_version_ranges_accept_supported_lower_bounds():
    assert _version_applies("6.14", (">=6.8",))
    assert _version_applies("7.1", (">=6.8",))
    assert _version_applies("6.8", ("6.8",))
    assert not _version_applies("6.7", (">=6.8",))
