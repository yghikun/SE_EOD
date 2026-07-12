"""Run the reproducible SE-EOD v1.3 static experiment matrix."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VERSIONS = {
    "linux-v6.8": "linux-sources/linux-v6.8-fs",
    "linux-v7.1": "linux-sources/linux-v7.1-fs",
}
FILESYSTEMS = ("ext4", "btrfs", "xfs", "f2fs")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def git_output(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, check=True, capture_output=True, text=True
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def csv_count(path: Path) -> int:
    with path.open(newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def jsonl_count(path: Path) -> int:
    with path.open(encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def collect_run_manifests(experiment_root: Path) -> list[dict[str, Any]]:
    """Collect every completed matrix cell, including cells from earlier partial runs."""

    manifests: list[dict[str, Any]] = []
    for path in sorted(experiment_root.glob("*/*/run_manifest.json")):
        manifest = read_json(path)
        if manifest.get("version") and manifest.get("filesystem"):
            manifests.append(manifest)
    return manifests


def parse_stdout_stats(stdout: str) -> dict[str, int | str]:
    stats: dict[str, int | str] = {}
    for line in stdout.splitlines():
        key, separator, value = line.partition("=")
        if not separator or not key.replace("_", "").isalnum():
            continue
        try:
            stats[key] = int(value)
        except ValueError:
            stats[key] = value
    return stats


def config_paths(root: Path, filesystem: str) -> dict[str, Path]:
    wrapper_name = "wrapper_summaries.json" if filesystem == "ext4" else f"{filesystem}_wrapper_summaries.json"
    return {
        "resource_map": root / "configs" / f"{filesystem}_resource_map.json",
        "protocols_dir": root / "configs" / f"{filesystem}_resource_protocols",
        "wrapper_summaries": root / "configs" / wrapper_name,
        "review_contracts": root / "configs" / f"{filesystem}_review_false_positives.json",
        "historical_fixes": root / "configs" / f"{filesystem}_historical_fixes.json",
    }


def config_hashes(paths: dict[str, Path]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, path in paths.items():
        if path.is_dir():
            result[name] = {
                item.name: sha256(item) for item in sorted(path.glob("*.json"))
            }
        elif path.exists():
            result[name] = sha256(path)
        else:
            result[name] = "missing"
    return result


def build_command(
    root: Path,
    linux_path: Path,
    output_dir: Path,
    filesystem: str,
    enable_interprocedural: bool = False,
) -> list[str]:
    configs = config_paths(root, filesystem)
    no_llm_evidence = output_dir / "_no_llm_evidence.jsonl"
    command = [
        sys.executable,
        "-m",
        "src.main",
        "--linux",
        str(linux_path),
        "--fs-subdir",
        f"fs/{filesystem}",
        "--resource-map",
        str(configs["resource_map"]),
        "--out",
        str(output_dir / "error_paths.csv"),
        "--check-candidates",
        "--candidates-out",
        str(output_dir / "suspicious_candidates.csv"),
        "--rank-evidence",
        "--protocols-dir",
        str(configs["protocols_dir"]),
        "--wrapper-summaries",
        str(configs["wrapper_summaries"]),
        "--enable-ownership-transfer-hints",
        "--deepseek-true-candidates-in",
        str(no_llm_evidence),
        "--ranked-candidates-out",
        str(output_dir / "ranked_candidates.jsonl"),
        "--candidates-with-evidence-out",
        str(output_dir / "candidates_with_evidence.csv"),
        "--build-llm-tasks",
        "--llm-tasks-out",
        str(output_dir / "llm_review_tasks.jsonl"),
    ]
    if configs["historical_fixes"].exists():
        command.extend(["--historical-fixes", str(configs["historical_fixes"])])
    if enable_interprocedural:
        command.extend(
            [
                "--enable-interprocedural",
                "--function-summaries-out",
                str(output_dir / "function_summaries.json"),
            ]
        )
    return command


def run_one(
    root: Path,
    experiment_root: Path,
    version: str,
    source_relative: str,
    filesystem: str,
    force: bool,
    experiment_name: str,
    enable_interprocedural: bool = False,
) -> dict[str, Any]:
    source = (root / source_relative).resolve()
    output_dir = experiment_root / version / filesystem
    manifest_path = output_dir / "run_manifest.json"
    if manifest_path.exists() and not force:
        print(f"skip_existing={version}/{filesystem}")
        return read_json(manifest_path)
    if not (source / "fs" / filesystem).is_dir():
        raise FileNotFoundError(f"missing source directory: {source / 'fs' / filesystem}")

    output_dir.mkdir(parents=True, exist_ok=True)
    command = build_command(
        root,
        source,
        output_dir.resolve(),
        filesystem,
        enable_interprocedural=enable_interprocedural,
    )
    started = datetime.now(timezone.utc)
    start_clock = time.perf_counter()
    result = subprocess.run(command, cwd=root, capture_output=True, text=True)
    duration = time.perf_counter() - start_clock
    (output_dir / "run.stdout.log").write_text(result.stdout, encoding="utf-8")
    (output_dir / "run.stderr.log").write_text(result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(
            f"run failed for {version}/{filesystem} with exit {result.returncode}; "
            f"see {output_dir / 'run.stderr.log'}"
        )

    configs = config_paths(root, filesystem)
    source_manifest = read_json(source / "SOURCE_MANIFEST.json")
    stats = parse_stdout_stats(result.stdout)
    stats.update(
        {
            "error_paths_file_rows": csv_count(output_dir / "error_paths.csv"),
            "candidates_file_rows": csv_count(output_dir / "suspicious_candidates.csv"),
            "ranked_file_rows": jsonl_count(output_dir / "ranked_candidates.jsonl"),
            "llm_tasks_file_rows": jsonl_count(output_dir / "llm_review_tasks.jsonl"),
        }
    )
    manifest = {
        "schema_version": 1,
        "experiment": experiment_name,
        "version": version,
        "filesystem": filesystem,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(duration, 4),
        "command": command,
        "llm_policy": "no historical verdict input; tasks generated but no model called",
        "manual_review_policy": "no manual review score input",
        "analysis": {
            "interprocedural": enable_interprocedural,
            "function_summaries": "function_summaries.json"
            if enable_interprocedural
            else None,
            "cfg_dataflow": {
                "functions": stats.get("cfg_functions", 0),
                "iterations": stats.get("cfg_iterations", 0),
                "truncated_functions": stats.get("cfg_truncated_functions", 0),
                "widened_blocks": stats.get("cfg_widened_blocks", 0),
                "max_states_per_block": stats.get("cfg_max_states_per_block", 0),
                "unresolved_indirect_calls": stats.get(
                    "cfg_unresolved_indirect_calls", 0
                ),
            },
        },
        "source": {
            "path": str(source),
            "git_commit": source_manifest.get("git_commit", "unknown"),
            "git_tag": source_manifest.get("git_tag", "unknown"),
            "archive_sha256": source_manifest.get("archive_sha256", "unknown"),
        },
        "tool": {
            "git_commit": git_output(root, "rev-parse", "HEAD"),
            "git_status": git_output(root, "status", "--porcelain"),
            "python": sys.version,
            "platform": platform.platform(),
        },
        "config_hashes": config_hashes(configs),
        "stats": stats,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"completed={version}/{filesystem} "
        f"paths={stats['error_paths_file_rows']} candidates={stats['candidates_file_rows']} "
        f"seconds={duration:.2f}"
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", default="outputs/experiment-v1.3", type=Path)
    parser.add_argument("--experiment-name", default="experiment-v1.3")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--version", action="append", choices=sorted(VERSIONS))
    parser.add_argument("--filesystem", action="append", choices=FILESYSTEMS)
    parser.add_argument(
        "--enable-interprocedural",
        action="store_true",
        help="Enable inferred function summaries and fixed-point ownership propagation.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    experiment_root = (root / args.output_root).resolve()
    versions = args.version or list(VERSIONS)
    filesystems = args.filesystem or list(FILESYSTEMS)
    experiment_root.mkdir(parents=True, exist_ok=True)

    runs = []
    for version in versions:
        for filesystem in filesystems:
            runs.append(
                run_one(
                    root,
                    experiment_root,
                    version,
                    VERSIONS[version],
                    filesystem,
                    args.force,
                    args.experiment_name,
                    args.enable_interprocedural,
                )
            )

    completed_runs = collect_run_manifests(experiment_root)
    root_manifest = {
        "schema_version": 1,
        "experiment": args.experiment_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_count": len(completed_runs),
        "runs": [
            {
                "version": run.get("version"),
                "filesystem": run.get("filesystem"),
                "duration_seconds": run.get("duration_seconds"),
                "stats": run.get("stats", {}),
            }
            for run in completed_runs
        ],
    }
    (experiment_root / "experiment_manifest.json").write_text(
        json.dumps(root_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
