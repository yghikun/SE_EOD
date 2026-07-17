from pathlib import Path

from src.error_condition import classify_condition
from src.error_path_extractor import ErrorPathExtractor
from src.function_extractor import extract_functions
from src.label_resolver import Statement
from src.parser import parse_c_file
from src.resource_tracker import ResourceTracker


def _resource_map() -> dict:
    return {
        "acquire_functions": {
            "kmalloc": {"resource_type": "memory", "release": ["kfree"]},
            "btrfs_alloc_path": {
                "resource_type": "btrfs_path",
                "release": ["btrfs_free_path"],
            },
        },
        "scope_cleanup_macros": {
            "AUTO_KFREE": "kfree",
            "AUTO_KVFREE": "kvfree",
            "BTRFS_PATH_AUTO_FREE": "btrfs_free_path",
        },
    }


def test_direct_free_attribute_releases_resource_at_scope_exit():
    tracker = ResourceTracker(_resource_map())
    statements = [
        Statement("struct item *ptr __free(kfree) = kmalloc(16);", 10),
    ]

    held = tracker.held_before(
        statements,
        error_line=20,
        condition=classify_condition("err"),
        error_source_expr="foo()",
    )

    assert len(held) == 1
    assert held[0].var == "ptr"
    assert held[0].scope_cleanup_function == "kfree"
    assert held[0].scope_cleanup_decl_line == 10
    assert tracker.missing_cleanup_candidates(held, []) == []


def test_cleanup_macro_suppresses_only_matching_release():
    tracker = ResourceTracker(_resource_map())
    statements = [
        Statement("BTRFS_PATH_AUTO_FREE(path);", 10),
        Statement("path = btrfs_alloc_path();", 11),
    ]
    held = tracker.held_before(
        statements,
        error_line=20,
        condition=classify_condition("ret"),
        error_source_expr="foo()",
    )

    assert held[0].scope_cleanup_function == "btrfs_free_path"
    assert tracker.missing_cleanup_candidates(held, []) == []

    tracker = ResourceTracker(
        {
            **_resource_map(),
            "scope_cleanup_macros": {"BTRFS_PATH_AUTO_FREE": "unrelated_put"},
        }
    )
    held = tracker.held_before(
        statements,
        error_line=20,
        condition=classify_condition("ret"),
        error_source_expr="foo()",
    )
    assert tracker.missing_cleanup_candidates(held, []) == ["btrfs_free_path(path)"]


def test_auto_memory_cleanup_macros_release_matching_allocations():
    tracker = ResourceTracker(
        {
            **_resource_map(),
            "acquire_functions": {
                **_resource_map()["acquire_functions"],
                "kvmalloc": {"resource_type": "memory", "release": ["kvfree"]},
            },
        }
    )
    statements = [
        Statement("struct item AUTO_KFREE(item);", 10),
        Statement("char AUTO_KVFREE(buf);", 11),
        Statement("item = kmalloc(16);", 12),
        Statement("buf = kvmalloc(32);", 13),
    ]

    held = tracker.held_before(
        statements,
        error_line=20,
        condition=classify_condition("err"),
        error_source_expr="foo()",
    )

    by_var = {resource.var: resource for resource in held}
    assert by_var["item"].scope_cleanup_function == "kfree"
    assert by_var["buf"].scope_cleanup_function == "kvfree"
    assert tracker.missing_cleanup_candidates(held, []) == []


def test_branch_prediction_wrapper_preserves_acquire_failure_semantics():
    tracker = ResourceTracker(_resource_map())
    held = tracker.held_before(
        [Statement("path = btrfs_alloc_path();", 10)],
        error_line=20,
        condition=classify_condition("unlikely(!path)"),
        error_source_expr="unknown",
    )

    assert classify_condition("unlikely(!path)").condition_type == "null_check"
    assert held == []


def test_ptr_err_or_zero_condition_does_not_hold_error_pointer():
    tracker = ResourceTracker(
        {
            "acquire_functions": {
                "get_root": {
                    "resource_type": "root_ref",
                    "release": ["put_root"],
                    "failed_check": "IS_ERR",
                }
            }
        }
    )
    held = tracker.held_before(
        [
            Statement("root = get_root();", 10),
            Statement("ret = PTR_ERR_OR_ZERO(root);", 11),
        ],
        error_line=20,
        condition=classify_condition("ret && ret != -ENOENT", "ret"),
        error_source_expr="PTR_ERR_OR_ZERO(root)",
    )

    assert held == []


def test_scope_cleanup_propagates_through_pointer_alias():
    tracker = ResourceTracker(_resource_map())
    held = tracker.held_before(
        [
            Statement("struct item AUTO_KFREE(original);", 10),
            Statement("cursor = kmalloc(16);", 11),
            Statement("original = cursor;", 12),
        ],
        error_line=20,
        condition=classify_condition("err"),
        error_source_expr="foo()",
    )

    assert held[0].scope_cleanup_function == "kfree"
    assert tracker.missing_cleanup_candidates(held, []) == []


def test_error_callee_consumption_and_field_ownership_transfer():
    tracker = ResourceTracker(
        {
            "acquire_functions": {
                "lock_tree": {
                    "resource_type": "tree_lock",
                    "release": ["unlock_tree"],
                    "direct_resource_arg": 0,
                },
                "grab_root": {
                    "resource_type": "root_ref",
                    "release": ["put_root"],
                },
            },
            "callee_resource_consumers": {
                "check_tree": {
                    "when": "error_return",
                    "resource_type": "tree_lock",
                    "resource_arg": 0,
                }
            },
            "resource_ownership_transfers": [
                {
                    "function": "recover",
                    "resource_type": "root_ref",
                    "resource_expr": "owner->root",
                }
            ],
        }
    )
    held = tracker.held_before(
        [
            Statement("lock_tree(node);", 10),
            Statement("owner->root = grab_root();", 11),
        ],
        error_line=20,
        condition=classify_condition("ret"),
        error_source_expr="check_tree(node)",
        function_name="recover",
    )

    assert len(held) == 1
    assert held[0].var == "owner->root"
    assert held[0].ownership_state == "MAY_ACQUIRED"
    assert held[0].uncertainty_causes == [
        "unreviewed_ownership_transfer_hint"
    ]


def test_auto_cleanup_applies_to_return_and_goto_exits(tmp_path: Path):
    source = """
int auto_return(void)
{
    BTRFS_PATH_AUTO_FREE(path);
    int ret;

    path = btrfs_alloc_path();
    ret = foo();
    if (ret)
        return ret;
    return 0;
}

int auto_goto(void)
{
    BTRFS_PATH_AUTO_FREE(path);
    int ret;

    path = btrfs_alloc_path();
    ret = foo();
    if (ret)
        goto out;
out:
    return ret;
}

int manual_required(void)
{
    struct btrfs_path *path;
    int ret;

    path = btrfs_alloc_path();
    ret = foo();
    if (ret)
        return ret;
    return 0;
}
"""
    path = tmp_path / "scope_cleanup.c"
    path.write_text(source, encoding="utf-8")
    extractor = ErrorPathExtractor(ResourceTracker(_resource_map()))
    functions = extract_functions(parse_c_file(path))
    by_name = {function.name: extractor.extract(function) for function in functions}

    assert any(row.condition == "ret" for row in by_name["auto_return"])
    assert all(not row.missing_cleanup_candidates for row in by_name["auto_return"])
    assert any(row.target_label == "out" for row in by_name["auto_goto"])
    assert all(not row.missing_cleanup_candidates for row in by_name["auto_goto"])
    assert any(
        "btrfs_free_path(path)" in row.missing_cleanup_candidates
        for row in by_name["manual_required"]
    )
