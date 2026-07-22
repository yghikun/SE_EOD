"""Verify pinned external evidence referenced by the metadata rule registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urldefrag

from .metadata_rule_registry import (
    EvidenceSplit,
    MetadataRuleRegistry,
    RuleSource,
)


class MetadataEvidenceVerificationError(ValueError):
    """An external evidence artifact does not match its registry record."""

    def __init__(self, source_id: str, message: str) -> None:
        self.source_id = source_id
        self.message = message
        super().__init__(f"{source_id}: {message}")


@dataclass(frozen=True)
class EvidenceVerification:
    source_id: str
    locator: str
    content_sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "locator": self.locator,
            "content_sha256": self.content_sha256,
        }


def verify_external_evidence(
    registry: MetadataRuleRegistry,
    *,
    fetch: Callable[[str], bytes] | None = None,
) -> tuple[EvidenceVerification, ...]:
    fetch_content = fetch or _fetch
    sources = tuple(
        source
        for rule in registry.rules
        for source in rule.sources
        if source.dataset_split is EvidenceSplit.EXTERNAL
        and source.content_sha256
    )
    results = [
        _verify_source(source, fetch_content(source.locator)) for source in sources
    ]
    return tuple(results)


def _verify_source(source: RuleSource, content: bytes) -> EvidenceVerification:
    actual_digest = hashlib.sha256(content).hexdigest()
    if actual_digest != source.content_sha256:
        raise MetadataEvidenceVerificationError(
            source.source_id,
            f"SHA-256 mismatch: expected {source.content_sha256}, got {actual_digest}",
        )
    text = content.decode("utf-8")
    if _normalize(source.quoted_text) not in _normalize(text):
        raise MetadataEvidenceVerificationError(
            source.source_id, "quoted_text is absent from the pinned document"
        )
    return EvidenceVerification(
        source_id=source.source_id,
        locator=source.locator,
        content_sha256=actual_digest,
    )


def _fetch(locator: str) -> bytes:
    url, _fragment = urldefrag(locator)
    curl = shutil.which("curl")
    if curl:
        try:
            completed = subprocess.run(
                [
                    curl,
                    "--silent",
                    "--show-error",
                    "--location",
                    "--fail",
                    "--max-time",
                    "60",
                    "--user-agent",
                    "MOCC-SE-evidence-verifier/1.0",
                    url,
                ],
                check=True,
                capture_output=True,
                timeout=75,
            )
            return completed.stdout
        except (OSError, subprocess.SubprocessError) as exc:
            raise MetadataEvidenceVerificationError(
                locator, f"cannot fetch external evidence with curl: {exc}"
            ) from exc
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "MOCC-SE-evidence-verifier/1.0"}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except OSError as exc:
        raise MetadataEvidenceVerificationError(
            locator, f"cannot fetch external evidence: {exc}"
        ) from exc


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify pinned external MOCC-SE rule evidence."
    )
    parser.add_argument(
        "--registry",
        default="configs/metadata_rules/rule_registry_v2.json",
        help="Path to the metadata rule registry.",
    )
    args = parser.parse_args(argv)
    registry = MetadataRuleRegistry.read_json(args.registry)
    results = verify_external_evidence(registry)
    print(
        json.dumps(
            {
                "registry_id": registry.registry_id,
                "verified_external_sources": len(results),
                "sources": [result.to_dict() for result in results],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
