"""Create a blinded, stratified benchmark pilot from ranked candidates."""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"expected an object at {path}:{line_number}")
            rows.append(row)
    if not rows:
        raise ValueError(f"no candidate rows found in {path}")
    return rows


def rank_bucket(index: int, total: int) -> str:
    # Equal thirds make the pilot cover high-, middle-, and low-ranked rows.
    if index < total / 3:
        return "top"
    if index < (2 * total) / 3:
        return "middle"
    return "low"


def stratified_pick(
    rows: list[dict[str, Any]], target: int, rng: random.Random
) -> list[dict[str, Any]]:
    """Pick across candidate types while preserving the ranked bucket."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get("candidate_type", "unknown"))].append(row)
    for group in groups.values():
        rng.shuffle(group)

    picked: list[dict[str, Any]] = []
    types = sorted(groups)
    while len(picked) < min(target, len(rows)) and types:
        next_types: list[str] = []
        for candidate_type in types:
            group = groups[candidate_type]
            if group and len(picked) < target:
                picked.append(group.pop())
            if group:
                next_types.append(candidate_type)
        types = next_types
    return sorted(picked, key=lambda row: row["_rank"])


def blinded_row(row: dict[str, Any], sample_id: str, version: str, filesystem: str) -> dict[str, Any]:
    static = row.get("static_evidence") or {}
    return {
        "sample_id": sample_id,
        "candidate_id": row.get("candidate_id"),
        "linux_version": version,
        "filesystem": filesystem,
        "file": row.get("file"),
        "function": row.get("function"),
        "error_line": row.get("error_line"),
        "path_id": row.get("path_id"),
        "candidate_type": row.get("candidate_type"),
        "severity": row.get("severity"),
        "condition": row.get("condition"),
        "final_return_expr": row.get("final_return_expr"),
        "error_source_expr": row.get("error_source_expr"),
        "target_label": static.get("target_label"),
        "annotation": {
            "verdict": None,
            "confidence": None,
            "reason": None,
            "evidence": [],
            "upstream_status": "unknown",
            "reviewer": None,
            "reviewed_at": None,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="ranked candidates JSONL")
    parser.add_argument("--output", required=True, type=Path, help="blinded pilot JSONL")
    parser.add_argument("--manifest-out", type=Path, help="optional non-blinded sampling manifest")
    parser.add_argument("--version", default="v6.8")
    parser.add_argument("--filesystem", default="ext4")
    parser.add_argument("--per-bucket", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260712)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.per_bucket <= 0:
        raise SystemExit("--per-bucket must be positive")

    rows = load_jsonl(args.input)
    for rank, row in enumerate(rows, 1):
        row["_rank"] = rank
        row["_bucket"] = rank_bucket(rank - 1, len(rows))

    rng = random.Random(args.seed)
    selected: list[dict[str, Any]] = []
    for bucket in ("top", "middle", "low"):
        bucket_rows = [row for row in rows if row["_bucket"] == bucket]
        picked = stratified_pick(bucket_rows, args.per_bucket, rng)
        selected.extend(picked)

    selected.sort(key=lambda row: row["_rank"])
    manifest = [
        {
            "sample_id": f"{args.filesystem}_{args.version}_{index:03d}",
            "candidate_id": row.get("candidate_id"),
            "source_rank": row["_rank"],
            "rank_bucket": row["_bucket"],
            "candidate_type": row.get("candidate_type"),
            "evidence_score": row.get("evidence_score"),
            "evidence_level": row.get("evidence_level"),
            "llm_verdict": (row.get("llm_evidence") or {}).get("verdict"),
        }
        for index, row in enumerate(selected, 1)
    ]
    output_rows = [
        blinded_row(row, f"{args.filesystem}_{args.version}_{index:03d}", args.version, args.filesystem)
        for index, row in enumerate(selected, 1)
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for row in output_rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    if args.manifest_out:
        args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
        with args.manifest_out.open("w", encoding="utf-8", newline="\n") as handle:
            for row in sorted(manifest, key=lambda item: item["source_rank"]):
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    print(f"input_candidates={len(rows)}")
    print(f"pilot_candidates={len(output_rows)}")
    print(f"per_bucket={args.per_bucket}")
    print(f"output={args.output}")
    if args.manifest_out:
        print(f"manifest={args.manifest_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
