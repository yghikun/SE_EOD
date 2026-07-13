from pathlib import Path

import json

from scripts.check_linux_v6_14_filesystems import build_command, combine_llm_tasks


def test_checker_builds_cfg_and_llm_pipeline(tmp_path: Path):
    args = type("Args", (), {"context_lines": 60, "min_evidence_score": 12, "run_deepseek": False, "deepseek_limit": None})()
    command = build_command(tmp_path, tmp_path / "linux", tmp_path / "out", "ext4", args)
    assert "--enable-interprocedural" in command
    assert "--build-llm-tasks" in command
    assert "--min-evidence-score" in command
    assert str(tmp_path / "out" / "llm_review_tasks.jsonl") in command


def test_combines_filesystem_tasks_for_llm(tmp_path: Path):
    source = tmp_path / "ext4.jsonl"
    source.write_text(json.dumps({"task_id": "task-1"}) + "\n", encoding="utf-8")
    output = tmp_path / "combined.jsonl"
    count = combine_llm_tasks(
        [{"filesystem": "ext4", "llm_tasks": str(source)}], output
    )
    assert count == 1
    assert json.loads(output.read_text(encoding="utf-8"))["filesystem"] == "ext4"
