"""Rank batch triage items for manual bug hunting without making bug claims."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


BUG_HUNT_RANKING_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RankedBugHuntItem:
    rank_key: tuple[int, int, int, str, str, str]
    record: dict[str, Any]
    triage: dict[str, Any]
    review_class: str
    risk_score: int
    risk_reasons: tuple[str, ...]
    downrank_reasons: tuple[str, ...]
    source_excerpt: tuple[str, ...]

    def to_dict(self, rank: int) -> dict[str, Any]:
        return {
            "rank": rank,
            "review_class": self.review_class,
            "risk_score": self.risk_score,
            "risk_reasons": list(self.risk_reasons),
            "downrank_reasons": list(self.downrank_reasons),
            "record": self.record,
            "triage": self.triage,
            "source_excerpt": list(self.source_excerpt),
        }


def build_bug_hunt_ranking(
    triage_report: Mapping[str, Any],
    *,
    workspace: str | Path = ".",
    source_root_template: str = "linux-sources/linux-v{version}-fs/fs",
    top: int = 50,
) -> dict[str, Any]:
    root = Path(workspace).resolve()
    items = [
        _rank_item(
            root,
            item,
            source_root_template=source_root_template,
        )
        for item in triage_report.get("items", ())
        if isinstance(item, Mapping)
    ]
    ranked = sorted(items, key=lambda item: item.rank_key)
    selected = ranked[:top] if top else ranked
    classes = Counter(item.review_class for item in ranked)
    protocols = Counter(item.record.get("protocol_id", "") for item in ranked)
    return {
        "schema_version": BUG_HUNT_RANKING_SCHEMA_VERSION,
        "result_semantics": "manual_bug_hunt_prioritization_not_bug_claims",
        "source_version": triage_report.get("source_version", ""),
        "summary": {
            "ranked_items": len(ranked),
            "emitted_items": len(selected),
            "by_review_class": dict(sorted(classes.items())),
            "by_protocol": dict(sorted(protocols.items())),
            "top_risk_score": selected[0].risk_score if selected else 0,
        },
        "ranking_policy": {
            "higher_priority": [
                "source-visible lifecycle candidate with exact opened object",
                "terminal action absent from the function body",
                "high static certainty and non-allocation-failure exit",
            ],
            "downranked": [
                "acquire failure guard returns before a resource exists",
                "allocated object is returned to caller",
                "automatic cleanup macro owns the object",
                "matching terminal action is visible in the function body",
                "analysis unknown caused by unresolved object identity",
            ],
        },
        "items": [item.to_dict(index) for index, item in enumerate(selected, 1)],
    }


def _rank_item(
    root: Path,
    item: Mapping[str, Any],
    *,
    source_root_template: str,
) -> RankedBugHuntItem:
    record = dict(item.get("record", {}))
    triage = dict(item.get("triage", {}))
    source = _resolve_source(root, record, source_root_template)
    function_text, excerpt = _function_source_excerpt(source, str(record.get("function", "")))
    features = _source_features(record, function_text)
    risk_score, risk_reasons, downrank_reasons = _score(record, triage, features)
    review_class = _review_class(risk_score, downrank_reasons, record)
    rank_key = (
        -risk_score,
        len(downrank_reasons),
        0 if triage.get("priority") == "P0" else 1,
        str(record.get("protocol_id", "")),
        str(record.get("source_file", "")),
        str(record.get("function", "")),
    )
    return RankedBugHuntItem(
        rank_key=rank_key,
        record=record,
        triage=triage,
        review_class=review_class,
        risk_score=risk_score,
        risk_reasons=tuple(risk_reasons),
        downrank_reasons=tuple(downrank_reasons),
        source_excerpt=tuple(excerpt),
    )


def _score(
    record: Mapping[str, Any],
    triage: Mapping[str, Any],
    features: Mapping[str, bool],
) -> tuple[int, list[str], list[str]]:
    score = 0
    risk: list[str] = []
    down: list[str] = []
    classification = str(record.get("classification", ""))
    reasons = set(str(item) for item in record.get("reasons", ()))
    open_effects = tuple(record.get("open_effects", ()))

    if classification == "DISCOVERY_REVIEW" and open_effects:
        score += 70
        risk.append("semantic review contains an opened lifecycle effect at an exit")
    if str(record.get("static_certainty", "")) == "high":
        score += 10
        risk.append("analyzer marked the lifecycle witness high-certainty")
    if record.get("exit_kind") == "failure":
        score += 6
        risk.append("the open effect reaches a failure exit")
    if record.get("exit_kind") == "success":
        score += 3
        risk.append("the open effect reaches a success exit")
    if triage.get("priority") == "P0":
        score += 8
        risk.append("triage priority is P0")
    if "summary_object_identity_unknown" in reasons:
        score -= 35
        down.append("analysis unknown: summary object identity unresolved")
    if "open_summary_not_proven_must" in reasons:
        score -= 20
        down.append("analysis unknown: open summary not proven must")
    if features["acquire_failure_guard"]:
        score -= 60
        down.append("exit appears to be the acquire-failure guard before ownership exists")
    if features["returned_allocated_object"]:
        score -= 55
        down.append("allocated object appears to be returned to caller as ownership transfer")
    if features["automatic_cleanup"]:
        score -= 50
        down.append("function uses an automatic cleanup macro for the object")
    if features["terminal_visible"]:
        score -= 35
        down.append("matching terminal action is visible in the function body")
    if features["caller_owned_argument"]:
        score -= 25
        down.append("the candidate object appears to be caller-owned or conditionally borrowed")

    return max(score, 0), risk, down


def _review_class(
    risk_score: int,
    downrank_reasons: tuple[str, ...],
    record: Mapping[str, Any],
) -> str:
    if risk_score >= 70 and not downrank_reasons:
        return "manual_source_review_high"
    if risk_score >= 45:
        return "manual_source_review_medium"
    if record.get("classification") == "DISCOVERY_REVIEW_UNKNOWN":
        return "analyzer_capability_gap"
    return "likely_protocol_gap_or_false_positive"


def _source_features(record: Mapping[str, Any], function_text: str) -> dict[str, bool]:
    expressions = tuple(
        str(effect.get("object_ref", {}).get("expression", ""))
        for effect in record.get("open_effects", ())
        if isinstance(effect, Mapping)
    )
    terminal_pattern = _terminal_pattern(record, expressions)
    return {
        "terminal_visible": bool(terminal_pattern and re.search(terminal_pattern, function_text)),
        "automatic_cleanup": _has_automatic_cleanup(function_text, expressions),
        "returned_allocated_object": _returns_allocated_object(function_text, expressions),
        "acquire_failure_guard": _is_acquire_failure_guard(record, function_text, expressions),
        "caller_owned_argument": _looks_caller_owned(function_text, expressions),
    }


def _terminal_pattern(record: Mapping[str, Any], expressions: tuple[str, ...]) -> str:
    protocol_id = str(record.get("protocol_id", ""))
    escaped = [re.escape(expr) for expr in expressions if expr]
    expr_group = "|".join(escaped) or r"[A-Za-z_]\w*"
    if protocol_id.endswith("allocation_lifecycle"):
        return rf"\bbtrfs_free_path\s*\(\s*(?:{expr_group})\s*\)"
    if protocol_id.endswith("transaction_lifecycle"):
        return rf"\b(?:ext4_journal_stop|xfs_trans_commit|xfs_trans_cancel)\s*\(\s*(?:{expr_group})\s*\)"
    return ""


def _has_automatic_cleanup(function_text: str, expressions: tuple[str, ...]) -> bool:
    for expr in expressions:
        if expr and re.search(rf"\bBTRFS_PATH_AUTO_FREE\s*\(\s*{re.escape(expr)}\s*\)", function_text):
            return True
    return "__free(" in function_text or "DEFINE_FREE(" in function_text


def _returns_allocated_object(function_text: str, expressions: tuple[str, ...]) -> bool:
    header = function_text.split("{", 1)[0]
    returns_pointer = "*" in header
    if not returns_pointer:
        return False
    return any(
        expr and re.search(rf"\breturn\s+{re.escape(expr)}\s*;", function_text)
        for expr in expressions
    )


def _is_acquire_failure_guard(
    record: Mapping[str, Any],
    function_text: str,
    expressions: tuple[str, ...],
) -> bool:
    witness = tuple(record.get("representative_witness", ()))
    exit_detail = " ".join(
        str(item.get("detail", ""))
        for item in witness
        if isinstance(item, Mapping) and item.get("kind") == "exit"
    )
    if not re.search(r"return\s+(?:-ENOMEM|PTR_ERR\(|NULL|ERR_PTR)", exit_detail):
        return False
    if re.search(r"return\s+(?:-ENOMEM|PTR_ERR\(|NULL|ERR_PTR)", exit_detail):
        for expr in expressions:
            if not expr:
                continue
            guard = (
                rf"if\s*\(\s*(?:unlikely\s*\(\s*)?"
                rf"(?:!{re.escape(expr)}|IS_ERR\s*\(\s*{re.escape(expr)}\s*\))"
                rf"[^)]*\)\s*(?:\{{[^{{}}]*)?"
                rf"(?:return\s+(?:-ENOMEM|PTR_ERR\(|NULL|ERR_PTR)|goto)\b"
            )
            if re.search(guard, function_text, re.DOTALL):
                return True
        if re.search(
            r"if\s*\([^;\n]*(?:xfs_trans_alloc|btrfs_alloc_path)\s*\([^;\n]*\)\s*\)"
            r"\s*(?:\{[^{}]*)?(?:return|goto)\b",
            function_text,
            re.DOTALL,
        ):
            return True
    return False


def _looks_caller_owned(function_text: str, expressions: tuple[str, ...]) -> bool:
    header = function_text.split("{", 1)[0]
    parameters = header.split("(", 1)[1].rsplit(")", 1)[0] if "(" in header and ")" in header else ""
    return any(expr and re.search(rf"\b{re.escape(expr)}\b", parameters) for expr in expressions)


def _resolve_source(
    root: Path,
    record: Mapping[str, Any],
    source_root_template: str,
) -> Path:
    source_file = str(record.get("source_file", ""))
    version = str(record.get("source_version", ""))
    if source_file.startswith(("E:/", "C:/")):
        return Path(source_file)
    source_root = source_root_template.format(version=version)
    return root / source_root / source_file


def _function_source_excerpt(path: Path, function: str) -> tuple[str, list[str]]:
    if not path.is_file() or not function:
        return "", []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = _find_function_start(lines, function)
    if start is None:
        return "", []
    end = _find_function_end(lines, start)
    function_lines = lines[start:end]
    excerpt_start = max(start, _witness_min_line(function_lines, start + 1) - 8)
    excerpt_end = min(len(lines), excerpt_start + 80)
    excerpt = [
        f"{line_no:5d}: {lines[line_no - 1]}"
        for line_no in range(excerpt_start + 1, excerpt_end + 1)
    ]
    return "\n".join(function_lines), excerpt


def _find_function_start(lines: list[str], function: str) -> int | None:
    pattern = re.compile(rf"\b{re.escape(function)}\s*\(")
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith(("*", "/*", "//")):
            continue
        if pattern.search(line):
            probe = index
            while probe < len(lines) and "{" not in lines[probe] and ";" not in lines[probe]:
                probe += 1
            if probe < len(lines) and "{" in lines[probe]:
                return index
    return None


def _find_function_end(lines: list[str], start: int) -> int:
    depth = 0
    seen_open = False
    for index in range(start, len(lines)):
        depth += lines[index].count("{")
        if "{" in lines[index]:
            seen_open = True
        depth -= lines[index].count("}")
        if seen_open and depth <= 0:
            return index + 1
    return min(len(lines), start + 120)


def _witness_min_line(function_lines: list[str], start_line: int) -> int:
    for offset, line in enumerate(function_lines):
        if "btrfs_alloc_path" in line or "ext4_journal_start" in line or "xfs_trans_alloc" in line:
            return start_line + offset
    return start_line


def load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rank MOCC-SE batch triage items for manual bug hunting."
    )
    parser.add_argument("--triage-report", required=True)
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--source-root-template", default="linux-sources/linux-v{version}-fs/fs")
    parser.add_argument("--top", type=int, default=50)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    payload = build_bug_hunt_ranking(
        load_json(args.triage_report),
        workspace=args.workspace,
        source_root_template=args.source_root_template,
        top=args.top,
    )
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
