"""Audit lifecycle API configuration drift against the scanned source tree.

This module is intentionally diagnostic only.  It does not decide whether a
candidate is a bug and it must not suppress static candidates.  Its job is to
surface places where resource-map/protocol/wrapper knowledge may have fallen
behind the current source version.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .function_extractor import Function
from .parser import call_name_and_args, extract_call_expressions
from .protocol_db import ResourceProtocolDB
from .wrapper_summary import WrapperSummaryDB


DRIFT_CSV_COLUMNS = [
    "severity",
    "kind",
    "function",
    "role",
    "resource_type",
    "configured_as",
    "observed_defs",
    "observed_calls",
    "evidence",
    "suggestion",
]

_LIFECYCLE_TOKENS = {
    "alloc",
    "bread",
    "cancel",
    "create",
    "destroy",
    "down",
    "drop",
    "end",
    "free",
    "get",
    "getblk",
    "journal",
    "lock",
    "put",
    "read",
    "release",
    "relse",
    "start",
    "stop",
    "unlock",
    "up",
}

_RELEASE_HINTS = {
    "cancel",
    "destroy",
    "drop",
    "end",
    "free",
    "put",
    "release",
    "relse",
    "stop",
    "unlock",
    "up",
}

_ACQUIRE_HINTS = {
    "alloc",
    "bread",
    "create",
    "down",
    "get",
    "getblk",
    "lock",
    "read",
    "start",
}


@dataclass(frozen=True)
class ObservedApi:
    name: str
    defined_in: tuple[str, ...] = ()
    called_in: tuple[str, ...] = ()

    @property
    def observed_defs(self) -> int:
        return len(self.defined_in)

    @property
    def observed_calls(self) -> int:
        return len(self.called_in)


@dataclass(frozen=True)
class ApiDriftIssue:
    severity: str
    kind: str
    function: str
    role: str
    resource_type: str
    configured_as: str
    observed_defs: int
    observed_calls: int
    evidence: str
    suggestion: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def audit_api_drift(
    functions: Iterable[Function],
    resource_map: dict[str, Any],
    protocols: ResourceProtocolDB | None = None,
    wrapper_db: WrapperSummaryDB | None = None,
    candidate_rows: Iterable[dict[str, str]] | None = None,
    max_similar_api_issues: int = 100,
) -> dict[str, Any]:
    """Return API drift issues and summary stats.

    The audit combines source observations with lifecycle configuration:

    - configured functions that are not observed in the scanned source subset;
    - protocol/resource-map mismatches;
    - wrapper summaries pointing at unknown release actions;
    - source APIs whose names look lifecycle-related but are not configured;
    - frequent missing cleanup actions in already-generated candidates.
    """

    observed = observe_apis(functions)
    configured = _configured_lifecycle_apis(resource_map, protocols, wrapper_db)
    issues: list[ApiDriftIssue] = []

    issues.extend(_configured_functions_not_observed(configured, observed))
    issues.extend(_protocol_resource_map_mismatches(resource_map, protocols))
    issues.extend(_wrapper_mismatches(resource_map, protocols, wrapper_db))
    issues.extend(
        _unconfigured_similar_lifecycle_apis(
            configured, observed, max_issues=max_similar_api_issues
        )
    )
    issues.extend(_frequent_missing_cleanup_issues(candidate_rows or []))

    issues = _dedupe_issues(issues)
    issues.sort(
        key=lambda issue: (
            _severity_rank(issue.severity),
            issue.kind,
            issue.resource_type,
            issue.function,
            issue.role,
        )
    )
    return {
        "kind": "api_drift_audit",
        "summary": _summary(issues, observed, configured),
        "issues": [issue.to_dict() for issue in issues],
    }


def observe_apis(functions: Iterable[Function]) -> dict[str, ObservedApi]:
    defined: dict[str, set[str]] = defaultdict(set)
    called: dict[str, set[str]] = defaultdict(set)
    for function in functions:
        location = _location(function)
        defined[function.name].add(location)
        for call in extract_call_expressions(function.source):
            name, _args = call_name_and_args(call)
            if not name or _looks_like_method_or_indirect(name):
                continue
            called[name].add(location)

    names = set(defined) | set(called)
    return {
        name: ObservedApi(
            name=name,
            defined_in=tuple(sorted(defined.get(name, set()))),
            called_in=tuple(sorted(called.get(name, set()))),
        )
        for name in names
    }


def write_api_drift_json(report: dict[str, Any], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_api_drift_csv(report: dict[str, Any], path: str | Path) -> int:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=DRIFT_CSV_COLUMNS)
        writer.writeheader()
        for issue in report.get("issues", []):
            if not isinstance(issue, dict):
                continue
            writer.writerow(
                {column: issue.get(column, "") for column in DRIFT_CSV_COLUMNS}
            )
            count += 1
    return count


def _location(function: Function) -> str:
    return f"{Path(function.file).as_posix()}:{function.start_line}:{function.name}"


def _configured_lifecycle_apis(
    resource_map: dict[str, Any],
    protocols: ResourceProtocolDB | None,
    wrapper_db: WrapperSummaryDB | None,
) -> dict[str, list[dict[str, str]]]:
    configured: dict[str, list[dict[str, str]]] = defaultdict(list)
    acquire_functions = resource_map.get("acquire_functions", {})
    if isinstance(acquire_functions, dict):
        for name, cfg in acquire_functions.items():
            if not isinstance(cfg, dict):
                continue
            resource_type = str(cfg.get("resource_type", "unknown"))
            configured[str(name)].append(
                {
                    "role": "acquire",
                    "resource_type": resource_type,
                    "configured_as": "resource_map.acquire_functions",
                }
            )
            releases = cfg.get("release", [])
            if isinstance(releases, str):
                releases = [releases]
            for release in releases:
                configured[str(release)].append(
                    {
                        "role": "release",
                        "resource_type": resource_type,
                        "configured_as": f"resource_map.release_for:{name}",
                    }
                )

    consumers = resource_map.get("callee_resource_consumers", {})
    if isinstance(consumers, dict):
        for name, raw in consumers.items():
            entries = raw if isinstance(raw, list) else [raw]
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                configured[str(name)].append(
                    {
                        "role": "consumer",
                        "resource_type": str(entry.get("resource_type", "")),
                        "configured_as": "resource_map.callee_resource_consumers",
                    }
                )

    seeds = resource_map.get("interprocedural_effect_seeds", {})
    if isinstance(seeds, dict):
        for name, raw in seeds.items():
            entries = raw if isinstance(raw, list) else [raw]
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                action = str(entry.get("action", "effect"))
                configured[str(name)].append(
                    {
                        "role": action,
                        "resource_type": str(entry.get("resource_type", "")),
                        "configured_as": "resource_map.interprocedural_effect_seeds",
                    }
                )

    if protocols:
        for protocol in protocols.protocols:
            for name in protocol.acquire_functions:
                configured[name].append(
                    {
                        "role": "acquire",
                        "resource_type": protocol.resource_kind,
                        "configured_as": f"protocol:{protocol.protocol_id}",
                    }
                )
            for name in protocol.release_functions:
                configured[name].append(
                    {
                        "role": "release",
                        "resource_type": protocol.resource_kind,
                        "configured_as": f"protocol:{protocol.protocol_id}",
                    }
                )

    if wrapper_db:
        for summary in wrapper_db.summaries:
            for name in summary.names():
                configured[name].append(
                    {
                        "role": "wrapper",
                        "resource_type": ",".join(summary.resource_kinds),
                        "configured_as": "wrapper_summary.function_or_alias",
                    }
                )
            for action in summary.releases:
                configured[action].append(
                    {
                        "role": "release_action",
                        "resource_type": ",".join(summary.resource_kinds),
                        "configured_as": f"wrapper_summary.release_for:{summary.function}",
                    }
                )

    return dict(configured)


def _configured_functions_not_observed(
    configured: dict[str, list[dict[str, str]]],
    observed: dict[str, ObservedApi],
) -> list[ApiDriftIssue]:
    issues: list[ApiDriftIssue] = []
    for name, entries in configured.items():
        if name in observed:
            continue
        for entry in entries:
            issues.append(
                ApiDriftIssue(
                    severity="low",
                    kind="configured_function_unobserved",
                    function=name,
                    role=entry["role"],
                    resource_type=entry["resource_type"],
                    configured_as=entry["configured_as"],
                    observed_defs=0,
                    observed_calls=0,
                    evidence="function name was not defined or called in the scanned source subset",
                    suggestion="check whether the target source version renamed, removed, or hides this API behind macros/includes",
                )
            )
    return issues


def _protocol_resource_map_mismatches(
    resource_map: dict[str, Any], protocols: ResourceProtocolDB | None
) -> list[ApiDriftIssue]:
    if not protocols:
        return []
    acquire_functions = resource_map.get("acquire_functions", {})
    if not isinstance(acquire_functions, dict):
        acquire_functions = {}
    resource_map_acquires = {str(name) for name in acquire_functions}
    resource_map_releases: set[str] = set()
    release_resource_types: dict[str, set[str]] = defaultdict(set)
    for name, cfg in acquire_functions.items():
        if not isinstance(cfg, dict):
            continue
        releases = cfg.get("release", [])
        if isinstance(releases, str):
            releases = [releases]
        for release in releases:
            release_name = str(release)
            resource_map_releases.add(release_name)
            release_resource_types[release_name].add(str(cfg.get("resource_type", "")))

    issues: list[ApiDriftIssue] = []
    for protocol in protocols.protocols:
        for name in protocol.acquire_functions:
            if name not in resource_map_acquires:
                issues.append(
                    ApiDriftIssue(
                        severity="medium",
                        kind="protocol_acquire_missing_from_resource_map",
                        function=name,
                        role="acquire",
                        resource_type=protocol.resource_kind,
                        configured_as=f"protocol:{protocol.protocol_id}",
                        observed_defs=0,
                        observed_calls=0,
                        evidence="protocol lists acquire function that resource_map will not track as an acquisition",
                        suggestion="add matching acquire_functions entry or remove stale protocol API",
                    )
                )
        for name in protocol.release_functions:
            if name not in resource_map_releases:
                issues.append(
                    ApiDriftIssue(
                        severity="medium",
                        kind="protocol_release_missing_from_resource_map",
                        function=name,
                        role="release",
                        resource_type=protocol.resource_kind,
                        configured_as=f"protocol:{protocol.protocol_id}",
                        observed_defs=0,
                        observed_calls=0,
                        evidence="protocol lists release function that resource_map acquisitions do not accept as release",
                        suggestion="add release alias to resource_map or remove stale protocol API",
                    )
                )
                continue
            if protocol.resource_kind not in release_resource_types.get(name, set()):
                issues.append(
                    ApiDriftIssue(
                        severity="low",
                        kind="protocol_release_resource_type_mismatch",
                        function=name,
                        role="release",
                        resource_type=protocol.resource_kind,
                        configured_as=f"protocol:{protocol.protocol_id}",
                        observed_defs=0,
                        observed_calls=0,
                        evidence=(
                            "release function exists in resource_map but not for the "
                            f"same resource kind; resource_map kinds={sorted(release_resource_types[name])}"
                        ),
                        suggestion="align protocol resource_kind with resource_map resource_type",
                    )
                )
    return issues


def _wrapper_mismatches(
    resource_map: dict[str, Any],
    protocols: ResourceProtocolDB | None,
    wrapper_db: WrapperSummaryDB | None,
) -> list[ApiDriftIssue]:
    if not wrapper_db:
        return []
    known_releases: set[str] = set()
    acquire_functions = resource_map.get("acquire_functions", {})
    if isinstance(acquire_functions, dict):
        for cfg in acquire_functions.values():
            if not isinstance(cfg, dict):
                continue
            releases = cfg.get("release", [])
            if isinstance(releases, str):
                releases = [releases]
            known_releases.update(str(item) for item in releases)
    if protocols:
        for protocol in protocols.protocols:
            known_releases.update(protocol.release_functions)
            known_releases.add(protocol.required_action)

    issues: list[ApiDriftIssue] = []
    for summary in wrapper_db.summaries:
        for action in summary.releases:
            if action in known_releases:
                continue
            issues.append(
                ApiDriftIssue(
                    severity="medium",
                    kind="wrapper_release_action_unknown",
                    function=summary.function,
                    role="wrapper",
                    resource_type=",".join(summary.resource_kinds),
                    configured_as="wrapper_summary",
                    observed_defs=0,
                    observed_calls=0,
                    evidence=f"wrapper summary releases {action}, but that action is not known by resource_map/protocols",
                    suggestion="add the underlying release action to protocol/resource_map or fix the wrapper summary",
                )
            )
    return issues


def _unconfigured_similar_lifecycle_apis(
    configured: dict[str, list[dict[str, str]]],
    observed: dict[str, ObservedApi],
    max_issues: int,
) -> list[ApiDriftIssue]:
    configured_names = set(configured)
    configured_by_role: dict[str, list[tuple[str, dict[str, str]]]] = defaultdict(list)
    for name, entries in configured.items():
        for entry in entries:
            configured_by_role[entry["role"]].append((name, entry))

    issues: list[ApiDriftIssue] = []
    for name, api in sorted(
        observed.items(),
        key=lambda item: (-(item[1].observed_calls + item[1].observed_defs), item[0]),
    ):
        if len(issues) >= max_issues:
            break
        if name in configured_names or not _looks_lifecycle_related(name):
            continue
        role_hint = _role_hint(name)
        if not role_hint:
            continue
        best = _best_configured_neighbor(name, configured_by_role.get(role_hint, []))
        if best is None:
            continue
        configured_name, entry, score = best
        if score < 0.58:
            continue
        issues.append(
            ApiDriftIssue(
                severity="medium" if api.observed_calls >= 2 else "low",
                kind="unconfigured_similar_lifecycle_api",
                function=name,
                role=role_hint,
                resource_type=entry.get("resource_type", ""),
                configured_as="source_observation",
                observed_defs=api.observed_defs,
                observed_calls=api.observed_calls,
                evidence=(
                    f"name resembles configured {role_hint} API {configured_name}; "
                    f"similarity={score:.2f}"
                ),
                suggestion=(
                    "review whether this is a new lifecycle API, alias, or wrapper; "
                    "if yes, update resource_map/protocol/wrapper summaries"
                ),
            )
        )
    return issues


def _frequent_missing_cleanup_issues(
    candidate_rows: Iterable[dict[str, str]],
    min_count: int = 3,
) -> list[ApiDriftIssue]:
    counts: Counter[str] = Counter()
    examples: dict[str, str] = {}
    for row in candidate_rows:
        if row.get("candidate_type") not in {"missing_cleanup", "partial_cleanup"}:
            continue
        missing_actions = _json_list(row.get("missing_cleanup_candidates", ""))
        if not missing_actions:
            evidence = _json_dict(row.get("evidence", "")).get("missing_releases", [])
            missing_actions = evidence if isinstance(evidence, list) else []
        for action in missing_actions:
            name, _args = call_name_and_args(str(action))
            if not name:
                continue
            counts[name] += 1
            examples.setdefault(name, f"{row.get('file', '')}:{row.get('function', '')}:{row.get('error_line', '')}")

    issues: list[ApiDriftIssue] = []
    for name, count in counts.most_common():
        if count < min_count:
            continue
        issues.append(
            ApiDriftIssue(
                severity="low",
                kind="frequent_missing_cleanup_action",
                function=name,
                role="release",
                resource_type="",
                configured_as="candidate_rows",
                observed_defs=0,
                observed_calls=count,
                evidence=f"missing cleanup action appears in {count} candidates; example={examples.get(name, '')}",
                suggestion="inspect candidates for unmodeled aliases, wrappers, ownership transfer, or API rename",
            )
        )
    return issues


def _dedupe_issues(issues: Iterable[ApiDriftIssue]) -> list[ApiDriftIssue]:
    seen: set[tuple[str, str, str, str, str]] = set()
    unique: list[ApiDriftIssue] = []
    for issue in issues:
        key = (
            issue.kind,
            issue.function,
            issue.role,
            issue.resource_type,
            issue.configured_as,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    return unique


def _summary(
    issues: list[ApiDriftIssue],
    observed: dict[str, ObservedApi],
    configured: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    by_kind = Counter(issue.kind for issue in issues)
    by_severity = Counter(issue.severity for issue in issues)
    return {
        "observed_api_names": len(observed),
        "configured_api_names": len(configured),
        "issues": len(issues),
        "by_kind": dict(sorted(by_kind.items())),
        "by_severity": dict(sorted(by_severity.items())),
    }


def _severity_rank(severity: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(severity, 3)


def _looks_like_method_or_indirect(name: str) -> bool:
    return any(token in name for token in ("->", ".", "[", "]"))


def _tokens(name: str) -> set[str]:
    parts = re.split(r"_+", name.lower())
    tokens: set[str] = set()
    for part in parts:
        if not part:
            continue
        tokens.add(part)
        for suffix in ["alloc", "free", "start", "stop", "getblk", "bread"]:
            if part.endswith(suffix) and part != suffix:
                tokens.add(suffix)
    return tokens


def _looks_lifecycle_related(name: str) -> bool:
    return bool(_tokens(name) & _LIFECYCLE_TOKENS)


def _role_hint(name: str) -> str:
    tokens = _tokens(name)
    if tokens & _RELEASE_HINTS:
        return "release"
    if tokens & _ACQUIRE_HINTS:
        return "acquire"
    return ""


def _best_configured_neighbor(
    name: str, candidates: list[tuple[str, dict[str, str]]]
) -> tuple[str, dict[str, str], float] | None:
    best: tuple[str, dict[str, str], float] | None = None
    name_tokens = _tokens(name)
    for configured_name, entry in candidates:
        score = _name_similarity(name, configured_name, name_tokens)
        if best is None or score > best[2]:
            best = (configured_name, entry, score)
    return best


def _name_similarity(name: str, configured_name: str, name_tokens: set[str]) -> float:
    configured_tokens = _tokens(configured_name)
    if not name_tokens or not configured_tokens:
        return 0.0
    overlap = len(name_tokens & configured_tokens) / len(name_tokens | configured_tokens)
    prefix_bonus = 0.0
    left_parts = name.split("_")
    right_parts = configured_name.split("_")
    common_prefix = 0
    for left, right in zip(left_parts, right_parts):
        if left != right:
            break
        common_prefix += 1
    if common_prefix:
        prefix_bonus = min(0.25, common_prefix / max(len(left_parts), len(right_parts), 1))
    substring_bonus = 0.15 if name in configured_name or configured_name in name else 0.0
    return min(1.0, overlap + prefix_bonus + substring_bonus)


def _json_list(value: str) -> list[Any]:
    parsed = _json_value(value, [])
    return parsed if isinstance(parsed, list) else []


def _json_dict(value: str) -> dict[str, Any]:
    parsed = _json_value(value, {})
    return parsed if isinstance(parsed, dict) else {}


def _json_value(value: str, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default
