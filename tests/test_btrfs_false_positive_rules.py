import json

from src.candidate_rules import missing_cleanup_candidates
from src.error_condition import classify_condition
from src.label_resolver import Statement
from src.protocol_db import ResourceProtocolDB
from src.resource_tracker import ResourceTracker, load_resource_map


def test_btrfs_extent_map_uses_free_extent_map_release():
    tracker = ResourceTracker(load_resource_map("configs/btrfs_resource_map.json"))
    held = tracker.held_before(
        [Statement("em = alloc_extent_map();", 10)],
        error_line=20,
        condition=classify_condition("ret"),
        error_source_expr="btrfs_search_slot(root)",
        function_name="defrag_get_extent",
    )

    assert tracker.missing_cleanup_candidates(held, ["free_extent_map(em)"]) == []


def test_btrfs_extent_map_protocol_is_configured():
    protocols = ResourceProtocolDB.load_from_dir("configs/btrfs_resource_protocols")

    assert protocols.find_by_acquire_function("alloc_extent_map")
    assert protocols.find_by_release_function("free_extent_map")


def test_btrfs_lock_cluster_lock_handoff_is_suppressed():
    row = {
        "file": "fs/btrfs/extent-tree.c",
        "function": "btrfs_lock_cluster",
        "error_line": "3589",
        "candidate_type": "missing_cleanup",
        "condition": "!used_bg",
        "held_resources": json.dumps(
            [
                {
                    "var": "&cluster->refill_lock",
                    "resource_type": "spinlock",
                    "acquire_func": "spin_lock",
                }
            ]
        ),
        "cleanup_calls": "[]",
        "missing_cleanup_candidates": json.dumps(["spin_unlock(&cluster->refill_lock)"]),
        "final_return_expr": "NULL",
    }

    assert missing_cleanup_candidates(row) == []


def test_btrfs_create_chunk_transaction_owned_block_group_is_suppressed():
    row = {
        "file": "fs/btrfs/block-group.c",
        "function": "reserve_chunk_space",
        "error_line": "4271",
        "candidate_type": "missing_cleanup",
        "condition": "ret < 0",
        "held_resources": json.dumps(
            [
                {
                    "var": "bg",
                    "resource_type": "memory",
                    "acquire_func": "btrfs_create_chunk",
                    "release_functions": ["kfree"],
                }
            ]
        ),
        "cleanup_calls": "[]",
        "missing_cleanup_candidates": json.dumps(["kfree(bg)"]),
        "final_return_expr": "unknown",
    }

    assert missing_cleanup_candidates(row) == []


def test_btrfs_init_first_rw_device_transaction_owned_metadata_bg_is_suppressed():
    row = {
        "file": "fs/btrfs/volumes.c",
        "function": "init_first_rw_device",
        "error_line": "5850",
        "candidate_type": "missing_cleanup",
        "condition": "IS_ERR(sys_bg)",
        "held_resources": json.dumps(
            [
                {
                    "var": "meta_bg",
                    "resource_type": "memory",
                    "acquire_func": "btrfs_create_chunk",
                    "release_functions": ["kfree"],
                }
            ]
        ),
        "cleanup_calls": "[]",
        "missing_cleanup_candidates": json.dumps(["kfree(meta_bg)"]),
        "final_return_expr": "PTR_ERR(sys_bg)",
    }

    assert missing_cleanup_candidates(row) == []
