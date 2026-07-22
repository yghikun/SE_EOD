import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from src.metadata_evidence_verifier import (
    MetadataEvidenceVerificationError,
    verify_external_evidence,
)
from src.metadata_rule_registry import EvidenceSplit, MetadataRuleRegistry, SourceKind


ROOT = Path(__file__).parents[1]
REGISTRY_PATH = ROOT / "configs" / "metadata_rules" / "rule_registry_v2.json"


def _registry_with_content(content: bytes, quoted_text: str) -> MetadataRuleRegistry:
    registry = MetadataRuleRegistry.read_json(REGISTRY_PATH)
    rule = next(
        rule
        for rule in registry.rules
        if rule.rule_id == "mocc.rule.transaction.ext4.journal_handle_lifecycle"
    )
    source = next(
        source
        for source in rule.sources
        if source.kind is SourceKind.KERNEL_DOCUMENTATION
    )
    source = replace(
        source,
        content_sha256=hashlib.sha256(content).hexdigest(),
        quoted_text=quoted_text,
    )
    return replace(registry, rules=(replace(rule, sources=(source,)),))


def test_external_evidence_verifies_digest_and_normalized_quote():
    content = b"must call journal_stop\n the same number of times as journal_start"
    registry = _registry_with_content(
        content, "journal_stop the same number of times as journal_start"
    )

    results = verify_external_evidence(registry, fetch=lambda _locator: content)

    assert len(results) == 1
    assert results[0].content_sha256 == hashlib.sha256(content).hexdigest()


def test_external_evidence_rejects_digest_drift():
    registry = _registry_with_content(b"original", "original")

    with pytest.raises(MetadataEvidenceVerificationError, match="SHA-256 mismatch"):
        verify_external_evidence(registry, fetch=lambda _locator: b"changed")


def test_external_evidence_rejects_missing_quote():
    content = b"pinned document without the expected sentence"
    registry = _registry_with_content(content, "required contract sentence")

    with pytest.raises(MetadataEvidenceVerificationError, match="quoted_text is absent"):
        verify_external_evidence(registry, fetch=lambda _locator: content)


def test_external_evidence_includes_pinned_commits_and_maintainer_mail():
    registry = MetadataRuleRegistry.read_json(REGISTRY_PATH)
    expected = {
        source.source_id
        for rule in registry.rules
        for source in rule.sources
        if source.dataset_split is EvidenceSplit.EXTERNAL
        and source.content_sha256
    }
    by_locator = {
        source.locator: source.quoted_text.encode("utf-8")
        for rule in registry.rules
        for source in rule.sources
        if source.dataset_split is EvidenceSplit.EXTERNAL
        and source.content_sha256
    }
    registry = replace(
        registry,
        rules=tuple(
            replace(
                rule,
                sources=tuple(
                    replace(
                        source,
                        content_sha256=hashlib.sha256(
                            by_locator[source.locator]
                        ).hexdigest(),
                    )
                    if source.locator in by_locator
                    else source
                    for source in rule.sources
                ),
            )
            for rule in registry.rules
        ),
    )

    results = verify_external_evidence(
        registry, fetch=lambda locator: by_locator[locator]
    )

    assert {result.source_id for result in results} == expected
