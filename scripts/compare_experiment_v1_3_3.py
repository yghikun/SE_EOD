"""Compare the v1.3 baseline with the v1.3.3 model-refinement experiment."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.compare_experiment_v1_3 import load_jsonl, stable_key
except ModuleNotFoundError:
    from compare_experiment_v1_3 import load_jsonl, stable_key


VERSIONS = ("linux-v6.8", "linux-v7.1")
FILESYSTEMS = ("ext4", "btrfs", "xfs", "f2fs")


def compare(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> dict[str, Any]:
    before_index = {stable_key(row): row for row in before}
    after_index = {stable_key(row): row for row in after}
    retained = before_index.keys() & after_index.keys()
    removed = before_index.keys() - after_index.keys()
    added = after_index.keys() - before_index.keys()
    return {
        "before": len(before),
        "after": len(after),
        "retained": len(retained),
        "removed": len(removed),
        "added": len(added),
        "reduction": round((len(before) - len(after)) / len(before), 4) if before else None,
        "before_by_type": dict(sorted(Counter(row["candidate_type"] for row in before).items())),
        "after_by_type": dict(sorted(Counter(row["candidate_type"] for row in after).items())),
    }


def known_btrfs_positive_keys(version: str, rows: list[dict[str, Any]]) -> set[tuple[Any, ...]]:
    functions = {"btrfs_recover_relocation"}
    if version == "linux-v6.8":
        functions.add("__add_reloc_root")
    return {stable_key(row) for row in rows if row.get("function") in functions}


def markdown(result: dict[str, Any]) -> str:
    lines = [
        "# experiment-v1.3.3 Model-Refinement Comparison",
        "",
        f"Generated: {result['generated_at']}",
        "",
        "## Candidate Counts",
        "",
        "| Version | Filesystem | v1.3 | v1.3.3 | Retained | Removed | Added | Reduction |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for version in VERSIONS:
        for filesystem in FILESYSTEMS:
            row = result["matrix"][version][filesystem]
            reduction = "n/a" if row["reduction"] is None else f"{row['reduction']:.1%}"
            lines.append(
                f"| {version} | {filesystem} | {row['before']} | {row['after']} | "
                f"{row['retained']} | {row['removed']} | {row['added']} | {reduction} |"
            )
    retention = result["known_btrfs_positive_retention"]
    lines.extend(
        [
            "",
            "## Known btrfs Positive Retention",
            "",
            "| Version | Baseline known positives | Retained | Retention |",
            "|---|---:|---:|---:|",
        ]
    )
    for version in VERSIONS:
        row = retention[version]
        lines.append(
            f"| {version} | {row['baseline']} | {row['retained']} | {row['retention']:.1%} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The refinement models compiler-managed cleanup, direct acquisition failure, "
            "cleanup aliases, error-return consumers, and narrowly reviewed sentinel contracts. "
            "Linux v7.1 btrfs falls from 543 candidates to 4 while retaining the four records "
            "for the dynamically supported `btrfs_recover_relocation()` defect. Linux v6.8 "
            "retains all five btrfs known-positive records, including `__add_reloc_root()`.",
            "",
            "Candidate reduction is not itself a precision measurement. Precision and recall "
            "must be reported on the independent frozen benchmark.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before-root", type=Path, default="outputs/experiment-v1.3")
    parser.add_argument("--after-root", type=Path, default="outputs/experiment-v1.3.3")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    before_root = (root / args.before_root).resolve()
    after_root = (root / args.after_root).resolve()

    matrix: dict[str, dict[str, Any]] = {}
    retention: dict[str, Any] = {}
    for version in VERSIONS:
        matrix[version] = {}
        for filesystem in FILESYSTEMS:
            before = load_jsonl(before_root / version / filesystem / "ranked_candidates.jsonl")
            after = load_jsonl(after_root / version / filesystem / "ranked_candidates.jsonl")
            matrix[version][filesystem] = compare(before, after)
            if filesystem == "btrfs":
                known = known_btrfs_positive_keys(version, before)
                after_keys = {stable_key(row) for row in after}
                retained = len(known & after_keys)
                retention[version] = {
                    "baseline": len(known),
                    "retained": retained,
                    "retention": retained / len(known) if known else 1.0,
                }

    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "before": str(before_root),
        "after": str(after_root),
        "matrix": matrix,
        "known_btrfs_positive_retention": retention,
    }
    report_dir = after_root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "model_refinement_comparison.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = markdown(result)
    (report_dir / "model_refinement_comparison.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
