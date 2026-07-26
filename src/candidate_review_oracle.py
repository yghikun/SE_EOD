"""Stable report-level oracle and audit for the M32d source review."""

from __future__ import annotations

import json
import hashlib
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ORACLE_SCHEMA_VERSION = 1
AUDIT_SCHEMA_VERSION = 2

FUNCTION_BOUNDARY = "FUNCTION_BOUNDARY_RESIDUAL"
LIVE = "LIVE_METADATA_RESIDUAL"
CONTAINED = "CONTAINED_METADATA_RESIDUAL"
UNKNOWN = "METADATA_RESIDUAL_UNKNOWN"
CLOSED = "CLOSED"
OUT_OF_SCOPE = "OUT_OF_SCOPE"

_TERMINAL_STATES = {CLOSED, OUT_OF_SCOPE}
_VISIBLE_LIVE_STATES = {FUNCTION_BOUNDARY, LIVE}


def build_oracle_record(
    review: dict[str, Any],
    report: dict[str, Any],
    *,
    baseline_run: str,
) -> dict[str, Any]:
    """Bind one report-level manual verdict to its complete source witness."""

    residual_slice = _mapping(report.get("residual_slice"))
    effects = sorted(
        (_effect_identity(item) for item in residual_slice.get("residuals", ())),
        key=_canonical_json,
    )
    stable_location = {
        "filesystem": str(review["filesystem"]),
        "function": str(report["function"]),
        "failure_site": _site(residual_slice.get("failure_site")),
        "exit_site": _site(residual_slice.get("exit_site")),
    }
    stable_report = {**stable_location, "residual_effects": effects}
    expected_state = _expected_final_state(review)
    return {
        "schema_version": ORACLE_SCHEMA_VERSION,
        "oracle_id": str(review["id"]),
        "oracle_granularity": "REPORT",
        "baseline_run": baseline_run,
        "stable_key": _stable_hash(stable_report),
        "stable_location_key": _stable_hash(stable_location),
        "stable_report": stable_report,
        "manual_class": _manual_class(review),
        "expected_final_state": expected_state,
        "report_validity": str(review["report_validity"]),
        "bug_status": str(review["bug_status"]),
        "source_verdict": str(review["source_verdict"]),
        "root_cause_family": str(review["root_cause_family"]),
        "rationale": str(review["rationale"]),
        "related_finding": str(review.get("related_finding", "")),
        "reviewed_on": str(review["reviewed_on"]),
    }


def audit_oracle(
    oracle_records: Iterable[dict[str, Any]],
    current_path: str | Path | Iterable[str | Path],
) -> dict[str, Any]:
    """Audit reviewed reports against full current slices without inventing fixes."""

    records = list(oracle_records)
    current_paths = _current_paths(current_path)
    current = [
        item
        for path in current_paths
        for item in _load_current_slices(path)
    ]
    by_location: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in current:
        by_location[item["stable_location_key"]].append(item)

    transitions = [
        _audit_record(record, by_location.get(str(record["stable_location_key"]), []))
        for record in records
    ]
    summary = _audit_summary(records, transitions, current_paths)
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "summary": summary,
        "transition_matrix": _transition_matrix(transitions),
        "transitions": transitions,
    }


def compare_audit_safety(
    audit: dict[str, Any],
    baseline_audit: dict[str, Any],
) -> dict[str, Any]:
    """Annotate an audit with safety issues newly introduced since a baseline."""

    current_ids = _safety_issue_ids(audit)
    baseline_ids = _safety_issue_ids(baseline_audit)
    summary = _mapping(audit.get("summary"))
    summary.update(
        {
            "baseline_safety_issue_count": len(baseline_ids),
            "preexisting_safety_issue_ids": sorted(current_ids & baseline_ids),
            "new_safety_regression_ids": sorted(current_ids - baseline_ids),
            "new_safety_regression_count": len(current_ids - baseline_ids),
            "resolved_safety_issue_ids": sorted(baseline_ids - current_ids),
        }
    )
    return audit


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")


def _expected_final_state(review: dict[str, Any]) -> str:
    verdict = str(review["source_verdict"])
    root_cause = str(review["root_cause_family"])
    if verdict in {"TRUE_ISSUE", "LIKELY_ISSUE"}:
        return LIVE
    if verdict == "CONTAINED_NOT_BUG":
        return CONTAINED
    if verdict == "UNRESOLVED":
        return UNKNOWN
    if root_cause.startswith("EXPLICIT_") or root_cause.endswith("_CLEANUP"):
        return CLOSED
    if root_cause in {"RELOCATION_ERROR_CLEANUP", "REMOUNT_RESTORE_PATH"}:
        return CLOSED
    return OUT_OF_SCOPE


def _manual_class(review: dict[str, Any]) -> str:
    verdict = str(review["source_verdict"])
    root_cause = str(review["root_cause_family"])
    if verdict in {"TRUE_ISSUE", "LIKELY_ISSUE"}:
        return "LIVE_RESIDUAL"
    if verdict == "CONTAINED_NOT_BUG":
        return "FAILURE_DOMAIN_CONTAINED"
    if verdict == "UNRESOLVED":
        return "UNCERTAIN"
    if verdict == "DIFFERENT_DEFECT":
        return "NON_METADATA_DEFECT"
    if root_cause == "FAILED_OBJECT_TEARDOWN":
        return "OWNER_DESTROYED"
    if root_cause == "INTENTIONAL_PROGRESS_OR_OUTPUT":
        return "INTENTIONAL_PROGRESS_STATE"
    if root_cause.startswith("EXPLICIT_") or root_cause.endswith("_CLEANUP"):
        return "ALREADY_CLEANED"
    if root_cause in {"RELOCATION_ERROR_CLEANUP", "REMOUNT_RESTORE_PATH"}:
        return "ALREADY_CLEANED"
    # The original report-level review did not distinguish these two cases.
    return "PRIVATE_OR_TRANSIENT_OR_ALREADY_CLEANED"


def _audit_record(
    oracle: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    stable_report = _mapping(oracle.get("stable_report"))
    old_effects = list(stable_report.get("residual_effects", ()))
    current = _best_current_slice(old_effects, candidates)
    if current is None:
        return {
            "oracle_id": oracle["oracle_id"],
            "stable_report": oracle["stable_report"],
            "expected_final_state": oracle["expected_final_state"],
            "current_classification": "UNMATCHED",
            "effect_states": ["UNMATCHED_EFFECT"] * len(old_effects),
            "status": "SAFETY_REGRESSION",
            "reason": "current_report_location_unmatched",
        }

    effect_states = [_effect_state(effect, current["slice"]) for effect in old_effects]
    status, reason = _transition_status(
        str(oracle["expected_final_state"]),
        str(current["classification"]),
        effect_states,
    )
    return {
        "oracle_id": oracle["oracle_id"],
        "stable_report": oracle["stable_report"],
        "expected_final_state": oracle["expected_final_state"],
        "current_classification": current["classification"],
        "current_state": current["slice"].get("state", ""),
        "effect_states": effect_states,
        "status": status,
        "reason": reason,
    }


def _best_current_slice(
    old_effects: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not candidates:
        return None
    old_keys = {_canonical_json(effect) for effect in old_effects}

    def score(item: dict[str, Any]) -> tuple[int, int]:
        residual_slice = item["slice"]
        current_effects = (
            list(residual_slice.get("residuals", ()))
            + list(residual_slice.get("reaching_effects", ()))
            + list(residual_slice.get("out_of_scope_effects", ()))
        )
        keys = {_canonical_json(_effect_identity(effect)) for effect in current_effects}
        return len(old_keys & keys), len(residual_slice.get("residuals", ()))

    return max(candidates, key=score)


def _effect_state(effect: dict[str, Any], residual_slice: dict[str, Any]) -> str:
    key = _canonical_json(effect)
    teardown_closed = {
        _canonical_json(_effect_identity(item))
        for proof in residual_slice.get("owner_teardown_proofs", ())
        for item in _mapping(proof).get("closed_effects", ())
    }
    containment_covered = {
        _canonical_json(_effect_identity(item))
        for proof in residual_slice.get("containment_proofs", ())
        for item in _mapping(proof).get("covered_effects", ())
    }
    out_of_scope = {
        _canonical_json(_effect_identity(item))
        for item in residual_slice.get("out_of_scope_effects", ())
    }
    residuals = {
        _canonical_json(_effect_identity(item))
        for item in residual_slice.get("residuals", ())
    }
    reaching = {
        _canonical_json(_effect_identity(item))
        for item in residual_slice.get("reaching_effects", ())
    }
    if key in teardown_closed:
        return CLOSED
    if key in out_of_scope:
        return OUT_OF_SCOPE
    if key in containment_covered:
        return CONTAINED
    if key in residuals:
        state = str(residual_slice.get("state", ""))
        if state == "EXPOSED" and _effect_is_owner_scope_review(effect, residual_slice):
            return "FUNCTION_BOUNDARY_RESIDUAL_REVIEW"
        return _slice_classification(residual_slice)
    if key in reaching:
        if str(residual_slice.get("state", "")) in {"CLOSED", "PROTECTED"}:
            return CLOSED
        return "RETAINED_REACHING"
    return "RETAINED_SLICE"


def _transition_status(
    expected: str,
    current: str,
    effect_states: list[str],
) -> tuple[str, str]:
    states = set(effect_states)
    if "UNMATCHED_EFFECT" in states:
        return "SAFETY_REGRESSION", "reviewed_effect_witness_unmatched"
    if expected == UNKNOWN and current == UNKNOWN:
        return "EXPECTED_STATE_REACHED", "manual_uncertainty_preserved"
    if UNKNOWN in states or current == UNKNOWN:
        return "SAFETY_REGRESSION", "reviewed_candidate_moved_to_unknown"
    if expected == LIVE:
        if states & _VISIBLE_LIVE_STATES:
            return "RETAINED_FOR_LATER_MILESTONE", "live_residual_remains_visible"
        return "SAFETY_REGRESSION", "manual_live_residual_not_visible"
    if expected == CONTAINED:
        if current == CONTAINED or CONTAINED in states:
            return "EXPECTED_STATE_REACHED", "containment_recognized"
        return "RETAINED_FOR_LATER_MILESTONE", "awaiting_failure_domain_semantics"
    if expected in _TERMINAL_STATES:
        if states and states <= _TERMINAL_STATES:
            return "EXPECTED_STATE_REACHED", "manual_false_positive_removed"
        return "RETAINED_FOR_LATER_MILESTONE", "awaiting_owner_or_scope_semantics"
    return "RETAINED_FOR_LATER_MILESTONE", "manual_uncertainty_still_visible"


def _audit_summary(
    oracle: list[dict[str, Any]],
    transitions: list[dict[str, Any]],
    current_paths: tuple[Path, ...],
) -> dict[str, Any]:
    expected = Counter(str(item["expected_final_state"]) for item in oracle)
    statuses = Counter(str(item["status"]) for item in transitions)
    current = Counter(str(item["current_classification"]) for item in transitions)
    false_positive_ids = {
        str(item["oracle_id"])
        for item in oracle
        if str(item["expected_final_state"]) in _TERMINAL_STATES
    }
    live_ids = {
        str(item["oracle_id"])
        for item in oracle
        if str(item["expected_final_state"]) == LIVE
    }
    contained_ids = {
        str(item["oracle_id"])
        for item in oracle
        if str(item["expected_final_state"]) == CONTAINED
    }
    by_id = {str(item["oracle_id"]): item for item in transitions}
    return {
        "oracle_entries": len(oracle),
        "current": [path.as_posix() for path in current_paths],
        "expected_final_state_counts": dict(sorted(expected.items())),
        "current_classification_counts": dict(sorted(current.items())),
        "status_counts": dict(sorted(statuses.items())),
        "matched_oracle_entries": sum(
            item["current_classification"] != "UNMATCHED" for item in transitions
        ),
        "unmatched_oracle_entries": current["UNMATCHED"],
        "unmatched_effect_count": sum(
            state == "UNMATCHED_EFFECT"
            for item in transitions
            for state in item["effect_states"]
        ),
        "manual_false_positives_correctly_moved": sum(
            by_id[item_id]["status"] == "EXPECTED_STATE_REACHED"
            for item_id in false_positive_ids
        ),
        "manual_false_positives_pending": sum(
            by_id[item_id]["status"] == "RETAINED_FOR_LATER_MILESTONE"
            for item_id in false_positive_ids
        ),
        "manual_live_residuals_retained": sum(
            by_id[item_id]["reason"] == "live_residual_remains_visible"
            for item_id in live_ids
        ),
        "manual_live_residuals_lost": sum(
            by_id[item_id]["status"] == "SAFETY_REGRESSION" for item_id in live_ids
        ),
        "manual_contained_residuals_recognized": sum(
            by_id[item_id]["reason"] == "containment_recognized"
            for item_id in contained_ids
        ),
        "manual_contained_residuals_pending": sum(
            by_id[item_id]["reason"] == "awaiting_failure_domain_semantics"
            for item_id in contained_ids
        ),
        "candidate_to_unknown_count": sum(
            item["current_classification"] == UNKNOWN or UNKNOWN in item["effect_states"]
            for item in transitions
        ),
        "safety_regression_count": statuses["SAFETY_REGRESSION"],
    }


def _transition_matrix(transitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(
        (str(item["expected_final_state"]), str(item["current_classification"]))
        for item in transitions
    )
    return [
        {"expected_final_state": old, "current_classification": new, "count": count}
        for (old, new), count in sorted(counts.items())
    ]


def _safety_issue_ids(audit: dict[str, Any]) -> set[str]:
    return {
        str(item["oracle_id"])
        for item in audit.get("transitions", ())
        if item.get("status") == "SAFETY_REGRESSION"
    }


def _load_current_slices(path: Path) -> list[dict[str, Any]]:
    evaluation_paths = _evaluation_paths(path)
    records: list[dict[str, Any]] = []
    for evaluation_path in evaluation_paths:
        payload = json.loads(evaluation_path.read_text(encoding="utf-8"))
        for analysis in payload.get("analyses", ()):
            function = str(analysis.get("function", ""))
            slicing = _mapping(analysis.get("slicing_result"))
            for residual_slice in slicing.get("slices", ()):
                slice_dict = _mapping(residual_slice)
                failure_site = _site(slice_dict.get("failure_site"))
                location = {
                    "filesystem": _filesystem_for_site(failure_site),
                    "function": function,
                    "failure_site": failure_site,
                    "exit_site": _site(slice_dict.get("exit_site")),
                }
                records.append(
                    {
                        "stable_location_key": _stable_hash(location),
                        "classification": _slice_classification(slice_dict),
                        "slice": slice_dict,
                    }
                )
    return records


def _evaluation_paths(path: Path) -> tuple[Path, ...]:
    if path.is_file():
        return (path,) if path.name == "evaluation.json" else ()
    file_paths = tuple(sorted((path / "files").glob("*/evaluation.json")))
    if file_paths:
        return file_paths
    direct = path / "evaluation.json"
    return (direct,) if direct.is_file() else ()


def _current_paths(value: str | Path | Iterable[str | Path]) -> tuple[Path, ...]:
    if isinstance(value, (str, Path)):
        return (Path(value),)
    return tuple(Path(item) for item in value)


def _slice_classification(residual_slice: dict[str, Any]) -> str:
    state = str(residual_slice.get("state", ""))
    residuals = list(residual_slice.get("residuals", ()))
    if residuals and state == "UNKNOWN":
        return UNKNOWN
    if residuals and state == "CONTAINED":
        return CONTAINED
    if residuals and state == "LIVE":
        return LIVE
    if residuals and state == "EXPOSED":
        review_owners = _owner_scope_review_owners(residual_slice)
        if review_owners and all(
            _leading_effect_owner(str(item.get("root", ""))) in review_owners
            for item in residuals
        ):
            return "FUNCTION_BOUNDARY_RESIDUAL_REVIEW"
        covered = {
            _canonical_json(_effect_identity(item))
            for proof in residual_slice.get("containment_proofs", ())
            for item in _mapping(proof).get("covered_effects", ())
        }
        uncontained = [
            item
            for item in residuals
            if _canonical_json(_effect_identity(item)) not in covered
        ]
        if all(
            str(item.get("evidence", "")) == "NAME_INFERRED"
            for item in uncontained
        ):
            return "FUNCTION_BOUNDARY_RESIDUAL_REVIEW"
        return FUNCTION_BOUNDARY
    if residual_slice.get("out_of_scope_effects"):
        return OUT_OF_SCOPE
    if state in {"CLOSED", "PROTECTED"}:
        return CLOSED
    return OUT_OF_SCOPE


def _effect_is_owner_scope_review(
    effect: dict[str, Any], residual_slice: dict[str, Any]
) -> bool:
    return _leading_effect_owner(str(effect.get("root", ""))) in (
        _owner_scope_review_owners(residual_slice)
    )


def _owner_scope_review_owners(residual_slice: dict[str, Any]) -> set[str]:
    prefix = "owner_scope_escape_review:"
    return {
        str(item).removeprefix(prefix)
        for item in residual_slice.get("semantic_blockers", ())
        if str(item).startswith(prefix)
    }


def _leading_effect_owner(root: str) -> str:
    match = re.match(r"[&*()\s]*([A-Za-z_]\w*)", root)
    return match.group(1) if match else ""


def _effect_identity(value: Any) -> dict[str, Any]:
    effect = _mapping(value)
    return {
        "root": str(effect.get("root", "")),
        "key": str(effect.get("key", "")),
        "plane": str(effect.get("plane", "")),
        "delta": str(effect.get("delta", "")),
        "value": str(effect.get("value", "")),
        "site": _site(effect.get("site")),
    }


def _site(value: Any) -> dict[str, Any]:
    site = _mapping(value)
    return {
        "file": str(site.get("file", "")),
        "line": int(site.get("line", 0) or 0),
        "expression": str(site.get("expression", "")),
    }


def _filesystem_for_site(site: dict[str, Any]) -> str:
    match = re.search(r"(?:^|[/\\])fs[/\\](btrfs|ext4|xfs|f2fs)(?:[/\\]|$)", site["file"])
    return match.group(1) if match else ""


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _stable_hash(value: Any) -> str:
    digest = hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
