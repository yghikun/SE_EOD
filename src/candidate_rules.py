"""Rules that convert error-path CSV rows into suspicious candidates."""

from __future__ import annotations

import json
import re
from typing import Any

from .false_positive_model import suppresses_missing_cleanup
from .parser import call_name_and_first_arg
from .resource_expr import same_resource_expr
from .resource_release import (
    cleanup_call_releases_resource,
    missing_cleanup_matches_resource,
)


ERROR_VARS = {"ret", "err", "error", "retval", "status"}


def _json_list(row: dict[str, str], field: str) -> list[Any]:
    value = row.get(field, "")
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _norm_expr(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _cleanup_releases_resource(cleanup_call: str, resource: dict[str, Any]) -> bool:
    return cleanup_call_releases_resource(cleanup_call, resource)


def _released_resources(
    held_resources: list[dict[str, Any]], cleanup_calls: list[str]
) -> list[dict[str, Any]]:
    released: list[dict[str, Any]] = []
    for resource in held_resources:
        if any(_cleanup_releases_resource(call, resource) for call in cleanup_calls):
            released.append(resource)
    return released


def _missing_resources(
    held_resources: list[dict[str, Any]], missing_releases: list[str]
) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    for resource in held_resources:
        if any(
            missing_cleanup_matches_resource(
                call_name_and_first_arg(release)[0],
                call_name_and_first_arg(release)[1],
                resource,
            )
            for release in missing_releases
        ):
            missing.append(resource)
    return missing


def _filter_already_released(
    row: dict[str, str],
    held_resources: list[dict[str, Any]],
    missing_releases: list[str],
    cleanup_calls: list[str],
) -> list[str]:
    filtered: list[str] = []
    for missing in missing_releases:
        missing_name, missing_arg = call_name_and_first_arg(missing)
        resources = [
            resource
            for resource in held_resources
            if missing_cleanup_matches_resource(missing_name, missing_arg, resource)
        ]
        if suppresses_missing_cleanup(
            row, missing_name, missing_arg, resources[0] if resources else None
        ):
            continue
        if resources and any(
            cleanup_call_releases_resource(cleanup, resource)
            for resource in resources
            for cleanup in cleanup_calls
        ):
            continue
        if not resources and any(_norm_expr(missing) == _norm_expr(cleanup) for cleanup in cleanup_calls):
            continue
        filtered.append(missing)
    return filtered


def _looks_like_acquire_failure(row: dict[str, str], resource: dict[str, Any]) -> bool:
    condition = row.get("condition", "")
    var = str(resource.get("var", ""))
    acquire_func = str(resource.get("acquire_func", ""))
    error_source = row.get("error_source_expr", "")
    if acquire_func and not error_source.startswith(f"{acquire_func}("):
        return False
    condition = condition.strip()
    null_check = condition.startswith("!") and same_resource_expr(condition[1:].strip(), var)
    null_eq = _condition_null_eq_resource(condition, var)
    err_check = re.search(r"\bIS_ERR(?:_OR_NULL)?\s*\(\s*(.+?)\s*\)", condition)
    err_resource = bool(err_check and same_resource_expr(err_check.group(1), var))
    return bool(null_check or null_eq or err_resource)


def _condition_null_eq_resource(condition: str, resource_var: str) -> bool:
    null_check = re.fullmatch(r"(.+?)\s*==\s*NULL", condition) or re.fullmatch(
        r"NULL\s*==\s*(.+)", condition
    )
    return bool(null_check and same_resource_expr(null_check.group(1), resource_var))


def _filter_acquire_failure_missing(
    row: dict[str, str],
    held_resources: list[dict[str, Any]],
    missing_releases: list[str],
) -> list[str]:
    if not missing_releases:
        return []
    acquire_failure_resources = [
        resource
        for resource in held_resources
        if _looks_like_acquire_failure(row, resource)
    ]
    if not acquire_failure_resources:
        return missing_releases

    filtered: list[str] = []
    for missing in missing_releases:
        missing_name, missing_arg = call_name_and_first_arg(missing)
        suppress = False
        for resource in acquire_failure_resources:
            if missing_cleanup_matches_resource(missing_name, missing_arg, resource):
                suppress = True
                break
        if not suppress:
            filtered.append(missing)
    return filtered


def _severity_for_missing(
    candidate_type: str,
    held_resources: list[dict[str, Any]],
    missing_releases: list[str],
    final_return_expr: str,
) -> str:
    if candidate_type == "error_swallowed" and _norm_expr(final_return_expr) == "0":
        return "P1"
    if candidate_type == "partial_cleanup":
        return "P2"

    missing_resource_types = {
        resource.get("resource_type", "")
        for resource in _missing_resources(held_resources, missing_releases)
    }
    missing_names = {call_name_and_first_arg(release)[0] for release in missing_releases}

    if "journal_handle" in missing_resource_types or "ext4_journal_stop" in missing_names:
        return "P1"
    if missing_resource_types.intersection({"mutex", "rwsem", "spinlock"}):
        return "P1"
    if missing_names.intersection({"mutex_unlock", "spin_unlock", "up_read", "up_write"}):
        return "P1"
    if missing_resource_types.intersection({"buffer_head", "memory", "posix_acl"}):
        return "P2"
    if missing_names.intersection({"brelse", "kfree", "kvfree", "vfree", "posix_acl_release"}):
        return "P2"
    return "P3"


def _evidence(
    held_resources: list[dict[str, Any]],
    missing_releases: list[str],
    cleanup_calls: list[str],
    final_return_expr: str,
) -> str:
    return json.dumps(
        {
            "acquired_resources": held_resources,
            "missing_releases": missing_releases,
            "cleanup_calls": cleanup_calls,
            "final_return_expr": final_return_expr,
        },
        ensure_ascii=False,
    )


def _base_candidate(
    row: dict[str, str],
    candidate_type: str,
    severity: str,
    evidence: str,
    reason: str,
) -> dict[str, str]:
    return {
        "linux_git_commit": row.get("linux_git_commit", ""),
        "linux_git_tag": row.get("linux_git_tag", ""),
        "file": row.get("file", ""),
        "function": row.get("function", ""),
        "path_id": row.get("path_id", ""),
        "error_line": row.get("error_line", ""),
        "candidate_type": candidate_type,
        "severity": severity,
        "condition": row.get("condition", ""),
        "exit_type": row.get("exit_type", ""),
        "target_label": row.get("target_label", ""),
        "error_source_expr": row.get("error_source_expr", ""),
        "held_resources": row.get("held_resources", "[]"),
        "cleanup_calls": row.get("cleanup_calls", "[]"),
        "missing_cleanup_candidates": row.get("missing_cleanup_candidates", "[]"),
        "final_return_expr": row.get("final_return_expr", ""),
        "evidence": evidence,
        "reason": reason,
    }


def _row_context(row: dict[str, str]) -> tuple[list[dict[str, Any]], list[str], list[str], str]:
    held_resources = [
        resource
        for resource in _json_list(row, "held_resources")
        if isinstance(resource, dict)
    ]
    cleanup_calls = [str(call) for call in _json_list(row, "cleanup_calls")]
    missing_releases = [
        str(call) for call in _json_list(row, "missing_cleanup_candidates")
    ]
    missing_releases = _filter_already_released(
        row, held_resources, missing_releases, cleanup_calls
    )
    missing_releases = _filter_acquire_failure_missing(
        row, held_resources, missing_releases
    )
    return held_resources, cleanup_calls, missing_releases, row.get("final_return_expr", "")


def missing_cleanup_candidates(
    row: dict[str, str], analysis_contracts: dict[str, Any] | None = None
) -> list[dict[str, str]]:
    if _suppressed_by_review_contract(row, "missing_cleanup", analysis_contracts):
        return []
    held_resources, cleanup_calls, missing_releases, final_return_expr = _row_context(row)
    if row.get("confidence") == "low":
        return []
    if not held_resources or not missing_releases:
        return []

    evidence = _evidence(held_resources, missing_releases, cleanup_calls, final_return_expr)
    severity = _severity_for_missing(
        "missing_cleanup", held_resources, missing_releases, final_return_expr
    )
    return [
        _base_candidate(
            row,
            "missing_cleanup",
            severity,
            evidence,
            "error path exits while resource acquired before error path has no matching release in cleanup.",
        )
    ]


def partial_cleanup_candidates(
    row: dict[str, str], analysis_contracts: dict[str, Any] | None = None
) -> list[dict[str, str]]:
    if _suppressed_by_review_contract(row, "partial_cleanup", analysis_contracts):
        return []
    held_resources, cleanup_calls, missing_releases, final_return_expr = _row_context(row)
    if row.get("confidence") == "low":
        return []
    if len(held_resources) < 2 or not cleanup_calls or not missing_releases:
        return []
    if not _released_resources(held_resources, cleanup_calls):
        return []

    evidence = _evidence(held_resources, missing_releases, cleanup_calls, final_return_expr)
    return [
        _base_candidate(
            row,
            "partial_cleanup",
            "P2",
            evidence,
            "cleanup label releases some resources but not all resources acquired before the error path.",
        )
    ]


def _error_returned_via_output_contract(
    row: dict[str, str], analysis_contracts: dict[str, Any] | None
) -> bool:
    if not analysis_contracts:
        return False
    for contract in analysis_contracts.get("error_output_contracts", []):
        if not isinstance(contract, dict):
            continue
        if contract.get("function") != row.get("function"):
            continue
        expected_return = contract.get("sentinel_return")
        if expected_return and _norm_expr(str(expected_return)) != _norm_expr(
            row.get("final_return_expr", "")
        ):
            continue
        return True
    return False


def _suppressed_by_review_contract(
    row: dict[str, str], candidate_type: str, analysis_contracts: dict[str, Any] | None
) -> bool:
    if not analysis_contracts:
        return False
    error_line = str(row.get("error_line", "")).strip()
    for contract in analysis_contracts.get("review_false_positive_rules", []):
        if not isinstance(contract, dict):
            continue
        if contract.get("file") != row.get("file"):
            continue
        if contract.get("function") != row.get("function"):
            continue
        if contract.get("candidate_type") != candidate_type:
            continue
        if error_line in {str(line) for line in contract.get("error_lines", [])}:
            return True
    return False


def error_swallowed_candidates(
    row: dict[str, str], analysis_contracts: dict[str, Any] | None = None
) -> list[dict[str, str]]:
    if _suppressed_by_review_contract(row, "error_swallowed", analysis_contracts):
        return []
    condition = row.get("condition", "")
    if not re.search(r"\b(?:ret|err|error|retval|status)\b", condition):
        return []

    final_return_expr = row.get("final_return_expr", "")
    normalized_return = _norm_expr(final_return_expr)
    returns_success = normalized_return == "0"
    returns_null_after_error = (
        normalized_return == "NULL"
        and re.search(r"\b(?:ret|err|error|retval|status)\b", condition)
    )
    if not returns_success and not returns_null_after_error:
        return []
    if _error_returned_via_output_contract(row, analysis_contracts):
        return []

    held_resources, cleanup_calls, missing_releases, _ = _row_context(row)
    evidence = _evidence(held_resources, missing_releases, cleanup_calls, final_return_expr)
    severity = "P1" if returns_success else "P2"
    return [
        _base_candidate(
            row,
            "error_swallowed",
            severity,
            evidence,
            "error-like condition is followed by successful return expression.",
        )
    ]


def run_candidate_rules(
    row: dict[str, str], analysis_contracts: dict[str, Any] | None = None
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    candidates.extend(partial_cleanup_candidates(row, analysis_contracts))
    candidates.extend(missing_cleanup_candidates(row, analysis_contracts))
    candidates.extend(error_swallowed_candidates(row, analysis_contracts))
    return candidates
