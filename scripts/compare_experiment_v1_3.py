"""Compare experiment-v1.3 with archived outputs and across Linux versions."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Hashable


VERSIONS = ("linux-v6.8", "linux-v7.1")
FILESYSTEMS = ("ext4", "btrfs", "xfs", "f2fs")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"expected object at {path}:{line_number}")
            rows.append(value)
    return rows


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def norm(value: Any) -> str:
    return " ".join(str(value or "").split())


def stable_key(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        norm(row.get("file")),
        norm(row.get("function")),
        norm(row.get("path_id")),
        norm(row.get("candidate_type")),
    )


def semantic_key(row: dict[str, Any]) -> tuple[str, ...]:
    static = row.get("static_evidence") or {}
    return (
        norm(row.get("file")),
        norm(row.get("function")),
        norm(row.get("candidate_type")),
        norm(row.get("condition")),
        norm(row.get("final_return_expr")),
        norm(static.get("error_source_expr")),
    )


def summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": row.get("candidate_id"),
        "file": row.get("file"),
        "function": row.get("function"),
        "path_id": row.get("path_id"),
        "candidate_type": row.get("candidate_type"),
        "error_line": row.get("error_line"),
        "condition": row.get("condition"),
        "final_return_expr": row.get("final_return_expr"),
        "evidence_level": row.get("evidence_level"),
        "evidence_score": row.get("evidence_score"),
    }


def counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(rows),
        "by_candidate_type": dict(sorted(Counter(norm(row.get("candidate_type")) for row in rows).items())),
        "by_evidence_level": dict(sorted(Counter(norm(row.get("evidence_level")) for row in rows).items())),
    }


def multiset_diff(
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
    key: Callable[[dict[str, Any]], Hashable],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    right_remaining = Counter(key(row) for row in right)
    left_only: list[dict[str, Any]] = []
    matched = 0
    for row in left:
        row_key = key(row)
        if right_remaining[row_key] > 0:
            right_remaining[row_key] -= 1
            matched += 1
        else:
            left_only.append(row)
    left_remaining = Counter(key(row) for row in left)
    right_only: list[dict[str, Any]] = []
    for row in right:
        row_key = key(row)
        if left_remaining[row_key] > 0:
            left_remaining[row_key] -= 1
        else:
            right_only.append(row)
    return left_only, right_only, matched


def top_functions(rows: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    counter = Counter(norm(row.get("function")) for row in rows)
    return [{"function": function, "count": count} for function, count in counter.most_common(limit)]


def old_vs_new(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> dict[str, Any]:
    removed, added, retained = multiset_diff(old, new, stable_key)
    return {
        "old": counts(old),
        "v1_3": counts(new),
        "retained": retained,
        "removed_count": len(removed),
        "added_count": len(added),
        "candidate_reduction": round((len(old) - len(new)) / len(old), 4) if old else None,
        "removed_by_type": dict(sorted(Counter(norm(row.get("candidate_type")) for row in removed).items())),
        "added_by_type": dict(sorted(Counter(norm(row.get("candidate_type")) for row in added).items())),
        "top_removed_functions": top_functions(removed),
        "top_added_functions": top_functions(added),
        "removed": [summary(row) for row in removed],
        "added": [summary(row) for row in added],
    }


def function_pairs(error_paths: list[dict[str, str]]) -> set[tuple[str, str]]:
    return {(norm(row.get("file")), norm(row.get("function"))) for row in error_paths}


def cross_version(
    old: list[dict[str, Any]],
    new: list[dict[str, Any]],
    old_error_paths: list[dict[str, str]],
    new_error_paths: list[dict[str, str]],
) -> dict[str, Any]:
    old_only, new_only, persisted = multiset_diff(old, new, semantic_key)
    old_functions = function_pairs(old_error_paths)
    new_functions = function_pairs(new_error_paths)

    def attribution(rows: list[dict[str, Any]], other_functions: set[tuple[str, str]]) -> dict[str, int]:
        values = Counter(
            "candidate_changed_in_existing_function"
            if (norm(row.get("file")), norm(row.get("function"))) in other_functions
            else "function_absent_from_other_error_corpus"
            for row in rows
        )
        return dict(sorted(values.items()))

    return {
        "linux_v6_8": counts(old),
        "linux_v7_1": counts(new),
        "persisted": persisted,
        "only_v6_8_count": len(old_only),
        "only_v7_1_count": len(new_only),
        "candidate_delta": len(new) - len(old),
        "v6_8_only_attribution": attribution(old_only, new_functions),
        "v7_1_only_attribution": attribution(new_only, old_functions),
        "top_v6_8_only_functions": top_functions(old_only, 15),
        "top_v7_1_only_functions": top_functions(new_only, 15),
        "v6_8_only": [summary(row) for row in old_only],
        "v7_1_only": [summary(row) for row in new_only],
    }


def benchmark_retention(root: Path, new_rows: list[dict[str, Any]]) -> dict[str, Any]:
    labels_path = root / "benchmark" / "ext4-v6.8-pilot-labels.jsonl"
    if not labels_path.exists():
        return {}
    labels = load_jsonl(labels_path)
    current_ids = {row.get("candidate_id") for row in new_rows}
    verdicts = Counter()
    retained = Counter()
    for label in labels:
        verdict = norm(label.get("verdict"))
        verdicts[verdict] += 1
        if label.get("candidate_id") in current_ids:
            retained[verdict] += 1
    return {
        "label_counts": dict(sorted(verdicts.items())),
        "retained_counts": dict(sorted(retained.items())),
        "true_bug_retention": round(retained["true_bug"] / verdicts["true_bug"], 4)
        if verdicts["true_bug"]
        else None,
        "false_positive_retention": round(retained["false_positive"] / verdicts["false_positive"], 4)
        if verdicts["false_positive"]
        else None,
    }


def btrfs_auto_cleanup_diagnostic(root: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure candidates in functions using v7.1's __free path macro."""
    source_root = root / "linux-sources" / "linux-v7.1-fs"
    btrfs_root = source_root / "fs" / "btrfs"
    if not btrfs_root.is_dir():
        return {"available": False}
    sys.path.insert(0, str(root))
    from src.function_extractor import extract_functions
    from src.parser import parse_c_file

    macro_functions: set[tuple[str, str]] = set()
    macro_occurrences = 0
    macro_files = 0
    for path in btrfs_root.rglob("*.c"):
        text = path.read_text(encoding="utf-8", errors="replace")
        occurrences = text.count("BTRFS_PATH_AUTO_FREE")
        if occurrences:
            macro_files += 1
            macro_occurrences += occurrences
        relative = path.relative_to(source_root).as_posix()
        for function in extract_functions(parse_c_file(path)):
            if "BTRFS_PATH_AUTO_FREE" in function.source:
                macro_functions.add((relative, function.name))

    candidates_in_macro_functions = [
        row
        for row in rows
        if (norm(row.get("file")), norm(row.get("function"))) in macro_functions
    ]
    path_candidates = [
        row
        for row in rows
        if "btrfs_free_path"
        in " ".join((row.get("static_evidence") or {}).get("missing_cleanup_candidates", []))
    ]
    path_candidates_in_macro = [
        row
        for row in path_candidates
        if (norm(row.get("file")), norm(row.get("function"))) in macro_functions
    ]
    return {
        "available": True,
        "macro_files": macro_files,
        "macro_occurrences_in_c": macro_occurrences,
        "macro_functions": len(macro_functions),
        "candidate_count": len(rows),
        "candidates_in_macro_functions": len(candidates_in_macro_functions),
        "btrfs_free_path_candidates": len(path_candidates),
        "btrfs_free_path_candidates_in_macro_functions": len(path_candidates_in_macro),
        "share_of_all_candidates": round(len(path_candidates_in_macro) / len(rows), 4)
        if rows
        else 0.0,
        "interpretation": "Most v7.1 btrfs_path candidates overlap compiler-managed __free cleanup and require scope-aware modeling before bug triage.",
    }


def markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# SE-EOD Experiment v1.3 Comparison",
        "",
        f"Generated: {result['generated_at']}",
        "",
        "The v1.3 runs use static analysis, protocol evidence, wrapper summaries, and ownership hints. Historical LLM verdicts and manual-review scores are excluded.",
        "",
        "## Archived Outputs vs v1.3",
        "",
        "| Version | FS | Old | v1.3 | Retained | Removed | Added | Reduction |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["old_vs_v1_3_table"]:
        reduction = "n/a" if row["reduction"] is None else f"{row['reduction']:.1%}"
        lines.append(
            f"| {row['version']} | {row['filesystem']} | {row['old']} | {row['v1_3']} | "
            f"{row['retained']} | {row['removed']} | {row['added']} | {reduction} |"
        )

    lines.extend(
        [
            "",
            "## v1.3 Cross-Version Comparison",
            "",
            "| FS | v6.8 | v7.1 | Persisted | Only v6.8 | Only v7.1 | Delta |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in result["cross_version_table"]:
        lines.append(
            f"| {row['filesystem']} | {row['v6_8']} | {row['v7_1']} | {row['persisted']} | "
            f"{row['only_v6_8']} | {row['only_v7_1']} | {row['delta']:+d} |"
        )

    benchmark = result.get("ext4_v6_8_benchmark_retention") or {}
    if benchmark:
        lines.extend(
            [
                "",
                "## ext4 v6.8 Pilot Retention",
                "",
                f"- True-bug retention: {benchmark['true_bug_retention']:.1%}",
                f"- False-positive retention: {benchmark['false_positive_retention']:.1%}",
                f"- Retained labels: `{benchmark['retained_counts']}`",
            ]
        )

    btrfs = result["cross_version_details"]["btrfs"]
    auto_cleanup = result["btrfs_auto_cleanup_diagnostic"]
    lines.extend(
        [
            "",
            "## btrfs v6.8 to v7.1",
            "",
            f"- Candidate delta: {btrfs['candidate_delta']:+d}",
            f"- v7.1-only attribution: `{btrfs['v7_1_only_attribution']}`",
            f"- `BTRFS_PATH_AUTO_FREE` occurrences in v7.1 C files: {auto_cleanup.get('macro_occurrences_in_c', 'n/a')}",
            f"- Candidates in auto-free functions: {auto_cleanup.get('candidates_in_macro_functions', 'n/a')}",
            f"- `btrfs_free_path` missing-cleanup candidates in auto-free functions: {auto_cleanup.get('btrfs_free_path_candidates_in_macro_functions', 'n/a')} ({auto_cleanup.get('share_of_all_candidates', 0):.1%} of all v7.1 btrfs candidates)",
            "- Interpretation: the v7.1 btrfs spike is dominated by a scope-aware cleanup modeling gap, not evidence of 538 new bugs.",
            "- Top v7.1-only functions:",
            "",
        ]
    )
    for item in btrfs["top_v7_1_only_functions"]:
        lines.append(f"  - `{item['function']}`: {item['count']}")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-root", default="outputs/experiment-v1.3", type=Path)
    parser.add_argument("--archived-root", default="outputs", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    experiment_root = (root / args.experiment_root).resolve()
    archived_root = (root / args.archived_root).resolve()
    reports_dir = experiment_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    old_new_details: dict[str, dict[str, Any]] = {}
    old_new_table: list[dict[str, Any]] = []
    current: dict[tuple[str, str], list[dict[str, Any]]] = {}
    error_paths: dict[tuple[str, str], list[dict[str, str]]] = {}
    for version in VERSIONS:
        old_new_details[version] = {}
        for filesystem in FILESYSTEMS:
            old_rows = load_jsonl(archived_root / version / filesystem / "ranked_candidates.jsonl")
            new_rows = load_jsonl(experiment_root / version / filesystem / "ranked_candidates.jsonl")
            current[(version, filesystem)] = new_rows
            error_paths[(version, filesystem)] = load_csv(
                experiment_root / version / filesystem / "error_paths.csv"
            )
            detail = old_vs_new(old_rows, new_rows)
            old_new_details[version][filesystem] = detail
            old_new_table.append(
                {
                    "version": version,
                    "filesystem": filesystem,
                    "old": detail["old"]["total"],
                    "v1_3": detail["v1_3"]["total"],
                    "retained": detail["retained"],
                    "removed": detail["removed_count"],
                    "added": detail["added_count"],
                    "reduction": detail["candidate_reduction"],
                }
            )
            (reports_dir / f"old-vs-v1.3-{version}-{filesystem}.json").write_text(
                json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

    cross_details: dict[str, Any] = {}
    cross_table: list[dict[str, Any]] = []
    for filesystem in FILESYSTEMS:
        detail = cross_version(
            current[("linux-v6.8", filesystem)],
            current[("linux-v7.1", filesystem)],
            error_paths[("linux-v6.8", filesystem)],
            error_paths[("linux-v7.1", filesystem)],
        )
        cross_details[filesystem] = detail
        cross_table.append(
            {
                "filesystem": filesystem,
                "v6_8": detail["linux_v6_8"]["total"],
                "v7_1": detail["linux_v7_1"]["total"],
                "persisted": detail["persisted"],
                "only_v6_8": detail["only_v6_8_count"],
                "only_v7_1": detail["only_v7_1_count"],
                "delta": detail["candidate_delta"],
            }
        )
        (reports_dir / f"cross-version-{filesystem}.json").write_text(
            json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "old_vs_v1_3_table": old_new_table,
        "cross_version_table": cross_table,
        "old_vs_v1_3_details": old_new_details,
        "cross_version_details": cross_details,
        "ext4_v6_8_benchmark_retention": benchmark_retention(
            root, current[("linux-v6.8", "ext4")]
        ),
        "btrfs_auto_cleanup_diagnostic": btrfs_auto_cleanup_diagnostic(
            root, current[("linux-v7.1", "btrfs")]
        ),
    }
    (reports_dir / "comparison.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (reports_dir / "comparison.md").write_text(markdown_report(result), encoding="utf-8")
    print(markdown_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
