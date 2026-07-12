"""Summarize benchmark true-positive families and false-positive root causes."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from scripts.evaluate_benchmark import index_by_sample, load_jsonl
except ModuleNotFoundError:  # Direct execution.
    from evaluate_benchmark import index_by_sample, load_jsonl


def analyze(labels_rows: list[dict[str, Any]], taxonomy_rows: list[dict[str, Any]]) -> dict[str, Any]:
    labels = index_by_sample(labels_rows, "labels")
    taxonomy = index_by_sample(taxonomy_rows, "taxonomy")
    if set(labels) != set(taxonomy):
        missing = sorted(set(labels) - set(taxonomy))
        extra = sorted(set(taxonomy) - set(labels))
        raise ValueError(f"sample mismatch: missing_taxonomy={missing}, extra_taxonomy={extra}")

    false_positive_causes: Counter[str] = Counter()
    true_bug_families: Counter[str] = Counter()
    actions: dict[str, Counter[str]] = defaultdict(Counter)
    for sample_id, label in labels.items():
        verdict = label.get("verdict")
        category = str(taxonomy[sample_id].get("category", "")).strip()
        action = str(taxonomy[sample_id].get("action", "")).strip()
        if not category:
            raise ValueError(f"empty taxonomy category for {sample_id}")
        if verdict == "false_positive":
            false_positive_causes[category] += 1
            actions[category][action] += 1
        elif verdict == "true_bug":
            true_bug_families[category] += 1
        else:
            raise ValueError(f"taxonomy requires resolved verdict for {sample_id}: {verdict}")

    false_total = sum(false_positive_causes.values())
    ranked_causes = [
        {
            "category": category,
            "count": count,
            "share": round(count / false_total, 4) if false_total else 0.0,
            "actions": [
                {"action": action, "count": action_count}
                for action, action_count in action_counts.most_common()
            ],
        }
        for category, count in false_positive_causes.most_common()
        for action_counts in [actions[category]]
    ]
    return {
        "sample_count": len(labels),
        "false_positive_count": false_total,
        "true_bug_count": sum(true_bug_families.values()),
        "false_positive_causes": ranked_causes,
        "true_bug_families": [
            {"category": category, "count": count}
            for category, count in true_bug_families.most_common()
        ],
    }


def markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# Benchmark Taxonomy",
        "",
        "> Based on the first source-review pass; use for development prioritization, not final paper claims.",
        "",
        f"- Samples: {result['sample_count']}",
        f"- True bugs: {result['true_bug_count']}",
        f"- False positives: {result['false_positive_count']}",
        "",
        "## False-Positive Causes",
        "",
        "| Priority | Category | Count | Share |",
        "|---:|---|---:|---:|",
    ]
    for priority, item in enumerate(result["false_positive_causes"], 1):
        lines.append(f"| {priority} | `{item['category']}` | {item['count']} | {item['share']:.1%} |")
    lines.extend(["", "## Recommended Actions", ""])
    for item in result["false_positive_causes"]:
        lines.append(f"### {item['category']}")
        lines.append("")
        for action in item["actions"]:
            lines.append(f"- {action['action']} ({action['count']})")
        lines.append("")
    lines.extend(["## True-Bug Families", "", "| Category | Count |", "|---|---:|"])
    for item in result["true_bug_families"]:
        lines.append(f"| `{item['category']}` | {item['count']} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--taxonomy", required=True, type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--report-out", type=Path)
    args = parser.parse_args()

    result = analyze(load_jsonl(args.labels), load_jsonl(args.taxonomy))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.report_out:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(markdown_report(result), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
