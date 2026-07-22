import json

from src.metadata_xfs_tempexch_transaction_audit import (
    audit_xfs_tempexch_transaction,
    main,
)


def test_xfs_tempexch_transaction_audit_extracts_source_facts(tmp_path):
    source_root = _write_xfs_scrub_fixture(tmp_path)

    report = audit_xfs_tempexch_transaction(source_root, source_version="test")
    payload = report.to_dict()

    assert payload["result_semantics"] == "source_facts_not_bug_claims"
    assert payload["bug_claims_allowed"] is False
    assert payload["summary"]["target_helper_allocates_sc_tp"] is True
    assert payload["summary"]["target_helper_returns_quota_result"] is True
    assert (
        payload["summary"]["quota_helper_has_failure_return_without_cleanup"]
        is True
    )
    assert payload["summary"]["callers"] == 3
    assert (
        payload["summary"]["callers_returning_error_without_visible_cleanup"]
        == 2
    )
    assert payload["conclusion"] == "strong_manual_review_candidate_not_confirmed_bug"


def test_xfs_tempexch_transaction_audit_cli_writes_outputs(tmp_path):
    source_root = _write_xfs_scrub_fixture(tmp_path)
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
    assert payload["summary"]["callers_returning_error_without_visible_cleanup"] == 2
    assert "not a confirmed-bug report" in markdown
    assert "strong_manual_review_candidate_not_confirmed_bug" in markdown


def _write_xfs_scrub_fixture(tmp_path):
    scrub = tmp_path / "fs" / "xfs" / "scrub"
    scrub.mkdir(parents=True)
    (scrub / "tempfile.c").write_text(
        "\n".join(
            [
                "static int",
                "xrep_tempexch_reserve_quota(struct xfs_scrub *sc, void *tx)",
                "{",
                "\tint error;",
                "\terror = xfs_trans_reserve_quota_nblks(sc->tp, sc->ip, 1, 0, true);",
                "\tif (error)",
                "\t\treturn error;",
                "\treturn xfs_trans_reserve_quota_nblks(sc->tp, sc->tempip, 1, 0, true);",
                "}",
                "",
                "int",
                "xrep_tempexch_trans_alloc(struct xfs_scrub *sc, int whichfork, void *tx)",
                "{",
                "\tint error;",
                "\terror = xfs_trans_alloc(sc->mp, 0, 0, 0, 0, &sc->tp);",
                "\tif (error)",
                "\t\treturn error;",
                "\txfs_exchrange_ilock(sc->tp, sc->ip, sc->tempip);",
                "\treturn xrep_tempexch_reserve_quota(sc, tx);",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    (scrub / "attr_repair.c").write_text(
        "\n".join(
            [
                "static int",
                "xrep_xattr_finalize_tempfile(struct repair *rx)",
                "{",
                "\tint error;",
                "\terror = xrep_tempexch_trans_alloc(rx->sc, 1, &rx->tx);",
                "\tif (error)",
                "\t\treturn error;",
                "\treturn 0;",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    (scrub / "dir_repair.c").write_text(
        "\n".join(
            [
                "static int",
                "xrep_dir_finalize_tempdir(struct repair *rd)",
                "{",
                "\tif (!rd->parent)",
                "\t\treturn xrep_tempexch_trans_alloc(rd->sc, 1, &rd->tx);",
                "\treturn 0;",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    (scrub / "safe_repair.c").write_text(
        "\n".join(
            [
                "static int",
                "xrep_safe_finalize(struct xfs_scrub *sc)",
                "{",
                "\tint error;",
                "\terror = xrep_tempexch_trans_alloc(sc, 1, sc->buf);",
                "\tif (error) {",
                "\t\txchk_trans_cancel(sc);",
                "\t\treturn error;",
                "\t}",
                "\treturn 0;",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    return tmp_path / "fs"
