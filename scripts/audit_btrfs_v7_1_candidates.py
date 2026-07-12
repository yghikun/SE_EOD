"""Audit the 95 Linux v7.1 btrfs candidates from experiment-v1.3.1."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from scripts.compare_experiment_v1_3 import load_jsonl, stable_key
except ModuleNotFoundError:
    from compare_experiment_v1_3 import load_jsonl, stable_key


ROOT = Path(__file__).resolve().parents[1]
BEFORE = ROOT / "outputs/experiment-v1.3.1/linux-v7.1/btrfs/ranked_candidates.jsonl"
AFTER = ROOT / "outputs/experiment-v1.3.2/linux-v7.1/btrfs/ranked_candidates.jsonl"
REPORT_DIR = ROOT / "outputs/experiment-v1.3.2/reports"


ACQUIRE_FAILURE_FUNCTIONS = {
    "__add_block_group_free_space",
    "btrfs_add_to_free_space_tree",
    "btrfs_find_orphan_roots",
    "btrfs_quota_enable",
    "btrfs_recover_log_trees",
    "btrfs_remove_block_group",
    "btrfs_remove_from_free_space_tree",
    "btrfs_symlink",
    "btrfs_zone_finish_endio",
    "remove_range_from_remap_tree",
    "unpin_extent_range",
}

SENTINEL_EVIDENCE = {
    "alloc_dummy_extent_buffer": (
        "pointer_error_sentinel",
        "The constructor releases the extent buffer and returns NULL on failure "
        "(extent_io.c:3141-3163); NULL is the documented pointer failure result.",
    ),
    "backref_in_log": (
        "not_found_sentinel",
        "btrfs_search_slot() returning 1 means the key was not found, so returning "
        "0 means the backreference is absent (tree-log.c:1193-1206).",
    ),
    "bio_add_paddrs": (
        "short_add_sentinel",
        "A short bio_add_page() result triggers size rollback and returns 0 to report "
        "that no bytes were added (raid56.c:1194-1208).",
    ),
    "btrfs_free_tree_block": (
        "boolean_helper_result",
        "check_ref_cleanup() is used as a boolean decision; zero means no immediate "
        "tree-block cleanup is needed (extent-tree.c:3657-3661).",
    ),
    "btrfs_init_dev_replace": (
        "documented_recovery_policy",
        "The source explicitly treats a missing or corrupt replace item as no active "
        "replacement when no target device exists; the same policy is present in Linux "
        "v6.8 (dev-replace.c:95-122).",
    ),
    "btrfs_qgroup_trace_extent": (
        "best_effort_duplicate_or_insert_failure",
        "The explicit cleanup branch covers insertion failure or an existing item and "
        "intentionally returns success after releasing the reservation and record "
        "(qgroup.c:2183-2189).",
    ),
    "can_nocow_extent": (
        "fail_safe_fallback",
        "The source explicitly converts helper errors into the safe COW fallback after "
        "the helper has freed the path (inode.c:7491-7497).",
    ),
    "extent_writepage": (
        "handled_page_sentinel",
        "A return value of 1 from the writepage helpers means the folio was already "
        "handled, so the wrapper intentionally returns success (extent_io.c:1889-1898).",
    ),
    "is_extent_unchanged": (
        "not_found_sentinel",
        "A positive btrfs_search_slot_for_read() result means no matching extent; zero "
        "correctly reports that the extent is not unchanged (send.c:6198-6202).",
    ),
}


def classify_retained(row: dict[str, Any]) -> tuple[str, str]:
    function = row["function"]
    if function in SENTINEL_EVIDENCE:
        return SENTINEL_EVIDENCE[function]
    if function in ACQUIRE_FAILURE_FUNCTIONS:
        return (
            "failed_acquisition_not_held",
            "The reported exit is dominated by a NULL/ERR_PTR acquisition result; no "
            "live resource exists on this path. Other already-held resources are cleaned "
            "by the shown exit cleanup.",
        )
    if function == "btrfs_ioctl_space_info":
        return (
            "alias_has_scope_cleanup",
            "dest_orig aliases the kzalloc() base pointer and is declared with "
            "AUTO_KFREE, so scope exit frees the allocation (ioctl.c:2836,2900-2903).",
        )
    if function == "do_walk_down":
        return (
            "callee_releases_on_error",
            "check_next_block_uptodate() unlocks and frees next before returning an "
            "error (extent-tree.c:5793-5799); the caller must not release it again.",
        )
    if function == "btrfs_recover_relocation":
        return (
            "confirmed_relocation_root_cleanup_defect",
            "The grabbed fs_root->reloc_root reference survives recovery failures that do "
            "not set BTRFS_FS_ERROR. Linux v6.8 QEMU fault injection confirms the defect, "
            "and Linux v7.1 retains the assignment and out_unset cleanup shape "
            "(relocation.c:5609-5639).",
        )
    raise ValueError(f"unclassified retained candidate: {row['path_id']} {row['candidate_type']}")


def main() -> int:
    before = load_jsonl(BEFORE)
    after = load_jsonl(AFTER)
    if len(before) != 95:
        raise ValueError(f"expected 95 input candidates, found {len(before)}")
    after_keys = {stable_key(row) for row in after}
    audited: list[dict[str, Any]] = []

    for row in before:
        retained = stable_key(row) in after_keys
        if retained:
            reason, evidence = classify_retained(row)
            stage = (
                "cross_version_dynamic_evidence"
                if row["function"] == "btrfs_recover_relocation"
                else "manual_source_audit"
            )
        else:
            reason = "compiler_managed_scope_cleanup"
            evidence = (
                "The candidate disappears after modeling AUTO_KFREE/AUTO_KVFREE. "
                "misc.h:16-21 defines them as __free(kfree)/__free(kvfree), so the "
                "compiler releases the resource at scope exit."
            )
            stage = "scope_cleanup_ablation"
        verdict = (
            "true_bug"
            if retained and row["function"] == "btrfs_recover_relocation"
            else "false_positive"
        )
        audited.append(
            {
                "path_id": row["path_id"],
                "candidate_type": row["candidate_type"],
                "file": row["file"],
                "function": row["function"],
                "error_line": row["error_line"],
                "condition": row["condition"],
                "verdict": verdict,
                "reason": reason,
                "evidence": evidence,
                "audit_stage": stage,
            }
        )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    jsonl_path = REPORT_DIR / "btrfs_v7_1_candidate_audit.jsonl"
    jsonl_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in audited),
        encoding="utf-8",
    )
    csv_path = REPORT_DIR / "btrfs_v7_1_candidate_audit.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(audited[0]))
        writer.writeheader()
        writer.writerows(audited)

    reasons = Counter(row["reason"] for row in audited)
    functions = Counter(row["function"] for row in audited)
    verdicts = Counter(row["verdict"] for row in audited)
    false_reasons = Counter(
        row["reason"] for row in audited if row["verdict"] == "false_positive"
    )
    lines = [
        "# Linux v7.1 btrfs 95-Candidate Audit",
        "",
        "## Verdict",
        "",
        f"- Confirmed bugs: **{verdicts['true_bug']}**",
        f"- False positives: **{verdicts['false_positive']}**",
        "- Uncertain: **0**",
        "- Static candidates after the second cleanup-model ablation: **35**",
        "",
        "Four candidate records (two paths, each emitted as missing and partial cleanup) "
        "represent the confirmed `btrfs_recover_relocation()` cleanup defect. The other 91 "
        "do not demonstrate their claimed missing-cleanup or swallowed-error defect.",
        "",
        "## False-Positive Causes",
        "",
        "| Cause | Candidates |",
        "|---|---:|",
    ]
    lines.extend(
        f"| `{reason}` | {count} |" for reason, count in false_reasons.most_common()
    )
    lines.extend(
        [
            "",
            "## Highest-Frequency Functions",
            "",
            "| Function | Candidates |",
            "|---|---:|",
        ]
    )
    lines.extend(f"| `{function}` | {count} |" for function, count in functions.most_common(12))
    lines.extend(
        [
            "",
            "## Reproducibility",
            "",
            "- Original set: `experiment-v1.3.1/linux-v7.1/btrfs` (95).",
            "- Added `AUTO_KFREE -> kfree` and `AUTO_KVFREE -> kvfree` from `fs/btrfs/misc.h`.",
            "- Rerun set: `experiment-v1.3.2/linux-v7.1/btrfs` (35).",
            "- Every retained candidate was classified by an explicit source-contract rule; "
            "the script fails if a retained candidate has no rule.",
            "",
        ]
    )
    (REPORT_DIR / "btrfs_v7_1_candidate_audit.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    print(f"audited={len(audited)}")
    print(f"true_bug={verdicts['true_bug']}")
    print(f"false_positive={verdicts['false_positive']}")
    print(f"retained_after_ablation={len(after)}")
    print(f"reason_counts={dict(reasons)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
