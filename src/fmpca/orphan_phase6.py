from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .c_cfg import FunctionCFG
from .c_cfg_extensions import build_phase5_function_cfg
from .dsl import load_protocol
from .model import AnalysisResult, EvidenceEvent
from .orphan_allpath import SourceLocation
from .orphan_ext4_contracts import UNSAFE, analyze_ext4_contracts
from .proof import analyze_state
from .report import count_bug_specific_conditions, write_json, write_markdown
from .semantics_extensions import ProtocolDeadlineEngine


CLOSED = "CLOSED"
BLOCKED = "BLOCKED"
BOUNDARY = "VALID_CONFIGURATION_BOUNDARY"


@dataclass(frozen=True)
class FailstopRecoveryProof:
    status: str
    conclusion: str
    evidence: Tuple[SourceLocation, ...] = ()
    blockers: Tuple[str, ...] = ()

    @property
    def closed(self) -> bool:
        return self.status == CLOSED and not self.blockers


@dataclass(frozen=True)
class TransactionCommitWitness:
    status: str
    metadata_filed_on_transaction: bool
    commit_reads_metadata_list: bool
    discard_requires_journal_abort: bool
    handle_abort_is_not_journal_abort: bool
    handle_abort_does_not_prevent_commit: bool
    evidence: Tuple[SourceLocation, ...] = ()
    blockers: Tuple[str, ...] = ()

    @property
    def closed(self) -> bool:
        return self.status == CLOSED and not self.blockers


@dataclass(frozen=True)
class ErrorsContinueWitness:
    stage: str
    configuration: str
    source_witness_closed: bool
    negative_outcome: str
    fixture: str
    result: str
    expected_rule: str
    violation_rules: Tuple[str, ...]
    evidence: Tuple[SourceLocation, ...] = ()
    blockers: Tuple[str, ...] = ()

    @property
    def closed(self) -> bool:
        return (
            self.source_witness_closed
            and self.result == AnalysisResult.VIOLATION.value
            and self.expected_rule in self.violation_rules
            and not self.blockers
        )


@dataclass(frozen=True)
class Phase6Assessment:
    failstop_recovery: FailstopRecoveryProof
    transaction_commit: TransactionCommitWitness
    errors_continue: Tuple[ErrorsContinueWitness, ...]
    configuration_scope_decision: str

    @property
    def failstop_profile_closed(self) -> bool:
        return self.failstop_recovery.closed

    @property
    def errors_continue_negative_witness_closed(self) -> bool:
        return all(witness.closed for witness in self.errors_continue)

    @property
    def universal_all_path_closed(self) -> bool:
        return False

    @property
    def blockers(self) -> Tuple[str, ...]:
        values: List[str] = []
        for blocker in self.failstop_recovery.blockers:
            if blocker not in values:
                values.append(blocker)
        for blocker in self.transaction_commit.blockers:
            if blocker not in values:
                values.append(blocker)
        for witness in self.errors_continue:
            for blocker in witness.blockers:
                if blocker not in values:
                    values.append(blocker)
        return tuple(values)

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["failstop_recovery"]["closed"] = self.failstop_recovery.closed
        value["transaction_commit"]["closed"] = self.transaction_commit.closed
        for item, witness in zip(value["errors_continue"], self.errors_continue):
            item["closed"] = witness.closed
        value["failstop_profile_closed"] = self.failstop_profile_closed
        value["errors_continue_negative_witness_closed"] = (
            self.errors_continue_negative_witness_closed
        )
        value["universal_all_path_closed"] = self.universal_all_path_closed
        value["blockers"] = list(self.blockers)
        return value


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _verify_artifacts(values: Dict[str, str]) -> Dict[str, bool]:
    if not values:
        raise ValueError("Phase 6 artifact hash lock must not be empty")
    result: Dict[str, bool] = {}
    for path, expected in values.items():
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(
                f"Phase 6 artifact hash mismatch for {path}: {actual} != {expected}"
            )
        result[path] = True
    return result


def _health(cfgs: Iterable[FunctionCFG]) -> Tuple[str, ...]:
    blockers: List[str] = []
    for cfg in cfgs:
        if cfg.parse_has_error:
            blockers.append(f"CFG_PARSE_ERROR:{cfg.function_name}")
        if cfg.unresolved_gotos:
            blockers.append(f"CFG_UNRESOLVED_GOTO:{cfg.function_name}")
    return tuple(blockers)


def _call(cfg: FunctionCFG, name: str, *, last: bool = False) -> Optional[int]:
    nodes = cfg.find_calls([name])
    if not nodes:
        return None
    key = lambda node: cfg.nodes[node].line
    return max(nodes, key=key) if last else min(nodes, key=key)


def _text(cfg: FunctionCFG, marker: str, *, last: bool = False) -> Optional[int]:
    nodes = cfg.find_text([marker])
    if not nodes:
        return None
    key = lambda node: cfg.nodes[node].line
    return max(nodes, key=key) if last else min(nodes, key=key)


def _loc(
    cfg: FunctionCFG, node: Optional[int], fact: str
) -> Tuple[SourceLocation, ...]:
    if node is None:
        return ()
    item = cfg.nodes[node]
    return (SourceLocation(cfg.source_path, cfg.function_name, item.line, node, fact),)


def _missing(values: Iterable[Tuple[str, Optional[int]]]) -> Tuple[str, ...]:
    return tuple(f"MISSING_PHASE6_EVIDENCE:{name}" for name, node in values if node is None)


def _run_fixture(protocol_path: str, fixture_path: str) -> Dict[str, Any]:
    spec = load_protocol(protocol_path)
    fixture = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    closure = fixture["closure"]
    state = ProtocolDeadlineEngine(spec).run(
        EvidenceEvent.from_dict(item) for item in fixture["events"]
    )
    report = analyze_state(
        state,
        path_model_closed=closure["path_model_closed"],
        all_paths_closed=closure["all_paths_closed"],
        repair_slice_closed=closure["repair_slice_closed"],
        alias_closed=closure["alias_closed"],
    )
    return {
        "result": report.result.value,
        "violation_rules": tuple(report.violation_rules),
        "unknown_rules": tuple(report.unknown_rules),
        "coverage": report.coverage,
    }


def analyze_failstop_recovery(source: str) -> FailstopRecoveryProof:
    handle_error = build_phase5_function_cfg(
        f"{source}/fs/ext4/super.c", "ext4_handle_error"
    )
    flush = build_phase5_function_cfg(
        f"{source}/fs/jbd2/journal.c", "jbd2_journal_flush"
    )
    mark = build_phase5_function_cfg(
        f"{source}/fs/ext4/super.c", "ext4_mark_recovery_complete"
    )
    fill = build_phase5_function_cfg(
        f"{source}/fs/ext4/super.c", "__ext4_fill_super"
    )
    abort = _call(handle_error, "jbd2_journal_abort")
    continue_guard = _text(handle_error, "continue_fs")
    aborted = _text(flush, "is_journal_aborted(journal)")
    eio = _text(flush, "return -EIO;")
    flush_call = _call(mark, "jbd2_journal_flush")
    flush_error = _text(mark, "err < 0")
    mark_return = _text(mark, "return err;")
    marker = _call(fill, "ext4_mark_recovery_complete")
    failure_goto = _text(fill, "goto failed_mount9;")
    failure_label = fill.labels.get("failed_mount9")
    mount_error = _text(fill, "return err;")
    nodes = (
        ("ext4_journal_abort", abort),
        ("ERRORS_CONT_guard", continue_guard),
        ("flush_aborted_guard", aborted),
        ("flush_EIO_return", eio),
        ("mark_recovery_flush", flush_call),
        ("mark_recovery_error_guard", flush_error),
        ("mark_recovery_error_return", mark_return),
        ("fill_super_recovery_marker", marker),
        ("fill_super_failure_goto", failure_goto),
        ("fill_super_failure_label", failure_label),
        ("fill_super_error_return", mount_error),
    )
    blockers = _health((handle_error, flush, mark, fill)) + _missing(nodes)
    flow_closed = (
        not blockers
        and flush.dominates(aborted, eio)
        and mark.can_reach(flush_call, flush_error)
        and mark.can_reach(flush_error, mark_return)
        and fill.dominates(marker, failure_goto)
        and fill.can_reach(failure_goto, failure_label)
        and fill.can_reach(failure_label, mount_error)
    )
    if not flow_closed and not blockers:
        blockers = ("EXT4_FAILSTOP_RECOVERY_PROPAGATION_NOT_CLOSED",)
    evidence = (
        _loc(handle_error, abort, "non-continuing writable error aborts journal")
        + _loc(handle_error, continue_guard, "ERRORS_CONT is a separate guard")
        + _loc(flush, aborted, "flush tests journal-level abort")
        + _loc(flush, eio, "aborted journal flush returns -EIO")
        + _loc(mark, flush_call, "recovery completion flushes journal")
        + _loc(mark, flush_error, "negative flush result takes error exit")
        + _loc(mark, mark_return, "recovery completion propagates error")
        + _loc(fill, marker, "mount calls recovery completion marker")
        + _loc(fill, failure_goto, "marker error selects failed_mount9")
        + _loc(fill, failure_label, "mount failure cleanup label")
        + _loc(fill, mount_error, "mount returns propagated error")
    )
    return FailstopRecoveryProof(
        CLOSED if flow_closed else BLOCKED,
        "journal abort forces flush -EIO through recovery completion into mount failure",
        evidence,
        blockers,
    )


def analyze_transaction_commit(source: str) -> TransactionCommitWitness:
    dirty = build_phase5_function_cfg(
        f"{source}/fs/jbd2/transaction.c", "jbd2_journal_dirty_metadata"
    )
    file_buffer = build_phase5_function_cfg(
        f"{source}/fs/jbd2/transaction.c", "__jbd2_journal_file_buffer"
    )
    commit = build_phase5_function_cfg(
        f"{source}/fs/jbd2/commit.c", "jbd2_journal_commit_transaction"
    )
    abort_handle = build_phase5_function_cfg(
        f"{source}/include/linux/jbd2.h", "jbd2_journal_abort_handle"
    )
    stop = build_phase5_function_cfg(
        f"{source}/fs/jbd2/transaction.c", "jbd2_journal_stop"
    )
    file_call = _call(dirty, "__jbd2_journal_file_buffer")
    metadata = _text(dirty, "BJ_Metadata")
    transaction_list = _text(file_buffer, "list = &transaction->t_buffers")
    list_add = _call(file_buffer, "__blist_add_buffer")
    commit_loop = _text(commit, "commit_transaction->t_buffers")
    journal_abort_guard = _text(commit, "is_journal_aborted(journal)")
    abort_discard = _call(commit, "clear_buffer_jbddirty")
    commit_record = _call(commit, "journal_submit_commit_record")
    handle_assignment = _text(abort_handle, "handle->h_aborted = 1")
    stop_handle_guard = _text(stop, "is_handle_aborted(handle)")
    stop_journal_abort = _call(stop, "jbd2_journal_abort")
    commit_handle_guard = _text(commit, "is_handle_aborted")
    nodes = (
        ("dirty_metadata_file_call", file_call),
        ("dirty_metadata_BJ_Metadata", metadata),
        ("transaction_t_buffers", transaction_list),
        ("transaction_list_add", list_add),
        ("commit_t_buffers_loop", commit_loop),
        ("commit_journal_abort_guard", journal_abort_guard),
        ("commit_abort_discard", abort_discard),
        ("commit_record", commit_record),
        ("handle_abort_assignment", handle_assignment),
        ("stop_handle_abort_guard", stop_handle_guard),
    )
    blockers = _health((dirty, file_buffer, commit, abort_handle, stop)) + _missing(nodes)
    metadata_filed = (
        file_call is not None
        and metadata is not None
        and transaction_list is not None
        and list_add is not None
    )
    commit_reads = commit_loop is not None and commit_record is not None
    journal_guarded = (
        journal_abort_guard is not None
        and abort_discard is not None
        and commit.dominates(journal_abort_guard, abort_discard)
    )
    handle_local = (
        handle_assignment is not None
        and stop_handle_guard is not None
        and stop_journal_abort is None
    )
    commit_possible = (
        metadata_filed
        and commit_reads
        and journal_guarded
        and handle_local
        and commit_handle_guard is None
    )
    closed = not blockers and commit_possible
    if not closed and not blockers:
        blockers = ("JBD2_HANDLE_LOCAL_ABORT_COMMIT_BOUNDARY_NOT_CLOSED",)
    evidence = (
        _loc(dirty, file_call, "dirty metadata files buffer as BJ_Metadata")
        + _loc(dirty, metadata, "BJ_Metadata transaction list selection")
        + _loc(file_buffer, transaction_list, "metadata maps to transaction t_buffers")
        + _loc(file_buffer, list_add, "buffer is added to selected transaction list")
        + _loc(commit, commit_loop, "commit consumes transaction metadata list")
        + _loc(commit, journal_abort_guard, "discard branch requires journal abort")
        + _loc(commit, abort_discard, "aborted-journal branch discards dirty buffer")
        + _loc(commit, commit_record, "non-aborted transaction writes commit record")
        + _loc(abort_handle, handle_assignment, "handle abort is handle-local state")
        + _loc(stop, stop_handle_guard, "journal stop observes handle-local abort")
    )
    return TransactionCommitWitness(
        CLOSED if closed else BLOCKED,
        metadata_filed,
        commit_reads,
        journal_guarded,
        handle_local,
        commit_possible,
        evidence,
        blockers,
    )


def analyze_errors_continue(
    config: Dict[str, Any], transaction: TransactionCommitWitness
) -> Tuple[ErrorsContinueWitness, ...]:
    source = config["source_root"]
    phase5 = analyze_ext4_contracts({"source_root": source})
    protocol = config["protocol"]

    delete_entry = build_phase5_function_cfg(
        f"{source}/fs/ext4/namei.c", "ext4_delete_entry"
    )
    dirty_dir = build_phase5_function_cfg(
        f"{source}/fs/ext4/namei.c", "ext4_handle_dirty_dirblock"
    )
    orphan_add = build_phase5_function_cfg(
        f"{source}/fs/ext4/orphan.c", "ext4_orphan_add"
    )
    get_inode = build_phase5_function_cfg(
        f"{source}/fs/ext4/inode.c", "__ext4_get_inode_loc"
    )
    registration_nodes = (
        (delete_entry, _call(delete_entry, "ext4_handle_dirty_dirblock"), "directory deletion metadata is dirtied"),
        (dirty_dir, _call(dirty_dir, "ext4_handle_dirty_metadata"), "directory buffer reaches JBD2 dirty metadata"),
        (orphan_add, _call(orphan_add, "ext4_reserve_inode_write"), "orphan registration reserves inode write"),
        (get_inode, _call(get_inode, "sb_getblk", last=True), "inode-location lookup allocates buffer head"),
        (get_inode, _text(get_inode, "return -ENOMEM;"), "buffer-head allocation failure returns -ENOMEM"),
        (orphan_add, _call(orphan_add, "ext4_std_error"), "registration failure enters configured error policy"),
    )
    registration_source = (
        not _health(cfg for cfg, _, _ in registration_nodes)
        and all(node is not None for _, node, _ in registration_nodes)
        and transaction.closed
        and next(item for item in phase5.registration.summaries if item.summary_id == "EXT4-RC-4").status == UNSAFE
    )

    evict = build_phase5_function_cfg(
        f"{source}/fs/ext4/inode.c", "ext4_evict_inode"
    )
    orphan_file_del = build_phase5_function_cfg(
        f"{source}/fs/ext4/orphan.c", "ext4_orphan_file_del"
    )
    settlement_nodes = (
        (orphan_file_del, _call(orphan_file_del, "ext4_handle_dirty_metadata"), "orphan-file removal metadata is dirtied"),
        (evict, _call(evict, "ext4_orphan_del"), "persistent orphan removal precedes terminal settlement"),
        (evict, _call(evict, "ext4_mark_inode_dirty", last=True), "post-removal inode mark-dirty can fail"),
        (evict, _call(evict, "ext4_clear_inode"), "mark-dirty failure selects in-core clear"),
        (evict, _call(evict, "ext4_free_inode"), "inode free exists only on mark-dirty success"),
        (evict, _call(evict, "ext4_journal_stop"), "eviction handle is stopped after branch join"),
    )
    settlement_source = (
        not _health(cfg for cfg, _, _ in settlement_nodes)
        and all(node is not None for _, node, _ in settlement_nodes)
        and transaction.closed
        and next(item for item in phase5.settlement.summaries if item.summary_id == "EXT4-SC-3").status == UNSAFE
    )

    cleanup = build_phase5_function_cfg(
        f"{source}/fs/ext4/orphan.c", "ext4_orphan_cleanup"
    )
    orphan_get = build_phase5_function_cfg(
        f"{source}/fs/ext4/ialloc.c", "ext4_orphan_get"
    )
    fill = build_phase5_function_cfg(
        f"{source}/fs/ext4/super.c", "__ext4_fill_super"
    )
    recovery_nodes = (
        (cleanup, _text(cleanup, "IS_ERR(inode)"), "orphan lookup has an error exit"),
        (orphan_get, _call(orphan_get, "ext4_error_err"), "orphan lookup error enters configured error policy"),
        (fill, _call(fill, "ext4_orphan_cleanup"), "mount invokes void orphan cleanup"),
        (fill, _call(fill, "ext4_mark_recovery_complete"), "recovery completion remains after void cleanup"),
        (fill, _text(fill, "return 0;"), "successful mount return remains reachable"),
    )
    recovery_source = (
        not _health(cfg for cfg, _, _ in recovery_nodes)
        and all(node is not None for _, node, _ in recovery_nodes)
        and next(item for item in phase5.recovery.summaries if item.summary_id == "EXT4-CC-4").status == UNSAFE
    )

    source_by_stage = {
        "registration": (registration_source, registration_nodes, "namespace-only transaction commit"),
        "settlement": (settlement_source, settlement_nodes, "orphan-removal-only transaction commit"),
        "recovery": (recovery_source, recovery_nodes, "successful recovery exposure without per-inode settlement"),
    }
    witnesses: List[ErrorsContinueWitness] = []
    for case in config["negative_witnesses"]:
        stage = case["stage"]
        source_closed, nodes_for_stage, outcome = source_by_stage[stage]
        replay = _run_fixture(protocol, case["fixture"])
        blockers: List[str] = []
        if not source_closed:
            blockers.append(f"EXT4_ERRORS_CONT_{stage.upper()}_SOURCE_WITNESS_NOT_CLOSED")
        if replay["result"] != AnalysisResult.VIOLATION.value:
            blockers.append(f"EXT4_ERRORS_CONT_{stage.upper()}_REPLAY_NOT_VIOLATION")
        if case["expected_rule"] not in replay["violation_rules"]:
            blockers.append(f"EXT4_ERRORS_CONT_{stage.upper()}_RULE_NOT_REACHED")
        evidence: Tuple[SourceLocation, ...] = ()
        for cfg, node, fact in nodes_for_stage:
            evidence += _loc(cfg, node, fact)
        witnesses.append(
            ErrorsContinueWitness(
                stage,
                "ERRORS_CONT",
                source_closed,
                outcome,
                case["fixture"],
                replay["result"],
                case["expected_rule"],
                replay["violation_rules"],
                evidence,
                tuple(blockers),
            )
        )
    return tuple(witnesses)


def analyze_phase6(config: Dict[str, Any]) -> Phase6Assessment:
    failstop = analyze_failstop_recovery(config["source_root"])
    transaction = analyze_transaction_commit(config["source_root"])
    errors_continue = analyze_errors_continue(config, transaction)
    return Phase6Assessment(failstop, transaction, errors_continue, BOUNDARY)


def run_manifest(path: str) -> Dict[str, Any]:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    locks = _verify_artifacts(manifest["artifact_hashes"])
    assessment = analyze_phase6(manifest)
    value = assessment.to_dict()
    failstop_closed = (
        manifest["phase5_failstop_gates"]["registration"]
        and manifest["phase5_failstop_gates"]["settlement"]
        and assessment.failstop_profile_closed
    )
    return {
        "schema_version": 1,
        "evaluation_id": manifest["evaluation_id"],
        "manifest": path,
        "manifest_sha256": _sha256(path),
        "artifact_hashes_verified": all(locks.values()),
        "bug_specific_condition_count": count_bug_specific_conditions([manifest]),
        "assessment": value,
        "failstop_profile_closed": failstop_closed,
        "errors_continue_negative_witness_closed": assessment.errors_continue_negative_witness_closed,
        "configuration_scope_decision": assessment.configuration_scope_decision,
        "universal_all_path_closed": False,
        "common_freeze_manifest_generated": False,
        "interpretation": manifest["interpretation"],
    }


def _markdown(summary: Dict[str, Any]) -> str:
    assessment = summary["assessment"]
    lines = [
        "# OIDS Phase 6 ext4 Configuration Boundary",
        "",
        f"Manifest: `{summary['manifest']}`",
        "",
        f"Failstop profile closed: `{summary['failstop_profile_closed']}`",
        f"ERRORS_CONT negative witnesses closed: `{summary['errors_continue_negative_witness_closed']}`",
        f"Configuration decision: `{summary['configuration_scope_decision']}`",
        f"Universal all-path closure: `{summary['universal_all_path_closed']}`",
        "",
        "## Failstop recovery",
        "",
        assessment["failstop_recovery"]["conclusion"],
        "",
        "## ERRORS_CONT witnesses",
        "",
        "| Stage | Source | Verdict | Required rule | Closed |",
        "|---|---|---|---|---|",
    ]
    for witness in assessment["errors_continue"]:
        lines.append(
            "| {stage} | {source} | `{result}` | `{rule}` | `{closed}` |".format(
                stage=witness["stage"],
                source=witness["source_witness_closed"],
                result=witness["result"],
                rule=witness["expected_rule"],
                closed=witness["closed"],
            )
        )
    lines.extend(["", "## Decision", "", summary["interpretation"], ""])
    return "\n".join(lines)


def run_and_write(manifest: str, json_out: str, markdown_out: str) -> Dict[str, Any]:
    summary = run_manifest(manifest)
    write_json(json_out, summary)
    write_markdown(markdown_out, _markdown(summary))
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.orphan_phase6")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    args = parser.parse_args(argv)
    summary = run_and_write(args.manifest, args.json_out, args.markdown_out)
    print(
        f"failstop_closed={summary['failstop_profile_closed']} "
        f"errors_cont_witnesses={summary['errors_continue_negative_witness_closed']} "
        f"universal_closed={summary['universal_all_path_closed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
