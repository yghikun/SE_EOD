#!/usr/bin/env bash
# Run the complete static-analysis and DeepSeek review pipeline for Linux v7.1.

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUTPUT_ROOT="$ROOT_DIR/outputs/linux-v7.1"
PYTHON_BIN=${PYTHON_BIN:-python}
RUN_DEEPSEEK=1

usage() {
    cat <<'EOF'
Usage: scripts/check_linux_v7_1_filesystems.sh [--no-deepseek] [ext4|btrfs|xfs|f2fs ...]

With no filesystem arguments, scans ext4, btrfs, xfs, and f2fs sequentially.
The default runs DeepSeek review and requires DEEPSEEK_API_KEY to be set.
Use --no-deepseek to generate static-analysis outputs and LLM tasks only.

Environment:
  PYTHON_BIN  Python interpreter to use (default: python)
  LINUX_DIR   Linux v7.1 checkout path (auto-detected by default)
  <FS>_MIN_EVIDENCE_SCORE
              Per-filesystem LLM task threshold, for example
              BTRFS_MIN_EVIDENCE_SCORE=40
EOF
}

filesystems=()
while (($#)); do
    case "$1" in
        --no-deepseek)
            RUN_DEEPSEEK=0
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        ext4|btrfs|xfs|f2fs)
            filesystems+=("$1")
            ;;
        *)
            printf 'Unknown argument: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

if ((${#filesystems[@]} == 0)); then
    filesystems=(ext4 btrfs xfs f2fs)
fi

if [[ -z ${LINUX_DIR:-} ]]; then
    for candidate in \
        "$ROOT_DIR/linux-v7.1" \
        "$ROOT_DIR/linux-sources/linux-v7.1-fs"; do
        if git -C "$candidate" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
            LINUX_DIR=$candidate
            break
        fi
    done
fi

if [[ -z ${LINUX_DIR:-} ]] || \
    ! git -C "$LINUX_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    printf 'Linux v7.1 checkout not found. Checked:\n' >&2
    printf '  %s\n' "$ROOT_DIR/linux-v7.1" >&2
    printf '  %s\n' "$ROOT_DIR/linux-sources/linux-v7.1-fs" >&2
    printf 'Set LINUX_DIR to use another location.\n' >&2
    exit 1
fi

if ((RUN_DEEPSEEK)) && [[ -z ${DEEPSEEK_API_KEY:-} ]]; then
    printf 'DEEPSEEK_API_KEY must be set unless --no-deepseek is used.\n' >&2
    exit 1
fi

cd "$ROOT_DIR"

for fs in "${filesystems[@]}"; do
    if [[ ! -d "$LINUX_DIR/fs/$fs" ]]; then
        printf 'Filesystem source directory not found: %s/fs/%s\n' \
            "$LINUX_DIR" "$fs" >&2
        exit 1
    fi

    out_dir="$OUTPUT_ROOT/$fs"
    mkdir -p "$out_dir"

    wrapper_summaries="configs/${fs}_wrapper_summaries.json"
    if [[ "$fs" == "ext4" ]]; then
        wrapper_summaries="configs/wrapper_summaries.json"
    fi

    cmd=(
        "$PYTHON_BIN" -m src.main
        --linux "$LINUX_DIR"
        --fs-subdir "fs/$fs"
        --resource-map "configs/${fs}_resource_map.json"
        --out "$out_dir/error_paths.csv"
        --check-candidates
        --candidates-out "$out_dir/suspicious_candidates.csv"
        --rank-evidence
        --protocols-dir "configs/${fs}_resource_protocols"
        --wrapper-summaries "$wrapper_summaries"
        --enable-ownership-transfer-hints
        --ranked-candidates-out "$out_dir/ranked_candidates.jsonl"
        --candidates-with-evidence-out "$out_dir/candidates_with_evidence.csv"
        --build-llm-tasks
        --llm-tasks-out "$out_dir/llm_review_tasks.jsonl"
    )

    threshold_var="${fs^^}_MIN_EVIDENCE_SCORE"
    min_evidence_score=${!threshold_var:-}
    if [[ -n "$min_evidence_score" ]]; then
        if [[ ! "$min_evidence_score" =~ ^-?[0-9]+$ ]]; then
            printf '%s must be an integer, got: %s\n' \
                "$threshold_var" "$min_evidence_score" >&2
            exit 2
        fi
        cmd+=(--min-evidence-score "$min_evidence_score")
    fi

    if ((RUN_DEEPSEEK)); then
        cmd+=(
            --run-deepseek-review
            --deepseek-reviews-out "$out_dir/deepseek_reviews.jsonl"
            --deepseek-true-candidates-out "$out_dir/deepseek_true_candidates.jsonl"
            --deepseek-reasoning-effort max
        )
    fi

    printf '\n==> Checking %s\n' "$fs"
    "${cmd[@]}"
done
