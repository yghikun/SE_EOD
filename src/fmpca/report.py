from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable


def write_json(path: str, value: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def evaluation_markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# FMPCA Evaluation Report",
        "",
        f"Manifest: `{summary['manifest']}`",
        "",
        f"Passed: {summary['passed']} / {summary['total']}",
        "",
        "| Case | Role | Expected | Actual | Pass |",
        "|---|---|---|---|---|",
    ]
    for case in summary["cases"]:
        lines.append(
            "| {id} | {role} | `{expected}` | `{actual}` | {passed} |".format(
                id=case["id"],
                role=case.get("role", "UNSPECIFIED"),
                expected=case["expected"],
                actual=case["actual"],
                passed="PASS" if case["passed"] else "FAIL",
            )
        )
    lines.extend(
        [
            "",
            "## Baseline Comparison",
            "",
            "| Case | B1 API pairing | B2 local restoration | B3 single-object typestate |",
            "|---|---|---|---|",
        ]
    )
    for case in summary["cases"]:
        baseline = case.get("baselines", {})
        lines.append(
            "| {id} | `{b1}` | `{b2}` | `{b3}` |".format(
                id=case["id"],
                b1=baseline.get("B1_API_PAIRING", "NOT_RUN"),
                b2=baseline.get("B2_LOCAL_FIELD_RESTORATION", "NOT_RUN"),
                b3=baseline.get("B3_SINGLE_OBJECT_TYPESTATE", "NOT_RUN"),
            )
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            f"- Catalog SHA-256: `{summary['catalog_sha256']}`",
            f"- Bug-specific condition count: `{summary['bug_specific_condition_count']}`",
            f"- Held-out checker modifications: `{summary['held_out_checker_modifications']}`",
            "- Results are relative to the loaded protocol, binding, path model, and assumptions; no absolute SAFE claim is made.",
            "",
        ]
    )
    rejections = summary.get("screening_rejections", [])
    if rejections:
        lines.extend(
            [
                "",
                "## Screening Rejections",
                "",
                "| Operation family | Status | Reason |",
                "|---|---|---|",
            ]
        )
        for rejection in rejections:
            lines.append(
                "| {operation_family} | `{candidate_status}` | {reason} |".format(
                    operation_family=rejection["operation_family"],
                    candidate_status=rejection["candidate_status"],
                    reason=rejection["reason"],
                )
            )
    return "\n".join(lines)


def write_markdown(path: str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def count_bug_specific_conditions(values: Iterable[Dict[str, Any]]) -> int:
    forbidden = {"bug_id", "target_function", "source_line", "patch_id"}
    count = 0

    def visit(value: Any) -> None:
        nonlocal count
        if isinstance(value, dict):
            for key, item in value.items():
                if key in forbidden:
                    count += 1
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    for value in values:
        visit(value)
    return count
