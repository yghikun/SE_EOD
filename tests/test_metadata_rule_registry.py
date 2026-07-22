import json
from pathlib import Path

import pytest

from src.metadata_protocol import load_metadata_protocols
from src.metadata_rule_registry import (
    EvidenceClass,
    EvidenceSplit,
    EvidenceUsage,
    MetadataRuleRegistry,
    MetadataRuleRegistryValidationError,
    RuleAuthority,
    RuleMaturity,
    validate_rule_registry,
)


ROOT = Path(__file__).parents[1]
REGISTRY_PATH = ROOT / "configs" / "metadata_rules" / "rule_registry_v2.json"
PROTOCOL_DIRECTORY = ROOT / "configs" / "metadata_protocols"


def _payload() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _registry() -> MetadataRuleRegistry:
    return MetadataRuleRegistry.from_dict(_payload())


def test_current_registry_covers_every_active_protocol_operation():
    registry, coverage = validate_rule_registry(REGISTRY_PATH, PROTOCOL_DIRECTORY)

    assert registry.active_protocol_ids == (
        "mocc.protocol_a.replay_recovery",
        "mocc.protocol_b.device_topology_rollback",
        "mocc.protocol_c.activation_accounting",
        "mocc.protocol_d.transaction_lifecycle",
        "mocc.protocol_e.allocation_lifecycle",
    )
    assert coverage.active_protocols == 5
    assert coverage.covered_operations == 12
    assert coverage.rules == 10
    assert coverage.coverage_targets == 6
    assert coverage.maturity_counts == {
        "development": 10,
        "validation": 0,
        "frozen": 0,
    }
    assert coverage.authority_counts == {
        "normative": 1,
        "confirmed": 7,
        "heuristic": 2,
    }
    assert coverage.evidence_class_counts == {
        "contract": 6,
        "implementation_evidence": 26,
        "historical_fix": 4,
        "maintainer_evidence": 4,
        "mined_hypothesis": 0,
    }
    assert coverage.evidence_usage_counts == {
        "construction": 29,
        "corroboration": 11,
        "evaluation": 0,
    }
    assert coverage.evidence_split_counts == {
        "external": 14,
        "development": 26,
        "validation": 0,
        "frozen_test": 0,
    }


def test_registry_json_round_trip_preserves_sources_and_bindings():
    registry = _registry()

    restored = MetadataRuleRegistry.from_json(registry.to_json())

    assert restored.to_dict() == registry.to_dict()
    assert restored.rules[0].maturity is RuleMaturity.DEVELOPMENT
    assert restored.rules[0].rule_authority is RuleAuthority.CONFIRMED
    assert (
        restored.rules[0].sources[0].evidence_class
        is EvidenceClass.IMPLEMENTATION_EVIDENCE
    )
    assert restored.rules[0].sources[0].usage is EvidenceUsage.CONSTRUCTION
    assert restored.rules[0].sources[0].dataset_split is EvidenceSplit.DEVELOPMENT
    assert restored.rules[0].bindings[0].operation_ids[0] == "ext4_replay_add_range"


def test_registry_write_and_read_round_trip(tmp_path):
    registry = _registry()
    target = tmp_path / "registry.json"

    registry.write_json(target)

    assert MetadataRuleRegistry.read_json(target).to_dict() == registry.to_dict()
    assert target.read_text(encoding="utf-8").endswith("\n")


def test_unknown_registry_field_is_rejected():
    payload = _payload()
    payload["ranking_hint"] = "must never alter protocol semantics"

    with pytest.raises(MetadataRuleRegistryValidationError, match="unknown field"):
        MetadataRuleRegistry.from_dict(payload)


def test_registry_version_must_be_semver():
    payload = _payload()
    payload["registry_version"] = "v1"

    with pytest.raises(MetadataRuleRegistryValidationError, match="semantic version"):
        MetadataRuleRegistry.from_dict(payload)


def test_normative_rule_requires_contract_evidence():
    payload = _payload()
    payload["rules"][0]["rule_authority"] = "normative"

    with pytest.raises(
        MetadataRuleRegistryValidationError,
        match="normative rule requires contract evidence",
    ):
        MetadataRuleRegistry.from_dict(payload)


def test_current_normative_rule_has_pinned_contract_evidence():
    rule = next(
        rule
        for rule in _registry().rules
        if rule.rule_id == "mocc.rule.transaction.ext4.journal_handle_lifecycle"
    )

    assert rule.rule_authority is RuleAuthority.NORMATIVE
    contracts = [
        source
        for source in rule.sources
        if source.evidence_class is EvidenceClass.CONTRACT
    ]
    assert [source.linux_versions for source in contracts] == [
        ("6.8",),
        ("6.14",),
        ("7.1",),
    ]
    assert all(len(source.content_sha256) == 64 for source in contracts)
    assert all("same number of times" in source.quoted_text for source in contracts)


def test_kernel_documentation_requires_versioned_url():
    payload = _payload()
    source = payload["rules"][8]["sources"][0]
    source["locator"] = (
        "https://docs.kernel.org/_sources/filesystems/journalling.rst.txt"
    )

    with pytest.raises(
        MetadataRuleRegistryValidationError, match="versioned docs.kernel.org"
    ):
        MetadataRuleRegistry.from_dict(payload)


def test_kernel_documentation_requires_digest_and_contract_quote():
    payload = _payload()
    source = payload["rules"][8]["sources"][0]
    source.pop("content_sha256")

    with pytest.raises(
        MetadataRuleRegistryValidationError, match="requires a lowercase SHA-256"
    ):
        MetadataRuleRegistry.from_dict(payload)

    payload = _payload()
    payload["rules"][8]["sources"][0].pop("quoted_text")
    with pytest.raises(
        MetadataRuleRegistryValidationError, match="exact quoted excerpt"
    ):
        MetadataRuleRegistry.from_dict(payload)


def test_external_upstream_and_maintainer_sources_require_pinned_locators():
    payload = _payload()
    replay_fix = payload["rules"][0]["sources"][-1]
    replay_fix["locator"] = (
        "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id="
        "ec0a7500d8eace5b4f305fa0c594dd148f0e8d29"
    )
    with pytest.raises(
        MetadataRuleRegistryValidationError, match="torvalds/linux patch URL"
    ):
        MetadataRuleRegistry.from_dict(payload)

    payload = _payload()
    maintainer = payload["rules"][2]["sources"][-1]
    maintainer["locator"] = maintainer["locator"].removesuffix("/raw")
    with pytest.raises(
        MetadataRuleRegistryValidationError, match="Message-ID /raw URL"
    ):
        MetadataRuleRegistry.from_dict(payload)


def test_confirmed_rule_requires_distinct_evidence_classes():
    payload = _payload()
    payload["rules"][0]["rule_authority"] = "confirmed"
    payload["rules"][0]["sources"] = [
        source
        for source in payload["rules"][0]["sources"]
        if source["evidence_class"] == "implementation_evidence"
    ]

    with pytest.raises(
        MetadataRuleRegistryValidationError,
        match="distinct evidence classes",
    ):
        MetadataRuleRegistry.from_dict(payload)


def test_construction_evidence_cannot_use_validation_split():
    payload = _payload()
    payload["rules"][0]["sources"][0]["dataset_split"] = "validation"

    with pytest.raises(
        MetadataRuleRegistryValidationError,
        match="construction evidence must be external or development",
    ):
        MetadataRuleRegistry.from_dict(payload)


def test_development_rule_cannot_consume_evaluation_evidence():
    payload = _payload()
    source = dict(payload["rules"][0]["sources"][0])
    source["source_id"] = "linux.ext4.fast_commit.replay.v6_8.validation"
    source["usage"] = "evaluation"
    source["dataset_split"] = "validation"
    payload["rules"][0]["sources"].append(source)

    with pytest.raises(
        MetadataRuleRegistryValidationError,
        match="development rules must not consume",
    ):
        MetadataRuleRegistry.from_dict(payload)


def test_frozen_rule_requires_frozen_test_evidence():
    payload = _payload()
    payload["rules"][0]["maturity"] = "frozen"

    with pytest.raises(
        MetadataRuleRegistryValidationError,
        match="frozen maturity requires frozen_test",
    ):
        MetadataRuleRegistry.from_dict(payload)


def test_same_locator_cannot_construct_and_evaluate_rule():
    payload = _payload()
    rule = payload["rules"][0]
    evaluation = dict(rule["sources"][0])
    evaluation["source_id"] = "linux.ext4.fast_commit.replay.v6_8.evaluation"
    evaluation["usage"] = "evaluation"
    evaluation["dataset_split"] = "validation"
    rule["sources"].append(evaluation)
    rule["maturity"] = "validation"

    with pytest.raises(
        MetadataRuleRegistryValidationError,
        match="same locator cannot be both construction and evaluation",
    ):
        MetadataRuleRegistry.from_dict(payload)


def test_duplicate_json_fields_are_rejected():
    payload = REGISTRY_PATH.read_text(encoding="utf-8")
    duplicated = payload.replace(
        '"schema_version": 2,',
        '"schema_version": 2, "schema_version": 2,',
        1,
    )

    with pytest.raises(MetadataRuleRegistryValidationError, match="duplicate JSON field"):
        MetadataRuleRegistry.from_json(duplicated)


def test_linux_source_locator_is_versioned_and_portable():
    payload = _payload()
    payload["rules"][0]["sources"][0]["locator"] = "fs/ext4/fast_commit.c"

    with pytest.raises(
        MetadataRuleRegistryValidationError,
        match="linux_source locator must use linux:vVERSION",
    ):
        MetadataRuleRegistry.from_dict(payload)


def test_source_version_must_fit_rule_applicability():
    payload = _payload()
    payload["rules"][0]["sources"][0]["linux_versions"] = ["5.10"]

    with pytest.raises(
        MetadataRuleRegistryValidationError,
        match="versioned locator v6.8 requires exactly",
    ):
        MetadataRuleRegistry.from_dict(payload)


def test_source_filesystem_must_fit_rule_applicability():
    payload = _payload()
    payload["rules"][0]["sources"][0]["filesystems"] = ["xfs"]

    with pytest.raises(
        MetadataRuleRegistryValidationError,
        match="outside the rule applicability: xfs",
    ):
        MetadataRuleRegistry.from_dict(payload)


def test_every_applicability_pair_requires_supporting_evidence_coverage():
    payload = _payload()
    payload["rules"][0]["rule_authority"] = "heuristic"
    payload["rules"][0]["sources"] = [
        source
        for source in payload["rules"][0]["sources"]
        if "7.1" not in source["linux_versions"]
    ]

    with pytest.raises(
        MetadataRuleRegistryValidationError,
        match=r"missing applicability pair.*ext4@7\.1",
    ):
        MetadataRuleRegistry.from_dict(payload)


def test_rule_must_reference_a_defined_family():
    payload = _payload()
    payload["rules"][0]["family_id"] = "unknown_family"

    with pytest.raises(MetadataRuleRegistryValidationError, match="undefined family"):
        MetadataRuleRegistry.from_dict(payload)


def test_rule_binding_must_reference_an_active_protocol():
    payload = _payload()
    payload["rules"][0]["bindings"][0]["protocol_id"] = (
        "mocc.protocol.example.fixture"
    )
    registry = MetadataRuleRegistry.from_dict(payload)

    with pytest.raises(
        MetadataRuleRegistryValidationError,
        match="binding must reference an active protocol",
    ):
        registry.validate_protocols(load_metadata_protocols(PROTOCOL_DIRECTORY))


def test_rule_binding_must_reference_a_real_operation():
    payload = _payload()
    payload["rules"][0]["bindings"][0]["operation_ids"][0] = "missing_operation"
    registry = MetadataRuleRegistry.from_dict(payload)

    with pytest.raises(
        MetadataRuleRegistryValidationError,
        match="references undefined operation",
    ):
        registry.validate_protocols(load_metadata_protocols(PROTOCOL_DIRECTORY))


def test_every_active_operation_requires_at_least_one_rule_binding():
    payload = _payload()
    payload["rules"][0]["bindings"][0]["operation_ids"].remove(
        "ext4_replay_add_range"
    )
    registry = MetadataRuleRegistry.from_dict(payload)

    with pytest.raises(
        MetadataRuleRegistryValidationError,
        match="active operation.*have no rule binding",
    ):
        registry.validate_protocols(load_metadata_protocols(PROTOCOL_DIRECTORY))


def test_protocol_iterators_are_validated_without_being_consumed_twice():
    registry = _registry()
    protocols = load_metadata_protocols(PROTOCOL_DIRECTORY)

    coverage = registry.validate_protocols(item for item in protocols)

    assert coverage.covered_operations == 12
