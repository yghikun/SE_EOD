import json

from src.metadata_ext4_replay_bookkeeping_audit import (
    audit_ext4_replay_bookkeeping,
    main,
)


def test_ext4_replay_bookkeeping_audit_extracts_source_facts(tmp_path):
    source_root = _write_ext4_fixture(tmp_path)

    report = audit_ext4_replay_bookkeeping(source_root, source_version="test")
    payload = report.to_dict()

    assert payload["result_semantics"] == "source_facts_not_bug_claims"
    assert payload["bug_claims_allowed"] is False
    assert payload["summary"]["audited_helpers"] == 2
    assert payload["summary"]["helpers_with_public_int_return"] == 2
    assert payload["summary"]["helpers_with_ignored_fast_commit_calls"] == 2
    assert payload["summary"]["helpers_swallowing_ext4_map_blocks_errors"] == 2

    by_function = {item["function"]: item for item in payload["helpers"]}
    set_iblocks = by_function["ext4_ext_replay_set_iblocks"]
    clear_bb = by_function["ext4_ext_clear_bb"]

    assert set_iblocks["conclusion"] == "needs_external_semantics"
    assert set_iblocks["fact_summary"]["metadata_bookkeeping_after_failure"] is True
    assert clear_bb["fact_summary"]["partial_metadata_mutation_before_failure"] is True
    assert all(item["bug_claim_allowed"] is False for item in payload["helpers"])


def test_ext4_replay_bookkeeping_audit_cli_writes_outputs(tmp_path):
    source_root = _write_ext4_fixture(tmp_path)
    out_json = tmp_path / "audit.json"
    out_md = tmp_path / "audit.md"

    assert (
        main(
            [
                "--source-root",
                str(source_root),
                "--source-version",
                "test",
                "--out-json",
                str(out_json),
                "--out-md",
                str(out_md),
            ]
        )
        == 0
    )

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    assert payload["summary"]["audited_helpers"] == 2
    assert "confirmed-bug report" in markdown
    assert "needs_external_semantics" in markdown


def _write_ext4_fixture(tmp_path):
    ext4 = tmp_path / "fs" / "ext4"
    ext4.mkdir(parents=True)
    (ext4 / "ext4.h").write_text(
        "\n".join(
            [
                "extern int ext4_ext_replay_set_iblocks(struct inode *inode);",
                "extern int ext4_ext_clear_bb(struct inode *inode);",
            ]
        ),
        encoding="utf-8",
    )
    (ext4 / "fast_commit.c").write_text(
        "\n".join(
            [
                "void ext4_fc_replay_inode(struct inode *inode)",
                "{",
                "\text4_ext_clear_bb(inode);",
                "\text4_ext_replay_set_iblocks(inode);",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    (ext4 / "extents.c").write_text(
        "\n".join(
            [
                "/* Count number of blocks used by this inode and update i_blocks */",
                "int ext4_ext_replay_set_iblocks(struct inode *inode)",
                "{",
                "\tint ret = 0;",
                "\tstruct ext4_map_blocks map;",
                "\tret = ext4_map_blocks(NULL, inode, &map, 0);",
                "\tif (ret < 0)",
                "\t\tbreak;",
                "out:",
                "\tinode->i_blocks = 1;",
                "\text4_mark_inode_dirty(NULL, inode);",
                "\treturn 0;",
                "}",
                "",
                "int ext4_ext_clear_bb(struct inode *inode)",
                "{",
                "\tint ret = 0;",
                "\tstruct ext4_map_blocks map;",
                "\text4_mb_mark_bb(inode->i_sb, map.m_pblk, map.m_len, false);",
                "\text4_fc_record_regions(inode->i_sb, inode->i_ino, 0, 1, 1, 1);",
                "\tret = ext4_map_blocks(NULL, inode, &map, 0);",
                "\tif (ret < 0)",
                "\t\tbreak;",
                "out:",
                "\treturn 0;",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    return tmp_path / "fs"
