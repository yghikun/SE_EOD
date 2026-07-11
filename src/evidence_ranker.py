"""Rank suspicious candidates by static, LLM, and API protocol evidence."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from .manual_review import ManualReviewDB, manual_score_adjustment
from .ownership_transfer import ownership_transfer_hints_for_candidate
from .protocol_db import ResourceProtocolDB
from .protocol_matcher import match_protocol_evidence
from .wrapper_summary import WrapperSummaryDB


E0_STATIC_RULE_ONLY = "E0_STATIC_RULE_ONLY"
E1_LLM_TRUE_CANDIDATE = "E1_LLM_TRUE_CANDIDATE"
E2_API_PROTOCOL_SUPPORTED = "E2_API_PROTOCOL_SUPPORTED"
E3_REPAIR_PATCH_SUPPORTED = "E3_REPAIR_PATCH_SUPPORTED"
E4_DYNAMICALLY_REPRODUCED = "E4_DYNAMICALLY_REPRODUCED"
E5_UPSTREAM_CONFIRMED = "E5_UPSTREAM_CONFIRMED"

MISSING_EVIDENCE_V1 = [
    "repair_patch",
    "dynamic_validation",
    "upstream_confirmation",
]

SUMMARY_COLUMNS = [
    "candidate_id",
    "file",
    "function",
    "error_line",
    "candidate_type",
    "severity",
    "evidence_level",
    "evidence_score",
    "matched_protocol_ids",
    "required_actions",
    "has_exception_hints",
    "exception_hints",
    "released_by_wrapper_possible",
    "ownership_transfer_possible",
    "manual_verdict",
    "manual_confidence",
    "manual_review_source",
    "manual_confirmed_exception",
    "manual_exception_type",
    "manual_score_adjustment",
    "manual_reason",
    "manual_next_action",
    "manual_validation_hint",
    "score_explanation",
    "missing_evidence",
    "final_return_expr",
]


def candidate_fingerprint(row: dict[str, str]) -> str:
    return "|".join(
        [
            row.get("file", ""),
            row.get("function", ""),
            row.get("path_id", ""),
            row.get("candidate_type", ""),
            row.get("error_line", ""),
        ]
    )


def candidate_id_for_row(row: dict[str, str]) -> str:
    digest = hashlib.sha1(
        candidate_fingerprint(row).encode("utf-8", errors="replace")
    ).hexdigest()[:12]
    return f"candidate_{digest}"


def llm_task_id_for_row(row: dict[str, str]) -> str:
    digest = hashlib.sha1(
        candidate_fingerprint(row).encode("utf-8", errors="replace")
    ).hexdigest()[:12]
    return f"llm_review_{digest}"


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


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _norm_expr(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _static_evidence(row: dict[str, str]) -> dict[str, Any]:
    evidence = _json_dict(row.get("evidence", ""))
    held_resources = evidence.get("acquired_resources")
    if not isinstance(held_resources, list):
        held_resources = _json_list(row.get("held_resources", ""))
    missing_releases = evidence.get("missing_releases")
    if not isinstance(missing_releases, list):
        missing_releases = _json_list(row.get("missing_cleanup_candidates", ""))
    cleanup_calls = evidence.get("cleanup_calls")
    if not isinstance(cleanup_calls, list):
        cleanup_calls = _json_list(row.get("cleanup_calls", ""))
    return {
        "reason": row.get("reason", ""),
        "held_resources": held_resources,
        "missing_cleanup_candidates": missing_releases,
        "cleanup_calls": cleanup_calls,
        "error_source_expr": row.get("error_source_expr", ""),
        "exit_type": row.get("exit_type", ""),
        "target_label": row.get("target_label", ""),
    }


def load_deepseek_true_candidates(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    source = Path(path)
    if not source.exists():
        return {}

    by_task_id: dict[str, dict[str, Any]] = {}
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        if record.get("verdict") != "true_candidate":
            continue
        task_id = str(record.get("task_id", ""))
        if task_id:
            by_task_id[task_id] = record
    return by_task_id


def _evidence_level(
    protocol_evidence: list[dict[str, Any]], llm_evidence: dict[str, Any] | None
) -> str:
    if protocol_evidence:
        return E2_API_PROTOCOL_SUPPORTED
    if llm_evidence:
        return E1_LLM_TRUE_CANDIDATE
    return E0_STATIC_RULE_ONLY


def _protocol_has_exception_hint(evidence: dict[str, Any]) -> bool:
    return bool(
        evidence.get("released_by_wrapper_possible")
        or evidence.get("ownership_transfer_possible")
    )


def _wrapper_evidence(
    protocol_evidence: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for evidence in protocol_evidence:
        for wrapper in evidence.get("wrapper_evidence", []):
            if not isinstance(wrapper, dict):
                continue
            key = (
                str(wrapper.get("function", "")),
                str(evidence.get("protocol_id", "")),
            )
            if key in seen:
                continue
            seen.add(key)
            enriched = dict(wrapper)
            enriched["protocol_id"] = evidence.get("protocol_id", "")
            enriched["required_action"] = evidence.get("required_action", "")
            collected.append(enriched)
    return collected


def _exception_hints(
    protocol_evidence: list[dict[str, Any]],
    ownership_transfer_hints: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for evidence in protocol_evidence:
        protocol_id = str(evidence.get("protocol_id", ""))
        resource_var = str(evidence.get("resource_var", ""))
        if evidence.get("released_by_wrapper_possible"):
            for wrapper in evidence.get("wrapper_evidence", []):
                function_name = str(wrapper.get("function", ""))
                key = ("released_by_wrapper", protocol_id, function_name)
                if key in seen:
                    continue
                seen.add(key)
                hints.append(
                    {
                        "type": "released_by_wrapper",
                        "protocol_id": protocol_id,
                        "function": function_name,
                        "resource_kind": evidence.get("resource_kind", ""),
                        "confidence": wrapper.get("confidence", "medium"),
                    }
                )
        if evidence.get("ownership_transfer_possible"):
            for hint in ownership_transfer_hints:
                if not isinstance(hint, dict):
                    continue
                same_var = str(hint.get("resource_expr", "")) == resource_var
                same_kind = str(hint.get("resource_kind", "")) == str(
                    evidence.get("resource_kind", "")
                )
                if not same_var and not same_kind:
                    continue
                key = (
                    "ownership_transferred",
                    protocol_id,
                    f"{hint.get('resource_expr', '')}:{hint.get('line', '')}",
                )
                if key in seen:
                    continue
                seen.add(key)
                enriched = dict(hint)
                enriched["type"] = "ownership_transferred"
                enriched["protocol_id"] = protocol_id
                hints.append(enriched)
    return hints


def _score(
    row: dict[str, str],
    protocol_evidence: list[dict[str, Any]],
    llm_evidence: dict[str, Any] | None,
) -> tuple[int, list[str]]:
    score = 10
    explanation = ["E0 static rule base +10"]
    if llm_evidence:
        score += 20
        explanation.append("E1 LLM true_candidate auxiliary signal +20")
    if protocol_evidence:
        if any(_protocol_has_exception_hint(evidence) for evidence in protocol_evidence):
            score += 10
            explanation.append("E2 API protocol support with exception hints +10")
        else:
            score += 30
            explanation.append("E2 API protocol support without exception hints +30")
    severity = row.get("severity", "")
    if severity == "P1":
        score += 20
        explanation.append("P1 severity +20")
    elif severity == "P2":
        score += 10
        explanation.append("P2 severity +10")
    if row.get("candidate_type") == "error_swallowed" and _norm_expr(
        row.get("final_return_expr", "")
    ) == "0":
        score += 20
        explanation.append("error_swallowed final return 0 +20")

    exception_kinds = {
        str(evidence.get("resource_kind", ""))
        for evidence in protocol_evidence
        if _protocol_has_exception_hint(evidence)
    }
    clean_kinds = {
        str(evidence.get("resource_kind", ""))
        for evidence in protocol_evidence
        if not _protocol_has_exception_hint(evidence)
    }
    all_kinds = {
        str(evidence.get("resource_kind", "")) for evidence in protocol_evidence
    }
    exception_actions = {
        str(evidence.get("required_action", ""))
        for evidence in protocol_evidence
        if _protocol_has_exception_hint(evidence)
    }
    clean_actions = {
        str(evidence.get("required_action", ""))
        for evidence in protocol_evidence
        if not _protocol_has_exception_hint(evidence)
    }
    all_actions = {
        str(evidence.get("required_action", "")) for evidence in protocol_evidence
    }
    high_kinds = {"journal", "journal_handle", "mutex", "spinlock", "rwsem"}
    high_actions = {
        "ext4_journal_stop",
        "mutex_unlock",
        "spin_unlock",
        "up_read",
        "up_write",
    }
    if clean_kinds.intersection(high_kinds) or clean_actions.intersection(high_actions):
        score += 20
        explanation.append("journal or lock protocol violation without exception hints +20")
    elif exception_kinds.intersection(high_kinds) or exception_actions.intersection(
        high_actions
    ):
        score += 5
        explanation.append("journal or lock protocol violation with exception hints +5")
    elif all_kinds.intersection(high_kinds) or all_actions.intersection(
        {"ext4_journal_stop", "mutex_unlock", "spin_unlock", "up_read", "up_write"}
    ):
        score += 20
        explanation.append("journal or lock protocol violation +20")

    if clean_kinds.intersection({"buffer_head", "memory"}):
        score += 10
        explanation.append("buffer_head or memory protocol violation without exception hints +10")
    elif exception_kinds.intersection({"buffer_head", "memory"}):
        score += 3
        explanation.append("buffer_head or memory protocol violation with exception hints +3")
    return score, explanation


def rank_candidate_rows(
    rows: Iterable[dict[str, str]],
    protocols: ResourceProtocolDB,
    deepseek_true_candidates: dict[str, dict[str, Any]] | None = None,
    wrapper_db: WrapperSummaryDB | None = None,
    linux_path: str | Path | None = None,
    enable_ownership_transfer_hints: bool = False,
    manual_reviews: ManualReviewDB | None = None,
) -> list[dict[str, Any]]:
    llm_records = deepseek_true_candidates or {}
    ranked: list[dict[str, Any]] = []
    for row in rows:
        static_evidence = _static_evidence(row)
        ownership_hints = (
            ownership_transfer_hints_for_candidate(
                row,
                linux_path or ".",
                static_evidence.get("held_resources", []),
            )
            if enable_ownership_transfer_hints
            else []
        )
        protocol_evidence = match_protocol_evidence(
            row,
            protocols,
            wrapper_db=wrapper_db,
            ownership_transfer_hints=ownership_hints,
        )
        task_id = llm_task_id_for_row(row)
        candidate_id = candidate_id_for_row(row)
        manual_review = (
            manual_reviews.find_any([candidate_id, task_id, row.get("path_id", "")])
            if manual_reviews
            else None
        )
        llm_record = llm_records.get(task_id)
        level = _evidence_level(protocol_evidence, llm_record)
        score, score_explanation = _score(row, protocol_evidence, llm_record)
        manual_adjustment, manual_explanation = manual_score_adjustment(manual_review)
        score += manual_adjustment
        score_explanation.extend(manual_explanation)
        wrapper_evidence = _wrapper_evidence(protocol_evidence)
        exception_hints = _exception_hints(protocol_evidence, ownership_hints)
        has_exception_hints = bool(exception_hints)
        ranked.append(
            {
                "candidate_id": candidate_id,
                "candidate_type": row.get("candidate_type", ""),
                "severity": row.get("severity", ""),
                "evidence_level": level,
                "evidence_score": score,
                "manual_review": manual_review.to_dict() if manual_review else {},
                "manual_score_adjustment": manual_adjustment,
                "static_evidence": static_evidence,
                "protocol_evidence": protocol_evidence,
                "wrapper_evidence": wrapper_evidence,
                "ownership_transfer_hints": ownership_hints,
                "has_exception_hints": has_exception_hints,
                "exception_hints": exception_hints,
                "score_explanation": score_explanation,
                "llm_evidence": llm_record or {},
                "missing_evidence": list(MISSING_EVIDENCE_V1),
                "file": row.get("file", ""),
                "function": row.get("function", ""),
                "path_id": row.get("path_id", ""),
                "error_line": _int_or_zero(row.get("error_line", "")),
                "condition": row.get("condition", ""),
                "final_return_expr": row.get("final_return_expr", ""),
                "llm_task_id": task_id,
            }
        )

    ranked.sort(
        key=lambda item: (
            -int(item.get("evidence_score", 0)),
            item.get("file", ""),
            item.get("function", ""),
            item.get("error_line", 0),
            item.get("candidate_type", ""),
        )
    )
    return ranked


def read_candidate_rows(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    if not source.exists():
        return []
    try:
        with source.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def write_ranked_candidates_jsonl(
    ranked: Iterable[dict[str, Any]], path: str | Path
) -> int:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", encoding="utf-8") as fh:
        for item in ranked:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
            count += 1
    return count


def write_candidates_with_evidence_csv(
    ranked: Iterable[dict[str, Any]], path: str | Path
) -> int:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        for item in ranked:
            protocol_evidence = item.get("protocol_evidence", [])
            matched_protocol_ids = [
                evidence.get("protocol_id", "") for evidence in protocol_evidence
            ]
            required_actions = [
                evidence.get("required_action", "") for evidence in protocol_evidence
            ]
            released_by_wrapper_possible = any(
                evidence.get("released_by_wrapper_possible")
                for evidence in protocol_evidence
            )
            ownership_transfer_possible = any(
                evidence.get("ownership_transfer_possible")
                for evidence in protocol_evidence
            )
            manual_review = item.get("manual_review", {})
            writer.writerow(
                {
                    "candidate_id": item.get("candidate_id", ""),
                    "file": item.get("file", ""),
                    "function": item.get("function", ""),
                    "error_line": item.get("error_line", ""),
                    "candidate_type": item.get("candidate_type", ""),
                    "severity": item.get("severity", ""),
                    "evidence_level": item.get("evidence_level", ""),
                    "evidence_score": item.get("evidence_score", ""),
                    "matched_protocol_ids": json.dumps(
                        matched_protocol_ids, ensure_ascii=False
                    ),
                    "required_actions": json.dumps(required_actions, ensure_ascii=False),
                    "has_exception_hints": str(
                        bool(item.get("has_exception_hints"))
                    ).lower(),
                    "exception_hints": json.dumps(
                        item.get("exception_hints", []), ensure_ascii=False
                    ),
                    "released_by_wrapper_possible": str(
                        released_by_wrapper_possible
                    ).lower(),
                    "ownership_transfer_possible": str(
                        ownership_transfer_possible
                    ).lower(),
                    "manual_verdict": manual_review.get("verdict", "")
                    if isinstance(manual_review, dict)
                    else "",
                    "manual_confidence": manual_review.get("confidence", "")
                    if isinstance(manual_review, dict)
                    else "",
                    "manual_review_source": manual_review.get("review_source", "")
                    if isinstance(manual_review, dict)
                    else "",
                    "manual_confirmed_exception": str(
                        bool(manual_review.get("confirmed_exception", False))
                    ).lower()
                    if isinstance(manual_review, dict) and manual_review
                    else "",
                    "manual_exception_type": manual_review.get(
                        "confirmed_exception_type", ""
                    )
                    if isinstance(manual_review, dict)
                    else "",
                    "manual_score_adjustment": item.get(
                        "manual_score_adjustment", 0
                    ),
                    "manual_reason": manual_review.get("reason", "")
                    if isinstance(manual_review, dict)
                    else "",
                    "manual_next_action": manual_review.get("next_action", "")
                    if isinstance(manual_review, dict)
                    else "",
                    "manual_validation_hint": manual_review.get(
                        "validation_hint", ""
                    )
                    if isinstance(manual_review, dict)
                    else "",
                    "score_explanation": json.dumps(
                        item.get("score_explanation", []), ensure_ascii=False
                    ),
                    "missing_evidence": json.dumps(
                        item.get("missing_evidence", []), ensure_ascii=False
                    ),
                    "final_return_expr": item.get("final_return_expr", ""),
                }
            )
            count += 1
    return count


def load_ranked_candidates_index(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    source = Path(path)
    if not source.exists():
        return {}

    index: dict[str, dict[str, Any]] = {}
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        for key in ["llm_task_id", "candidate_id"]:
            value = str(item.get(key, ""))
            if value:
                index[value] = item
    return index


def rank_candidates_from_csv(
    candidates_csv: str | Path,
    protocols: ResourceProtocolDB,
    ranked_candidates_out: str | Path,
    candidates_with_evidence_out: str | Path,
    deepseek_true_candidates_in: str | Path | None = None,
    wrapper_db: WrapperSummaryDB | None = None,
    linux_path: str | Path | None = None,
    enable_ownership_transfer_hints: bool = False,
    manual_review_labels_in: str | Path | None = None,
) -> dict[str, int]:
    rows = read_candidate_rows(candidates_csv)
    llm_records = load_deepseek_true_candidates(deepseek_true_candidates_in)
    manual_reviews = ManualReviewDB.load_from_file(manual_review_labels_in)
    ranked = rank_candidate_rows(
        rows,
        protocols,
        llm_records,
        wrapper_db=wrapper_db,
        linux_path=linux_path,
        enable_ownership_transfer_hints=enable_ownership_transfer_hints,
        manual_reviews=manual_reviews,
    )
    jsonl_count = write_ranked_candidates_jsonl(ranked, ranked_candidates_out)
    csv_count = write_candidates_with_evidence_csv(
        ranked, candidates_with_evidence_out
    )
    return {
        "total_candidates_in": len(rows),
        "ranked_candidates": len(ranked),
        "ranked_candidates_jsonl": jsonl_count,
        "candidates_with_evidence_csv": csv_count,
        "E0_STATIC_RULE_ONLY_count": sum(
            1 for item in ranked if item["evidence_level"] == E0_STATIC_RULE_ONLY
        ),
        "E1_LLM_TRUE_CANDIDATE_count": sum(
            1 for item in ranked if item["evidence_level"] == E1_LLM_TRUE_CANDIDATE
        ),
        "E2_API_PROTOCOL_SUPPORTED_count": sum(
            1
            for item in ranked
            if item["evidence_level"] == E2_API_PROTOCOL_SUPPORTED
        ),
        "exception_hints_count": sum(
            1 for item in ranked if item.get("has_exception_hints")
        ),
        "manual_review_labels_count": len(manual_reviews.labels),
        "manual_review_applied_count": sum(
            1 for item in ranked if item.get("manual_review")
        ),
    }
