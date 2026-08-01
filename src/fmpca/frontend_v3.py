from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from .frontend import extract_function
from .frontend_extensions import (
    RevisionSourceBinding,
    _git_source,
    analyze_revision_source,
)


@dataclass(frozen=True)
class LifecycleWitness:
    evidence: List[Dict[str, Any]]
    origin_closed: bool
    import_closed: bool
    normal_handoff_closed: bool
    normal_cleanup_closed: bool
    caller_order_closed: bool

    @property
    def selected_normal_path_closed(self) -> bool:
        return all(
            (
                self.origin_closed,
                self.import_closed,
                self.normal_handoff_closed,
                self.normal_cleanup_closed,
                self.caller_order_closed,
            )
        )


def _match_evidence(function: Any, kind: str, pattern: str) -> Dict[str, Any]:
    match = re.search(pattern, function.masked_text, re.MULTILINE)
    return {
        "kind": kind,
        "function": function.name,
        "found": match is not None,
        "line": function.line_for_offset(match.start()) if match else None,
    }


def analyze_preexisting_attachment_lifecycle(
    binding: RevisionSourceBinding,
    repo: str,
    revision: str,
    source_path: str,
    function_roles: Dict[str, str],
    cleanup_consumers: Sequence[str],
) -> LifecycleWitness:
    """Build a selected cross-function origin-to-settlement source witness."""
    required_roles = {
        "origin",
        "merge_driver",
        "merge_helper",
        "handoff",
        "cleanup",
        "caller",
    }
    missing = required_roles - set(function_roles)
    if missing:
        raise ValueError(f"missing lifecycle function roles: {sorted(missing)}")

    source = _git_source(repo, revision, source_path)
    functions = {
        role: extract_function(source, name) for role, name in function_roles.items()
    }
    relation = binding.field_paths[0]
    owner, field = relation.split(".", 1)
    attachment = binding.attachment_primitives[0]
    clear_primitive = binding.restore_sequences[0]["required_primitives"][0]

    origin = _match_evidence(
        functions["origin"],
        "attachment_origin",
        rf"\b{re.escape(owner)}\s*->\s*{re.escape(field)}\s*=\s*"
        rf"{re.escape(attachment)}\s*\(",
    )
    imported = _match_evidence(
        functions["merge_driver"],
        "attachment_identity_import",
        rf"\b{re.escape(owner)}\s*->\s*{re.escape(field)}\s*(?:==|!=)\s*reloc_root\b",
    )
    driver_to_helper = _match_evidence(
        functions["merge_driver"],
        "merge_driver_to_helper",
        rf"\b{re.escape(function_roles['merge_helper'])}\s*\(",
    )
    helper_to_handoff = _match_evidence(
        functions["merge_helper"],
        "merge_helper_to_handoff",
        rf"\b{re.escape(function_roles['handoff'])}\s*\(",
    )
    handoff = _match_evidence(
        functions["handoff"],
        "normal_cleanup_handoff",
        rf"\blist_add_tail\s*\(\s*&\s*{re.escape(owner)}\s*->\s*reloc_dirty_list\s*,"
        rf"\s*&\s*rc\s*->\s*dirty_subvol_roots\s*\)",
    )
    cleanup_clear = _match_evidence(
        functions["cleanup"],
        "normal_relation_clear",
        rf"\b{re.escape(clear_primitive)}\s*\(\s*{re.escape(owner)}\s*\)",
    )
    consumer_pattern = "|".join(re.escape(item) for item in cleanup_consumers)
    cleanup_consumer = _match_evidence(
        functions["cleanup"],
        "normal_reference_consumer",
        rf"\b(?:{consumer_pattern})\s*\(\s*reloc_root\b",
    )
    caller = functions["caller"]
    merge_call = re.search(
        rf"\b{re.escape(function_roles['merge_driver'])}\s*\(", caller.masked_text
    )
    cleanup_call = re.search(
        rf"\b{re.escape(function_roles['cleanup'])}\s*\(", caller.masked_text
    )
    caller_order = {
        "kind": "caller_settlement_order",
        "function": caller.name,
        "found": bool(
            merge_call and cleanup_call and merge_call.start() < cleanup_call.start()
        ),
        "merge_line": caller.line_for_offset(merge_call.start()) if merge_call else None,
        "cleanup_line": caller.line_for_offset(cleanup_call.start()) if cleanup_call else None,
    }
    evidence = [
        origin,
        imported,
        driver_to_helper,
        helper_to_handoff,
        handoff,
        cleanup_clear,
        cleanup_consumer,
        caller_order,
    ]
    return LifecycleWitness(
        evidence=evidence,
        origin_closed=origin["found"],
        import_closed=imported["found"],
        normal_handoff_closed=all(
            item["found"] for item in (driver_to_helper, helper_to_handoff, handoff)
        ),
        normal_cleanup_closed=cleanup_clear["found"] and cleanup_consumer["found"],
        caller_order_closed=caller_order["found"],
    )


def analyze_relocation_revision_source(
    binding: RevisionSourceBinding,
    repo: str,
    revision: str,
    source_path: str,
    function_name: str,
    source_version: str,
):
    """Adapt frozen revision evidence to the v0.3 preexisting-attachment draft."""
    analysis = analyze_revision_source(
        binding, repo, revision, source_path, function_name, source_version
    )
    relation = binding.field_paths[0]
    for index, event in enumerate(analysis.events):
        if "recovery_owner" in event.roles:
            event.roles["relocation_owner"] = event.roles.pop("recovery_owner")
        if index == 0 and event.event == binding.event_names["snapshot"]:
            event.data["value"] = "DETACHED"
        if event.event == binding.event_names["failure"]:
            event.data["relation"] = relation
    return analysis
