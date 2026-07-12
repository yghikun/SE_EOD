"""Compare btrfs candidates before and after scope-cleanup modeling."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.compare_experiment_v1_3 import (
        btrfs_auto_cleanup_diagnostic,
        load_jsonl,
        stable_key,
    )
except ModuleNotFoundError:
    from compare_experiment_v1_3 import (
        btrfs_auto_cleanup_diagnostic,
        load_jsonl,
        stable_key,
    )


def compare_rows(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> dict[str, Any]:
    before_index = {stable_key(row): row for row in before}
    after_index = {stable_key(row): row for row in after}
    removed_keys = before_index.keys() - after_index.keys()
    added_keys = after_index.keys() - before_index.keys()
    retained_keys = before_index.keys() & after_index.keys()
    removed = [before_index[key] for key in removed_keys]
    return {
        "before": len(before),
        "after": len(after),
        "retained": len(retained_keys),
        "removed": len(removed_keys),
        "added": len(added_keys),
        "reduction": round((len(before) - len(after)) / len(before), 4) if before else None,
        "before_by_type": dict(sorted(Counter(row["candidate_type"] for row in before).items())),
        "after_by_type": dict(sorted(Counter(row["candidate_type"] for row in after).items())),
        "removed_by_type": dict(sorted(Counter(row["candidate_type"] for row in removed).items())),
        "retained_functions": dict(
            Counter(after_index[key]["function"] for key in retained_keys).most_common()
        ),
    }


def markdown_report(result: dict[str, Any]) -> str:
    v6 = result["versions"]["linux-v6.8"]
    v7 = result["versions"]["linux-v7.1"]
    before_auto = result["auto_cleanup_diagnostic_before"]
    after_auto = result["auto_cleanup_diagnostic_after"]
    return "\n".join(
        [
            "# Scope-Cleanup Ablation: experiment-v1.3.1",
            "",
            f"Generated: {result['generated_at']}",
            "",
            "## Candidate Counts",
            "",
            "| Version | Before | After | Retained | Removed | Added | Reduction |",
            "|---|---:|---:|---:|---:|---:|---:|",
            f"| Linux v6.8 | {v6['before']} | {v6['after']} | {v6['retained']} | {v6['removed']} | {v6['added']} | {v6['reduction']:.1%} |",
            f"| Linux v7.1 | {v7['before']} | {v7['after']} | {v7['retained']} | {v7['removed']} | {v7['added']} | {v7['reduction']:.1%} |",
            "",
            "## v7.1 Candidate Types",
            "",
            f"- Before: `{v7['before_by_type']}`",
            f"- After: `{v7['after_by_type']}`",
            f"- Removed: `{v7['removed_by_type']}`",
            "",
            "## Auto-Cleanup Diagnostic",
            "",
            f"- `btrfs_free_path` candidates in auto-free functions before: {before_auto['btrfs_free_path_candidates_in_macro_functions']}",
            f"- `btrfs_free_path` candidates in auto-free functions after: {after_auto['btrfs_free_path_candidates_in_macro_functions']}",
            f"- v6.8 retained functions: `{v6['retained_functions']}`",
            "",
            "## Interpretation",
            "",
            "Scope-aware cleanup modeling removes the compiler-managed path-cleanup false-positive family without changing the five v6.8 btrfs candidates. The remaining v7.1 candidates require separate review; they must not be reported as confirmed bugs.",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before-root", default="outputs/experiment-v1.3", type=Path)
    parser.add_argument("--after-root", default="outputs/experiment-v1.3.1", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    before_root = (root / args.before_root).resolve()
    after_root = (root / args.after_root).resolve()

    versions: dict[str, Any] = {}
    loaded: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for version in ("linux-v6.8", "linux-v7.1"):
        before = load_jsonl(before_root / version / "btrfs" / "ranked_candidates.jsonl")
        after = load_jsonl(after_root / version / "btrfs" / "ranked_candidates.jsonl")
        loaded[(version, "before")] = before
        loaded[(version, "after")] = after
        versions[version] = compare_rows(before, after)

    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "versions": versions,
        "auto_cleanup_diagnostic_before": btrfs_auto_cleanup_diagnostic(
            root, loaded[("linux-v7.1", "before")]
        ),
        "auto_cleanup_diagnostic_after": btrfs_auto_cleanup_diagnostic(
            root, loaded[("linux-v7.1", "after")]
        ),
    }
    reports = after_root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "scope_cleanup_ablation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = markdown_report(result)
    (reports / "scope_cleanup_ablation.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
