"""Function-level source diffs for MOCC-SE development triage."""

from __future__ import annotations

import argparse
import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .frontend.model import FunctionIR
from .frontend.tree_sitter_frontend import TreeSitterFrontend


FUNCTION_DIFF_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class FunctionSourceInput:
    version: str
    path: str
    function: FunctionIR | None


@dataclass(frozen=True)
class FunctionPairDiff:
    from_version: str
    to_version: str
    function: str
    unified_diff: tuple[str, ...]
    removed_lines: tuple[str, ...]
    added_lines: tuple[str, ...]
    semantic_hints: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_version": self.from_version,
            "to_version": self.to_version,
            "function": self.function,
            "unified_diff": list(self.unified_diff),
            "removed_lines": list(self.removed_lines),
            "added_lines": list(self.added_lines),
            "semantic_hints": list(self.semantic_hints),
        }


@dataclass(frozen=True)
class FunctionDiffReport:
    function: str
    inputs: tuple[FunctionSourceInput, ...]
    pair_diffs: tuple[FunctionPairDiff, ...]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": FUNCTION_DIFF_SCHEMA_VERSION,
            "function": self.function,
            "inputs": [
                {
                    "version": item.version,
                    "path": item.path,
                    "found": item.function is not None,
                    "start_line": item.function.start_line if item.function else 0,
                    "end_line": item.function.end_line if item.function else 0,
                    "calls": _call_names(item.function) if item.function else [],
                    "return_expressions": _return_expressions(item.function.source)
                    if item.function
                    else [],
                }
                for item in self.inputs
            ],
            "summary": self.summary,
            "pair_diffs": [item.to_dict() for item in self.pair_diffs],
        }


def load_function_source(spec: str, function_name: str) -> FunctionSourceInput:
    if "=" not in spec:
        raise ValueError("function source must use VERSION=PATH")
    version, path = spec.split("=", 1)
    if not version or not path:
        raise ValueError("function source must use VERSION=PATH")
    unit = TreeSitterFrontend().parse(path)
    function = next((item for item in unit.functions if item.name == function_name), None)
    return FunctionSourceInput(version, path, function)


def build_function_diff(
    function_name: str,
    inputs: Iterable[FunctionSourceInput],
) -> FunctionDiffReport:
    ordered = tuple(inputs)
    pair_diffs = tuple(
        _pair_diff(left, right, function_name)
        for left, right in zip(ordered, ordered[1:])
    )
    summary = {
        "versions": [item.version for item in ordered],
        "found_versions": [
            item.version for item in ordered if item.function is not None
        ],
        "missing_versions": [
            item.version for item in ordered if item.function is None
        ],
        "pairs": len(pair_diffs),
        "pairs_with_changes": sum(1 for item in pair_diffs if item.unified_diff),
        "semantic_hints": _counts(
            hint for item in pair_diffs for hint in item.semantic_hints
        ),
    }
    return FunctionDiffReport(function_name, ordered, pair_diffs, summary)


def write_function_diff_json(report: FunctionDiffReport, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_function_diff_markdown(report: FunctionDiffReport, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Function diff: {report.function}",
        "",
        "This is a MOCC-SE development source-diff artifact, not benchmark evidence.",
        "",
        "Inputs:",
        "",
    ]
    for item in report.inputs:
        status = "found" if item.function else "missing"
        line_range = (
            f"L{item.function.start_line}-L{item.function.end_line}"
            if item.function
            else "n/a"
        )
        lines.append(f"- `{item.version}`: {status}, {line_range}, `{item.path}`")
    for diff in report.pair_diffs:
        lines.extend(
            [
                "",
                f"## {diff.from_version} -> {diff.to_version}",
                "",
                "Semantic hints:",
                "",
            ]
        )
        if diff.semantic_hints:
            lines.extend(f"- `{hint}`" for hint in diff.semantic_hints)
        else:
            lines.append("- none")
        lines.extend(["", "Unified diff:", "", "```diff"])
        lines.extend(diff.unified_diff or ["# no source changes"])
        lines.append("```")
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Diff one function across source versions for MOCC-SE triage."
    )
    parser.add_argument("--function", required=True)
    parser.add_argument("--source", action="append", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args(argv)

    report = build_function_diff(
        args.function,
        (load_function_source(spec, args.function) for spec in args.source),
    )
    write_function_diff_json(report, args.out_json)
    write_function_diff_markdown(report, args.out_md)
    print(f"function={report.function}")
    print(f"pairs={report.summary['pairs']}")
    print(f"pairs_with_changes={report.summary['pairs_with_changes']}")
    print(f"out_json={args.out_json}")
    print(f"out_md={args.out_md}")
    return 0


def _pair_diff(
    left: FunctionSourceInput,
    right: FunctionSourceInput,
    function_name: str,
) -> FunctionPairDiff:
    left_lines = _source_lines(left.function)
    right_lines = _source_lines(right.function)
    diff = tuple(
        difflib.unified_diff(
            left_lines,
            right_lines,
            fromfile=f"{left.version}:{left.path}",
            tofile=f"{right.version}:{right.path}",
            lineterm="",
        )
    )
    removed = tuple(line[1:] for line in diff if line.startswith("-") and not line.startswith("---"))
    added = tuple(line[1:] for line in diff if line.startswith("+") and not line.startswith("+++"))
    return FunctionPairDiff(
        left.version,
        right.version,
        function_name,
        diff,
        removed,
        added,
        _semantic_hints(left.function, right.function, removed, added),
    )


def _source_lines(function: FunctionIR | None) -> list[str]:
    if function is None:
        return []
    return function.source.splitlines()


def _call_names(function: FunctionIR | None) -> list[str]:
    if function is None:
        return []
    return sorted({call.callee_spelling for call in function.calls if call.callee_spelling})


def _return_expressions(source: str) -> list[str]:
    return [
        match.group(1).strip()
        for match in re.finditer(r"\breturn\s+(.+?);", source, re.DOTALL)
    ]


def _semantic_hints(
    left: FunctionIR | None,
    right: FunctionIR | None,
    removed: tuple[str, ...],
    added: tuple[str, ...],
) -> tuple[str, ...]:
    hints: list[str] = []
    if left is None and right is not None:
        hints.append("function_added")
    if left is not None and right is None:
        hints.append("function_removed")
    left_returns = set(_return_expressions(left.source)) if left else set()
    right_returns = set(_return_expressions(right.source)) if right else set()
    if "0" in left_returns and right_returns & {"ret", "error", "err"}:
        hints.append("return_success_changed_to_error_symbol")
    if any("return 0" in line for line in removed) and any(
        re.search(r"\breturn\s+(?:ret|error|err)\s*;", line) for line in added
    ):
        hints.append("local_return_propagation_repair")
    if any("XFS_IS_CORRUPT" in line for line in added):
        hints.append("added_corruption_guard")
    left_calls = set(_call_names(left))
    right_calls = set(_call_names(right))
    if right_calls - left_calls:
        hints.append("callee_set_expanded")
    if left_calls - right_calls:
        hints.append("callee_set_reduced")
    return tuple(dict.fromkeys(hints))


def _counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    raise SystemExit(main())
