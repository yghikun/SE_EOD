"""Conservative ownership transfer hinting for ranked candidates."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .parser import call_name_and_first_arg, extract_call_expressions


TRANSFER_NAME_HINTS = (
    "add",
    "insert",
    "attach",
    "link",
    "set",
    "init",
    "cache",
    "store",
    "put",
    "record",
)
LIST_NAME_HINTS = (
    "list_add",
    "list_add_tail",
    "hlist_add",
    "rb_link_node",
    "radix_tree_insert",
    "xa_store",
    "xas_store",
)


def ownership_transfer_hints_for_candidate(
    row: dict[str, str],
    linux_path: str | Path,
    held_resources: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    resources = held_resources if held_resources is not None else _held_resources(row)
    if not resources:
        return []

    source = _source_path(Path(linux_path), row.get("file", ""))
    error_line = _int_or_zero(row.get("error_line", ""))
    try:
        lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    if error_line <= 0:
        end_index = len(lines)
    else:
        end_index = min(len(lines), error_line - 1)
    start_index = max(0, _first_acquire_line(resources) - 1)

    hints: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, str]] = set()
    for line_no, text in enumerate(lines[start_index:end_index], start_index + 1):
        stripped = _strip_comments(text).strip()
        if not stripped:
            continue
        for resource in resources:
            var = str(resource.get("var", "")).strip()
            if not var or not _contains_identifier(stripped, var):
                continue
            for hint in _line_hints(stripped, line_no, resource):
                key = (
                    hint["resource_kind"],
                    hint["resource_expr"],
                    int(hint["line"]),
                    hint["reason"],
                )
                if key in seen:
                    continue
                seen.add(key)
                hints.append(hint)
    return hints


def _held_resources(row: dict[str, str]) -> list[dict[str, Any]]:
    evidence = _json_dict(row.get("evidence", ""))
    resources = evidence.get("acquired_resources")
    if not isinstance(resources, list):
        resources = _json_list(row.get("held_resources", ""))
    return [item for item in resources if isinstance(item, dict)]


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


def _source_path(linux_path: Path, file_value: str) -> Path:
    source = Path(file_value)
    if source.is_absolute():
        return source
    return linux_path / source


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _resource_kind(resource: dict[str, Any]) -> str:
    return str(resource.get("resource_kind") or resource.get("resource_type") or "")


def _first_acquire_line(resources: list[dict[str, Any]]) -> int:
    lines: list[int] = []
    for resource in resources:
        line = _int_or_zero(resource.get("acquire_line", 0))
        if line > 0:
            lines.append(line)
    return min(lines) if lines else 1


def _contains_identifier(text: str, name: str) -> bool:
    return bool(re.search(rf"\b{re.escape(name)}\b", text))


def _strip_comments(text: str) -> str:
    return text.split("//", 1)[0]


def _line_hints(
    text: str, line_no: int, resource: dict[str, Any]
) -> list[dict[str, Any]]:
    var = str(resource.get("var", "")).strip()
    resource_kind = _resource_kind(resource)
    hints: list[dict[str, Any]] = []

    field_assignment = re.search(
        rf"(?:->|\.)\s*[A-Za-z_]\w*\s*=\s*(?:\([^)]+\)\s*)?{re.escape(var)}\b",
        text,
    )
    if field_assignment:
        hints.append(
            _hint(
                resource_kind,
                var,
                line_no,
                "resource assigned into a struct field before the error path",
            )
        )

    for call in extract_call_expressions(text):
        name, first_arg = call_name_and_first_arg(call)
        if name in _obvious_release_names(resource):
            continue
        if _call_contains_arg(call, var) and _function_name_suggests_transfer(name):
            hints.append(
                _hint(
                    resource_kind,
                    var,
                    line_no,
                    "resource passed to function that may retain ownership",
                    call,
                )
            )
        if _call_contains_arg(call, var) and name in LIST_NAME_HINTS:
            hints.append(
                _hint(
                    resource_kind,
                    var,
                    line_no,
                    "resource added to a list-like structure",
                    call,
                )
            )
        elif (
            _call_contains_arg(call, var)
            and name not in _obvious_release_names(resource)
            and not name.startswith(("IS_ERR", "PTR_ERR"))
        ):
            hints.append(
                _hint(
                    resource_kind,
                    var,
                    line_no,
                    "resource appears in a call before the error path",
                    call,
                )
            )
    return hints


def _call_contains_arg(call: str, var: str) -> bool:
    open_idx = call.find("(")
    close_idx = call.rfind(")")
    if open_idx == -1 or close_idx == -1 or close_idx < open_idx:
        return False
    args = call[open_idx + 1 : close_idx]
    return _contains_identifier(args, var)


def _function_name_suggests_transfer(name: str) -> bool:
    lower = name.lower()
    return any(hint in lower for hint in TRANSFER_NAME_HINTS)


def _obvious_release_names(resource: dict[str, Any]) -> set[str]:
    releases = resource.get("release_functions", [])
    if isinstance(releases, str):
        releases = [releases]
    return {str(item) for item in releases}


def _hint(
    resource_kind: str,
    resource_expr: str,
    line_no: int,
    reason: str,
    call: str = "",
) -> dict[str, Any]:
    hint = {
        "type": "ownership_transfer_hint",
        "resource_kind": resource_kind,
        "resource_expr": resource_expr,
        "line": line_no,
        "reason": reason,
        "confidence": "low",
    }
    if call:
        hint["call"] = call
    return hint
