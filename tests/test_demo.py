import csv
import json
import shutil
from pathlib import Path

from src.evidence_ranker import (
    E0_STATIC_RULE_ONLY,
    E2_API_PROTOCOL_SUPPORTED,
    candidate_id_for_row,
    rank_candidate_rows,
)
from src.error_condition import classify_condition
from src.label_resolver import Statement
from src.llm_task_builder import extract_deepseek_true_candidates
from src.main import main
from src.manual_review import ManualReviewDB, ManualReviewLabel
from src.ownership_transfer import ownership_transfer_hints_for_candidate
from src.protocol_db import ResourceProtocolDB
from src.resource_expr import same_resource_expr
from src.resource_release import cleanup_call_releases_resource
from src.resource_tracker import ResourceTracker, load_resource_map
from src.wrapper_summary import WrapperSummaryDB


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _run_demo(tmp_path: Path) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
    linux = tmp_path / "linux"
    ext4 = linux / "fs" / "ext4"
    ext4.mkdir(parents=True)
    shutil.copy(Path(__file__).with_name("demo_ext4_like.c"), ext4 / "demo_ext4_like.c")
    out = tmp_path / "ext4_error_paths.csv"
    candidates_out = tmp_path / "suspicious_candidates.csv"
    llm_tasks_out = tmp_path / "llm_review_tasks.jsonl"
    ranked_out = tmp_path / "ranked_candidates.jsonl"
    candidates_with_evidence_out = tmp_path / "candidates_with_evidence.csv"

    rc = main(
        [
            "--linux",
            str(linux),
            "--out",
            str(out),
            "--include-low-confidence",
            "--check-candidates",
            "--candidates-out",
            str(candidates_out),
            "--rank-evidence",
            "--enable-ownership-transfer-hints",
            "--ranked-candidates-out",
            str(ranked_out),
            "--candidates-with-evidence-out",
            str(candidates_with_evidence_out),
            "--build-llm-tasks",
            "--llm-tasks-out",
            str(llm_tasks_out),
            "--context-lines",
            "20",
        ]
    )
    assert rc == 0
    assert out.exists()
    assert candidates_out.exists()
    assert llm_tasks_out.exists()
    assert ranked_out.exists()
    assert candidates_with_evidence_out.exists()
    return (
        _read_csv(out),
        _read_csv(candidates_out),
        _read_jsonl(llm_tasks_out),
        _read_jsonl(ranked_out),
        _read_csv(candidates_with_evidence_out),
    )


def test_cli_scans_configured_fs_subdir(tmp_path):
    linux = tmp_path / "linux"
    btrfs = linux / "fs" / "btrfs"
    btrfs.mkdir(parents=True)
    shutil.copy(Path(__file__).with_name("demo_ext4_like.c"), btrfs / "demo_btrfs_like.c")
    out = tmp_path / "btrfs_error_paths.csv"
    candidates_out = tmp_path / "btrfs_suspicious_candidates.csv"

    rc = main(
        [
            "--linux",
            str(linux),
            "--fs-subdir",
            "fs/btrfs",
            "--resource-map",
            "configs/ext4_resource_map.json",
            "--out",
            str(out),
            "--include-low-confidence",
            "--check-candidates",
            "--candidates-out",
            str(candidates_out),
        ]
    )

    assert rc == 0
    rows = _read_csv(out)
    candidates = _read_csv(candidates_out)
    assert rows
    assert all(row["file"].startswith("fs/btrfs/") for row in rows)
    assert any(row["function"] == "demo_missing_brelse" for row in candidates)


def _rows(rows: list[dict], function: str) -> list[dict]:
    return [row for row in rows if row["function"] == function]


def _json(row: dict, field: str):
    return json.loads(row[field])


def test_demo_extracts_required_error_paths(tmp_path):
    rows, candidates, llm_tasks, ranked, evidence_rows = _run_demo(tmp_path)

    ret_rows = _rows(rows, "demo_ret_return")
    assert any(
        row["condition"] == "ret"
        and row["final_return_expr"] == "ret"
        and row["error_source_expr"] == "foo()"
        for row in ret_rows
    )

    goto_rows = _rows(rows, "demo_goto_out")
    assert any(
        row["exit_type"] == "goto"
        and row["target_label"] == "out"
        and row["final_return_expr"] == "ret"
        for row in goto_rows
    )

    brelse_rows = _rows(rows, "demo_goto_brelse")
    assert any(
        row["target_label"] == "out_brelse"
        and "brelse(bh)" in _json(row, "cleanup_calls")
        and "brelse(bh)" not in _json(row, "missing_cleanup_candidates")
        for row in brelse_rows
    )

    null_bh_rows = [
        row
        for row in _rows(rows, "demo_null_bh")
        if row["condition"] == "!bh" and row["final_return_expr"] == "-EIO"
    ]
    assert null_bh_rows
    assert all("brelse(bh)" not in _json(row, "missing_cleanup_candidates") for row in null_bh_rows)

    missing_brelse_rows = [
        row
        for row in _rows(rows, "demo_missing_brelse")
        if row["condition"] == "ret" and row["final_return_expr"] == "ret"
    ]
    assert missing_brelse_rows
    assert any(
        "brelse(bh)" in _json(row, "missing_cleanup_candidates")
        for row in missing_brelse_rows
    )

    handle_rows = [
        row
        for row in _rows(rows, "demo_handle_is_err")
        if row["condition"] == "IS_ERR(handle)"
    ]
    assert handle_rows
    assert all(
        "ext4_journal_stop(handle)" not in _json(row, "missing_cleanup_candidates")
        for row in handle_rows
    )

    missing_stop_rows = [
        row
        for row in _rows(rows, "demo_missing_journal_stop")
        if row["condition"] == "ret" and row["final_return_expr"] == "ret"
    ]
    assert missing_stop_rows
    assert any(
        "ext4_journal_stop(handle)" in _json(row, "missing_cleanup_candidates")
        for row in missing_stop_rows
    )

    acl_rows = _rows(rows, "ext4_acl_from_disk_like")
    assert any(
        "!value" in row["condition"]
        and "NULL" in row["final_return_expr"]
        and row["error_source_expr"] == "function_parameter"
        for row in acl_rows
    )
    assert any(
        "size < sizeof" in row["condition"]
        and "ERR_PTR(-EINVAL)" in row["final_return_expr"]
        and row["error_source_expr"] == "function_parameter"
        for row in acl_rows
    )
    assert any(
        "a_version" in row["condition"]
        and "ERR_PTR(-EINVAL)" in row["final_return_expr"]
        for row in acl_rows
    )
    assert any(
        "count < 0" in row["condition"]
        and "ext4_acl_count(size)" in row["error_source_expr"]
        and "ERR_PTR(-EINVAL)" in row["final_return_expr"]
        for row in acl_rows
    )
    assert any(
        "count == 0" in row["condition"]
        and "NULL" in row["final_return_expr"]
        for row in acl_rows
    )
    assert any(
        "!acl" in row["condition"]
        and "posix_acl_alloc" in row["error_source_expr"]
        and "ERR_PTR(-ENOMEM)" in row["final_return_expr"]
        for row in acl_rows
    )

    bounds_rows = [
        row
        for row in acl_rows
        if ("value + sizeof" in row["condition"] or "> end" in row["condition"])
        and row["exit_type"] == "goto"
        and row["target_label"] == "fail"
    ]
    assert bounds_rows
    assert any(
        "kfree(acl)" in _json(row, "cleanup_calls")
        and "ERR_PTR(-EINVAL)" in row["final_return_expr"]
        and "kfree(acl)" not in _json(row, "missing_cleanup_candidates")
        for row in bounds_rows
    )

    missing_candidates = [
        row for row in candidates if row["candidate_type"] == "missing_cleanup"
    ]
    assert any(
        row["function"] == "demo_missing_brelse"
        and "brelse(bh)" in _json(row, "missing_cleanup_candidates")
        and row["severity"] == "P2"
        for row in missing_candidates
    )
    assert any(
        row["function"] == "demo_goto_out_missing_brelse"
        and "brelse(bh)" in _json(row, "missing_cleanup_candidates")
        for row in missing_candidates
    )
    assert not any(
        row["function"] == "demo_wrapper_possible"
        and row["candidate_type"] == "missing_cleanup"
        for row in candidates
    )
    assert any(
        row["function"] == "demo_ownership_transfer_hint"
        and "brelse(bh)" in _json(row, "missing_cleanup_candidates")
        for row in missing_candidates
    )
    assert not any(
        row["function"] == "demo_goto_brelse"
        and row["candidate_type"] == "missing_cleanup"
        for row in candidates
    )
    for function in [
        "demo_field_alias_cleanup",
        "demo_array_element_cleanup",
        "demo_kmem_cache_free_second_arg",
        "demo_kobject_put_cleanup",
        "demo_ext4_fc_free_cleanup",
        "demo_null_eq_goto_acquire_failure",
    ]:
        assert not any(
            row["function"] == function
            and row["candidate_type"] in {"missing_cleanup", "partial_cleanup"}
            for row in candidates
        )
    assert not any(
        row["function"] == "demo_nested_if_not_outer_error"
        and row["condition"] == "len > 4"
        and row["final_return_expr"] == "-ENOMEM"
        for row in rows
    )

    swallowed_candidates = [
        row for row in candidates if row["candidate_type"] == "error_swallowed"
    ]
    assert any(
        row["function"] == "demo_error_swallowed"
        and row["final_return_expr"] == "0"
        and row["severity"] == "P1"
        for row in swallowed_candidates
    )

    partial_candidates = [
        row for row in candidates if row["candidate_type"] == "partial_cleanup"
    ]
    assert any(
        row["function"] == "demo_partial_cleanup"
        and "brelse(bh)" in _json(row, "cleanup_calls")
        and "mutex_unlock(lock)" in _json(row, "missing_cleanup_candidates")
        and row["severity"] == "P2"
        for row in partial_candidates
    )
    assert any(
        row["function"] == "demo_partial_cleanup"
        and row["candidate_type"] == "missing_cleanup"
        and "mutex_unlock(lock)" in _json(row, "missing_cleanup_candidates")
        and row["severity"] == "P1"
        for row in candidates
    )
    assert any(
        row["function"] == "demo_missing_mutex_unlock"
        and row["candidate_type"] == "missing_cleanup"
        and "mutex_unlock(lock)" in _json(row, "missing_cleanup_candidates")
        and row["severity"] == "P1"
        for row in candidates
    )

    assert len(llm_tasks) == len(candidates)
    missing_task = next(
        task
        for task in llm_tasks
        if task["function"] == "demo_missing_brelse"
        and task["candidate_type"] == "missing_cleanup"
    )
    assert missing_task["task_id"].startswith("llm_review_")
    assert missing_task["file"] == "fs/ext4/demo_ext4_like.c"
    assert missing_task["severity"] == "P2"
    assert isinstance(missing_task["held_resources"], list)
    assert isinstance(missing_task["cleanup_calls"], list)
    assert "brelse(bh)" in missing_task["missing_cleanup_candidates"]
    assert missing_task["matched_protocols"]
    assert missing_task["protocol_exceptions_to_check"]
    assert missing_task["evidence_level"] == E2_API_PROTOCOL_SUPPORTED
    assert missing_task["evidence_score"] > 0
    assert "wrapper_evidence" in missing_task
    assert "ownership_transfer_hints" in missing_task
    assert "has_exception_hints" in missing_task
    assert "manual_review" in missing_task
    assert "manual_score_adjustment" in missing_task
    assert "score_explanation" in missing_task
    assert "demo_missing_brelse" in missing_task["source_context"]
    assert any(line.startswith(">") for line in missing_task["source_context"].splitlines())
    assert any("该候选应判为 true_candidate" in q for q in missing_task["review_questions"])
    assert any("协议要求的 release action" in q for q in missing_task["review_questions"])
    assert any("wrapper 是否真的释放" in q for q in missing_task["review_questions"])

    assert len(ranked) == len(candidates)
    assert len(evidence_rows) == len(candidates)
    assert ranked == sorted(
        ranked,
        key=lambda item: (
            -item["evidence_score"],
            item["file"],
            item["function"],
            item["error_line"],
            item["candidate_type"],
        ),
    )

    ranked_missing_brelse = next(
        item
        for item in ranked
        if item["function"] == "demo_missing_brelse"
        and item["candidate_type"] == "missing_cleanup"
    )
    assert ranked_missing_brelse["evidence_level"] == E2_API_PROTOCOL_SUPPORTED
    assert any(
        evidence["resource_kind"] == "buffer_head"
        and evidence["required_action"] == "brelse"
        and evidence["release_found"] is False
        for evidence in ranked_missing_brelse["protocol_evidence"]
    )
    assert ranked_missing_brelse["has_exception_hints"] is False
    assert ranked_missing_brelse["score_explanation"]

    ranked_transfer = next(
        item
        for item in ranked
        if item["function"] == "demo_ownership_transfer_hint"
        and item["candidate_type"] == "missing_cleanup"
    )
    assert ranked_transfer["evidence_level"] == E2_API_PROTOCOL_SUPPORTED
    assert ranked_transfer["has_exception_hints"] is True
    assert ranked_transfer["ownership_transfer_hints"]
    assert any(
        evidence["ownership_transfer_possible"] is True
        for evidence in ranked_transfer["protocol_evidence"]
    )
    assert any(
        hint["type"] == "ownership_transferred"
        for hint in ranked_transfer["exception_hints"]
    )

    ranked_missing_journal = next(
        item
        for item in ranked
        if item["function"] == "demo_missing_journal_stop"
        and item["candidate_type"] == "missing_cleanup"
    )
    assert ranked_missing_journal["evidence_level"] == E2_API_PROTOCOL_SUPPORTED
    assert any(
        evidence["resource_kind"] == "journal_handle"
        and evidence["required_action"] == "ext4_journal_stop"
        for evidence in ranked_missing_journal["protocol_evidence"]
    )

    ranked_missing_mutex = next(
        item
        for item in ranked
        if item["function"] == "demo_missing_mutex_unlock"
        and item["candidate_type"] == "missing_cleanup"
    )
    assert ranked_missing_mutex["evidence_level"] == E2_API_PROTOCOL_SUPPORTED
    assert any(
        evidence["resource_kind"] == "mutex"
        and evidence["required_action"] == "mutex_unlock"
        for evidence in ranked_missing_mutex["protocol_evidence"]
    )

    ranked_swallowed = next(
        item
        for item in ranked
        if item["function"] == "demo_error_swallowed"
        and item["candidate_type"] == "error_swallowed"
    )
    assert ranked_swallowed["evidence_level"] == E0_STATIC_RULE_ONLY
    assert ranked_swallowed["protocol_evidence"] == []
    assert ranked_swallowed["evidence_score"] >= 50

    summary_brelse = next(
        row
        for row in evidence_rows
        if row["function"] == "demo_missing_brelse"
        and row["candidate_type"] == "missing_cleanup"
    )
    assert summary_brelse["evidence_level"] == E2_API_PROTOCOL_SUPPORTED
    assert "buffer_head" in summary_brelse["matched_protocol_ids"]
    assert "brelse" in summary_brelse["required_actions"]
    for column in [
        "has_exception_hints",
        "exception_hints",
        "released_by_wrapper_possible",
        "ownership_transfer_possible",
        "manual_verdict",
        "manual_confidence",
        "manual_review_source",
        "manual_confirmed_exception",
        "manual_exception_type",
        "manual_score_adjustment",
        "manual_reason",
        "manual_next_action",
        "manual_validation_hint",
        "score_explanation",
    ]:
        assert column in summary_brelse

    transfer_task = next(
        task
        for task in llm_tasks
        if task["function"] == "demo_ownership_transfer_hint"
        and task["candidate_type"] == "missing_cleanup"
    )
    assert transfer_task["ownership_transfer_hints"]


def test_protocol_db_loads_default_protocols():
    db = ResourceProtocolDB.load_from_dir("configs/resource_protocols")

    assert not db.warnings
    assert len(db.protocols) >= 9
    assert db.find_by_resource_kind("buffer_head")
    assert db.find_by_required_action("brelse")
    assert db.find_by_acquire_function("ext4_journal_start")
    assert db.find_by_release_function("mutex_unlock")


def test_wrapper_summary_db_loads_default_summaries():
    db = WrapperSummaryDB.load_from_file("configs/wrapper_summaries.json")

    assert not db.warnings
    assert db.find("brelse")
    assert db.find("put_bh")
    assert db.find("ext4_fc_free")
    assert db.find("kobject_put")
    assert db.releases_resource_kind("put_bh", "buffer_head")
    assert db.release_actions_for("put_bh") == ["brelse"]
    assert db.releases_resource_kind("ext4_fc_free", "memory")
    assert db.release_actions_for("ext4_fc_free") == ["kfree"]
    assert db.releases_resource_kind("kobject_put", "memory")


def test_resource_expression_aliases_keep_indexed_fields_conservative():
    assert same_resource_expr("s->base", "base")
    assert same_resource_expr("bhs[i]", "bhs")
    assert not same_resource_expr("oi->of_binfo[i].ob_bh", "ob_bh")


def test_ownership_transfer_hint_from_struct_assignment(tmp_path):
    linux = tmp_path / "linux"
    source = linux / "fs" / "ext4" / "demo.c"
    source.parent.mkdir(parents=True)
    source.write_text(
        "\n".join(
            [
                "int demo(struct holder *holder) {",
                "  struct buffer_head *bh;",
                "  bh = sb_bread(sb, 1);",
                "  holder->bh = bh;",
                "  if (ret) return ret;",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    row = {
        "file": "fs/ext4/demo.c",
        "error_line": "5",
        "held_resources": json.dumps(
            [
                {
                    "var": "bh",
                    "resource_type": "buffer_head",
                    "release_functions": ["brelse"],
                }
            ]
        ),
    }

    hints = ownership_transfer_hints_for_candidate(row, linux)

    assert hints
    assert any(
        hint["type"] == "ownership_transfer_hint"
        and hint["resource_expr"] == "bh"
        and hint["confidence"] == "low"
        for hint in hints
    )


def test_manual_review_labels_adjust_score_without_deleting_candidate():
    row = {
        "file": "fs/ext4/demo.c",
        "function": "demo_missing_brelse",
        "path_id": "demo_missing_brelse#001",
        "candidate_type": "missing_cleanup",
        "error_line": "42",
        "severity": "P2",
        "condition": "ret",
        "final_return_expr": "ret",
        "evidence": json.dumps(
            {
                "acquired_resources": [
                    {
                        "var": "bh",
                        "acquire_func": "sb_bread",
                        "resource_type": "buffer_head",
                        "release_functions": ["brelse"],
                        "acquire_line": 10,
                    }
                ],
                "missing_releases": ["brelse(bh)"],
                "cleanup_calls": [],
                "final_return_expr": "ret",
            }
        ),
        "held_resources": "[]",
        "missing_cleanup_candidates": "[]",
        "cleanup_calls": "[]",
    }
    protocols = ResourceProtocolDB.load_from_dir("configs/resource_protocols")
    baseline = rank_candidate_rows([row], protocols)[0]
    label = ManualReviewLabel(
        candidate_id=candidate_id_for_row(row),
        verdict="false_positive",
        confidence="high",
        reason="released by wrapper in manual review",
        confirmed_exception=True,
        confirmed_exception_type="released_by_wrapper",
        suggested_rule_update="add wrapper summary",
        next_action="add_wrapper_summary",
        validation_hint="none",
    )
    manual_db = ManualReviewDB(labels={label.candidate_id: label})

    ranked = rank_candidate_rows([row], protocols, manual_reviews=manual_db)

    assert len(ranked) == 1
    assert ranked[0]["candidate_id"] == baseline["candidate_id"]
    assert ranked[0]["evidence_level"] == E2_API_PROTOCOL_SUPPORTED
    assert ranked[0]["manual_review"]["verdict"] == "false_positive"
    assert ranked[0]["manual_review"]["review_source"] == "human_manual_review"
    assert ranked[0]["manual_review"]["next_action"] == "add_wrapper_summary"
    assert ranked[0]["manual_review"]["validation_hint"] == "none"
    assert ranked[0]["manual_score_adjustment"] == -60
    assert ranked[0]["evidence_score"] == baseline["evidence_score"] - 60
    assert any(
        "human_manual_review false_positive high confidence -60" in part
        for part in ranked[0]["score_explanation"]
    )
    assert any(
        "human_manual_review confirmed exception noted: released_by_wrapper" in part
        for part in ranked[0]["score_explanation"]
    )


def test_review_source_controls_score_strength_without_deleting_candidate():
    row = {
        "file": "fs/ext4/demo.c",
        "function": "demo_missing_brelse",
        "path_id": "demo_missing_brelse#001",
        "candidate_type": "missing_cleanup",
        "error_line": "42",
        "severity": "P2",
        "condition": "ret",
        "final_return_expr": "ret",
        "evidence": json.dumps(
            {
                "acquired_resources": [
                    {
                        "var": "bh",
                        "acquire_func": "sb_bread",
                        "resource_type": "buffer_head",
                        "release_functions": ["brelse"],
                        "acquire_line": 10,
                    }
                ],
                "missing_releases": ["brelse(bh)"],
                "cleanup_calls": [],
                "final_return_expr": "ret",
            }
        ),
        "held_resources": "[]",
        "missing_cleanup_candidates": "[]",
        "cleanup_calls": "[]",
    }
    protocols = ResourceProtocolDB.load_from_dir("configs/resource_protocols")
    baseline = rank_candidate_rows([row], protocols)[0]

    codex_label = ManualReviewLabel(
        candidate_id=candidate_id_for_row(row),
        verdict="false_positive",
        confidence="high",
        reviewer="codex_static_review",
    )
    codex_ranked = rank_candidate_rows(
        [row],
        protocols,
        manual_reviews=ManualReviewDB(labels={codex_label.candidate_id: codex_label}),
    )[0]

    assert codex_ranked["candidate_id"] == baseline["candidate_id"]
    assert codex_ranked["manual_review"]["review_source"] == "codex_static_review"
    assert codex_ranked["manual_score_adjustment"] == -30
    assert codex_ranked["evidence_score"] == baseline["evidence_score"] - 30
    assert any(
        "codex_static_review false_positive high confidence -30" in part
        for part in codex_ranked["score_explanation"]
    )

    upstream_label = ManualReviewLabel(
        candidate_id=candidate_id_for_row(row),
        verdict="fixed",
        confidence="low",
        review_source="upstream_confirmed",
        reviewer="stable_patch",
    )
    upstream_ranked = rank_candidate_rows(
        [row],
        protocols,
        manual_reviews=ManualReviewDB(
            labels={upstream_label.candidate_id: upstream_label}
        ),
    )[0]

    assert upstream_ranked["manual_review"]["verdict"] == "true_candidate"
    assert upstream_ranked["manual_review"]["review_source"] == "upstream_confirmed"
    assert upstream_ranked["manual_score_adjustment"] == 100
    assert upstream_ranked["evidence_score"] == baseline["evidence_score"] + 100


def test_manual_review_loader_ignores_todo_placeholder_labels(tmp_path):
    labels = tmp_path / "manual_review_labels_todo.jsonl"
    labels.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "_comment": (
                            "Fill these TODO labels, then copy reviewed JSON objects "
                            "to outputs/ext4/manual_review_labels.jsonl."
                        )
                    }
                ),
                json.dumps(
                    {
                        "candidate_id": "candidate_todo",
                        "verdict": "true_candidate | false_positive | uncertain",
                        "confidence": "high | medium | low",
                        "reason": "",
                        "confirmed_exception": False,
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    db = ManualReviewDB.load_from_file(labels)

    assert db.labels == {}
    assert any("unsupported verdict" in warning for warning in db.warnings)


def test_extract_deepseek_true_candidates(tmp_path):
    reviews = tmp_path / "deepseek_reviews.jsonl"
    true_out = tmp_path / "deepseek_true_candidates.jsonl"

    def review_record(task_id: str, verdict: str) -> dict:
        return {
            "ok": True,
            "task_id": task_id,
            "task_index": 7,
            "file": "fs/ext4/demo.c",
            "function": "demo",
            "candidate_type": "error_swallowed",
            "severity": "P1",
            "model": "deepseek-test",
            "response": {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "verdict": verdict,
                                    "confidence": "high",
                                    "evidence_lines": [12],
                                    "explanation": "evidence",
                                    "suggested_next_step": "inspect",
                                }
                            )
                        }
                    }
                ]
            },
        }

    rows = [
        review_record("true-one", "true_candidate"),
        review_record("false-one", "false_positive"),
        {"ok": False, "task_id": "failed-one", "error": "timeout"},
    ]
    with reviews.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")

    stats = extract_deepseek_true_candidates(reviews, true_out)
    extracted = _read_jsonl(true_out)

    assert stats["deepseek_reviews_in"] == 3
    assert stats["deepseek_review_ok"] == 2
    assert stats["deepseek_review_failed"] == 1
    assert stats["deepseek_true_candidates"] == 1
    assert stats["deepseek_false_positive"] == 1
    assert extracted == [
        {
            "source_line": 1,
            "task_index": 7,
            "task_id": "true-one",
            "file": "fs/ext4/demo.c",
            "function": "demo",
            "candidate_type": "error_swallowed",
            "severity": "P1",
            "model": "deepseek-test",
            "verdict": "true_candidate",
            "confidence": "high",
            "evidence_lines": [12],
            "explanation": "evidence",
            "suggested_next_step": "inspect",
        }
    ]


def test_xfs_config_loads_protocols_and_wrappers():
    resource_map = load_resource_map("configs/xfs_resource_map.json")
    protocols = ResourceProtocolDB.load_from_dir("configs/xfs_resource_protocols")
    wrappers = WrapperSummaryDB.load_from_file("configs/xfs_wrapper_summaries.json")

    assert "xfs_trans_alloc" in resource_map["acquire_functions"]
    assert not protocols.warnings
    assert protocols.find_by_resource_kind("xfs_transaction")
    assert protocols.find_by_required_action("xfs_trans_cancel")
    assert protocols.find_by_acquire_function("xfs_trans_get_buf")
    assert protocols.find_by_release_function("xfs_qm_dqrele")
    assert not wrappers.warnings
    assert wrappers.releases_resource_kind("xfs_trans_brelse", "xfs_trans_buf")
    assert wrappers.releases_resource_kind("xfs_irele", "xfs_inode_ref")


def test_xfs_out_parameter_acquire_and_second_arg_release_tracking():
    tracker = ResourceTracker(load_resource_map("configs/xfs_resource_map.json"))
    statements = [
        Statement("error = xfs_trans_alloc(mp, resv, 0, 0, 0, &tp);", 10),
        Statement("error = xfs_trans_get_buf(tp, target, blkno, len, 0, &bp);", 11),
        Statement("xfs_trans_brelse(tp, bp);", 12),
    ]
    condition = classify_condition("other_error")

    held = tracker.held_before(
        statements,
        error_line=20,
        condition=condition,
        error_source_expr="some_other_call()",
        function_name="demo_xfs",
    )

    assert [resource.var for resource in held] == ["tp"]
    assert held[0].release_suggestion == "xfs_trans_cancel(tp)"


def test_xfs_out_parameter_acquire_failure_is_not_reported_as_held():
    tracker = ResourceTracker(load_resource_map("configs/xfs_resource_map.json"))
    statements = [
        Statement("error = xfs_trans_alloc(mp, resv, 0, 0, 0, &tp);", 10),
    ]
    condition = classify_condition("error")

    held = tracker.held_before(
        statements,
        error_line=11,
        condition=condition,
        error_source_expr="xfs_trans_alloc(mp, resv, 0, 0, 0, &tp)",
        function_name="demo_xfs",
    )

    assert held == []


def test_release_arg_index_matches_xfs_trans_brelse_second_arg():
    resource = {
        "var": "bp",
        "resource_type": "xfs_trans_buf",
        "release_functions": ["xfs_trans_brelse", "xfs_buf_relse"],
        "release_arg_index": 1,
    }

    assert cleanup_call_releases_resource("xfs_trans_brelse(tp, bp)", resource)
    assert cleanup_call_releases_resource("xfs_buf_relse(bp)", resource)
    assert not cleanup_call_releases_resource("xfs_trans_brelse(tp, other_bp)", resource)
