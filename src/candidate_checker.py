"""Read error-path CSV rows and write suspicious candidate CSV rows."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from .candidate_rules import run_candidate_rules


CANDIDATE_COLUMNS = [
    "linux_git_commit",
    "linux_git_tag",
    "file",
    "function",
    "path_id",
    "error_line",
    "candidate_type",
    "severity",
    "condition",
    "branch_taken",
    "condition_start_byte",
    "condition_end_byte",
    "cfg_edge_id",
    "cfg_source_block",
    "cfg_target_block",
    "cfg_edge_kind",
    "cfg_witness",
    "exit_type",
    "target_label",
    "error_source_expr",
    "held_resources",
    "cleanup_calls",
    "missing_cleanup_candidates",
    "released_cleanup_candidates",
    "partial_cleanup",
    "resource_analysis",
    "final_return_expr",
    "evidence",
    "reason",
]


def read_error_paths(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_candidates_csv(
    candidates: Iterable[dict[str, str]], path: str | Path
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CANDIDATE_COLUMNS)
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(
                {column: candidate.get(column, "") for column in CANDIDATE_COLUMNS}
            )


def check_candidates(
    error_paths_csv: str | Path,
    candidates_csv: str | Path,
    analysis_contracts: dict | None = None,
    include_low_confidence: bool = False,
) -> dict[str, int]:
    rows = read_error_paths(error_paths_csv)
    candidates: list[dict[str, str]] = []
    for row in rows:
        candidates.extend(
            run_candidate_rules(
                row,
                analysis_contracts,
                include_low_confidence=include_low_confidence,
            )
        )

    write_candidates_csv(candidates, candidates_csv)

    stats = {
        "total_error_paths": len(rows),
        "total_candidates": len(candidates),
        "missing_cleanup_count": sum(
            1 for candidate in candidates if candidate["candidate_type"] == "missing_cleanup"
        ),
        "error_swallowed_count": sum(
            1 for candidate in candidates if candidate["candidate_type"] == "error_swallowed"
        ),
        "partial_cleanup_count": sum(
            1 for candidate in candidates if candidate["candidate_type"] == "partial_cleanup"
        ),
        "P1_count": sum(1 for candidate in candidates if candidate["severity"] == "P1"),
        "P2_count": sum(1 for candidate in candidates if candidate["severity"] == "P2"),
        "P3_count": sum(1 for candidate in candidates if candidate["severity"] == "P3"),
    }
    return stats
