from pathlib import Path

from src.metadata_bug_hunt_ranking import build_bug_hunt_ranking


def _write_source(root: Path, relative: str, source: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _triage_item(
    function: str,
    *,
    exit_kind: str = "failure",
    exit_detail: str = "return 0;",
) -> dict:
    return {
        "record": {
            "classification": "DISCOVERY_REVIEW",
            "protocol_id": "mocc.protocol_e.allocation_lifecycle",
            "operation_id": "btrfs_parent_lookup_path_allocation",
            "source_file": "btrfs/demo.c",
            "source_version": "9.9",
            "function": function,
            "exit_kind": exit_kind,
            "static_certainty": "high",
            "open_effects": [
                {
                    "object_ref": {
                        "expression": "path",
                    },
                }
            ],
            "representative_witness": [
                {"kind": "effect_created", "line": 3, "detail": "allocation"},
                {"kind": "exit", "line": 7, "detail": exit_detail},
            ],
        },
        "triage": {"priority": "P2", "verdict": "uncertain"},
    }


def _ranking(
    tmp_path: Path,
    source: str,
    function: str = "demo",
    *,
    exit_kind: str = "failure",
    exit_detail: str = "return 0;",
) -> dict:
    _write_source(
        tmp_path,
        "linux-sources/linux-v9.9-fs/fs/btrfs/demo.c",
        source,
    )
    return build_bug_hunt_ranking(
        {
            "source_version": "9.9",
            "items": [
                _triage_item(
                    function,
                    exit_kind=exit_kind,
                    exit_detail=exit_detail,
                )
            ],
        },
        workspace=tmp_path,
        top=1,
    )["items"][0]


def test_bug_hunt_ranking_prioritizes_unclosed_lifecycle_shape(tmp_path):
    item = _ranking(
        tmp_path,
        """
int demo(void)
{
    struct btrfs_path *path = btrfs_alloc_path();
    if (!path)
        return -ENOMEM;
    do_work(path);
    return 0;
}
""",
    )

    assert item["review_class"] == "manual_source_review_high"
    assert item["downrank_reasons"] == []


def test_bug_hunt_ranking_downranks_visible_terminal_action(tmp_path):
    item = _ranking(
        tmp_path,
        """
int demo(void)
{
    struct btrfs_path *path = btrfs_alloc_path();
    if (!path)
        return -ENOMEM;
    do_work(path);
    btrfs_free_path(path);
    return 0;
}
""",
    )

    assert item["review_class"] == "manual_source_review_medium"
    assert "matching terminal action is visible" in item["downrank_reasons"][0]


def test_bug_hunt_ranking_downranks_returned_ownership(tmp_path):
    item = _ranking(
        tmp_path,
        """
struct btrfs_path *demo(void)
{
    struct btrfs_path *path = btrfs_alloc_path();
    if (!path)
        return NULL;
    return path;
}
""",
        "demo",
        exit_kind="success",
        exit_detail="return path;",
    )

    assert item["review_class"] == "likely_protocol_gap_or_false_positive"
    assert "returned to caller" in item["downrank_reasons"][0]
