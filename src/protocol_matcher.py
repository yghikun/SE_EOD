"""Match suspicious candidate rows against resource protocol obligations."""

from __future__ import annotations

import json
from typing import Any

from .parser import call_name_and_args, call_name_and_first_arg
from .protocol_db import ResourceProtocol, ResourceProtocolDB
from .resource_expr import same_resource_expr
from .resource_release import call_releases_resource, cleanup_call_releases_resource
from .wrapper_summary import WrapperSummaryDB


def _json_value(value: str, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _json_list(value: str) -> list[Any]:
    parsed = _json_value(value, [])
    return parsed if isinstance(parsed, list) else []


def _json_dict(value: str) -> dict[str, Any]:
    parsed = _json_value(value, {})
    return parsed if isinstance(parsed, dict) else {}


def _row_context(row: dict[str, str]) -> dict[str, Any]:
    evidence = _json_dict(row.get("evidence", ""))
    held_resources = evidence.get("acquired_resources")
    if not isinstance(held_resources, list):
        held_resources = _json_list(row.get("held_resources", ""))
    held_resources = [item for item in held_resources if isinstance(item, dict)]

    missing_releases = evidence.get("missing_releases")
    if not isinstance(missing_releases, list):
        missing_releases = _json_list(row.get("missing_cleanup_candidates", ""))
    missing_releases = [str(item) for item in missing_releases]

    cleanup_calls = evidence.get("cleanup_calls")
    if not isinstance(cleanup_calls, list):
        cleanup_calls = _json_list(row.get("cleanup_calls", ""))
    cleanup_calls = [str(item) for item in cleanup_calls]

    final_return_expr = str(
        evidence.get("final_return_expr", row.get("final_return_expr", ""))
    )
    return {
        "held_resources": held_resources,
        "missing_releases": missing_releases,
        "cleanup_calls": cleanup_calls,
        "final_return_expr": final_return_expr,
    }


def _resource_kind(resource: dict[str, Any]) -> str:
    return str(resource.get("resource_kind") or resource.get("resource_type") or "")


def _resource_release_functions(resource: dict[str, Any]) -> list[str]:
    releases = resource.get("release_functions", [])
    if isinstance(releases, str):
        releases = [releases]
    return [str(item) for item in releases]


def _same_resource_arg(left: str, right: str) -> bool:
    return same_resource_expr(left, right)


def _release_found(
    cleanup_calls: list[str],
    protocol: ResourceProtocol,
    missing_arg: str,
    resource: dict[str, Any] | None,
) -> bool:
    for cleanup_call in cleanup_calls:
        if resource and cleanup_call_releases_resource(cleanup_call, resource):
            return True
        name, args = call_name_and_args(cleanup_call)
        arg = args[0] if args else ""
        if name in protocol.release_functions and _same_resource_arg(arg, missing_arg):
            return True
    return False


def _wrapper_evidence_for(
    cleanup_calls: list[str],
    wrapper_db: WrapperSummaryDB | None,
    protocol: ResourceProtocol,
    resource_kind: str,
) -> list[dict[str, Any]]:
    if not wrapper_db:
        return []

    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for cleanup_call in cleanup_calls:
        function_name, _ = call_name_and_first_arg(cleanup_call)
        if function_name in protocol.release_functions:
            continue
        summary = wrapper_db.find(function_name)
        if not summary:
            continue
        releases_required_action = protocol.required_action in summary.releases
        releases_protocol_action = any(
            action in protocol.release_functions for action in summary.releases
        )
        releases_kind = wrapper_db.releases_resource_kind(function_name, resource_kind)
        if not (releases_required_action or releases_protocol_action or releases_kind):
            continue
        if function_name in seen:
            continue
        seen.add(function_name)
        evidence.append(
            {
                "type": "wrapper_summary",
                "function": function_name,
                "releases": list(summary.releases),
                "resource_kinds": list(summary.resource_kinds),
                "confidence": summary.confidence,
                "description": summary.description,
            }
        )
    return evidence


def _ownership_transfer_possible(
    ownership_transfer_hints: list[dict[str, Any]] | None,
    resource_kind: str,
    resource_var: str,
) -> bool:
    if not ownership_transfer_hints:
        return False
    for hint in ownership_transfer_hints:
        if not isinstance(hint, dict):
            continue
        same_var = _same_resource_arg(str(hint.get("resource_expr", "")), resource_var)
        same_kind = str(hint.get("resource_kind", "")) == resource_kind
        if same_var or (not resource_var and same_kind):
            return True
    return False


def _matching_resources(
    held_resources: list[dict[str, Any]], missing_action: str, missing_args: list[str]
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for resource in held_resources:
        if call_releases_resource(missing_action, missing_args, resource):
            matches.append(resource)
    return matches


def _protocol_matches_resource(
    protocol: ResourceProtocol,
    resource: dict[str, Any] | None,
    missing_action: str,
) -> bool:
    if missing_action in protocol.release_functions:
        return True
    if protocol.required_action == missing_action:
        return True
    if not resource:
        return False
    if str(resource.get("acquire_func", "")) in protocol.acquire_functions:
        return True
    return False


def _candidate_protocols(
    db: ResourceProtocolDB,
    missing_action: str,
    resources: list[dict[str, Any]],
) -> list[tuple[ResourceProtocol, dict[str, Any] | None]]:
    matched: list[tuple[ResourceProtocol, dict[str, Any] | None]] = []
    seen: set[tuple[str, str]] = set()

    def add(protocol: ResourceProtocol, resource: dict[str, Any] | None = None) -> None:
        key = (protocol.protocol_id, str(resource.get("var", "")) if resource else "")
        if key not in seen:
            matched.append((protocol, resource))
            seen.add(key)

    for resource in resources:
        for protocol in db.find_by_resource_kind(_resource_kind(resource)):
            if _protocol_matches_resource(protocol, resource, missing_action):
                add(protocol, resource)
        acquire_func = str(resource.get("acquire_func", ""))
        for protocol in db.find_by_acquire_function(acquire_func):
            if _protocol_matches_resource(protocol, resource, missing_action):
                add(protocol, resource)
    if matched:
        return matched

    for protocol in db.find_by_required_action(missing_action):
        add(protocol)
    for protocol in db.find_by_release_function(missing_action):
        add(protocol)
    return matched


def match_protocol_evidence(
    row: dict[str, str],
    db: ResourceProtocolDB,
    wrapper_db: WrapperSummaryDB | None = None,
    ownership_transfer_hints: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return API protocol evidence records for one suspicious candidate row."""

    context = _row_context(row)
    held_resources = context["held_resources"]
    cleanup_calls = context["cleanup_calls"]
    protocol_evidence: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for missing_release in context["missing_releases"]:
        missing_action, missing_args = call_name_and_args(missing_release)
        missing_arg = missing_args[0] if missing_args else ""
        if not missing_action:
            continue
        resources = _matching_resources(held_resources, missing_action, missing_args)
        if not resources:
            resources = []
        for protocol, resource in _candidate_protocols(db, missing_action, resources):
            if not _protocol_matches_resource(protocol, resource, missing_action):
                continue
            key = (protocol.protocol_id, missing_release)
            if key in seen:
                continue
            seen.add(key)
            resource_kind = protocol.resource_kind
            resource_var = str(resource.get("var", "")) if resource else missing_arg
            wrapper_evidence = _wrapper_evidence_for(
                cleanup_calls, wrapper_db, protocol, resource_kind
            )
            released_by_wrapper_possible = bool(wrapper_evidence)
            ownership_possible = _ownership_transfer_possible(
                ownership_transfer_hints, resource_kind, resource_var
            )
            exceptions_to_check = list(protocol.exceptions)
            if released_by_wrapper_possible and "released_by_wrapper" not in exceptions_to_check:
                exceptions_to_check.append("released_by_wrapper")
            if ownership_possible and "ownership_transferred" not in exceptions_to_check:
                exceptions_to_check.append("ownership_transferred")
            protocol_evidence.append(
                {
                    "type": "api_protocol",
                    "evidence_level": protocol.evidence_level,
                    "protocol_id": protocol.protocol_id,
                    "resource_kind": resource_kind,
                    "required_action": protocol.required_action,
                    "missing_cleanup": missing_release,
                    "resource_var": resource_var,
                    "acquire_function": str(resource.get("acquire_func", ""))
                    if resource
                    else "",
                    "release_found": _release_found(
                        cleanup_calls, protocol, missing_arg, resource
                    ),
                    "released_by_wrapper_possible": released_by_wrapper_possible,
                    "ownership_transfer_possible": ownership_possible,
                    "wrapper_evidence": wrapper_evidence,
                    "confidence": protocol.confidence,
                    "exceptions_to_check": exceptions_to_check,
                    "description": protocol.description,
                }
            )
    return protocol_evidence
