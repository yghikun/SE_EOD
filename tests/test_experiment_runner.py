import json
from pathlib import Path

from scripts.run_experiment_v1_3 import build_command, collect_run_manifests


def test_collect_run_manifests_preserves_previous_matrix_cells(tmp_path: Path):
    for version, filesystem in (("linux-v6.8", "ext4"), ("linux-v7.1", "btrfs")):
        output = tmp_path / version / filesystem
        output.mkdir(parents=True)
        (output / "run_manifest.json").write_text(
            json.dumps({"version": version, "filesystem": filesystem, "stats": {}}),
            encoding="utf-8",
        )

    runs = collect_run_manifests(tmp_path)

    assert {(run["version"], run["filesystem"]) for run in runs} == {
        ("linux-v6.8", "ext4"),
        ("linux-v7.1", "btrfs"),
    }


def test_build_command_records_interprocedural_summary_output(tmp_path: Path):
    command = build_command(
        tmp_path,
        tmp_path / "linux",
        tmp_path / "output",
        "ext4",
        enable_interprocedural=True,
    )

    assert "--enable-interprocedural" in command
    index = command.index("--function-summaries-out")
    assert command[index + 1].endswith("function_summaries.json")
