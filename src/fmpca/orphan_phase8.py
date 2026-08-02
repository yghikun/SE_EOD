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
from .frontend import extract_function
from .frontend_orphan_common import load_orphan_binding
from .model import AnalysisResult, EvidenceEvent
from .orphan_allpath import SourceLocation
from .proof import analyze_state
from .report import count_bug_specific_conditions, write_json, write_markdown
from .semantics_extensions import ProtocolDeadlineEngine


CLOSED = "CLOSED"
BLOCKED = "BLOCKED"
APPLICABLE = "APPLICABLE"
VALIDATED_PROFILE = "SUCCESSFUL_RW_RECOVERY_EXPOSURE"
DEFERRED_PROFILE = "RECOVERY_DEFERRED_OUTSIDE_VALIDATED_RW_EXPOSURE"


@dataclass(frozen=True)
class StageProof:
    stage: str
    status: str
    conclusion: str
    partitions: Tuple[str, ...]
    evidence: Tuple[SourceLocation, ...]
    blockers: Tuple[str, ...] = ()

    @property
    def closed(self) -> bool:
        return self.status == CLOSED and not self.blockers


@dataclass(frozen=True)
class CorrespondenceDimension:
    dimension: str
    status: str
    conclusion: str
    evidence: Tuple[SourceLocation, ...]
    blockers: Tuple[str, ...] = ()

    @property
    def closed(self) -> bool:
        return self.status == CLOSED and not self.blockers


@dataclass(frozen=True)
class ReplayResult:
    profile: str
    fixture: str
    expected: str
    actual: str
    violation_rules: Tuple[str, ...]
    closed: bool


@dataclass(frozen=True)
class Phase8Assessment:
    correspondence: Tuple[CorrespondenceDimension, ...]
    registration: StageProof
    settlement: StageProof
    recovery: StageProof
    replays: Tuple[ReplayResult, ...]

    @property
    def correspondence_closed(self) -> bool:
        return len(self.correspondence) == 5 and all(item.closed for item in self.correspondence)

    @property
    def source_proof_closed(self) -> bool:
        return self.registration.closed and self.settlement.closed and self.recovery.closed

    @property
    def replay_closed(self) -> bool:
        return all(item.closed for item in self.replays)

    @property
    def blockers(self) -> Tuple[str, ...]:
        values: List[str] = []
        for item in (*self.correspondence, self.registration, self.settlement, self.recovery):
            for blocker in item.blockers:
                if blocker not in values:
                    values.append(blocker)
        for replay in self.replays:
            if not replay.closed:
                values.append(f"PHASE8_REPLAY_MISMATCH:{replay.profile}")
        return tuple(values)

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        for item, source in zip(value["correspondence"], self.correspondence):
            item["closed"] = source.closed
        for name, source in (
            ("registration", self.registration),
            ("settlement", self.settlement),
            ("recovery", self.recovery),
        ):
            value[name]["closed"] = source.closed
        value["correspondence_closed"] = self.correspondence_closed
        value["source_proof_closed"] = self.source_proof_closed
        value["replay_closed"] = self.replay_closed
        value["blockers"] = list(self.blockers)
        return value


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load(path: str) -> Dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _verify_hashes(values: Dict[str, str], label: str) -> Dict[str, bool]:
    if not values:
        raise ValueError(f"{label} hash lock must not be empty")
    result: Dict[str, bool] = {}
    for path, expected in values.items():
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(f"{label} hash mismatch for {path}: {actual} != {expected}")
        result[path] = True
    return result


def _verify_source_manifest(source_root: str, manifest_path: str) -> Dict[str, bool]:
    manifest = _load(manifest_path)
    result: Dict[str, bool] = {}
    for item in manifest["supplementary_source_files"]:
        path = str(Path(source_root) / item["path"])
        actual = _sha256(path)
        if actual != item["sha256"]:
            raise ValueError(f"Phase 8 source hash mismatch for {path}")
        result[item["path"]] = True
    return result


def _cfg(source_root: str, relative: str, function: str) -> FunctionCFG:
    return build_phase5_function_cfg(str(Path(source_root) / relative), function)


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


def _loc(cfg: FunctionCFG, node: Optional[int], fact: str) -> Tuple[SourceLocation, ...]:
    if node is None:
        return ()
    value = cfg.nodes[node]
    return (SourceLocation(cfg.source_path, cfg.function_name, value.line, node, fact),)


def _source_loc(path: str, function_name: str, marker: str, fact: str) -> Optional[SourceLocation]:
    source = Path(path).read_text(encoding="utf-8")
    function = extract_function(source, function_name)
    offset = function.masked_text.find(marker)
    if offset < 0:
        return None
    return SourceLocation(path, function_name, function.line_for_offset(offset), -1, fact)


def _health(cfgs: Iterable[FunctionCFG]) -> Tuple[str, ...]:
    blockers: List[str] = []
    for cfg in cfgs:
        if cfg.parse_has_error:
            blockers.append(f"CFG_PARSE_ERROR:{cfg.function_name}")
        if cfg.unresolved_gotos:
            blockers.append(f"CFG_UNRESOLVED_GOTO:{cfg.function_name}")
    return tuple(blockers)


def _missing(values: Iterable[Tuple[str, Any]]) -> Tuple[str, ...]:
    return tuple(f"MISSING_PHASE8_EVIDENCE:{name}" for name, value in values if value is None)


def _lines_in_order(*items: Tuple[FunctionCFG, Optional[int]]) -> bool:
    lines = [cfg.nodes[node].line for cfg, node in items if node is not None]
    return len(lines) == len(items) and lines == sorted(lines) and len(set(lines)) == len(lines)


def analyze_registration(source_root: str) -> StageProof:
    unlink = _cfg(source_root, "fs/ubifs/dir.c", "ubifs_unlink")
    update = _cfg(source_root, "fs/ubifs/journal.c", "ubifs_jnl_update")
    do_commit = _cfg(source_root, "fs/ubifs/commit.c", "do_commit")
    drop = _call(unlink, "drop_nlink")
    update_call = _call(unlink, "ubifs_jnl_update")
    restore = _call(unlink, "set_nlink")
    last_reference = _text(update, "deletion && inode->i_nlink == 0")
    add = _call(update, "ubifs_add_orphan")
    write = _call(update, "write_head")
    ro_mode = _call(update, "ubifs_ro_mode")
    rollback = _call(update, "ubifs_delete_orphan", last=True)
    start_commit = _call(do_commit, "ubifs_orphan_start_commit")
    end_commit = _call(do_commit, "ubifs_orphan_end_commit")
    missing = _missing(
        (
            ("unlink_drop_nlink", drop),
            ("unlink_journal_update", update_call),
            ("unlink_error_restore", restore),
            ("last_reference_guard", last_reference),
            ("orphan_add", add),
            ("journal_group_write", write),
            ("post_write_ro_mode", ro_mode),
            ("failed_write_orphan_rollback", rollback),
            ("orphan_start_commit", start_commit),
            ("orphan_end_commit", end_commit),
        )
    )
    ordered = (
        _lines_in_order((unlink, drop), (unlink, update_call), (unlink, restore))
        and _lines_in_order((update, last_reference), (update, add), (update, write), (update, ro_mode), (update, rollback))
        and _lines_in_order((do_commit, start_commit), (do_commit, end_commit))
    )
    blockers = _health((unlink, update, do_commit)) + missing
    if not ordered and not blockers:
        blockers = ("UBIFS_REGISTRATION_PARTITIONS_NOT_ORDERED",)
    evidence = (
        _loc(unlink, drop, "unlink drops the selected inode link count")
        + _loc(unlink, update_call, "unlink submits dent and zero-link inode journal group")
        + _loc(unlink, restore, "journal failure restores the saved link count")
        + _loc(update, last_reference, "orphan registration is zero-link deletion scoped")
        + _loc(update, add, "orphan responsibility is accepted before journal group write")
        + _loc(update, write, "dent, inode, and parent inode are written as one journal group")
        + _loc(update, ro_mode, "post-write bookkeeping failure enters read-only failstop")
        + _loc(update, rollback, "failed journal update removes only the uncommitted in-memory orphan")
        + _loc(do_commit, start_commit, "commit generation snapshots new orphans")
        + _loc(do_commit, end_commit, "orphan area is completed before commit publication")
    )
    return StageProof(
        "registration",
        CLOSED if ordered and not blockers else BLOCKED,
        "Zero-link responsibility is accepted before the namespace journal group can settle; pre-write failure rolls back and post-write failure failstops.",
        ("pre_write_failure_rollback", "successful_journal_group", "post_write_failure_read_only_failstop", "commit_generation_persistence"),
        evidence,
        blockers,
    )


def analyze_settlement(source_root: str) -> StageProof:
    evict = _cfg(source_root, "fs/ubifs/super.c", "ubifs_evict_inode")
    delete = _cfg(source_root, "fs/ubifs/journal.c", "ubifs_jnl_delete_inode")
    write_inode = _cfg(source_root, "fs/ubifs/journal.c", "ubifs_jnl_write_inode")
    apply_replay = _cfg(source_root, "fs/ubifs/replay.c", "apply_replay_entry")
    orphan_end = _cfg(source_root, "fs/ubifs/orphan.c", "ubifs_orphan_end_commit")
    do_commit = _cfg(source_root, "fs/ubifs/commit.c", "do_commit")
    evict_delete = _call(evict, "ubifs_jnl_delete_inode")
    delegated_write = _call(delete, "ubifs_jnl_write_inode")
    direct_remove = _call(delete, "ubifs_tnc_remove_ino")
    direct_ro = _call(delete, "ubifs_ro_mode")
    direct_orphan_delete = _call(delete, "ubifs_delete_orphan")
    deletion_write = _call(write_inode, "write_head")
    written_remove = _call(write_inode, "ubifs_tnc_remove_ino")
    written_orphan_delete = _call(write_inode, "ubifs_delete_orphan")
    written_ro = _call(write_inode, "ubifs_ro_mode", last=True)
    replay_remove = _call(apply_replay, "ubifs_tnc_remove_ino")
    commit_orphans = _call(orphan_end, "commit_orphans")
    erase_deleted = _call(orphan_end, "erase_deleted")
    commit_ro = _call(do_commit, "ubifs_ro_mode")
    orphan_delete_path = str(Path(source_root) / "fs/ubifs/orphan.c")
    delayed_delete = _source_loc(orphan_delete_path, "orphan_delete", "orph->del = 1", "commit-owned orphan removal is deferred")
    deletion_list = _source_loc(orphan_delete_path, "orphan_delete", "c->orph_dnext = orph", "deferred deletion retains a commit-owned record")
    missing = _missing(
        (
            ("eviction_dispatch", evict_delete),
            ("post_commit_write_delegate", delegated_write),
            ("no_commit_tnc_remove", direct_remove),
            ("no_commit_error_failstop", direct_ro),
            ("no_commit_orphan_delete", direct_orphan_delete),
            ("deletion_inode_write", deletion_write),
            ("post_commit_tnc_remove", written_remove),
            ("post_commit_orphan_delete", written_orphan_delete),
            ("post_commit_error_failstop", written_ro),
            ("replay_terminal_remove", replay_remove),
            ("commit_orphans", commit_orphans),
            ("erase_deleted", erase_deleted),
            ("commit_failure_failstop", commit_ro),
            ("commit_owned_del_marker", delayed_delete),
            ("commit_owned_dnext_marker", deletion_list),
        )
    )
    ordered = (
        _lines_in_order((delete, delegated_write), (delete, direct_remove), (delete, direct_ro), (delete, direct_orphan_delete))
        and _lines_in_order((write_inode, deletion_write), (write_inode, written_remove), (write_inode, written_orphan_delete), (write_inode, written_ro))
        and _lines_in_order((orphan_end, commit_orphans), (orphan_end, erase_deleted))
        and evict_delete is not None
        and replay_remove is not None
    )
    blockers = _health((evict, delete, write_inode, apply_replay, orphan_end, do_commit)) + missing
    if not ordered and not blockers:
        blockers = ("UBIFS_SETTLEMENT_PARTITIONS_NOT_ORDERED",)
    evidence = (
        _loc(evict, evict_delete, "final reference dispatches inode settlement")
        + _loc(delete, delegated_write, "commit-generation change requires a fresh deletion inode")
        + _loc(delete, direct_remove, "same-generation path removes all inode keys under commit_sem")
        + _loc(delete, direct_ro, "same-generation TNC failure enters read-only failstop")
        + _loc(delete, direct_orphan_delete, "same-generation removal retires orphan only after TNC removal")
        + _loc(write_inode, deletion_write, "post-commit path writes a replayable deletion inode")
        + _loc(write_inode, written_remove, "post-commit path removes all inode keys")
        + _loc(write_inode, written_orphan_delete, "post-commit path retires orphan after terminal removal")
        + _loc(write_inode, written_ro, "post-commit failure enters read-only failstop")
        + _loc(apply_replay, replay_remove, "replay applies zero-link inode nodes as whole-inode deletion")
        + _loc(orphan_end, commit_orphans, "commit writes retained orphans before deletion-list erasure")
        + _loc(orphan_end, erase_deleted, "commit-owned deleted entries are erased after orphan write")
        + ((delayed_delete, deletion_list) if delayed_delete and deletion_list else ())
        + _loc(do_commit, commit_ro, "commit failure marks the filesystem read-only")
    )
    return StageProof(
        "settlement",
        CLOSED if ordered and not blockers else BLOCKED,
        "Both commit-generation partitions retain replayable deletion responsibility until terminal TNC removal and orphan retirement are safely ordered.",
        ("no_intervening_commit", "intervening_commit", "orphan_owned_by_active_commit", "settlement_error_failstop"),
        evidence,
        blockers,
    )


def analyze_recovery(source_root: str) -> StageProof:
    replay = _cfg(source_root, "fs/ubifs/replay.c", "replay_bud")
    apply_replay = _cfg(source_root, "fs/ubifs/replay.c", "apply_replay_entry")
    kill = _cfg(source_root, "fs/ubifs/orphan.c", "kill_orphans")
    mount_orphans = _cfg(source_root, "fs/ubifs/orphan.c", "ubifs_mount_orphans")
    recovery_commit = _cfg(source_root, "fs/ubifs/recovery.c", "ubifs_rcvry_gc_commit")
    mount = _cfg(source_root, "fs/ubifs/super.c", "mount_ubifs")
    fill = _cfg(source_root, "fs/ubifs/super.c", "ubifs_fill_super")
    nlink_zero = _text(replay, "ino->nlink) == 0")
    replay_remove = _call(apply_replay, "ubifs_tnc_remove_ino")
    kill_dispatch = _call(kill, "do_kill_orphans")
    mount_kill = _call(mount_orphans, "kill_orphans")
    run_commit = _call(recovery_commit, "ubifs_run_commit")
    journal = _call(mount, "ubifs_replay_journal")
    orphan_scan = _call(mount, "ubifs_mount_orphans")
    rw_commit = _call(mount, "ubifs_rcvry_gc_commit")
    successful_mount = _text(mount, "return 0;", last=True)
    mount_call = _call(fill, "mount_ubifs")
    root_read = _call(fill, "ubifs_iget")
    root_exposure = _call(fill, "d_make_root")
    ro_deferred = _text(mount, '"recovery deferred"')
    missing = _missing(
        (
            ("replay_zero_link_classification", nlink_zero),
            ("replay_tnc_remove", replay_remove),
            ("orphan_kill_dispatch", kill_dispatch),
            ("unclean_mount_kill_orphans", mount_kill),
            ("recovery_commit", run_commit),
            ("mount_journal_replay", journal),
            ("mount_orphan_scan", orphan_scan),
            ("mount_rw_recovery_commit", rw_commit),
            ("mount_success", successful_mount),
            ("fill_super_mount", mount_call),
            ("root_read", root_read),
            ("root_exposure", root_exposure),
            ("read_only_deferred_marker", ro_deferred),
        )
    )
    ordered = (
        _lines_in_order((mount, journal), (mount, orphan_scan), (mount, rw_commit), (mount, successful_mount))
        and _lines_in_order((fill, mount_call), (fill, root_read), (fill, root_exposure))
        and mount_call is not None
        and root_exposure is not None
        and fill.dominates(mount_call, root_exposure)
    )
    blockers = _health((apply_replay, kill, mount_orphans, recovery_commit, mount, fill)) + missing
    if not ordered and not blockers:
        blockers = ("UBIFS_RW_RECOVERY_EXPOSURE_NOT_ORDERED",)
    evidence = (
        _loc(replay, nlink_zero, "journal replay classifies zero-link inode nodes as deletions")
        + _loc(apply_replay, replay_remove, "journal deletion removes the inode from TNC")
        + _loc(kill, kill_dispatch, "persistent orphan area dispatches per-LEB deletion")
        + _loc(mount_orphans, mount_kill, "unclean mount invokes persistent orphan killing")
        + _loc(recovery_commit, run_commit, "RW recovery commits orphan TNC updates to flash")
        + _loc(mount, journal, "mount replays journal before orphan processing")
        + _loc(mount, orphan_scan, "mount processes persistent orphans after replay")
        + _loc(mount, rw_commit, "successful RW recovery commits before mount completion")
        + _loc(mount, ro_deferred, "read-only recovery is explicitly deferred")
        + _loc(fill, mount_call, "fill_super requires successful mount_ubifs")
        + _loc(fill, root_exposure, "root is constructed only after mount_ubifs succeeds")
    )
    return StageProof(
        "recovery",
        CLOSED if ordered and not blockers else BLOCKED,
        "Successful RW mount exposure is dominated by journal replay, orphan killing, and a durable recovery commit; read-only recovery remains explicitly deferred.",
        ("uncommitted_journal_deletion", "committed_orphan_area_deletion", "successful_rw_recovery", "read_only_recovery_deferred"),
        evidence,
        blockers,
    )


def _run_fixture(protocol_path: str, fixture_path: str, profile: str) -> ReplayResult:
    spec = load_protocol(protocol_path)
    fixture = _load(fixture_path)
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
    expected = fixture["expected"]
    return ReplayResult(
        profile,
        fixture_path,
        expected,
        report.result.value,
        tuple(report.violation_rules),
        report.result.value == expected,
    )


def assess_correspondence(
    source_root: str, registration: StageProof, settlement: StageProof, recovery: StageProof
) -> Tuple[CorrespondenceDimension, ...]:
    orphan_path = str(Path(source_root) / "fs/ubifs/orphan.c")
    header_path = str(Path(source_root) / "fs/ubifs/ubifs.h")
    source = Path(header_path).read_text(encoding="utf-8")
    offset = source.find("struct ubifs_orphan {")
    object_fact = None
    if offset >= 0:
        object_fact = SourceLocation(
            header_path,
            "struct ubifs_orphan",
            source[:offset].count("\n") + 1,
            -1,
            "orphan object stores inode identity and lifecycle flags",
        )
    relation_fact = _source_loc(orphan_path, "ubifs_add_orphan", "orphan->inum = inum", "persistent registry identity is the inode number")
    dimensions = (
        ("object", "UBIFS has a concrete orphan object and filesystem-scoped orphan-area state.", object_fact, registration.closed),
        ("relation", "A zero-link inode is related to an orphan-area record by inode number.", relation_fact, registration.closed),
        ("lifecycle", "Unlink registration, final eviction, and RW recovery cover the required lifecycle.", registration.evidence[0] if registration.evidence else None, registration.closed and settlement.closed and recovery.closed),
        ("authority", "Final eviction and mount recovery are distinct deletion authorities.", settlement.evidence[0] if settlement.evidence else None, settlement.closed and recovery.closed),
        ("deadline", "Registration precedes commit; removal follows terminal preparation; RW recovery precedes root exposure.", recovery.evidence[-1] if recovery.evidence else None, registration.closed and settlement.closed and recovery.closed),
    )
    values: List[CorrespondenceDimension] = []
    for name, conclusion, evidence, closed in dimensions:
        blockers: Tuple[str, ...] = ()
        if evidence is None:
            blockers = (f"UBIFS_{name.upper()}_CORRESPONDENCE_EVIDENCE_MISSING",)
        elif not closed:
            blockers = (f"UBIFS_{name.upper()}_CORRESPONDENCE_STAGE_NOT_CLOSED",)
        values.append(
            CorrespondenceDimension(
                name,
                CLOSED if closed and not blockers else BLOCKED,
                conclusion,
                (evidence,) if evidence else (),
                blockers,
            )
        )
    return tuple(values)


def analyze_phase8(config: Dict[str, Any]) -> Phase8Assessment:
    load_orphan_binding(config["binding"])
    source_root = config["source_root"]
    registration = analyze_registration(source_root)
    settlement = analyze_settlement(source_root)
    recovery = analyze_recovery(source_root)
    correspondence = assess_correspondence(source_root, registration, settlement, recovery)
    replays = tuple(
        _run_fixture(config["protocol"], item["fixture"], item["profile"])
        for item in config["replays"]
    )
    return Phase8Assessment(correspondence, registration, settlement, recovery, replays)


def run_manifest(path: str) -> Dict[str, Any]:
    manifest = _load(path)
    preregistration = _load(manifest["preregistration"])
    amendment = _load(manifest["preregistration_amendment"])
    preregistration_hash_ok = _sha256(manifest["preregistration"]) == amendment["preregistration_sha256"]
    if not preregistration_hash_ok:
        raise ValueError("Phase 8 preregistration no longer matches its amendment")
    pre_reveal = _verify_hashes(preregistration["pre_reveal_locks"], "Phase 8 pre-reveal")
    artifacts = _verify_hashes(manifest["artifact_hashes"], "Phase 8 artifact")
    sources = _verify_source_manifest(manifest["source_root"], manifest["source_manifest"])
    effective_sources = set(amendment["effective_target_sources"])
    if set(sources) != effective_sources:
        raise ValueError("Phase 8 source manifest does not match the effective preregistered targets")
    assessment = analyze_phase8(manifest)
    positive_replays = [item for item in assessment.replays if item.profile != DEFERRED_PROFILE]
    deferred_replays = [item for item in assessment.replays if item.profile == DEFERRED_PROFILE]
    rw_replay_closed = bool(positive_replays) and all(
        item.actual == AnalysisResult.CONFORMANT.value and item.closed for item in positive_replays
    )
    deferred_boundary_closed = len(deferred_replays) == 1 and all(
        item.actual == AnalysisResult.INCOMPLETE.value and item.closed for item in deferred_replays
    )
    validation_closed = (
        all(pre_reveal.values())
        and all(artifacts.values())
        and all(sources.values())
        and assessment.correspondence_closed
        and assessment.source_proof_closed
        and rw_replay_closed
        and deferred_boundary_closed
    )
    return {
        "schema_version": 1,
        "evaluation_id": manifest["evaluation_id"],
        "manifest": path,
        "manifest_sha256": _sha256(path),
        "candidate_filesystem": "UBIFS",
        "candidate_status_before_reveal": preregistration["candidate_status_before_reveal"],
        "validation_role": "PREREGISTERED_BLIND_INDEPENDENT_FAMILY",
        "applicability": APPLICABLE if validation_closed else "UNRESOLVED",
        "validated_profile": VALIDATED_PROFILE,
        "read_only_recovery_profile": DEFERRED_PROFILE,
        "preregistration_hash_verified": preregistration_hash_ok,
        "pre_reveal_locks_verified": all(pre_reveal.values()),
        "artifact_hashes_verified": all(artifacts.values()),
        "source_hashes_verified": all(sources.values()),
        "bug_specific_condition_count": count_bug_specific_conditions([manifest]),
        "assessment": assessment.to_dict(),
        "rw_replay_closed": rw_replay_closed,
        "deferred_boundary_closed": deferred_boundary_closed,
        "candidate_validation_closed": validation_closed,
        "phase7_scope_unchanged": True,
        "common_freeze_manifest_generated": False,
        "blind_held_out_claim_allowed": validation_closed,
        "common_heldout_validated": False,
        "interpretation": manifest["interpretation"],
    }


def _markdown(summary: Dict[str, Any]) -> str:
    assessment = summary["assessment"]
    lines = [
        "# OIDS Phase 8 UBIFS Independent-family Validation",
        "",
        f"Manifest: `{summary['manifest']}`",
        "",
        f"Applicability: `{summary['applicability']}`",
        f"Candidate validation closed: `{summary['candidate_validation_closed']}`",
        f"Validated recovery profile: `{summary['validated_profile']}`",
        f"Read-only profile: `{summary['read_only_recovery_profile']}`",
        f"Phase 7 scope unchanged: `{summary['phase7_scope_unchanged']}`",
        f"COMMON freeze generated: `{summary['common_freeze_manifest_generated']}`",
        f"Preregistered blind independent-family claim: `{summary['blind_held_out_claim_allowed']}`",
        f"COMMON held-out validated: `{summary['common_heldout_validated']}`",
        "",
        "## Source proof",
        "",
        "| Stage | Status | Partitions |",
        "|---|---|---|",
    ]
    for stage in ("registration", "settlement", "recovery"):
        value = assessment[stage]
        lines.append(f"| {stage} | `{value['status']}` | {', '.join(value['partitions'])} |")
    lines.extend(["", "## Correspondence", "", "| Dimension | Status |", "|---|---|"])
    for item in assessment["correspondence"]:
        lines.append(f"| {item['dimension']} | `{item['status']}` |")
    lines.extend(["", "## Replay", "", "| Profile | Expected | Actual | Closed |", "|---|---|---|---|"])
    for replay in assessment["replays"]:
        lines.append(
            f"| {replay['profile']} | `{replay['expected']}` | `{replay['actual']}` | `{replay['closed']}` |"
        )
    lines.extend(["", "## Decision", "", summary["interpretation"], ""])
    return "\n".join(lines)


def run_and_write(manifest: str, json_out: str, markdown_out: str) -> Dict[str, Any]:
    summary = run_manifest(manifest)
    write_json(json_out, summary)
    write_markdown(markdown_out, _markdown(summary))
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.orphan_phase8")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    args = parser.parse_args(argv)
    summary = run_and_write(args.manifest, args.json_out, args.markdown_out)
    print(
        f"applicability={summary['applicability']} "
        f"validation_closed={summary['candidate_validation_closed']} "
        f"common_freeze={summary['common_freeze_manifest_generated']}"
    )
    return 0 if summary["candidate_validation_closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
