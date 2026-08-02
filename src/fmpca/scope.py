from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


class ScopeTaxonomyError(ValueError):
    """Raised when taxonomy or scope evidence violates the executable contract."""


@dataclass(frozen=True)
class ScopeAssessment:
    protocol_id: str
    declared_semantic_scope: str
    freeze_boundary: str
    declaration_valid: bool
    common_candidate_ready: bool
    common_freeze_ready: bool
    common_heldout_validated: bool
    failed_scope_gates: List[str]
    failed_candidate_gates: List[str]
    failed_freeze_gates: List[str]
    failed_heldout_gates: List[str]
    applicable_filesystems: List[str]
    non_applicable_filesystems: List[str]
    unresolved_filesystems: List[str]
    cross_filesystem_claim_allowed: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _load_json(path: str) -> Dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ScopeTaxonomyError("scope JSON root must be an object")
    return value


def _require_keys(value: Mapping[str, Any], required: Sequence[str], label: str) -> None:
    missing = sorted(set(required) - set(value))
    if missing:
        raise ScopeTaxonomyError(f"{label} is missing required keys: {missing}")


def load_taxonomy(path: str) -> Dict[str, Any]:
    taxonomy = _load_json(path)
    _require_keys(
        taxonomy,
        [
            "schema_version",
            "taxonomy_id",
            "taxonomy_version",
            "semantic_scopes",
            "freeze_boundaries",
            "correspondence_dimensions",
            "validation_roles",
            "applicability",
            "common_readiness",
            "scope_declaration_required_gates",
            "current_protocol_scopes",
        ],
        "taxonomy",
    )
    if taxonomy["schema_version"] != 1:
        raise ScopeTaxonomyError("unsupported taxonomy schema_version")

    scopes = taxonomy["semantic_scopes"]
    boundaries = taxonomy["freeze_boundaries"]
    if set(scopes) != {"COMMON", "FS_FAMILY", "FS_SPECIFIC"}:
        raise ScopeTaxonomyError("semantic scopes must be COMMON, FS_FAMILY and FS_SPECIFIC")
    if set(boundaries) != {"STANDARD", "NARROW_FREEZE"}:
        raise ScopeTaxonomyError("freeze boundaries must be STANDARD and NARROW_FREEZE")

    dimensions = taxonomy["correspondence_dimensions"]
    if dimensions != ["object", "relation", "lifecycle", "authority", "deadline"]:
        raise ScopeTaxonomyError("correspondence dimensions must preserve semantic decision order")
    if len(dimensions) != len(set(dimensions)):
        raise ScopeTaxonomyError("correspondence dimensions must be unique")

    applicability = taxonomy["applicability"]
    _require_keys(
        applicability,
        ["statuses", "non_applicable_reason_codes", "rules"],
        "applicability",
    )
    if set(applicability["statuses"]) != {
        "APPLICABLE",
        "NON_APPLICABLE",
        "UNRESOLVED",
    }:
        raise ScopeTaxonomyError("invalid applicability statuses")

    readiness = taxonomy["common_readiness"]
    _require_keys(
        readiness,
        [
            "candidate_required_gates",
            "freeze_required_gates",
            "heldout_required_gates",
        ],
        "common readiness",
    )
    for stage, gates in readiness.items():
        if not isinstance(gates, list) or not gates or len(gates) != len(set(gates)):
            raise ScopeTaxonomyError(f"{stage} must contain unique readiness gates")

    scope_gates = taxonomy["scope_declaration_required_gates"]
    if set(scope_gates) != set(scopes):
        raise ScopeTaxonomyError("scope declaration gates must cover every semantic scope")
    for scope, gates in scope_gates.items():
        if not isinstance(gates, list) or not gates or len(gates) != len(set(gates)):
            raise ScopeTaxonomyError(
                f"{scope} must contain unique scope declaration gates"
            )

    seen_protocols = set()
    for entry in taxonomy["current_protocol_scopes"]:
        _require_keys(
            entry,
            [
                "protocol_id",
                "semantic_scope",
                "freeze_boundary",
                "filesystem_or_family",
                "cross_filesystem_status",
                "rationale",
            ],
            "current protocol scope",
        )
        if entry["protocol_id"] in seen_protocols:
            raise ScopeTaxonomyError("current protocol IDs must be unique")
        seen_protocols.add(entry["protocol_id"])
        if entry["semantic_scope"] not in scopes:
            raise ScopeTaxonomyError("current protocol uses an unknown semantic scope")
        if entry["freeze_boundary"] not in boundaries:
            raise ScopeTaxonomyError("current protocol uses an unknown freeze boundary")
        if entry["cross_filesystem_status"] not in applicability["statuses"]:
            raise ScopeTaxonomyError("current protocol uses an unknown applicability status")
        if entry["semantic_scope"] != "COMMON" and entry["cross_filesystem_status"] == "APPLICABLE":
            raise ScopeTaxonomyError(
                "a non-COMMON current protocol cannot claim cross-filesystem applicability"
            )
    return taxonomy


def current_scope_index(taxonomy: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        entry["protocol_id"]: dict(entry)
        for entry in taxonomy["current_protocol_scopes"]
    }


def _validate_filesystem_evidence(
    taxonomy: Mapping[str, Any], evidence: Sequence[Mapping[str, Any]]
) -> None:
    statuses = set(taxonomy["applicability"]["statuses"])
    reason_codes = set(taxonomy["applicability"]["non_applicable_reason_codes"])
    roles = set(taxonomy["validation_roles"])
    dimensions = set(taxonomy["correspondence_dimensions"])
    seen = set()
    for item in evidence:
        _require_keys(item, ["filesystem", "applicability"], "filesystem evidence")
        filesystem = item["filesystem"]
        if filesystem in seen:
            raise ScopeTaxonomyError("filesystem evidence entries must be unique")
        seen.add(filesystem)
        status = item["applicability"]
        if status not in statuses:
            raise ScopeTaxonomyError(f"unknown applicability status for {filesystem}")
        if status == "NON_APPLICABLE":
            if item.get("reason_code") not in reason_codes:
                raise ScopeTaxonomyError(
                    f"NON_APPLICABLE evidence for {filesystem} needs a controlled reason code"
                )
            if not str(item.get("evidence_note", "")).strip():
                raise ScopeTaxonomyError(
                    f"NON_APPLICABLE evidence for {filesystem} needs an evidence note"
                )
        elif status == "APPLICABLE":
            _require_keys(
                item,
                [
                    "validation_role",
                    "operation_family",
                    "correspondence",
                    "source_witness_closed",
                    "replay_closed",
                    "proof_closure_closed",
                ],
                f"APPLICABLE evidence for {filesystem}",
            )
            if item["validation_role"] not in roles:
                raise ScopeTaxonomyError(f"unknown validation role for {filesystem}")
            if set(item["correspondence"]) != dimensions:
                raise ScopeTaxonomyError(
                    f"correspondence for {filesystem} must declare every dimension"
                )


def _all_true(items: Sequence[Mapping[str, Any]], field: str) -> bool:
    return bool(items) and all(bool(item.get(field, False)) for item in items)


def _failed(required: Sequence[str], gates: Mapping[str, bool]) -> List[str]:
    missing = sorted(set(required) - set(gates))
    if missing:
        raise ScopeTaxonomyError(f"readiness implementation is missing gates: {missing}")
    return sorted(name for name in required if not gates[name])


def assess_scope(
    taxonomy: Mapping[str, Any], declaration: Mapping[str, Any]
) -> ScopeAssessment:
    _require_keys(
        declaration,
        [
            "protocol_id",
            "semantic_scope",
            "freeze_boundary",
            "canonical_dsl_defined",
            "bindings_defined",
            "source_witness_defined",
            "result_partition_closed",
            "hashes_locked",
            "filesystems",
        ],
        "scope declaration",
    )
    semantic_scope = declaration["semantic_scope"]
    freeze_boundary = declaration["freeze_boundary"]
    if semantic_scope not in taxonomy["semantic_scopes"]:
        raise ScopeTaxonomyError(f"unknown semantic scope: {semantic_scope}")
    if freeze_boundary not in taxonomy["freeze_boundaries"]:
        raise ScopeTaxonomyError(f"unknown freeze boundary: {freeze_boundary}")

    filesystems = declaration["filesystems"]
    if not isinstance(filesystems, list):
        raise ScopeTaxonomyError("filesystems must be a list")
    _validate_filesystem_evidence(taxonomy, filesystems)
    applicable = [item for item in filesystems if item["applicability"] == "APPLICABLE"]
    non_applicable = [
        item for item in filesystems if item["applicability"] == "NON_APPLICABLE"
    ]
    unresolved = [item for item in filesystems if item["applicability"] == "UNRESOLVED"]
    freeze_members = [
        item for item in applicable if item["validation_role"] != "HELD_OUT"
    ]
    heldout = [item for item in applicable if item["validation_role"] == "HELD_OUT"]

    candidate_gates = {
        "canonical_dsl_defined": bool(declaration["canonical_dsl_defined"]),
        "bindings_defined": bool(declaration["bindings_defined"]),
        "source_witness_defined": bool(declaration["source_witness_defined"]),
        "development_fs_replay_closed": any(
            item["validation_role"] == "DEVELOPMENT" and item["replay_closed"]
            for item in applicable
        ),
        "result_partition_closed": bool(declaration["result_partition_closed"]),
    }
    readiness = taxonomy["common_readiness"]
    failed_candidate = _failed(readiness["candidate_required_gates"], candidate_gates)
    candidate_ready = not failed_candidate

    correspondence_closed = bool(freeze_members) and all(
        all(bool(value) for value in item["correspondence"].values())
        for item in freeze_members
    )
    families = [item["operation_family"] for item in freeze_members]
    hashes = declaration["hashes_locked"]
    if not isinstance(hashes, dict):
        raise ScopeTaxonomyError("hashes_locked must be an object")
    freeze_gates = {
        "common_candidate_ready": candidate_ready,
        "minimum_two_applicable_filesystems": len(freeze_members) >= 2,
        "all_correspondence_dimensions_closed": correspondence_closed,
        "independent_operation_family_per_filesystem": bool(families)
        and len(families) == len(set(families)),
        "source_witness_closed_per_filesystem": _all_true(
            freeze_members, "source_witness_closed"
        ),
        "replay_closed_per_filesystem": _all_true(freeze_members, "replay_closed"),
        "proof_closure_closed_per_filesystem": _all_true(
            freeze_members, "proof_closure_closed"
        ),
        "protocol_binding_test_hashes_locked": all(
            bool(hashes.get(name, False)) for name in ("protocol", "binding", "test")
        ),
    }
    failed_freeze = _failed(readiness["freeze_required_gates"], freeze_gates)
    freeze_ready = not failed_freeze

    heldout_correspondence = bool(heldout) and all(
        all(bool(value) for value in item["correspondence"].values())
        for item in heldout
    )
    no_modifications = bool(heldout) and all(
        not bool(item.get(field, False))
        for item in heldout
        for field in (
            "protocol_modified_after_freeze",
            "binding_modified_after_freeze",
            "acceptance_relaxed_after_freeze",
        )
    )
    heldout_gates = {
        "common_freeze_ready": freeze_ready,
        "third_filesystem_post_freeze": bool(heldout)
        and len({item["filesystem"] for item in applicable}) >= 3
        and all(bool(item.get("post_freeze", False)) for item in heldout),
        "heldout_correspondence_closed": heldout_correspondence,
        "heldout_source_witness_closed": _all_true(heldout, "source_witness_closed"),
        "heldout_replay_closed": _all_true(heldout, "replay_closed"),
        "heldout_proof_closure_closed": _all_true(heldout, "proof_closure_closed"),
        "no_post_freeze_semantic_modifications": no_modifications,
    }
    failed_heldout = _failed(readiness["heldout_required_gates"], heldout_gates)
    heldout_validated = not failed_heldout

    filesystem_family_id = str(declaration.get("filesystem_family_id", "")).strip()
    scope_gates = {
        "at_least_one_applicable_filesystem": bool(freeze_members),
        "named_filesystem_family": bool(filesystem_family_id),
        "minimum_two_family_members": len(freeze_members) >= 2,
        "all_members_match_named_family": bool(freeze_members)
        and bool(filesystem_family_id)
        and all(
            item.get("filesystem_family_id") == filesystem_family_id
            for item in freeze_members
        ),
        "common_freeze_ready": freeze_ready,
    }
    failed_scope = _failed(
        taxonomy["scope_declaration_required_gates"][semantic_scope], scope_gates
    )
    declaration_valid = not failed_scope
    return ScopeAssessment(
        protocol_id=declaration["protocol_id"],
        declared_semantic_scope=semantic_scope,
        freeze_boundary=freeze_boundary,
        declaration_valid=declaration_valid,
        common_candidate_ready=candidate_ready,
        common_freeze_ready=freeze_ready,
        common_heldout_validated=heldout_validated,
        failed_scope_gates=failed_scope,
        failed_candidate_gates=failed_candidate,
        failed_freeze_gates=failed_freeze,
        failed_heldout_gates=failed_heldout,
        applicable_filesystems=[item["filesystem"] for item in applicable],
        non_applicable_filesystems=[item["filesystem"] for item in non_applicable],
        unresolved_filesystems=[item["filesystem"] for item in unresolved],
        cross_filesystem_claim_allowed=semantic_scope == "COMMON" and freeze_ready,
    )


def assess_scope_files(taxonomy_path: str, declaration_path: str) -> ScopeAssessment:
    return assess_scope(load_taxonomy(taxonomy_path), _load_json(declaration_path))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.scope")
    parser.add_argument("--taxonomy", required=True)
    parser.add_argument("--declaration")
    parser.add_argument("--list-current", action="store_true")
    args = parser.parse_args(argv)
    taxonomy = load_taxonomy(args.taxonomy)
    if args.list_current:
        print(json.dumps(current_scope_index(taxonomy), indent=2, sort_keys=True))
        return 0
    if not args.declaration:
        parser.error("--declaration is required unless --list-current is used")
    assessment = assess_scope(taxonomy, _load_json(args.declaration))
    print(json.dumps(assessment.to_dict(), indent=2, sort_keys=True))
    return 0 if assessment.declaration_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
