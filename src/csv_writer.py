"""CSV output helpers."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .error_path_extractor import ErrorPath


CSV_COLUMNS = [
    "linux_git_commit",
    "linux_git_tag",
    "file",
    "function",
    "function_start_line",
    "function_end_line",
    "path_id",
    "error_line",
    "condition",
    "condition_type",
    "branch_taken",
    "condition_start_byte",
    "condition_end_byte",
    "cfg_edge_id",
    "cfg_source_block",
    "cfg_target_block",
    "cfg_edge_kind",
    "cfg_witness",
    "error_var",
    "error_source_expr",
    "exit_type",
    "target_label",
    "cleanup_calls",
    "final_return_expr",
    "held_resources",
    "missing_cleanup_candidates",
    "released_cleanup_candidates",
    "partial_cleanup",
    "resource_analysis",
    "confidence",
    "reason",
]


JSON_FIELDS = {
    "cleanup_calls",
    "held_resources",
    "missing_cleanup_candidates",
    "released_cleanup_candidates",
    "cfg_witness",
}


def write_error_paths_csv(paths: Iterable[ErrorPath], out_path: str | Path) -> None:
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for path in paths:
            row = asdict(path)
            for field in JSON_FIELDS:
                row[field] = json.dumps(row[field], ensure_ascii=False)
            writer.writerow({column: row.get(column, "") for column in CSV_COLUMNS})
