import json

import pytest

from src.metadata_function_diff import (
    build_function_diff,
    load_function_source,
    main,
)


def _write_source(path, body: str):
    path.write_text(
        "\n".join(
            [
                "static int helper(void) { return 0; }",
                "static int work(void)",
                "{",
                *body.splitlines(),
                "}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_function_diff_detects_return_propagation_repair(tmp_path):
    old = tmp_path / "old.c"
    new = tmp_path / "new.c"
    _write_source(old, "    int error = helper();\n    if (error)\n        goto out;\nout:\n    return 0;")
    _write_source(new, "    int error = helper();\n    if (error)\n        goto out;\nout:\n    return error;")

    report = build_function_diff(
        "work",
        [
            load_function_source(f"old={old}", "work"),
            load_function_source(f"new={new}", "work"),
        ],
    ).to_dict()

    assert report["summary"]["pairs_with_changes"] == 1
    hints = report["pair_diffs"][0]["semantic_hints"]
    assert "return_success_changed_to_error_symbol" in hints
    assert "local_return_propagation_repair" in hints


def test_load_function_source_rejects_invalid_spec(tmp_path):
    with pytest.raises(ValueError, match="VERSION=PATH"):
        load_function_source(str(tmp_path / "old.c"), "work")


def test_cli_writes_function_diff_json_and_markdown(tmp_path):
    old = tmp_path / "old.c"
    new = tmp_path / "new.c"
    out_json = tmp_path / "diff.json"
    out_md = tmp_path / "diff.md"
    _write_source(old, "    return 0;")
    _write_source(new, "    return error;")

    assert (
        main(
            [
                "--function",
                "work",
                "--source",
                f"old={old}",
                "--source",
                f"new={new}",
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
    assert payload["function"] == "work"
    assert payload["summary"]["pairs"] == 1
    assert "Function diff: work" in markdown
