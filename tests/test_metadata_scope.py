import json

import pytest

from src.metadata_scope import MetadataScope, MetadataScopeValidationError


def _scope() -> MetadataScope:
    return MetadataScope.read_json("configs/metadata_scope/metadata_scope_v1.json")


def test_scope_loads_metawindow_boundary():
    scope = _scope()

    assert scope.scope_id == "metadata_residual.metadata_scope"
    assert scope.target_filesystems == ("ext4", "xfs", "btrfs", "f2fs")
    assert scope.decision_for(3).status == "out_of_scope"
    assert scope.decision_for(12).domain_ids == ("quota_refcount",)


def test_scope_rejects_in_scope_decision_without_domain():
    scope = _scope()
    payload = scope.to_dict()
    payload["confirmed_bug_decisions"] = [
        {
            "bug_id": 99,
            "status": "in_scope",
            "domain_ids": [],
            "rationale": "invalid fixture",
        }
    ]

    with pytest.raises(MetadataScopeValidationError, match="requires domain_ids"):
        MetadataScope.from_dict(payload)


def test_scope_rejects_unknown_domain_in_decision():
    scope = _scope()
    payload = scope.to_dict()
    payload["confirmed_bug_decisions"] = [
        {
            "bug_id": 99,
            "status": "in_scope",
            "domain_ids": ["not_a_domain"],
            "rationale": "invalid fixture",
        }
    ]

    with pytest.raises(MetadataScopeValidationError, match="unknown domain"):
        MetadataScope.from_dict(payload)


def test_scope_json_round_trip():
    scope = _scope()
    encoded = json.dumps(scope.to_dict())
    decoded = MetadataScope.from_dict(json.loads(encoded))

    assert decoded.to_dict() == scope.to_dict()
