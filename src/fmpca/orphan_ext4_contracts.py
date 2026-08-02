from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .c_cfg import FunctionCFG
from .c_cfg_extensions import build_phase5_function_cfg
from .orphan_allpath import SourceLocation
from .report import count_bug_specific_conditions, write_json, write_markdown


CLOSED = "CLOSED"
BLOCKED = "BLOCKED"
UNSAFE = "UNSAFE"
NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class GuardedSummary:
    summary_id: str
    guard: str
    configuration: str
    outcome: str
    status: str
    evidence: Tuple[SourceLocation, ...] = ()
    assumptions: Tuple[str, ...] = ()
    blockers: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Ext4ContractStage:
    stage: str
    summaries: Tuple[GuardedSummary, ...]

    @property
    def universal_closed(self) -> bool:
        return all(summary.status in {CLOSED, NOT_APPLICABLE} for summary in self.summaries)

    @property
    def failstop_closed(self) -> bool:
        return all(
            summary.status in {CLOSED, NOT_APPLICABLE}
            for summary in self.summaries
            if summary.configuration != "ERRORS_CONT"
        )

    @property
    def blockers(self) -> Tuple[str, ...]:
        values: List[str] = []
        for summary in self.summaries:
            for blocker in summary.blockers:
                if blocker not in values:
                    values.append(blocker)
        return tuple(values)


@dataclass(frozen=True)
class Ext4ContractAssessment:
    registration: Ext4ContractStage
    settlement: Ext4ContractStage
    recovery: Ext4ContractStage
    universal_closed: bool
    failstop_profile_closed: bool

    @property
    def blockers(self) -> Tuple[str, ...]:
        values: List[str] = []
        for stage in (self.registration, self.settlement, self.recovery):
            for blocker in stage.blockers:
                if blocker not in values:
                    values.append(blocker)
        return tuple(values)

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        for name, stage in (
            ("registration", self.registration),
            ("settlement", self.settlement),
            ("recovery", self.recovery),
        ):
            value[name]["universal_closed"] = stage.universal_closed
            value[name]["failstop_closed"] = stage.failstop_closed
            value[name]["blockers"] = list(stage.blockers)
        value["blockers"] = list(self.blockers)
        return value


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _verify_artifacts(values: Dict[str, str]) -> Dict[str, bool]:
    if not values:
        raise ValueError("Phase 5 artifact hash lock must not be empty")
    result: Dict[str, bool] = {}
    for path, expected in values.items():
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(f"Phase 5 artifact hash mismatch for {path}: {actual} != {expected}")
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
    return max(nodes, key=lambda node: cfg.nodes[node].line) if last else min(
        nodes, key=lambda node: cfg.nodes[node].line
    )


def _text(cfg: FunctionCFG, marker: str) -> Optional[int]:
    return next(iter(cfg.find_text([marker])), None)


def _loc(cfg: FunctionCFG, node: Optional[int], fact: str) -> Tuple[SourceLocation, ...]:
    if node is None:
        return ()
    item = cfg.nodes[node]
    return (SourceLocation(cfg.source_path, cfg.function_name, item.line, node, fact),)


def _summary(
    summary_id: str,
    guard: str,
    configuration: str,
    outcome: str,
    status: str,
    evidence: Iterable[SourceLocation] = (),
    assumptions: Iterable[str] = (),
    blockers: Iterable[str] = (),
) -> GuardedSummary:
    return GuardedSummary(
        summary_id,
        guard,
        configuration,
        outcome,
        status,
        tuple(evidence),
        tuple(assumptions),
        tuple(blockers),
    )


def analyze_ext4_contracts(config: Dict[str, Any]) -> Ext4ContractAssessment:
    source = config["source_root"]
    namei = build_phase5_function_cfg(f"{source}/fs/ext4/namei.c", "__ext4_unlink")
    orphan_add = build_phase5_function_cfg(f"{source}/fs/ext4/orphan.c", "ext4_orphan_add")
    orphan_file_add = build_phase5_function_cfg(
        f"{source}/fs/ext4/orphan.c", "ext4_orphan_file_add"
    )
    reserve = build_phase5_function_cfg(
        f"{source}/fs/ext4/inode.c", "ext4_reserve_inode_write"
    )
    dirty = build_phase5_function_cfg(
        f"{source}/fs/ext4/ext4_jbd2.c", "__ext4_handle_dirty_metadata"
    )
    std_error = build_phase5_function_cfg(
        f"{source}/fs/ext4/super.c", "__ext4_std_error"
    )
    handle_error = build_phase5_function_cfg(
        f"{source}/fs/ext4/super.c", "ext4_handle_error"
    )
    abort_handle = build_phase5_function_cfg(
        f"{source}/include/linux/jbd2.h", "jbd2_journal_abort_handle"
    )
    journal_stop = build_phase5_function_cfg(
        f"{source}/fs/jbd2/transaction.c", "jbd2_journal_stop"
    )
    health = _health(
        (namei, orphan_add, orphan_file_add, reserve, dirty, std_error, handle_error, abort_handle, journal_stop)
    )

    add = _call(namei, "ext4_orphan_add")
    post_dirty = _call(namei, "ext4_mark_inode_dirty", last=True)
    unlink_stop = _call(namei, "ext4_journal_stop")
    fallback = _text(orphan_add, "err != -ENOSPC")
    file_write = _call(orphan_file_add, "ext4_journal_get_write_access")
    file_dirty = _call(orphan_file_add, "ext4_handle_dirty_metadata")
    legacy_write = _call(orphan_add, "ext4_journal_get_write_access")
    abort_assignment = _text(abort_handle, "handle->h_aborted = 1")
    stop_aborted = _text(journal_stop, "is_handle_aborted(handle)")
    stop_abort_journal = _call(journal_stop, "jbd2_journal_abort")
    continue_guard = _text(handle_error, "continue_fs")
    abort_journal = _call(handle_error, "jbd2_journal_abort")
    required = (add, post_dirty, unlink_stop, fallback, file_write, file_dirty, legacy_write)
    structural_blockers = tuple(
        f"MISSING_PHASE5_EVIDENCE:{name}"
        for name, node in zip(
            (
                "ext4_orphan_add",
                "post_registration_ext4_mark_inode_dirty",
                "unlink_ext4_journal_stop",
                "orphan_add_ENOSPC_partition",
                "orphan_file_write_access",
                "orphan_file_dirty_metadata",
                "legacy_write_access",
            ),
            required,
        )
        if node is None
    )
    contract_closed = (
        not health
        and not structural_blockers
        and abort_assignment is not None
        and stop_aborted is not None
        and stop_abort_journal is None
        and continue_guard is not None
        and abort_journal is not None
    )
    registration_evidence = (
        _loc(namei, add, "caller ignores ext4_orphan_add return")
        + _loc(namei, post_dirty, "post-registration inode dirty operation")
        + _loc(namei, unlink_stop, "same unlink handle stop")
        + _loc(orphan_add, fallback, "-ENOSPC falls back to legacy orphan list")
        + _loc(orphan_file_add, file_write, "orphan-file write access")
        + _loc(orphan_file_add, file_dirty, "orphan-file metadata dirty")
        + _loc(abort_handle, abort_assignment, "JBD2 handle-only abort state")
        + _loc(journal_stop, stop_aborted, "JBD2 stop observes aborted handle")
        + _loc(handle_error, continue_guard, "ERRORS_CONT policy guard")
        + _loc(handle_error, abort_journal, "non-continuing policy aborts journal")
    )
    registration = Ext4ContractStage(
        "registration",
        (
            _summary(
                "EXT4-RC-1",
                "no journal OR bad inode OR already registered",
                "ALL",
                "no new persistent registration required",
                CLOSED if contract_closed else BLOCKED,
                registration_evidence,
                blockers=(*health, *structural_blockers),
            ),
            _summary(
                "EXT4-RC-2",
                "orphan-file available AND orphan-file add returns -ENOSPC",
                "ALL",
                "legacy orphan-list registration is selected",
                CLOSED if contract_closed else BLOCKED,
                registration_evidence,
                blockers=(*health, *structural_blockers),
            ),
            _summary(
                "EXT4-RC-3",
                "registration helper error AND ERRORS_RO/PANIC/failstop policy",
                "ERRORS_RO_OR_FAILSTOP",
                "journal abort or non-RW failstop prevents successful RW commit",
                CLOSED if contract_closed else BLOCKED,
                registration_evidence,
                assumptions=("The policy does not include ERRORS_CONT.",),
                blockers=(*health, *structural_blockers),
            ),
            _summary(
                "EXT4-RC-4",
                "registration helper error AND ERRORS_CONT",
                "ERRORS_CONT",
                "handle is marked aborted, but jbd2 stop does not abort the journal; commit is not excluded",
                UNSAFE if contract_closed else BLOCKED,
                registration_evidence,
                blockers=(
                    *health,
                    *structural_blockers,
                    "EXT4_ERRORS_CONT_REGISTRATION_COMMIT_NOT_EXCLUDED",
                ),
            ),
        ),
    )

    evict = build_phase5_function_cfg(f"{source}/fs/ext4/inode.c", "ext4_evict_inode")
    orphan_del = build_phase5_function_cfg(f"{source}/fs/ext4/orphan.c", "ext4_orphan_del")
    orphan_file_del = build_phase5_function_cfg(
        f"{source}/fs/ext4/orphan.c", "ext4_orphan_file_del"
    )
    mark_inode = build_phase5_function_cfg(
        f"{source}/fs/ext4/inode.c", "__ext4_mark_inode_dirty"
    )
    evict_health = _health((evict, orphan_del, orphan_file_del, mark_inode))
    persistent_del = next(
        (
            node
            for node in evict.find_calls(["ext4_orphan_del"])
            if any(
                call.name == "ext4_orphan_del"
                and call.arguments
                and call.arguments[0] == "handle"
                for call in evict.nodes[node].calls
            )
        ),
        None,
    )
    free = _call(evict, "ext4_free_inode")
    stop = _call(evict, "ext4_journal_stop", last=True)
    mark_error = _call(mark_inode, "ext4_error_inode_err")
    dirty_helper = _call(mark_inode, "ext4_mark_iloc_dirty")
    settlement_structural = (
        not evict_health
        and persistent_del is not None
        and free is not None
        and stop is not None
        and mark_error is not None
        and dirty_helper is not None
        and evict.dominates(persistent_del, free)
        and evict.dominates(persistent_del, stop)
    )
    settlement_evidence = (
        _loc(evict, persistent_del, "persistent orphan removal on handle")
        + _loc(evict, free, "terminal inode free on handle")
        + _loc(evict, stop, "journal stop after free/error branch")
        + _loc(mark_inode, dirty_helper, "mark-iloc dirty helper")
        + _loc(mark_inode, mark_error, "mark-dirty error reporting")
        + _loc(abort_handle, abort_assignment, "JBD2 handle-only abort state")
        + _loc(handle_error, continue_guard, "ERRORS_CONT policy guard")
    )
    settlement = Ext4ContractStage(
        "settlement",
        (
            _summary(
                "EXT4-SC-1",
                "persistent orphan removal succeeds AND inode mark/free succeeds",
                "ALL",
                "registry removal, inode free, and journal stop share the eviction handle",
                CLOSED if settlement_structural else BLOCKED,
                settlement_evidence,
                blockers=(*evict_health, *( () if settlement_structural else ("EXT4_SETTLEMENT_STRUCTURE_NOT_PROVEN",) )),
            ),
            _summary(
                "EXT4-SC-2",
                "post-removal mark/free error AND ERRORS_RO/PANIC/failstop policy",
                "ERRORS_RO_OR_FAILSTOP",
                "journal abort or non-RW failstop prevents removal-only commit",
                CLOSED if settlement_structural else BLOCKED,
                settlement_evidence,
                assumptions=("The policy does not include ERRORS_CONT.",),
                blockers=(*evict_health, *( () if settlement_structural else ("EXT4_SETTLEMENT_STRUCTURE_NOT_PROVEN",) )),
            ),
            _summary(
                "EXT4-SC-3",
                "post-removal mark/free error AND ERRORS_CONT",
                "ERRORS_CONT",
                "partial registry removal may be journaled while inode free is skipped; commit is not excluded",
                UNSAFE if settlement_structural else BLOCKED,
                settlement_evidence,
                blockers=(
                    *evict_health,
                    *( () if settlement_structural else ("EXT4_SETTLEMENT_STRUCTURE_NOT_PROVEN",) ),
                    "EXT4_ERRORS_CONT_REMOVAL_ONLY_COMMIT_NOT_EXCLUDED",
                ),
            ),
        ),
    )

    cleanup = build_phase5_function_cfg(f"{source}/fs/ext4/orphan.c", "ext4_orphan_cleanup")
    orphan_get = build_phase5_function_cfg(f"{source}/fs/ext4/ialloc.c", "ext4_orphan_get")
    fill = build_phase5_function_cfg(f"{source}/fs/ext4/super.c", "__ext4_fill_super")
    recovery_health = _health((cleanup, orphan_get, fill))
    cleanup_call = _call(fill, "ext4_orphan_cleanup")
    marker = _call(fill, "ext4_mark_recovery_complete")
    dispatch = _call(cleanup, "ext4_process_orphan")
    get_error = _text(cleanup, "IS_ERR(inode)")
    get_error_report = _call(orphan_get, "ext4_error_err")
    fill_return = _text(fill, "return 0;")
    recovery_structure = (
        not recovery_health
        and cleanup_call is not None
        and marker is not None
        and dispatch is not None
        and get_error is not None
        and get_error_report is not None
        and fill_return is not None
        and fill.dominates(cleanup_call, marker)
    )
    recovery_evidence = (
        _loc(cleanup, dispatch, "valid orphan dispatch")
        + _loc(cleanup, get_error, "orphan-get error partition")
        + _loc(orphan_get, get_error_report, "orphan-get error reporting")
        + _loc(fill, cleanup_call, "void cleanup call")
        + _loc(fill, marker, "recovery completion marker")
        + _loc(fill, fill_return, "successful mount return")
        + _loc(handle_error, continue_guard, "ERRORS_CONT policy guard")
    )
    recovery = Ext4ContractStage(
        "recovery",
        (
            _summary(
                "EXT4-CC-1",
                "orphan registry is empty at cleanup entry",
                "ALL",
                "no OIDS recovery instance is applicable",
                NOT_APPLICABLE if recovery_structure else BLOCKED,
                recovery_evidence,
                blockers=(*recovery_health, *( () if recovery_structure else ("EXT4_RECOVERY_STRUCTURE_NOT_PROVEN",) )),
            ),
            _summary(
                "EXT4-CC-2",
                "valid orphan is obtained and dispatched to ext4_process_orphan",
                "ALL",
                "selected zero-link inode reaches iput-driven eviction before completion marker",
                CLOSED if recovery_structure else BLOCKED,
                recovery_evidence,
                assumptions=("The instance is restricted to a valid inode dispatch, not a skipped/error lookup.",),
                blockers=(*recovery_health, *( () if recovery_structure else ("EXT4_RECOVERY_STRUCTURE_NOT_PROVEN",) )),
            ),
            _summary(
                "EXT4-CC-3",
                "orphan-get error/skip AND ERRORS_RO/PANIC/failstop policy",
                "ERRORS_RO_OR_FAILSTOP",
                "error handling is visible, but journal-flush-to-mount-failure propagation remains unclosed",
                BLOCKED,
                recovery_evidence,
                blockers=(
                    *recovery_health,
                    "EXT4_RECOVERY_FAILSTOP_FLUSH_CONTRACT_NOT_LOCKED",
                ),
            ),
            _summary(
                "EXT4-CC-4",
                "orphan-get error/skip AND ERRORS_CONT",
                "ERRORS_CONT",
                "void cleanup can return and fill_super can reach recovery completion and mount return",
                UNSAFE if recovery_structure else BLOCKED,
                recovery_evidence,
                blockers=(
                    *recovery_health,
                    *( () if recovery_structure else ("EXT4_RECOVERY_STRUCTURE_NOT_PROVEN",) ),
                    "EXT4_ERRORS_CONT_RECOVERY_EXPOSURE_NOT_EXCLUDED",
                ),
            ),
        ),
    )
    return Ext4ContractAssessment(
        registration,
        settlement,
        recovery,
        registration.universal_closed and settlement.universal_closed and recovery.universal_closed,
        registration.failstop_closed and settlement.failstop_closed and recovery.failstop_closed,
    )


def run_manifest(path: str) -> Dict[str, Any]:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    locks = _verify_artifacts(manifest["artifact_hashes"])
    assessment = analyze_ext4_contracts(manifest)
    value = assessment.to_dict()
    return {
        "schema_version": 1,
        "evaluation_id": manifest["evaluation_id"],
        "manifest": path,
        "manifest_sha256": _sha256(path),
        "artifact_hashes_verified": all(locks.values()),
        "bug_specific_condition_count": count_bug_specific_conditions([manifest]),
        "assessment": value,
        "universal_all_path_closed": assessment.universal_closed,
        "failstop_profile_closed": assessment.failstop_profile_closed,
        "common_freeze_manifest_generated": False,
        "interpretation": manifest["interpretation"],
    }


def _markdown(summary: Dict[str, Any]) -> str:
    assessment = summary["assessment"]
    lines = [
        "# OIDS Phase 5 ext4 Interprocedural Contracts",
        "",
        f"Manifest: `{summary['manifest']}`",
        "",
        f"Universal all-path closure: `{summary['universal_all_path_closed']}`",
        f"Failstop-profile closure: `{summary['failstop_profile_closed']}`",
        "",
        "| Stage | Summary | Configuration | Status | Outcome |",
        "|---|---|---|---|---|",
    ]
    for stage_name in ("registration", "settlement", "recovery"):
        for item in assessment[stage_name]["summaries"]:
            lines.append(
                f"| {stage_name} | `{item['summary_id']}` | `{item['configuration']}` | `{item['status']}` | {item['outcome']} |"
            )
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- `{blocker}`" for blocker in assessment["blockers"])
    lines.extend(["", summary["interpretation"], ""])
    return "\n".join(lines)


def run_and_write(manifest: str, json_out: str, markdown_out: str) -> Dict[str, Any]:
    summary = run_manifest(manifest)
    write_json(json_out, summary)
    write_markdown(markdown_out, _markdown(summary))
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.orphan_ext4_contracts")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    args = parser.parse_args(argv)
    summary = run_and_write(args.manifest, args.json_out, args.markdown_out)
    print(
        f"universal_closed={summary['universal_all_path_closed']} "
        f"failstop_closed={summary['failstop_profile_closed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
