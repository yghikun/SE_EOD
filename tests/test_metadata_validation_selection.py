from pathlib import Path
from types import SimpleNamespace

import pytest

from src.metadata_validation_manifest import ProtocolFreeze
from src.metadata_validation_selection import (
    _candidate_from_analysis,
    _draft_manifest,
    _exact_entry_space,
    _parse_source,
    _stratified_select,
)


def test_parse_source_requires_version_path_pair():
    assert _parse_source("7.1=linux-sources/linux-v7.1-fs/fs") == (
        "7.1",
        Path("linux-sources/linux-v7.1-fs/fs"),
    )

    with pytest.raises(ValueError, match="VERSION=PATH"):
        _parse_source("linux-sources/linux-v7.1-fs/fs")


def test_candidate_from_analysis_builds_manifest_ready_payload(tmp_path):
    source = tmp_path / "linux-sources" / "linux-v9.9-fs" / "fs" / "ext4" / "demo.c"
    source.parent.mkdir(parents=True)
    source.write_text("int fresh_case(void) { return 0; }\n", encoding="utf-8")
    applicability = SimpleNamespace(
        match_kind="semantic",
        to_dict=lambda: {
            "operation_id": "operation",
            "match_kind": "semantic",
        },
    )
    analysis = SimpleNamespace(
        applicability=applicability,
        result=SimpleNamespace(
            source_file=source.as_posix(),
            protocol_id="test.protocol",
            operation_id="operation",
            function="fresh_case",
            candidates=(),
            unknown=(),
        ),
    )

    candidate = _candidate_from_analysis(
        tmp_path,
        analysis,
        "9.9",
        {("test.protocol", "operation", "ext4", "9.9"): ("test.rule",)},
        set(),
    )

    assert candidate is not None
    assert candidate["source_path"] == "linux-sources/linux-v9.9-fs/fs/ext4/demo.c"
    assert candidate["candidate_rule_ids"] == ["test.rule"]
    assert candidate["applicability_match_kind"] == "semantic"


def test_candidate_from_analysis_rejects_construction_overlap(tmp_path):
    source = tmp_path / "linux-sources" / "linux-v9.9-fs" / "fs" / "ext4" / "demo.c"
    source.parent.mkdir(parents=True)
    source.write_text("int reused(void) { return 0; }\n", encoding="utf-8")
    analysis = SimpleNamespace(
        applicability=SimpleNamespace(match_kind="exact_entry", to_dict=lambda: {}),
        result=SimpleNamespace(
            source_file=source.as_posix(),
            protocol_id="test.protocol",
            operation_id="operation",
            function="reused",
            candidates=(),
            unknown=(),
        ),
    )

    candidate = _candidate_from_analysis(
        tmp_path,
        analysis,
        "9.9",
        {("test.protocol", "operation", "ext4", "9.9"): ("test.rule",)},
        {("ext4", "9.9", "fs/ext4/demo.c", "reused")},
    )

    assert candidate is None


def test_stratified_select_is_seeded_and_protocol_balanced():
    candidates = [
        {
            "protocol_id": "protocol.a",
            "operation_id": "operation",
            "source_path": f"fs/a/{index}.c",
            "function": f"a_{index}",
        }
        for index in range(3)
    ] + [
        {
            "protocol_id": "protocol.b",
            "operation_id": "operation",
            "source_path": f"fs/b/{index}.c",
            "function": f"b_{index}",
        }
        for index in range(3)
    ]

    first = _stratified_select(candidates, 1, "seed")
    second = _stratified_select(candidates, 1, "seed")

    assert first == second
    assert [item["protocol_id"] for item in first] == ["protocol.a", "protocol.b"]


def test_exact_entry_space_reports_construction_overlap():
    operation = SimpleNamespace(
        operation_id="operation",
        entry_functions=("entry",),
    )
    protocol = SimpleNamespace(
        protocol_id="test.protocol",
        operations=(operation,),
    )
    rule = SimpleNamespace(
        rule_id="test.rule",
        filesystems=("ext4",),
        linux_versions=("9.9",),
        bindings=(
            SimpleNamespace(
                protocol_id="test.protocol",
                operation_ids=("operation",),
            ),
        ),
    )
    registry = SimpleNamespace(rules=(rule,))

    payload = _exact_entry_space(
        (protocol,),
        registry,
        {("ext4", "9.9", "fs/ext4/demo.c", "entry")},
    )

    assert payload["summary"]["registered_exact_entry_identities"] == 1
    assert payload["summary"]["construction_overlaps"] == 1
    assert payload["summary"]["available_exact_entries"] == 0
    assert payload["entries"][0]["status"] == "construction_overlap"


def test_draft_manifest_keeps_samples_blind_and_unlabeled():
    freeze = ProtocolFreeze.from_dict(
        {
            "schema_version": 1,
            "freeze_id": "test.freeze",
            "created_at": "2026-07-22",
            "status": "frozen",
            "registry_path": "configs/rules.json",
            "protocol_directory": "configs/protocols",
            "artifacts": [
                {
                    "path": "configs/rules.json",
                    "artifact_kind": "registry",
                    "logical_id": "rules",
                    "schema_version": 1,
                    "semantic_version": "1.0.0",
                    "content_sha256": "0" * 64,
                }
            ],
        }
    )
    manifest = _draft_manifest(
        freeze,
        "test.manifest",
        "1.0.0",
        "validation",
        [
            {
                "selection_key": "abcdef123456",
                "protocol_id": "test.protocol",
                "operation_id": "operation",
                "candidate_rule_ids": ["test.rule"],
                "filesystem": "ext4",
                "source_version": "9.9",
                "source_path": "linux-sources/linux-v9.9-fs/fs/ext4/demo.c",
                "source_sha256": "1" * 64,
                "function": "fresh_case",
                "applicability_match_kind": "semantic",
            }
        ],
    )

    sample = manifest["samples"][0]
    assert manifest["label_visibility"] == "blind"
    assert sample["label_status"] == "unlabeled"
    assert sample["selection_kind"] == "fresh_discovery"
    assert "out_of_scope" in sample["allowed_verdicts"]
