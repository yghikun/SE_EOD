import json
from pathlib import Path

import pytest

from src.metadata_protocol import MetadataProtocol, MetadataProtocolValidationError
from src.metadata_protocol_package import (
    MetadataProtocolPackageError,
    compose_protocol_package,
)


ROOT = Path(__file__).parents[1]
PROTOCOL_D = (
    ROOT
    / "configs"
    / "metadata_protocols"
    / "protocol_d_transaction_lifecycle_v2.json"
)
FAMILY = ROOT / "configs" / "protocol_families" / "transaction_lifecycle_v1.json"
BINDING = ROOT / "configs" / "filesystem_bindings" / "xfs_transaction_v1.json"
OPERATION = ROOT / "configs" / "operations" / "xfs_acl_mode_transaction_v1.json"


def test_package_composes_existing_runtime_protocol():
    payload = compose_protocol_package(PROTOCOL_D)
    protocol = MetadataProtocol.from_dict(payload)

    assert protocol.protocol_id == "mocc.protocol_d.transaction_lifecycle"
    assert {item.operation_id for item in protocol.operations} == {
        "xfs_acl_mode_transaction",
        "ext4_verity_journal_transaction",
    }
    assert {item.summary_id for item in protocol.callee_summaries} == {
        "xfs.transaction.alloc",
        "xfs.transaction.commit",
        "xfs.transaction.cancel",
        "ext4.transaction.start",
        "ext4.transaction.stop",
    }


def test_family_contains_semantics_but_no_filesystem_api_names():
    family = FAMILY.read_text(encoding="utf-8")

    assert "transaction_resource_must_close" in family
    assert "xfs_" not in family
    assert "ext4_" not in family
    assert "btrfs_" not in family


def test_binding_contains_api_semantics_but_no_operation_entry():
    binding = BINDING.read_text(encoding="utf-8")

    assert "xfs_trans_alloc" in binding
    assert "xfs_acl_set_mode" not in binding


def test_operation_contains_entry_but_no_callee_summary_definition():
    operation = json.loads(OPERATION.read_text(encoding="utf-8"))

    assert operation["entry_functions"] == ["xfs_acl_set_mode"]
    assert "actions" not in operation
    assert "callees" not in operation


def test_package_rejects_operation_with_missing_binding(tmp_path):
    operation = json.loads(OPERATION.read_text(encoding="utf-8"))
    operation["binding_id"] = "xfs.missing"
    operation_path = tmp_path / "operation.json"
    operation_path.write_text(json.dumps(operation), encoding="utf-8")
    manifest = json.loads(PROTOCOL_D.read_text(encoding="utf-8"))
    manifest["family"] = str(FAMILY)
    manifest["bindings"] = [str(BINDING)]
    manifest["operations"] = [str(operation_path)]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        MetadataProtocolPackageError, match="references an unloaded binding"
    ):
        compose_protocol_package(manifest_path)


def test_metadata_protocol_read_wraps_package_errors(tmp_path):
    manifest = json.loads(PROTOCOL_D.read_text(encoding="utf-8"))
    manifest["family"] = "missing-family.json"
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(MetadataProtocolValidationError, match="does not exist"):
        MetadataProtocol.read_json(manifest_path)


def test_package_rejects_binding_action_with_unknown_role(tmp_path):
    binding = json.loads(BINDING.read_text(encoding="utf-8"))
    binding["actions"][0]["object_binding"]["abstract_role"] = "unknown_role"
    binding_path = tmp_path / "binding.json"
    binding_path.write_text(json.dumps(binding), encoding="utf-8")
    manifest = json.loads(PROTOCOL_D.read_text(encoding="utf-8"))
    manifest["family"] = str(FAMILY)
    manifest["bindings"] = [str(binding_path)]
    manifest["operations"] = [str(OPERATION)]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        MetadataProtocolPackageError, match="undefined family role"
    ):
        compose_protocol_package(manifest_path)


def test_package_rejects_duplicate_json_fields(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        '{"protocol_package_schema_version": 1, '
        '"protocol_package_schema_version": 1}',
        encoding="utf-8",
    )

    with pytest.raises(MetadataProtocolPackageError, match="duplicate JSON field"):
        compose_protocol_package(manifest_path)
