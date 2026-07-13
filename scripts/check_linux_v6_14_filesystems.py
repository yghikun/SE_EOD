"""Run CFG/resource bug checks on Linux v6.14 and prepare LLM review tasks.

The script is intentionally orchestration-only: the analysis remains in
``src.main``.  By default it never calls an external model; each filesystem
gets a self-contained ``llm_review_tasks.jsonl`` that can be sent to an LLM.
Use ``--run-deepseek`` only when ``DEEPSEEK_API_KEY`` is configured.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FILESYSTEMS = ("ext4", "btrfs", "f2fs", "xfs")


def build_command(root: Path, source: Path, output: Path, fs: str, args: argparse.Namespace) -> list[str]:
    configs = root / "configs"
    command = [
        sys.executable, "-m", "src.main", "--linux", str(source),
        "--fs-subdir", f"fs/{fs}",
        "--resource-map", str(configs / f"{fs}_resource_map.json"),
        "--out", str(output / "error_paths.csv"),
        "--check-candidates", "--candidates-out", str(output / "suspicious_candidates.csv"),
        "--rank-evidence", "--protocols-dir", str(configs / f"{fs}_resource_protocols"),
        "--wrapper-summaries", str(configs / ("wrapper_summaries.json" if fs == "ext4" else f"{fs}_wrapper_summaries.json")),
        "--enable-ownership-transfer-hints",
        "--deepseek-true-candidates-in", str(output / "_no_llm_evidence.jsonl"),
        "--ranked-candidates-out", str(output / "ranked_candidates.jsonl"),
        "--candidates-with-evidence-out", str(output / "candidates_with_evidence.csv"),
        "--build-llm-tasks", "--llm-tasks-out", str(output / "llm_review_tasks.jsonl"),
        "--context-lines", str(args.context_lines),
        "--enable-interprocedural", "--function-summaries-out", str(output / "function_summaries.json"),
    ]
    historical = configs / f"{fs}_historical_fixes.json"
    if historical.exists():
        command.extend(["--historical-fixes", str(historical)])
    if args.min_evidence_score is not None:
        command.extend(["--min-evidence-score", str(args.min_evidence_score)])
    if args.run_deepseek:
        command.extend([
            "--run-deepseek-review",
            "--deepseek-reviews-out", str(output / "deepseek_reviews.jsonl"),
            "--deepseek-true-candidates-out", str(output / "deepseek_true_candidates.jsonl"),
        ])
        if args.deepseek_limit is not None:
            command.extend(["--deepseek-limit", str(args.deepseek_limit)])
    return command


def parse_stats(stdout: str) -> dict[str, int | str]:
    stats: dict[str, int | str] = {}
    for line in stdout.splitlines():
        key, sep, value = line.partition("=")
        if not sep or not key.replace("_", "").isalnum():
            continue
        try:
            stats[key] = int(value)
        except ValueError:
            stats[key] = value
    return stats


def combine_llm_tasks(runs: list[dict[str, Any]], output: Path) -> int:
    """Combine per-filesystem JSONL tasks into one model-ready input file."""

    count = 0
    with output.open("w", encoding="utf-8") as target:
        for run in runs:
            task_path = Path(run["llm_tasks"])
            with task_path.open(encoding="utf-8") as source:
                for line in source:
                    if not line.strip():
                        continue
                    task = json.loads(line)
                    task.setdefault("filesystem", run["filesystem"])
                    target.write(json.dumps(task, ensure_ascii=False) + "\n")
                    count += 1
    return count


def run_one(root: Path, source: Path, output: Path, fs: str, args: argparse.Namespace) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    command = build_command(root, source, output, fs, args)
    started = time.perf_counter()
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=args.timeout)
    duration = round(time.perf_counter() - started, 3)
    (output / "run.stdout.log").write_text(result.stdout, encoding="utf-8")
    (output / "run.stderr.log").write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"{fs} analysis failed with exit {result.returncode}; see {output / 'run.stderr.log'}")
    stats = parse_stats(result.stdout)
    return {
        "filesystem": fs,
        "output": str(output),
        "duration_seconds": duration,
        "stats": stats,
        "command": command,
        "llm_tasks": str(output / "llm_review_tasks.jsonl"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("linux-sources/linux-v6.14-fs"))
    parser.add_argument("--output-root", type=Path, default=Path("outputs/linux-v6.14-bug-check"))
    parser.add_argument("--filesystem", action="append", choices=FILESYSTEMS)
    parser.add_argument("--context-lines", type=int, default=80)
    parser.add_argument("--min-evidence-score", type=int)
    parser.add_argument("--timeout", type=int, default=3600, help="Per-filesystem timeout in seconds.")
    parser.add_argument("--run-deepseek", action="store_true", help="Call existing DeepSeek review after task generation.")
    parser.add_argument("--deepseek-limit", type=int)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = (root / args.source).resolve()
    output_root = (root / args.output_root).resolve()
    if not (source / "SOURCE_MANIFEST.json").exists():
        raise SystemExit(f"missing Linux source manifest: {source / 'SOURCE_MANIFEST.json'}")
    filesystems = args.filesystem or list(FILESYSTEMS)
    runs: list[dict[str, Any]] = []
    for fs in filesystems:
        print(f"checking=linux-v6.14/{fs}", flush=True)
        runs.append(run_one(root, source, output_root / fs, fs, args))
        print(f"completed=linux-v6.14/{fs}", flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    combined_tasks = output_root / "llm_review_tasks.jsonl"
    combined_task_count = combine_llm_tasks(runs, combined_tasks)
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "source_manifest": json.loads((source / "SOURCE_MANIFEST.json").read_text(encoding="utf-8")),
        "llm_policy": "deepseek_enabled" if args.run_deepseek else "tasks_only",
        "combined_llm_tasks": str(combined_tasks),
        "combined_llm_task_count": combined_task_count,
        "runs": runs,
    }
    (output_root / "check_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"manifest={output_root / 'check_manifest.json'}")
    print(f"llm_tasks={combined_task_count}")
    print(f"llm_input={combined_tasks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
