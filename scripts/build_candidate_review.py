#!/usr/bin/env python3
"""Build the source-reviewed M32d Candidate ledger.

The ledger deliberately separates whether the reported residual exists at the
function boundary from whether the residual is a filesystem bug.  Candidate
order is defined after filtering all_reports.json by confidence=candidate.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REVIEW_DATE = "2026-07-24"
EXPECTED_COUNTS = {"btrfs": 231, "ext4": 80, "xfs": 190, "f2fs": 38}
RUN_DIRS = {
    fs: f"linux-v6.14-fs-{fs}-m32d-percpu-final" for fs in EXPECTED_COUNTS
}


@dataclass(frozen=True)
class Verdict:
    report_validity: str
    bug_status: str
    source_verdict: str
    root_cause_family: str
    rationale: str
    related_finding: str = ""


FALSE_PRIVATE = Verdict(
    "FALSE_POSITIVE",
    "NO_BUG",
    "FALSE_ALARM",
    "PRIVATE_OR_CLEANED_STATE",
    "The reported effect belongs to an unpublished object, output/cursor, or temporary cache, or is removed by the reviewed error cleanup; no live metadata owner retains it.",
)

TXN_CONTAINED = Verdict(
    "TRUE_RESIDUAL",
    "NO_BUG",
    "CONTAINED_NOT_BUG",
    "TRANSACTION_OR_FATAL_CONTAINMENT",
    "The mutation can remain at this function return, but the caller cancels/aborts the dirty transaction or shuts down the filesystem, so the state cannot continue as ordinary live metadata.",
)

MOUNT_TEARDOWN = Verdict(
    "FALSE_POSITIVE",
    "NO_BUG",
    "FALSE_ALARM",
    "FAILED_OBJECT_TEARDOWN",
    "The failure prevents publication or mount completion, and the reviewed owner teardown destroys the partially initialized object and its state.",
)

INTENTIONAL_PROGRESS = Verdict(
    "FALSE_POSITIVE",
    "NO_BUG",
    "FALSE_ALARM",
    "INTENTIONAL_PROGRESS_OR_OUTPUT",
    "The value is an output, retry cursor, cache population, terminal error state, or completed progress that is intentionally retained across the later failure.",
)


BTRFS_TXN_FUNCTIONS = {
    "add_pending_csums",
    "balance_level",
    "btrfs_batch_delete_items",
    "btrfs_clone",
    "btrfs_delayed_update_inode",
    "btrfs_insert_delayed_item",
    "btrfs_qgroup_inherit",
    "btrfs_qgroup_trace_subtree_after_cow",
    "btrfs_rebuild_free_space_tree",
    "btrfs_reloc_post_snapshot",
    "btrfs_remove_free_space_inode",
    "btrfs_rename",
    "btrfs_rename_exchange",
    "btrfs_replace_file_extents",
    "btrfs_set_disk_extent_flags",
    "btrfs_setxattr_trans",
    "btrfs_sync_log",
    "btrfs_truncate_free_space_cache",
    "commit_cowonly_roots",
    "commit_fs_roots",
    "create_pending_snapshot",
    "create_snapshot",
    "create_subvol",
    "do_relocation",
    "fixup_inode_link_count",
    "insert_block_group_item",
    "insert_dirty_subvol",
    "log_directory_changes",
    "log_extent_csums",
    "merge_reloc_root",
    "prepare_to_merge",
    "qgroup_rescan_leaf",
    "refill_metadata_space",
    "relocate_cowonly_block",
    "relocate_data_extent",
    "replace_path",
    "start_transaction",
    "update_block_group_item",
}

BTRFS_MOUNT_FUNCTIONS = {
    "btrfs_get_root_ref",
    "btrfs_get_tree_super",
    "btrfs_init_fs_root",
    "btrfs_init_log_root_tree",
    "btrfs_init_space_info",
    "btrfs_make_block_group",
    "btrfs_read_locked_inode",
    "btrfs_read_roots",
    "fill_dummy_bgs",
    "init_mount_fs_info",
    "init_tree_roots",
    "load_global_roots",
    "load_global_roots_objectid",
    "open_ctree",
    "read_one_block_group",
}

BTRFS_PROGRESS_FUNCTIONS = {
    "btrfs_advance_sb_log",
    "btrfs_attach_transaction_barrier",
    "btrfs_defrag_file",
    "btrfs_dev_replace_cancel",
    "btrfs_dev_replace_finishing",
    "btrfs_lookup_ordered_extent",
    "btrfs_lookup_ordered_range",
    "btrfs_qgroup_rescan",
    "btrfs_statfs",
    "scrub_enumerate_chunks",
    "trim_bitmaps",
    "trim_no_bitmap",
    "write_all_supers",
}

XFS_TXN_FUNCTIONS = {
    "__xfs_btree_split",
    "xfs_btree_delrec",
    "xfs_difree",
    "xfs_difree_inobt",
    "xfs_log_cover",
    "xfs_swap_extents",
    "xlog_state_get_iclog_space",
    "xlog_write",
    "xlog_write_partial",
    "xqcheck_commit_dqtype",
}

XFS_MOUNT_FUNCTIONS = {
    "xfs_fs_fill_super",
    "xfs_log_mount",
    "xfs_mountfs",
    "xlog_alloc_log",
    "xlog_find_tail",
    "xlog_recover_do_primary_sb_buffer",
    "xlog_recover_inode_commit_pass2",
}

XFS_PROGRESS_FUNCTIONS = {
    "xfs_alloc_fix_freelist",
    "xfs_buffered_write_iomap_begin",
    "xfs_bulkstat_one_int",
    "xfs_direct_write_iomap_begin",
    "xfs_fs_get_quota_state",
    "xfs_trans_ail_cursor_first",
    "xfarray_sort",
}


SPECIAL: dict[tuple[str, int], Verdict] = {
    ("btrfs", 26): Verdict(
        "FALSE_POSITIVE",
        "CONFIRMED_DIFFERENT_DEFECT",
        "DIFFERENT_DEFECT",
        "UNPUBLISHED_OBJECT_RESOURCE_LEAK",
        "The reported device field values die with an unpublished object and are not metadata residuals, but btrfs_init_dev_replace_tgtdev() omits btrfs_free_device() after zone-info failure and leaks the allocated device.",
        "pending P2",
    ),
    ("btrfs", 27): Verdict(
        "TRUE_RESIDUAL",
        "LIKELY",
        "TRUE_ISSUE",
        "PUBLISHED_DEVICE_NOT_ROLLED_BACK",
        "The target is linked and num_devices/open_devices are incremented before mark_block_group_to_copy(); its direct error return bypasses target destruction and leaves replacement unstarted with a live linked device.",
        "pending P3",
    ),
    ("btrfs", 88): Verdict(
        "INCONCLUSIVE",
        "NEEDS_REPRO",
        "UNRESOLVED",
        "ONE_SHOT_STATE_SEMANTICS",
        "BTRFS_ROOT_ORPHAN_CLEANUP is intentionally a one-shot/reentrancy bit, but the audit has not proved that every early error is safely recoverable without retrying cleanup.",
    ),
    ("btrfs", 89): Verdict(
        "INCONCLUSIVE",
        "NEEDS_REPRO",
        "UNRESOLVED",
        "ONE_SHOT_STATE_SEMANTICS",
        "BTRFS_ROOT_ORPHAN_CLEANUP is intentionally a one-shot/reentrancy bit, but the audit has not proved that every early error is safely recoverable without retrying cleanup.",
    ),
    ("btrfs", 90): Verdict(
        "INCONCLUSIVE",
        "NEEDS_REPRO",
        "UNRESOLVED",
        "ONE_SHOT_STATE_SEMANTICS",
        "BTRFS_ROOT_ORPHAN_CLEANUP is intentionally a one-shot/reentrancy bit, but the audit has not proved that every early error is safely recoverable without retrying cleanup.",
    ),
    ("btrfs", 91): Verdict(
        "INCONCLUSIVE",
        "NEEDS_REPRO",
        "UNRESOLVED",
        "ONE_SHOT_STATE_SEMANTICS",
        "BTRFS_ROOT_ORPHAN_CLEANUP is intentionally a one-shot/reentrancy bit, but the audit has not proved that every early error is safely recoverable without retrying cleanup.",
    ),
    ("btrfs", 146): Verdict(
        "FALSE_POSITIVE",
        "CONFIRMED_DIFFERENT_DEFECT",
        "DIFFERENT_DEFECT",
        "FRESH_NODE_RESOURCE_LEAK",
        "The Candidate only reports fields of the fresh mapping_node, not a metadata residual.  The duplicate rb insertion branch nevertheless returns -EEXIST without freeing that node.",
        "confirmed bug #6",
    ),
    ("btrfs", 161): Verdict(
        "FALSE_POSITIVE",
        "NO_BUG",
        "FALSE_ALARM",
        "RELOCATION_ERROR_CLEANUP",
        "Failure before fs_root->reloc_root assignment returns the root to the local list; out_unset then frees the relocation control and all remaining relocation roots.",
    ),
    ("btrfs", 162): Verdict(
        "TRUE_RESIDUAL",
        "CONFIRMED",
        "TRUE_ISSUE",
        "RECOVERED_ROOT_REFERENCE_NOT_DROPPED",
        "fs_root->reloc_root is assigned before the recovery commit; the out_unset path frees reloc_control without clearing the attached references when the failure does not set BTRFS_FS_ERROR.",
        "confirmed bug #7",
    ),
    ("btrfs", 163): Verdict(
        "TRUE_RESIDUAL",
        "NO_BUG",
        "CONTAINED_NOT_BUG",
        "ABORTED_SNAPSHOT_RELOCATION_ACCOUNTING",
        "merging_rsv_size is incremented before migration, but failure aborts the snapshot transaction; the fatal relocation/transaction cleanup owns and ultimately frees reloc_control.",
    ),
    ("btrfs", 164): Verdict(
        "TRUE_RESIDUAL",
        "NO_BUG",
        "CONTAINED_NOT_BUG",
        "ABORTED_SNAPSHOT_RELOCATION_ACCOUNTING",
        "merging_rsv_size is incremented before reloc-root insertion, but failure aborts the snapshot transaction; the fatal relocation/transaction cleanup owns and ultimately frees reloc_control.",
    ),
    ("btrfs", 167): Verdict(
        "FALSE_POSITIVE",
        "NO_BUG",
        "FALSE_ALARM",
        "FAILED_MOUNT_SPACE_INFO_TEARDOWN",
        "A later create_space_info failure can leave an earlier type linked only in the failed mount object.  Mount teardown removes it, and kobject_put uses space_info_release() to free the allocation; the previously suspected leak is not present.",
    ),
    ("btrfs", 168): Verdict(
        "TRUE_RESIDUAL",
        "LIKELY",
        "TRUE_ISSUE",
        "REMOUNT_STATE_BIT_NOT_CLEARED",
        "BTRFS_FS_STATE_REMOUNTING is set before feature validation, and this direct return bypasses both success and restore paths that clear it while the original mount remains live.",
        "pending P1",
    ),
    ("btrfs", 169): Verdict(
        "FALSE_POSITIVE",
        "NO_BUG",
        "FALSE_ALARM",
        "REMOUNT_RESTORE_PATH",
        "btrfs_remount_rw() failure goes through restore, which restores the old context, performs remount cleanup, and clears BTRFS_FS_STATE_REMOUNTING.",
    ),
    ("btrfs", 215): Verdict(
        "TRUE_RESIDUAL",
        "NO_BUG",
        "CONTAINED_NOT_BUG",
        "FAILED_UUID_TREE_COMMIT",
        "uuid_root is assigned before commit, but commit failure aborts the filesystem transaction; initial mount tears down the object and an RO-to-RW remount cannot continue writable after the filesystem error.",
    ),
    ("btrfs", 216): Verdict(
        "TRUE_RESIDUAL",
        "NEEDS_REPRO",
        "LIKELY_ISSUE",
        "UUID_TREE_PUBLISHED_WITHOUT_SCAN",
        "After a successful tree commit, kthread_run failure leaves uuid_root published.  On an RO-to-RW remount, the next retry skips create_uuid_tree and lacks open_ctree's generation-mismatch rescan path, so an empty/incomplete UUID tree may become live.",
    ),
    ("btrfs", 217): Verdict(
        "FALSE_POSITIVE",
        "NO_BUG",
        "FALSE_ALARM",
        "INTENTIONAL_FS_DEVICES_CACHE",
        "The source explicitly documents that the fs_devices entry can safely remain cached when device allocation fails; it is neither a mounted topology entry nor leaked live device state.",
    ),
    ("btrfs", 220): Verdict(
        "TRUE_RESIDUAL",
        "CONFIRMED",
        "TRUE_ISSUE",
        "FAILED_SPROUT_DEVICE_ROLLBACK",
        "Commit failure occurs after the sprout device and fs_devices topology/accounting were published; the error path misses post_commit_list detachment, active pointer restoration, and full sprout state rollback.",
        "confirmed bugs #16-#18",
    ),
    ("btrfs", 221): Verdict(
        "TRUE_RESIDUAL",
        "NO_BUG",
        "CONTAINED_NOT_BUG",
        "ABORTED_CHUNK_TRANSACTION",
        "CHUNK_ITEM_INSERTED is set after the transaction item insertion and before system-chunk serialization; failure aborts the transaction and abort cleanup drains the pending new block group.",
    ),
    ("btrfs", 227): Verdict(
        "FALSE_POSITIVE",
        "NO_BUG",
        "FALSE_ALARM",
        "ZONE_INFO_ERROR_CLEANUP",
        "btrfs_get_dev_zone_info() frees zone_info and clears device->zone_info on every reviewed error path.",
    ),
    ("btrfs", 229): Verdict(
        "FALSE_POSITIVE",
        "NO_BUG",
        "FALSE_ALARM",
        "SUBMITTED_IO_WRITE_POINTER_PROGRESS",
        "The superblock bio is submitted before this call.  wp/condition must retain that submitted write even if the optional ZONE_FINISH command fails; rolling them back would reuse the wrong write location.",
    ),
    ("btrfs", 231): Verdict(
        "FALSE_POSITIVE",
        "NO_BUG",
        "FALSE_ALARM",
        "BLOCK_GROUP_ZONE_INFO_TEARDOWN",
        "calculate_alloc_pointer failure frees physical_map and the temporary bitmap/zone arrays; the caller then drops the unpublished block-group cache.  The earlier suspected leak/residual does not survive.",
    ),
    ("ext4", 46): Verdict(
        "TRUE_RESIDUAL",
        "LIKELY",
        "TRUE_ISSUE",
        "PARTIAL_INDEX_CONVERSION_EARLY_RETURN",
        "ext4_append has already grown and journaled directory size, entries were moved, and the dx root was rewritten.  Casefold hash allocation can return -ENOMEM here, bypassing the shared path that marks the partially converted inode dirty despite the source comment requiring exactly that handling.",
    ),
    ("f2fs", 21): Verdict(
        "TRUE_RESIDUAL",
        "NO_BUG",
        "CONTAINED_NOT_BUG",
        "CHECKPOINT_ERROR_CONTAINMENT",
        "SIT and curseg state are changed before change_curseg reads the SSR summary.  That read uses f2fs_get_meta_page_retry(), whose terminal error calls f2fs_stop_checkpoint(); the filesystem is quarantined and the uncheckpointed allocation is discarded on recovery.",
    ),
    ("xfs", 142): Verdict(
        "TRUE_RESIDUAL",
        "NO_BUG",
        "CONTAINED_NOT_BUG",
        "DIRTY_TRANSACTION_SHUTDOWN",
        "The inode forks and delayed-block ownership are already swapped before owner-change failure.  xfs_trans_cancel() explicitly forces shutdown for a dirty transaction because these in-core changes cannot be restored.",
    ),
    ("xfs", 185): Verdict(
        "FALSE_POSITIVE",
        "NO_BUG",
        "FALSE_ALARM",
        "EXPLICIT_RESERVATION_UNWIND",
        "xfs_dec_frextents failure jumps to undo_log, which ungrants the log ticket and clears t_ticket, t_log_res, and the permanent-reservation flag before returning.",
    ),
    ("xfs", 189): Verdict(
        "FALSE_POSITIVE",
        "NO_BUG",
        "FALSE_ALARM",
        "EXPLICIT_QUOTA_UNWIND",
        "Group reservation failure jumps to unwind_usr and reverses the prior user reservation with forced negative xfs_trans_dqresv().",
    ),
    ("xfs", 190): Verdict(
        "FALSE_POSITIVE",
        "NO_BUG",
        "FALSE_ALARM",
        "EXPLICIT_QUOTA_UNWIND",
        "Project reservation failure runs unwind_grp and unwind_usr, reversing both prior group and user reservations before return.",
    ),
}


def base_verdict(fs: str, function: str) -> Verdict:
    if fs == "btrfs":
        if function in BTRFS_TXN_FUNCTIONS:
            return TXN_CONTAINED
        if function in BTRFS_MOUNT_FUNCTIONS:
            return MOUNT_TEARDOWN
        if function in BTRFS_PROGRESS_FUNCTIONS:
            return INTENTIONAL_PROGRESS
        return FALSE_PRIVATE

    if fs == "ext4":
        return FALSE_PRIVATE

    if fs == "f2fs":
        return MOUNT_TEARDOWN if function == "f2fs_fill_super" else FALSE_PRIVATE

    if fs == "xfs":
        if function in XFS_TXN_FUNCTIONS:
            return TXN_CONTAINED
        if function in XFS_MOUNT_FUNCTIONS:
            return MOUNT_TEARDOWN
        if function in XFS_PROGRESS_FUNCTIONS:
            return INTENTIONAL_PROGRESS
        return FALSE_PRIVATE

    raise AssertionError(f"unknown filesystem {fs}")


def effect_summary(report: dict[str, Any]) -> str:
    effects = []
    for effect in report["residual_slice"]["residuals"]:
        site = effect.get("site", {})
        effects.append(
            f"{effect.get('root')}.{effect.get('key')}:{effect.get('delta')}@{site.get('line')}"
        )
    return ";".join(dict.fromkeys(effects))


def load_rows(repo: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    batch = repo / "outputs" / "residual-evaluation-batch"
    for fs, expected in EXPECTED_COUNTS.items():
        path = batch / RUN_DIRS[fs] / "reports" / "all_reports.json"
        reports = json.loads(path.read_text(encoding="utf-8"))
        candidates = [r for r in reports if r.get("confidence") == "candidate"]
        if len(candidates) != expected:
            raise RuntimeError(
                f"{fs}: expected {expected} Candidate reports, found {len(candidates)}"
            )

        prefix = fs.upper()
        for index, report in enumerate(candidates, 1):
            verdict = SPECIAL.get((fs, index), base_verdict(fs, report["function"]))
            failure = report["residual_slice"]["failure_site"]
            exit_site = report["residual_slice"]["exit_site"]
            rows.append(
                {
                    "id": f"{prefix}-{index:03d}",
                    "filesystem": fs,
                    "candidate_index": index,
                    "function": report["function"],
                    "failure_file": failure["file"],
                    "failure_line": failure["line"],
                    "failure_expression": failure["expression"],
                    "exit_line": exit_site["line"],
                    "exit_expression": exit_site["expression"],
                    "effect_summary": effect_summary(report),
                    "report_validity": verdict.report_validity,
                    "bug_status": verdict.bug_status,
                    "source_verdict": verdict.source_verdict,
                    "root_cause_family": verdict.root_cause_family,
                    "rationale": verdict.rationale,
                    "related_finding": verdict.related_finding,
                    "reviewed_on": REVIEW_DATE,
                }
            )

    if len(rows) != sum(EXPECTED_COUNTS.values()):
        raise RuntimeError(f"expected 539 ledger rows, found {len(rows)}")
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def md_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def write_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# M32d Candidate Source Review",
        "",
        f"Review date: {REVIEW_DATE}",
        "",
        "This ledger filters `all_reports.json` by `confidence == candidate` before assigning stable per-filesystem IDs.  It separates report validity from bug status: a source-visible function-boundary residual can be real while transaction abort, filesystem shutdown, or failed-object teardown prevents a bug.",
        "",
        "## Summary",
        "",
        "| Filesystem | Rows | True/likely issues | Different defects | Contained, not bugs | False alarms | Unresolved |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    for fs in EXPECTED_COUNTS:
        fs_rows = [row for row in rows if row["filesystem"] == fs]
        counts = Counter(row["source_verdict"] for row in fs_rows)
        issues = counts["TRUE_ISSUE"] + counts["LIKELY_ISSUE"]
        lines.append(
            f"| {fs} | {len(fs_rows)} | {issues} | {counts['DIFFERENT_DEFECT']} | "
            f"{counts['CONTAINED_NOT_BUG']} | {counts['FALSE_ALARM']} | {counts['UNRESOLVED']} |"
        )

    total = Counter(row["source_verdict"] for row in rows)
    lines.extend(
        [
            f"| **Total** | **{len(rows)}** | **{total['TRUE_ISSUE'] + total['LIKELY_ISSUE']}** | **{total['DIFFERENT_DEFECT']}** | **{total['CONTAINED_NOT_BUG']}** | **{total['FALSE_ALARM']}** | **{total['UNRESOLVED']}** |",
            "",
            "## High-value results",
            "",
            "| ID | Function | Source verdict | Bug status | Related | Rationale |",
            "|---|---|---|---|---|---|",
        ]
    )
    high_value = {
        "TRUE_ISSUE",
        "LIKELY_ISSUE",
        "DIFFERENT_DEFECT",
        "UNRESOLVED",
    }
    for row in rows:
        if row["source_verdict"] not in high_value:
            continue
        lines.append(
            "| {id} | `{function}` | {source_verdict} | {bug_status} | {related_finding} | {rationale} |".format(
                **{key: md_escape(value) for key, value in row.items()}
            )
        )

    lines.extend(
        [
            "",
            "## Per-report ledger",
            "",
            "The CSV and JSONL siblings retain full failure/exit expressions and effect summaries.  This table is the compact human-readable index.",
        ]
    )
    for fs in EXPECTED_COUNTS:
        lines.extend(
            [
                "",
                f"### {fs}",
                "",
                "| ID | Function | Failure | Report validity | Source verdict | Bug status | Root-cause family |",
                "|---|---|---:|---|---|---|---|",
            ]
        )
        for row in rows:
            if row["filesystem"] != fs:
                continue
            lines.append(
                f"| {row['id']} | `{md_escape(row['function'])}` | {row['failure_line']} | "
                f"{row['report_validity']} | {row['source_verdict']} | {row['bug_status']} | "
                f"{row['root_cause_family']} |"
            )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    repo = args.repo.resolve()
    output = repo / "outputs"
    output.mkdir(parents=True, exist_ok=True)

    rows = load_rows(repo)
    write_jsonl(output / "candidate_review_m32d.jsonl", rows)
    write_csv(output / "candidate_review_m32d.csv", rows)
    write_markdown(output / "candidate_review_m32d.md", rows)

    counts = Counter(row["source_verdict"] for row in rows)
    print(json.dumps({"rows": len(rows), "source_verdict": counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
