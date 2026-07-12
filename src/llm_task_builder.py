"""Build LLM review task JSONL files from suspicious candidates.

This module only prepares structured inputs by default. The optional DeepSeek
helper is deliberately opt-in and reads its API key from an environment
variable; secrets should not be stored in this repository.
"""

from __future__ import annotations

import csv
import hashlib
import http.client
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .evidence_ranker import load_ranked_candidates_index


REVIEW_QUESTIONS = [
    "资源是否真的在错误路径前成功获取？",
    "错误路径是否真的退出函数？",
    "cleanup label 是否已经释放对应资源？",
    "是否存在资源所有权转移给子函数？",
    "是否存在封装函数隐含释放？",
    "该候选应判为 true_candidate、false_positive 还是 uncertain？请给出代码行证据。",
]
PROTOCOL_REVIEW_QUESTIONS = [
    "协议证据中的资源获取在该错误路径前是否确定成功？",
    "协议要求的 release action 是否已经在所有退出路径上执行？",
    "资源是否由当前模型未覆盖的 cleanup wrapper 释放？",
    "资源所有权是否转移给其他函数或持久结构？",
    "这条静态协议义务是否因路径语义不适用？",
    "如果候选为真，应补充哪一个具体缺失动作？",
    "最合适的运行时验证方式是什么：ENOSPC、EIO、ENOMEM、quota failure 还是 journal failure？",
    "列出的 wrapper 是否真的释放了 required resource？",
    "ownership transfer hint 是真实转移还是保守静态猜测？",
    "如果 ownership 已转移，谁负责后续 cleanup？",
    "如果 wrapper cleanup 存在，它在这条错误路径上是否可达？",
    "该候选是否应因协议 exception 成立而降级？",
    "还需要补充什么静态 summary 才能精确判断？",
    "如果已有 review feedback label，它的证据来源和结论是否仍然成立？",
    "review feedback 结论是否应沉淀为 wrapper summary、ownership pattern 或 scoring 调整？",
]

DEFAULT_DEEPSEEK_ENDPOINT = "https://api.deepseek.com/chat/completions"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"
DEFAULT_DEEPSEEK_REASONING_EFFORT = "max"
DEFAULT_DEEPSEEK_THINKING = {"type": "enabled"}
TRANSIENT_DEEPSEEK_ERRORS = (
    urllib.error.URLError,
    TimeoutError,
    socket.timeout,
    http.client.HTTPException,
    http.client.IncompleteRead,
    json.JSONDecodeError,
    OSError,
)


def _json_list(value: str) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _int_or_zero(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _task_id(row: dict[str, str]) -> str:
    raw = "|".join(
        [
            row.get("file", ""),
            row.get("function", ""),
            row.get("path_id", ""),
            row.get("candidate_type", ""),
            row.get("error_line", ""),
        ]
    )
    digest = hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"llm_review_{digest}"


def _source_path(linux_path: Path, file_value: str) -> Path:
    source = Path(file_value)
    if source.is_absolute():
        return source
    return linux_path / source


def source_context(
    linux_path: str | Path, file_value: str, error_line: int, context_lines: int
) -> str:
    source = _source_path(Path(linux_path), file_value)
    try:
        lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "<source unavailable>"

    if error_line <= 0:
        start_line = 1
        end_line = min(len(lines), max(1, context_lines * 2 + 1))
    else:
        start_line = max(1, error_line - context_lines)
        end_line = min(len(lines), error_line + context_lines)

    width = max(len(str(end_line)), 4)
    rendered: list[str] = []
    for line_no in range(start_line, end_line + 1):
        marker = ">" if line_no == error_line else " "
        rendered.append(f"{marker}{line_no:>{width}}: {lines[line_no - 1]}")
    return "\n".join(rendered)


def task_from_candidate(
    row: dict[str, str],
    linux_path: str | Path,
    context_lines: int,
    ranked_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error_line = _int_or_zero(row.get("error_line", ""))
    protocol_evidence = (
        ranked_evidence.get("protocol_evidence", []) if ranked_evidence else []
    )
    wrapper_evidence = (
        ranked_evidence.get("wrapper_evidence", []) if ranked_evidence else []
    )
    ownership_transfer_hints = (
        ranked_evidence.get("ownership_transfer_hints", []) if ranked_evidence else []
    )
    exception_hints = (
        ranked_evidence.get("exception_hints", []) if ranked_evidence else []
    )
    manual_review = (
        ranked_evidence.get("manual_review", {}) if ranked_evidence else {}
    )
    matched_protocols = [
        evidence.get("protocol_id", "")
        for evidence in protocol_evidence
        if isinstance(evidence, dict) and evidence.get("protocol_id")
    ]
    exceptions_to_check: list[str] = []
    for evidence in protocol_evidence:
        if not isinstance(evidence, dict):
            continue
        for exception in evidence.get("exceptions_to_check", []):
            if exception not in exceptions_to_check:
                exceptions_to_check.append(str(exception))
    questions = list(REVIEW_QUESTIONS)
    for question in PROTOCOL_REVIEW_QUESTIONS:
        if question not in questions:
            questions.append(question)

    return {
        "task_id": _task_id(row),
        "file": row.get("file", ""),
        "function": row.get("function", ""),
        "candidate_type": row.get("candidate_type", ""),
        "severity": row.get("severity", ""),
        "error_line": error_line,
        "condition": row.get("condition", ""),
        "error_source_expr": row.get("error_source_expr", ""),
        "held_resources": _json_list(row.get("held_resources", "")),
        "cleanup_calls": _json_list(row.get("cleanup_calls", "")),
        "missing_cleanup_candidates": _json_list(
            row.get("missing_cleanup_candidates", "")
        ),
        "final_return_expr": row.get("final_return_expr", ""),
        "source_context": source_context(
            linux_path, row.get("file", ""), error_line, context_lines
        ),
        "static_reason": row.get("reason", ""),
        "matched_protocols": matched_protocols,
        "protocol_exceptions_to_check": exceptions_to_check,
        "wrapper_evidence": wrapper_evidence,
        "ownership_transfer_hints": ownership_transfer_hints,
        "has_exception_hints": ranked_evidence.get("has_exception_hints", False)
        if ranked_evidence
        else False,
        "exception_hints": exception_hints,
        "manual_review": manual_review,
        "manual_score_adjustment": ranked_evidence.get("manual_score_adjustment", 0)
        if ranked_evidence
        else 0,
        "evidence_level": ranked_evidence.get("evidence_level", "")
        if ranked_evidence
        else "",
        "evidence_score": ranked_evidence.get("evidence_score", 0)
        if ranked_evidence
        else 0,
        "score_explanation": ranked_evidence.get("score_explanation", [])
        if ranked_evidence
        else [],
        "protocol_evidence": protocol_evidence,
        "review_questions": questions,
    }


def build_llm_review_tasks(
    linux_path: str | Path,
    candidates_csv: str | Path,
    tasks_out: str | Path,
    context_lines: int = 80,
    ranked_candidates_jsonl: str | Path | None = None,
    min_evidence_score: int | None = None,
) -> dict[str, int]:
    candidates_path = Path(candidates_csv)
    tasks_path = Path(tasks_out)
    tasks_path.parent.mkdir(parents=True, exist_ok=True)
    ranked_index = load_ranked_candidates_index(ranked_candidates_jsonl)

    total_candidates = 0
    total_tasks = 0
    filtered_by_score = 0
    unavailable_contexts = 0
    tasks_with_protocols = 0
    with candidates_path.open(newline="", encoding="utf-8") as input_fh, tasks_path.open(
        "w", encoding="utf-8"
    ) as output_fh:
        for row in csv.DictReader(input_fh):
            total_candidates += 1
            ranked_evidence = ranked_index.get(_task_id(row))
            if min_evidence_score is not None:
                score = _int_or_zero(
                    ranked_evidence.get("evidence_score") if ranked_evidence else None
                )
                if score < min_evidence_score:
                    filtered_by_score += 1
                    continue
            task = task_from_candidate(
                row, linux_path, context_lines, ranked_evidence=ranked_evidence
            )
            if task["source_context"] == "<source unavailable>":
                unavailable_contexts += 1
            if task["matched_protocols"]:
                tasks_with_protocols += 1
            output_fh.write(json.dumps(task, ensure_ascii=False) + "\n")
            total_tasks += 1

    return {
        "total_candidates_in": total_candidates,
        "llm_review_tasks": total_tasks,
        "evidence_score_filtered_count": filtered_by_score,
        "source_unavailable_count": unavailable_contexts,
        "llm_tasks_with_protocol_evidence": tasks_with_protocols,
    }


def _deepseek_prompt(task: dict[str, Any]) -> str:
    file_value = str(task.get("file", ""))
    path_parts = Path(file_value).parts
    filesystem = path_parts[1] if len(path_parts) >= 2 and path_parts[0] == "fs" else "filesystem"
    return (
        f"请精检下面的 Linux {filesystem} 静态分析候选。"
        "请独立根据代码证据判断，不要预设它是否为 confirmed bug。\n\n"
        f"task_id: {task.get('task_id')}\n"
        f"file: {task.get('file')}\n"
        f"function: {task.get('function')}\n"
        f"candidate_type: {task.get('candidate_type')}\n"
        f"severity: {task.get('severity')}\n"
        f"error_line: {task.get('error_line')}\n"
        f"condition: {task.get('condition')}\n"
        f"error_source_expr: {task.get('error_source_expr')}\n"
        f"held_resources: {json.dumps(task.get('held_resources', []), ensure_ascii=False)}\n"
        f"cleanup_calls: {json.dumps(task.get('cleanup_calls', []), ensure_ascii=False)}\n"
        "missing_cleanup_candidates: "
        f"{json.dumps(task.get('missing_cleanup_candidates', []), ensure_ascii=False)}\n"
        f"final_return_expr: {task.get('final_return_expr')}\n"
        f"matched_protocols: {json.dumps(task.get('matched_protocols', []), ensure_ascii=False)}\n"
        "protocol_exceptions_to_check: "
        f"{json.dumps(task.get('protocol_exceptions_to_check', []), ensure_ascii=False)}\n"
        f"wrapper_evidence: {json.dumps(task.get('wrapper_evidence', []), ensure_ascii=False)}\n"
        "ownership_transfer_hints: "
        f"{json.dumps(task.get('ownership_transfer_hints', []), ensure_ascii=False)}\n"
        f"has_exception_hints: {task.get('has_exception_hints')}\n"
        f"exception_hints: {json.dumps(task.get('exception_hints', []), ensure_ascii=False)}\n"
        f"manual_review: {json.dumps(task.get('manual_review', {}), ensure_ascii=False)}\n"
        f"manual_score_adjustment: {task.get('manual_score_adjustment')}\n"
        f"evidence_level: {task.get('evidence_level')}\n"
        f"evidence_score: {task.get('evidence_score')}\n"
        f"score_explanation: {json.dumps(task.get('score_explanation', []), ensure_ascii=False)}\n"
        f"static_reason: {task.get('static_reason')}\n\n"
        "源码上下文：\n"
        f"{task.get('source_context')}\n\n"
        "请返回 JSON 对象，字段包括 verdict(true_candidate|false_positive|uncertain), "
        "confidence(high|medium|low), evidence_lines, explanation, suggested_next_step。"
    )


def _validate_deepseek_api_key(api_key: str, api_key_env: str) -> None:
    if api_key.strip() != api_key:
        raise RuntimeError(f"{api_key_env} contains leading/trailing whitespace.")
    try:
        api_key.encode("ascii")
    except UnicodeEncodeError as exc:
        raise RuntimeError(
            f"{api_key_env} must be an ASCII API key, not a placeholder such as 你的key."
        ) from exc
    if not api_key.startswith("sk-"):
        raise RuntimeError(f"{api_key_env} does not look like a DeepSeek API key.")


def _deepseek_request(
    task: dict[str, Any],
    api_key: str,
    model: str,
    reasoning_effort: str,
    endpoint: str,
    timeout: int,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a careful Linux kernel static-analysis reviewer. Return JSON only.",
            },
            {"role": "user", "content": _deepseek_prompt(task)},
        ],
        "stream": False,
        "reasoning_effort": reasoning_effort,
        "thinking": DEFAULT_DEEPSEEK_THINKING,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
    return json.loads(body)


def run_deepseek_review(
    tasks_in: str | Path,
    reviews_out: str | Path,
    api_key_env: str = "DEEPSEEK_API_KEY",
    model: str = DEFAULT_DEEPSEEK_MODEL,
    reasoning_effort: str = DEFAULT_DEEPSEEK_REASONING_EFFORT,
    endpoint: str = DEFAULT_DEEPSEEK_ENDPOINT,
    limit: int | None = None,
    start_index: int = 1,
    timeout: int = 60,
    sleep_seconds: float = 0.0,
    retries: int = 2,
    retry_sleep_seconds: float = 3.0,
    progress: bool = True,
) -> dict[str, int]:
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise RuntimeError(
            f"{api_key_env} is not set; export it in your shell instead of storing keys in source."
        )
    _validate_deepseek_api_key(api_key, api_key_env)

    tasks_path = Path(tasks_in)
    reviews_path = Path(reviews_out)
    reviews_path.parent.mkdir(parents=True, exist_ok=True)
    start_index = max(1, start_index)

    attempted = 0
    succeeded = 0
    failed = 0
    seen_tasks = 0
    with tasks_path.open(encoding="utf-8") as input_fh, reviews_path.open(
        "a" if start_index > 1 else "w", encoding="utf-8"
    ) as output_fh:
        for line in input_fh:
            seen_tasks += 1
            if seen_tasks < start_index:
                continue
            if limit is not None and attempted >= limit:
                break
            if not line.strip():
                continue
            task = json.loads(line)
            attempted += 1
            task_index = seen_tasks
            if progress:
                print(
                    "deepseek_progress="
                    f"{attempted}"
                    + (f"/{limit}" if limit is not None else "")
                    + f" task_index={task_index} task_id={task.get('task_id')} "
                    f"candidate_type={task.get('candidate_type')} "
                    f"function={task.get('function')}",
                    file=sys.stderr,
                    flush=True,
                )
            record: dict[str, Any] = {
                "task_id": task.get("task_id"),
                "file": task.get("file"),
                "function": task.get("function"),
                "candidate_type": task.get("candidate_type"),
                "severity": task.get("severity"),
                "model": model,
                "task_index": task_index,
            }
            last_error: BaseException | None = None
            for attempt_no in range(1, retries + 2):
                try:
                    response = _deepseek_request(
                        task, api_key, model, reasoning_effort, endpoint, timeout
                    )
                    record["ok"] = True
                    record["response"] = response
                    record["thinking"] = DEFAULT_DEEPSEEK_THINKING
                    record["reasoning_effort"] = reasoning_effort
                    record["attempts"] = attempt_no
                    succeeded += 1
                    break
                except TRANSIENT_DEEPSEEK_ERRORS as exc:
                    last_error = exc
                    if attempt_no <= retries:
                        if progress:
                            print(
                                f"deepseek_progress={attempted} retry={attempt_no}/{retries} "
                                f"error={type(exc).__name__}: {exc}",
                                file=sys.stderr,
                                flush=True,
                            )
                        if retry_sleep_seconds > 0:
                            time.sleep(retry_sleep_seconds)
                        continue
                    record["ok"] = False
                    record["error"] = f"{type(exc).__name__}: {exc}"
                    record["attempts"] = attempt_no
                    failed += 1
                except Exception as exc:
                    last_error = exc
                    record["ok"] = False
                    record["error"] = f"{type(exc).__name__}: {exc}"
                    record["attempts"] = attempt_no
                    failed += 1
                    break
            if "ok" not in record:
                record["ok"] = False
                record["error"] = str(last_error or "unknown DeepSeek failure")
                failed += 1
            output_fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            output_fh.flush()
            if progress:
                status = "ok" if record["ok"] else "failed"
                print(
                    f"deepseek_progress={attempted} status={status} "
                    f"succeeded={succeeded} failed={failed}",
                    file=sys.stderr,
                    flush=True,
                )
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

    return {
        "deepseek_review_attempted": attempted,
        "deepseek_review_succeeded": succeeded,
        "deepseek_review_failed": failed,
    }


def _deepseek_message_content(record: dict[str, Any]) -> str:
    return record["response"]["choices"][0]["message"]["content"]


def _true_candidate_record(
    source_line: int, record: dict[str, Any], review: dict[str, Any]
) -> dict[str, Any]:
    return {
        "source_line": source_line,
        "task_index": record.get("task_index"),
        "task_id": record.get("task_id"),
        "file": record.get("file"),
        "function": record.get("function"),
        "candidate_type": record.get("candidate_type"),
        "severity": record.get("severity"),
        "model": record.get("model"),
        "verdict": review.get("verdict"),
        "confidence": review.get("confidence"),
        "evidence_lines": review.get("evidence_lines"),
        "explanation": review.get("explanation"),
        "suggested_next_step": review.get("suggested_next_step"),
    }


def extract_deepseek_true_candidates(
    reviews_in: str | Path,
    true_candidates_out: str | Path,
) -> dict[str, int]:
    """Write DeepSeek records whose parsed verdict is true_candidate."""

    reviews_path = Path(reviews_in)
    output_path = Path(true_candidates_out)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    ok = 0
    failed = 0
    parse_failed = 0
    true_candidates = 0
    false_positive = 0
    uncertain = 0
    other_verdict = 0

    with reviews_path.open(encoding="utf-8") as input_fh, output_path.open(
        "w", encoding="utf-8"
    ) as output_fh:
        for source_line, line in enumerate(input_fh, 1):
            if not line.strip():
                continue
            total += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                parse_failed += 1
                continue

            if not record.get("ok"):
                failed += 1
                continue
            ok += 1

            try:
                review = json.loads(_deepseek_message_content(record))
            except (KeyError, IndexError, TypeError, json.JSONDecodeError):
                parse_failed += 1
                continue

            verdict = review.get("verdict")
            if verdict == "true_candidate":
                output_fh.write(
                    json.dumps(
                        _true_candidate_record(source_line, record, review),
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                true_candidates += 1
            elif verdict == "false_positive":
                false_positive += 1
            elif verdict == "uncertain":
                uncertain += 1
            else:
                other_verdict += 1

    return {
        "deepseek_reviews_in": total,
        "deepseek_review_ok": ok,
        "deepseek_review_failed": failed,
        "deepseek_review_parse_failed": parse_failed,
        "deepseek_true_candidates": true_candidates,
        "deepseek_false_positive": false_positive,
        "deepseek_uncertain": uncertain,
        "deepseek_other_verdict": other_verdict,
    }
