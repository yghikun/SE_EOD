"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .candidate_checker import check_candidates
from .csv_writer import write_error_paths_csv
from .error_path_extractor import ErrorPathExtractor
from .evidence_ranker import rank_candidates_from_csv
from .file_walker import iter_c_files
from .function_extractor import extract_functions
from .llm_task_builder import (
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_DEEPSEEK_REASONING_EFFORT,
    build_llm_review_tasks,
    extract_deepseek_true_candidates,
    run_deepseek_review,
)
from .parser import parse_c_file
from .protocol_db import ResourceProtocolDB
from .resource_tracker import ResourceTracker, load_resource_map
from .wrapper_summary import WrapperSummaryDB


DEFAULT_CANDIDATES_IN = "outputs/linux-v6.8/ext4/suspicious_candidates.csv"
DEFAULT_DEEPSEEK_TRUE_CANDIDATES_OUT = "outputs/linux-v6.8/ext4/deepseek_true_candidates.jsonl"
DEFAULT_PROTOCOLS_DIR = "configs/resource_protocols"
DEFAULT_RANKED_CANDIDATES_OUT = "outputs/linux-v6.8/ext4/ranked_candidates.jsonl"
DEFAULT_CANDIDATES_WITH_EVIDENCE_OUT = "outputs/linux-v6.8/ext4/candidates_with_evidence.csv"
DEFAULT_WRAPPER_SUMMARIES = "configs/wrapper_summaries.json"
DEFAULT_MANUAL_REVIEW_LABELS = None
DEFAULT_RESOURCE_MAP = "configs/ext4_resource_map.json"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_review_false_positive_contracts(
    resource_map: dict, resource_map_path: Path
) -> None:
    configured = resource_map.get("review_false_positive_contracts_file")
    if not configured:
        return
    source = Path(str(configured))
    if not source.is_absolute():
        source = resource_map_path.parent / source
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"warning: unable to load review contracts {source}: {exc}", file=sys.stderr)
        return
    rules = raw.get("rules", []) if isinstance(raw, dict) else []
    if not isinstance(rules, list):
        print(f"warning: invalid review contracts {source}: rules must be a list", file=sys.stderr)
        return
    resource_map["review_false_positive_rules"] = rules


def _git_value(linux_path: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(linux_path), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        value = result.stdout.strip()
        return value or "unknown"
    except Exception:
        return "unknown"


def linux_version(linux_path: Path) -> tuple[str, str]:
    commit = _git_value(linux_path, ["rev-parse", "HEAD"])
    tag = _git_value(linux_path, ["describe", "--tags", "--always"])
    return commit, tag


def _write_deepseek_true_candidates(args: argparse.Namespace) -> None:
    stats = extract_deepseek_true_candidates(
        Path(args.deepseek_reviews_out),
        Path(args.deepseek_true_candidates_out),
    )
    for key in [
        "deepseek_reviews_in",
        "deepseek_review_ok",
        "deepseek_review_failed",
        "deepseek_review_parse_failed",
        "deepseek_true_candidates",
        "deepseek_false_positive",
        "deepseek_uncertain",
        "deepseek_other_verdict",
    ]:
        print(f"{key}={stats[key]}")


def _candidate_input_for_current_run(args: argparse.Namespace) -> Path:
    if args.check_candidates and args.candidates_in == DEFAULT_CANDIDATES_IN:
        return Path(args.candidates_out)
    return Path(args.candidates_in)


def _rank_evidence(args: argparse.Namespace, candidates_in: Path) -> dict[str, int]:
    db = ResourceProtocolDB.load_from_dir(Path(args.protocols_dir))
    for warning in db.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    wrapper_db = WrapperSummaryDB.load_from_file(Path(args.wrapper_summaries))
    missing_wrapper_file = False
    for warning in wrapper_db.warnings:
        if str(warning).startswith("wrapper_summaries_missing:"):
            missing_wrapper_file = True
            continue
        print(f"warning: {warning}", file=sys.stderr)
    if missing_wrapper_file:
        wrapper_db = WrapperSummaryDB()
    stats = rank_candidates_from_csv(
        candidates_in,
        db,
        Path(args.ranked_candidates_out),
        Path(args.candidates_with_evidence_out),
        Path(args.deepseek_true_candidates_in),
        wrapper_db=wrapper_db,
        linux_path=Path(args.linux).resolve(),
        enable_ownership_transfer_hints=args.enable_ownership_transfer_hints,
        manual_review_labels_in=Path(args.manual_review_labels)
        if args.manual_review_labels
        else None,
    )
    for key in [
        "total_candidates_in",
        "ranked_candidates",
        "ranked_candidates_jsonl",
        "candidates_with_evidence_csv",
        "E0_STATIC_RULE_ONLY_count",
        "E1_LLM_TRUE_CANDIDATE_count",
        "E2_API_PROTOCOL_SUPPORTED_count",
        "exception_hints_count",
        "manual_review_labels_count",
        "manual_review_applied_count",
    ]:
        print(f"{key}={stats[key]}")
    return stats


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract function-local filesystem error paths into CSV."
    )
    parser.add_argument(
        "--linux",
        default=".",
        help="Path to a Linux source tree. Defaults to current directory.",
    )
    parser.add_argument(
        "--fs-subdir",
        default="fs/ext4",
        help="Filesystem source subdirectory under --linux, e.g. fs/ext4 or fs/btrfs.",
    )
    parser.add_argument(
        "--resource-map",
        default=DEFAULT_RESOURCE_MAP,
        help="Resource acquire/release map JSON file.",
    )
    parser.add_argument(
        "--out",
        default="outputs/linux-v6.8/ext4/error_paths.csv",
        help="Output CSV path.",
    )
    parser.add_argument(
        "--include-low-confidence",
        action="store_true",
        help="Include low/uncertain candidates. Default keeps high and medium only.",
    )
    parser.add_argument(
        "--check-candidates",
        action="store_true",
        help="Run suspicious candidate rules after writing the error-path CSV.",
    )
    parser.add_argument(
        "--candidates-out",
        default="outputs/linux-v6.8/ext4/suspicious_candidates.csv",
        help="Output CSV path for suspicious candidates.",
    )
    parser.add_argument(
        "--build-llm-tasks",
        action="store_true",
        help="Build LLM review task JSONL from suspicious candidates.",
    )
    parser.add_argument(
        "--candidates-in",
        default=DEFAULT_CANDIDATES_IN,
        help="Input suspicious candidate CSV for --build-llm-tasks or --rank-evidence.",
    )
    parser.add_argument(
        "--rank-evidence",
        action="store_true",
        help="Rank suspicious candidates with API protocol and optional LLM evidence.",
    )
    parser.add_argument(
        "--protocols-dir",
        default=DEFAULT_PROTOCOLS_DIR,
        help="Directory containing resource protocol JSON files.",
    )
    parser.add_argument(
        "--ranked-candidates-out",
        default=DEFAULT_RANKED_CANDIDATES_OUT,
        help="Output JSONL path for ranked candidates.",
    )
    parser.add_argument(
        "--candidates-with-evidence-out",
        default=DEFAULT_CANDIDATES_WITH_EVIDENCE_OUT,
        help="Output CSV path for ranked candidate summary.",
    )
    parser.add_argument(
        "--deepseek-true-candidates-in",
        default=DEFAULT_DEEPSEEK_TRUE_CANDIDATES_OUT,
        help="Optional DeepSeek verdict=true_candidate JSONL input for evidence ranking.",
    )
    parser.add_argument(
        "--wrapper-summaries",
        default=DEFAULT_WRAPPER_SUMMARIES,
        help="Optional cleanup wrapper summary JSON file for evidence ranking.",
    )
    parser.add_argument(
        "--enable-ownership-transfer-hints",
        action="store_true",
        help="Enable conservative pattern-based ownership transfer hints during ranking.",
    )
    parser.add_argument(
        "--manual-review-labels",
        default=DEFAULT_MANUAL_REVIEW_LABELS,
        help=(
            "Optional review feedback labels JSONL for score feedback. "
            "If omitted, ranking does not apply review labels."
        ),
    )
    parser.add_argument(
        "--llm-tasks-out",
        default="outputs/linux-v6.8/ext4/llm_review_tasks.jsonl",
        help="Output JSONL path for LLM review tasks.",
    )
    parser.add_argument(
        "--context-lines",
        type=int,
        default=80,
        help="Source context lines before and after each candidate error line.",
    )
    parser.add_argument(
        "--run-deepseek-review",
        action="store_true",
        help="Optionally call DeepSeek on llm_review_tasks.jsonl. Requires DEEPSEEK_API_KEY.",
    )
    parser.add_argument(
        "--deepseek-reviews-out",
        default="outputs/linux-v6.8/ext4/deepseek_reviews.jsonl",
        help="Output JSONL path for optional DeepSeek responses.",
    )
    parser.add_argument(
        "--deepseek-true-candidates-out",
        default=DEFAULT_DEEPSEEK_TRUE_CANDIDATES_OUT,
        help="Output JSONL path for DeepSeek verdict=true_candidate records.",
    )
    parser.add_argument(
        "--extract-deepseek-true-candidates",
        action="store_true",
        help=(
            "Extract verdict=true_candidate rows from --deepseek-reviews-out "
            "without calling DeepSeek."
        ),
    )
    parser.add_argument(
        "--deepseek-model",
        default=DEFAULT_DEEPSEEK_MODEL,
        help="DeepSeek model for --run-deepseek-review.",
    )
    parser.add_argument(
        "--deepseek-reasoning-effort",
        default=DEFAULT_DEEPSEEK_REASONING_EFFORT,
        choices=["minimal", "low", "medium", "high", "max"],
        help="Reasoning effort for DeepSeek thinking mode.",
    )
    parser.add_argument(
        "--deepseek-limit",
        type=int,
        default=None,
        help="Optional maximum number of tasks to send to DeepSeek.",
    )
    parser.add_argument(
        "--deepseek-start-index",
        type=int,
        default=1,
        help="1-based task index to start sending to DeepSeek. Values >1 append to reviews output.",
    )
    parser.add_argument(
        "--deepseek-retries",
        type=int,
        default=2,
        help="Retries per DeepSeek task for transient network/read failures.",
    )
    parser.add_argument(
        "--deepseek-retry-sleep",
        type=float,
        default=3.0,
        help="Seconds to sleep between DeepSeek retries.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    linux_path = Path(args.linux).resolve()
    out_path = Path(args.out)
    resource_map_path = Path(args.resource_map)
    if not resource_map_path.is_absolute():
        resource_map_path = _project_root() / resource_map_path

    if (
        args.extract_deepseek_true_candidates
        and not args.check_candidates
        and not args.build_llm_tasks
        and not args.run_deepseek_review
        and not args.rank_evidence
    ):
        _write_deepseek_true_candidates(args)
        return 0

    if (
        args.rank_evidence
        and not args.check_candidates
        and not args.build_llm_tasks
        and not args.run_deepseek_review
        and not args.extract_deepseek_true_candidates
    ):
        _rank_evidence(args, Path(args.candidates_in))
        return 0

    if args.build_llm_tasks and not args.check_candidates:
        candidates_in = _candidate_input_for_current_run(args)
        if args.rank_evidence:
            _rank_evidence(args, candidates_in)
        task_stats = build_llm_review_tasks(
            linux_path,
            candidates_in,
            Path(args.llm_tasks_out),
            args.context_lines,
            Path(args.ranked_candidates_out) if args.rank_evidence else None,
        )
        for key in [
            "total_candidates_in",
            "llm_review_tasks",
            "source_unavailable_count",
            "llm_tasks_with_protocol_evidence",
        ]:
            print(f"{key}={task_stats[key]}")
        if args.run_deepseek_review:
            try:
                deepseek_stats = run_deepseek_review(
                    Path(args.llm_tasks_out),
                    Path(args.deepseek_reviews_out),
                    model=args.deepseek_model,
                    reasoning_effort=args.deepseek_reasoning_effort,
                    limit=args.deepseek_limit,
                    start_index=args.deepseek_start_index,
                    retries=args.deepseek_retries,
                    retry_sleep_seconds=args.deepseek_retry_sleep,
                )
            except RuntimeError as exc:
                print(f"deepseek_error={exc}", file=sys.stderr)
                return 2
            for key in [
                "deepseek_review_attempted",
                "deepseek_review_succeeded",
                "deepseek_review_failed",
            ]:
                print(f"{key}={deepseek_stats[key]}")
            _write_deepseek_true_candidates(args)
        elif args.extract_deepseek_true_candidates:
            _write_deepseek_true_candidates(args)
        return 0

    commit, tag = linux_version(linux_path)
    resource_map = load_resource_map(resource_map_path)
    _load_review_false_positive_contracts(resource_map, resource_map_path)
    resource_tracker = ResourceTracker(resource_map)
    extractor = ErrorPathExtractor(resource_tracker)

    scanned_files = 0
    scanned_functions = 0
    all_paths = []
    warnings: list[str] = []

    for c_file in iter_c_files(linux_path, args.fs_subdir):
        scanned_files += 1
        try:
            parsed = parse_c_file(c_file)
            warnings.extend(f"{c_file}: {warning}" for warning in parsed.warnings)
            functions = extract_functions(parsed)
        except Exception as exc:
            warnings.append(f"{c_file}: parse/extract failed: {exc}")
            continue

        scanned_functions += len(functions)
        for function in functions:
            try:
                paths = extractor.extract(function)
            except Exception as exc:
                warnings.append(f"{c_file}:{function.name}: analysis failed: {exc}")
                continue

            for path in paths:
                if not args.include_low_confidence and path.confidence not in {
                    "high",
                    "medium",
                }:
                    continue
                path.linux_git_commit = commit
                path.linux_git_tag = tag
                try:
                    path.file = str(Path(path.file).resolve().relative_to(linux_path))
                except ValueError:
                    path.file = str(Path(path.file))
                all_paths.append(path)

    write_error_paths_csv(all_paths, out_path)

    high = sum(1 for path in all_paths if path.confidence == "high")
    medium = sum(1 for path in all_paths if path.confidence == "medium")
    low = sum(1 for path in all_paths if path.confidence == "low")
    suspicious = sum(1 for path in all_paths if path.missing_cleanup_candidates)

    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    print(f"scanned_files={scanned_files}")
    print(f"scanned_functions={scanned_functions}")
    print(f"extracted_error_paths={len(all_paths)}")
    print(f"high_confidence_paths={high}")
    print(f"medium_confidence_paths={medium}")
    print(f"low_confidence_paths={low}")
    print(f"suspicious_missing_cleanup_candidates={suspicious}")

    if args.check_candidates:
        candidate_stats = check_candidates(
            out_path, Path(args.candidates_out), resource_map
        )
        for key in [
            "total_error_paths",
            "total_candidates",
            "missing_cleanup_count",
            "error_swallowed_count",
            "partial_cleanup_count",
            "P1_count",
            "P2_count",
            "P3_count",
        ]:
            print(f"{key}={candidate_stats[key]}")

    if args.rank_evidence:
        _rank_evidence(args, _candidate_input_for_current_run(args))

    if args.build_llm_tasks:
        candidates_in = _candidate_input_for_current_run(args)
        task_stats = build_llm_review_tasks(
            linux_path,
            candidates_in,
            Path(args.llm_tasks_out),
            args.context_lines,
            Path(args.ranked_candidates_out) if args.rank_evidence else None,
        )
        for key in [
            "total_candidates_in",
            "llm_review_tasks",
            "source_unavailable_count",
            "llm_tasks_with_protocol_evidence",
        ]:
            print(f"{key}={task_stats[key]}")

    if args.run_deepseek_review:
        try:
            deepseek_stats = run_deepseek_review(
                Path(args.llm_tasks_out),
                Path(args.deepseek_reviews_out),
                model=args.deepseek_model,
                reasoning_effort=args.deepseek_reasoning_effort,
                limit=args.deepseek_limit,
                start_index=args.deepseek_start_index,
                retries=args.deepseek_retries,
                retry_sleep_seconds=args.deepseek_retry_sleep,
            )
        except RuntimeError as exc:
            print(f"deepseek_error={exc}", file=sys.stderr)
            return 2
        for key in [
            "deepseek_review_attempted",
            "deepseek_review_succeeded",
            "deepseek_review_failed",
        ]:
            print(f"{key}={deepseek_stats[key]}")
        _write_deepseek_true_candidates(args)
    elif args.extract_deepseek_true_candidates:
        _write_deepseek_true_candidates(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
