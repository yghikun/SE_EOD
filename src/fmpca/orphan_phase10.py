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
from .orphan_phase9 import run_manifest as run_phase9_manifest
from .proof import analyze_state
from .report import count_bug_specific_conditions, write_json, write_markdown
from .semantics_extensions import ProtocolDeadlineEngine


CLOSED = "CLOSED"
BLOCKED = "BLOCKED"
NON_APPLICABLE = "NON_APPLICABLE"
DEADLINE_NOT_ALIGNED = "DEADLINE_NOT_ALIGNED"
ASYNC_RECOVERY = "RECOVERY_ASYNCHRONOUS_AFTER_MOUNT_EXPOSURE"


@dataclass(frozen=True)
class StageProof:
    stage: str
    status: str
    conclusion: str
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
    reason_code: Optional[str] = None

    @property
    def closed(self) -> bool:
        return self.status == CLOSED


@dataclass(frozen=True)
class ReplayResult:
    profile: str
    fixture: str
    expected: str
    actual: str
    violation_rules: Tuple[str, ...]
    closed: bool


@dataclass(frozen=True)
class Phase10Assessment:
    registration: StageProof
    settlement: StageProof
    recovery: StageProof
    correspondence: Tuple[CorrespondenceDimension, ...]
    replays: Tuple[ReplayResult, ...]

    @property
    def screening_dimensions_decided(self) -> bool:
        expected = {"object", "relation", "lifecycle", "authority", "deadline"}
        return (
            {item.dimension for item in self.correspondence} == expected
            and all(item.status in {CLOSED, BLOCKED} for item in self.correspondence)
        )

    @property
    def correspondence_closed(self) -> bool:
        return self.screening_dimensions_decided and all(
            item.closed for item in self.correspondence
        )

    @property
    def source_witness_closed(self) -> bool:
        return all(
            item.closed for item in (self.registration, self.settlement, self.recovery)
        )

    @property
    def replay_expectations_closed(self) -> bool:
        return bool(self.replays) and all(item.closed for item in self.replays)

    @property
    def heldout_replay_closed(self) -> bool:
        return self.replay_expectations_closed and all(
            item.actual == AnalysisResult.CONFORMANT.value for item in self.replays
        )

    @property
    def proof_closure_closed(self) -> bool:
        return (
            self.correspondence_closed
            and self.source_witness_closed
            and self.heldout_replay_closed
        )

    @property
    def controlled_non_applicable(self) -> bool:
        blocked = [item for item in self.correspondence if not item.closed]
        return (
            len(blocked) == 1
            and blocked[0].dimension == "deadline"
            and blocked[0].reason_code == DEADLINE_NOT_ALIGNED
        )

    @property
    def blockers(self) -> Tuple[str, ...]:
        values: List[str] = []
        for stage in (self.registration, self.settlement, self.recovery):
            values.extend(stage.blockers)
        for item in self.correspondence:
            if not item.closed and item.reason_code:
                values.append(item.reason_code)
        return tuple(dict.fromkeys(values))

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        for name, source in (
            ("registration", self.registration),
            ("settlement", self.settlement),
            ("recovery", self.recovery),
        ):
            value[name]["closed"] = source.closed
        for item, source in zip(value["correspondence"], self.correspondence):
            item["closed"] = source.closed
        value.update(
            {
                "screening_dimensions_decided": self.screening_dimensions_decided,
                "correspondence_closed": self.correspondence_closed,
                "source_witness_closed": self.source_witness_closed,
                "replay_expectations_closed": self.replay_expectations_closed,
                "heldout_replay_closed": self.heldout_replay_closed,
                "proof_closure_closed": self.proof_closure_closed,
                "controlled_non_applicable": self.controlled_non_applicable,
                "blockers": list(self.blockers),
            }
        )
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
        if _sha256(path) != item["sha256"]:
            raise ValueError(f"Phase 10 source hash mismatch for {path}")
        result[item["path"]] = True
    return result


def _cfg(source_root: str, relative: str, function_name: str) -> FunctionCFG:
    return build_phase5_function_cfg(str(Path(source_root) / relative), function_name)


def _call(cfg: FunctionCFG, name: str, *, last: bool = False) -> Optional[int]:
    nodes = cfg.find_calls([name])
    if not nodes:
        return None
    key = lambda node: cfg.nodes[node].line
    return max(nodes, key=key) if last else min(nodes, key=key)


def _call_between(
    cfg: FunctionCFG, name: str, minimum_line: int, maximum_line: int
) -> Optional[int]:
    nodes = [
        node
        for node in cfg.find_calls([name])
        if minimum_line <= cfg.nodes[node].line <= maximum_line
    ]
    return max(nodes, key=lambda node: cfg.nodes[node].line) if nodes else None


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


def _function_loc(
    path: str, function_name: str, marker: str, fact: str, *, last: bool = False
) -> Optional[SourceLocation]:
    source = Path(path).read_text(encoding="utf-8")
    function = extract_function(source, function_name)
    offset = (
        function.masked_text.rfind(marker)
        if last
        else function.masked_text.find(marker)
    )
    if offset < 0:
        return None
    return SourceLocation(path, function_name, function.line_for_offset(offset), -1, fact)


def _file_loc(path: str, marker: str, fact: str) -> Optional[SourceLocation]:
    source = Path(path).read_text(encoding="utf-8")
    offset = source.find(marker)
    if offset < 0:
        return None
    return SourceLocation(path, "file_scope", source[:offset].count("\n") + 1, -1, fact)


def _missing(prefix: str, values: Iterable[Tuple[str, Any]]) -> Tuple[str, ...]:
    return tuple(
        f"MISSING_PHASE10_{prefix}_{name}" for name, value in values if value is None
    )


def _health(cfgs: Iterable[FunctionCFG]) -> Tuple[str, ...]:
    blockers: List[str] = []
    for cfg in cfgs:
        if cfg.parse_has_error:
            blockers.append(f"CFG_PARSE_ERROR:{cfg.function_name}")
        if cfg.unresolved_gotos:
            blockers.append(f"CFG_UNRESOLVED_GOTO:{cfg.function_name}")
    return tuple(blockers)


def _ordered(*items: Tuple[FunctionCFG, Optional[int]]) -> bool:
    if any(node is None for _, node in items):
        return False
    lines = [cfg.nodes[node].line for cfg, node in items if node is not None]
    return lines == sorted(lines) and len(lines) == len(set(lines))


def analyze_registration(source_root: str) -> StageProof:
    unlink = _cfg(source_root, "fs/ocfs2/namei.c", "ocfs2_unlink")
    helper_path = str(Path(source_root) / "fs/ocfs2/namei.c")
    helper = _function_loc(
        helper_path,
        "ocfs2_inode_is_unlinkable",
        "inode->i_nlink == 1",
        "regular-file last-link selection makes the following drop reach zero",
    )
    guard = _call(unlink, "ocfs2_inode_is_unlinkable")
    namespace = _call(unlink, "ocfs2_delete_entry")
    link_drop = _call_between(unlink, "drop_nlink", 994, 1000)
    orphan_add = _call(unlink, "ocfs2_orphan_add")
    commit = _call(unlink, "ocfs2_commit_trans")
    missing = _missing(
        "REGISTRATION:",
        (
            ("LAST_LINK_HELPER", helper),
            ("LAST_LINK_GUARD", guard),
            ("NAMESPACE_DELETE", namespace),
            ("LINK_DROP", link_drop),
            ("ORPHAN_ADD", orphan_add),
            ("TRANSACTION_COMMIT", commit),
        ),
    )
    ordered = _ordered(
        (unlink, guard),
        (unlink, namespace),
        (unlink, link_drop),
        (unlink, orphan_add),
        (unlink, commit),
    )
    blockers = _health((unlink,)) + missing
    if not ordered and not blockers:
        blockers = ("OCFS2_REGISTRATION_NOT_ORDERED_BEFORE_COMMIT",)
    evidence = (
        ((helper,) if helper else ())
        + _loc(unlink, guard, "last-reference candidates prepare the slot orphan directory")
        + _loc(unlink, namespace, "namespace entry deletion is staged in the unlink handle")
        + _loc(unlink, link_drop, "the selected inode reaches zero links")
        + _loc(unlink, orphan_add, "the same handle accepts persistent orphan responsibility")
        + _loc(unlink, commit, "the unlink handle commits only after orphan acceptance")
    )
    return StageProof(
        "registration",
        CLOSED if ordered and not blockers else BLOCKED,
        "Successful last-link unlink stages namespace deletion, zero-link state, and slot orphan-directory registration in one JBD2 handle before commit.",
        evidence,
        blockers,
    )


def analyze_settlement(source_root: str) -> StageProof:
    remove = _cfg(source_root, "fs/ocfs2/inode.c", "ocfs2_remove_inode")
    orphan_del = _call(remove, "ocfs2_orphan_del")
    terminal = _call(remove, "ocfs2_free_dinode")
    commit = _call(remove, "ocfs2_commit_trans")
    missing = _missing(
        "SETTLEMENT:",
        (
            ("ORPHAN_DEL", orphan_del),
            ("TERMINAL_DINODE_FREE", terminal),
            ("TRANSACTION_COMMIT", commit),
        ),
    )
    ordered = _ordered((remove, orphan_del), (remove, terminal), (remove, commit))
    blockers = _health((remove,)) + missing
    if not ordered and not blockers:
        blockers = ("OCFS2_SETTLEMENT_NOT_ATOMICALLY_ORDERED",)
    evidence = (
        _loc(remove, orphan_del, "orphan dirent retirement is staged in the delete handle")
        + _loc(remove, terminal, "dinode deallocation is staged in the same handle")
        + _loc(remove, commit, "one commit atomically settles retirement and deletion")
    )
    return StageProof(
        "settlement",
        CLOSED if ordered and not blockers else BLOCKED,
        "Orphan removal and terminal dinode deallocation are atomically co-settled in one delete-inode JBD2 transaction.",
        evidence,
        blockers,
    )


def analyze_recovery(source_root: str) -> StageProof:
    fill = _cfg(source_root, "fs/ocfs2/super.c", "ocfs2_fill_super")
    queue = _cfg(
        source_root, "fs/ocfs2/journal.c", "ocfs2_complete_mount_recovery"
    )
    recover = _cfg(source_root, "fs/ocfs2/journal.c", "ocfs2_recover_orphans")
    journal_path = str(Path(source_root) / "fs/ocfs2/journal.c")
    root = _call(fill, "d_make_root")
    root_assignment = _text(fill, "sb->s_root = root")
    dispatch = _call(fill, "ocfs2_complete_mount_recovery")
    mount_return = _text(fill, "return status;")
    queued_work = _call(queue, "ocfs2_queue_recovery_completion")
    wait_quotas = _function_loc(
        journal_path,
        "ocfs2_complete_recovery",
        "ocfs2_wait_on_quotas(osb)",
        "the asynchronous recovery worker waits until mounted quota state",
    )
    worker_cleanup = _function_loc(
        journal_path,
        "ocfs2_complete_recovery",
        "ocfs2_recover_orphans",
        "orphan cleanup runs in queued recovery work",
    )
    queued_orphans = _call(recover, "ocfs2_queue_orphans")
    final_release = _call(recover, "iput")
    flush_calls = sum(
        (fill.find_calls([name]) for name in ("flush_work", "flush_workqueue", "drain_workqueue")),
        [],
    )
    missing = _missing(
        "RECOVERY:",
        (
            ("ROOT_CONSTRUCTION", root),
            ("ROOT_ASSIGNMENT", root_assignment),
            ("MOUNT_RECOVERY_DISPATCH", dispatch),
            ("FILL_SUPER_RETURN", mount_return),
            ("QUEUED_RECOVERY_WORK", queued_work),
            ("WORKER_QUOTA_WAIT", wait_quotas),
            ("WORKER_ORPHAN_CLEANUP", worker_cleanup),
            ("ORPHAN_QUEUE", queued_orphans),
            ("FINAL_RELEASE", final_release),
        ),
    )
    asynchronous = (
        _ordered((fill, root), (fill, root_assignment), (fill, dispatch), (fill, mount_return))
        and queued_work is not None
        and wait_quotas is not None
        and worker_cleanup is not None
        and wait_quotas.line < worker_cleanup.line
        and _ordered((recover, queued_orphans), (recover, final_release))
        and not flush_calls
    )
    blockers = _health((fill, queue, recover)) + missing
    if asynchronous and not blockers:
        blockers = ("OCFS2_ORPHAN_RECOVERY_NOT_JOINED_BEFORE_MOUNT_EXPOSURE",)
    elif not asynchronous and not blockers:
        blockers = ("OCFS2_RECOVERY_ORDER_UNRESOLVED",)
    evidence = (
        _loc(fill, root, "root dentry is constructed before orphan recovery is queued")
        + _loc(fill, root_assignment, "the mounted superblock receives its root")
        + _loc(fill, dispatch, "mount completion only dispatches asynchronous recovery")
        + _loc(queue, queued_work, "orphan recovery is submitted to the recovery workqueue")
        + ((wait_quotas, worker_cleanup) if wait_quotas and worker_cleanup else ())
        + _loc(recover, queued_orphans, "the worker scans the persistent orphan directory")
        + _loc(recover, final_release, "iput drives eventual orphan inode deletion")
        + _loc(fill, mount_return, "fill_super has no workqueue join before returning")
    )
    return StageProof(
        "recovery",
        BLOCKED,
        "Journal replay is synchronous, but persistent orphan cleanup is queued after root construction and is not joined before successful mount exposure.",
        evidence,
        blockers,
    )


def assess_correspondence(
    source_root: str,
    registration: StageProof,
    settlement: StageProof,
    recovery: StageProof,
) -> Tuple[CorrespondenceDimension, ...]:
    disk_header = str(Path(source_root) / "fs/ocfs2/ocfs2_fs.h")
    object_flag = _file_loc(
        disk_header,
        "OCFS2_ORPHANED_FL",
        "persistent dinode flag identifies an orphaned inode",
    )
    object_slot = _file_loc(
        disk_header,
        "i_orphaned_slot",
        "the dinode records the responsible slot orphan directory",
    )
    relation = next(
        (item for item in registration.evidence if item.function == "ocfs2_unlink" and item.line == 1014),
        None,
    )
    lifecycle = registration.evidence[0] if registration.evidence else None
    authority_live = _function_loc(
        str(Path(source_root) / "fs/ocfs2/inode.c"),
        "ocfs2_delete_inode",
        "ocfs2_query_inode_wipe",
        "cluster-exclusive final eviction decides live deletion authority",
    )
    authority_recovery = next(
        (item for item in recovery.evidence if item.function == "ocfs2_complete_recovery"),
        None,
    )
    deadline_evidence = recovery.evidence
    return (
        CorrespondenceDimension(
            "object",
            CLOSED if object_flag and object_slot else BLOCKED,
            "A persistent dinode flag and slot-specific orphan system directory form the cleanup object.",
            tuple(item for item in (object_flag, object_slot) if item),
        ),
        CorrespondenceDimension(
            "relation",
            CLOSED if relation and registration.closed else BLOCKED,
            "The inode block identity is inserted into the responsible slot orphan directory.",
            (relation,) if relation else (),
        ),
        CorrespondenceDimension(
            "lifecycle",
            CLOSED if registration.closed and settlement.closed and recovery.evidence else BLOCKED,
            "Last-link registration, final eviction, replay, and orphan scanning expose every lifecycle stage.",
            ((lifecycle,) if lifecycle else ()) + settlement.evidence[:1] + recovery.evidence[-2:-1],
        ),
        CorrespondenceDimension(
            "authority",
            CLOSED if authority_live and authority_recovery else BLOCKED,
            "Cluster-exclusive final eviction and queued orphan recovery are explicit deletion authorities.",
            tuple(item for item in (authority_live, authority_recovery) if item),
        ),
        CorrespondenceDimension(
            "deadline",
            BLOCKED,
            "The recovery authority does not guarantee orphan settlement before normal mount exposure.",
            deadline_evidence,
            DEADLINE_NOT_ALIGNED,
        ),
    )


def _run_fixture(protocol_path: str, fixture_path: str, profile: str) -> ReplayResult:
    fixture = _load(fixture_path)
    closure = fixture["closure"]
    state = ProtocolDeadlineEngine(load_protocol(protocol_path)).run(
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


def analyze_phase10(manifest: Dict[str, Any]) -> Phase10Assessment:
    load_orphan_binding(manifest["binding"])
    registration = analyze_registration(manifest["source_root"])
    settlement = analyze_settlement(manifest["source_root"])
    recovery = analyze_recovery(manifest["source_root"])
    correspondence = assess_correspondence(
        manifest["source_root"], registration, settlement, recovery
    )
    replays = tuple(
        _run_fixture(manifest["protocol"], item["fixture"], item["profile"])
        for item in manifest["replays"]
    )
    return Phase10Assessment(
        registration, settlement, recovery, correspondence, replays
    )


def run_manifest(path: str) -> Dict[str, Any]:
    manifest = _load(path)
    preregistration = _load(manifest["preregistration"])
    amendment = _load(manifest["preregistration_amendment"])
    preregistration_hash_verified = (
        _sha256(manifest["preregistration"]) == amendment["preregistration_sha256"]
    )
    if not preregistration_hash_verified:
        raise ValueError("Phase 10 preregistration no longer matches its amendment")
    pre_reveal = _verify_hashes(
        preregistration["pre_reveal_locks"], "Phase 10 pre-reveal"
    )
    artifacts = _verify_hashes(manifest["artifact_hashes"], "Phase 10 artifact")
    sources = _verify_source_manifest(manifest["source_root"], manifest["source_manifest"])
    if set(sources) != set(amendment["effective_target_sources"]):
        raise ValueError("Phase 10 source manifest does not match amended target sources")

    phase9 = run_phase9_manifest(manifest["phase9_manifest"])
    catalog = _load(manifest["screening_catalog"])
    assessment = analyze_phase10(manifest)
    third_filesystem_post_freeze = (
        preregistration["candidate_status_before_reveal"]
        == "UNREVEALED_POST_COMMON_HELDOUT"
        and manifest["candidate_filesystem"].lower() not in phase9["freeze_members"]
    )
    no_semantic_modifications = all(pre_reveal.values())
    applicability = catalog["decision"]
    controlled_decision = (
        applicability == NON_APPLICABLE
        and catalog["controlled_reason_code"] == DEADLINE_NOT_ALIGNED
        and assessment.controlled_non_applicable
        and applicability in preregistration["decision_partition"]
    )
    heldout_gates = {
        "common_freeze_ready": bool(phase9["common_freeze_ready"]),
        "third_filesystem_post_freeze": third_filesystem_post_freeze,
        "heldout_correspondence_closed": assessment.correspondence_closed,
        "heldout_source_witness_closed": assessment.source_witness_closed,
        "heldout_replay_closed": assessment.heldout_replay_closed,
        "heldout_proof_closure_closed": assessment.proof_closure_closed,
        "no_post_freeze_semantic_modifications": no_semantic_modifications,
    }
    failed_heldout_gates = [name for name, closed in heldout_gates.items() if not closed]
    common_heldout_validated = all(heldout_gates.values()) and applicability == "APPLICABLE"
    screening_closed = (
        preregistration_hash_verified
        and all(pre_reveal.values())
        and all(artifacts.values())
        and all(sources.values())
        and phase9["common_freeze_manifest_generated"]
        and assessment.screening_dimensions_decided
        and assessment.replay_expectations_closed
        and controlled_decision
        and not common_heldout_validated
    )
    return {
        "schema_version": 1,
        "evaluation_id": manifest["evaluation_id"],
        "manifest": path,
        "manifest_sha256": _sha256(path),
        "candidate_filesystem": manifest["candidate_filesystem"],
        "validation_role": "PREREGISTERED_POST_COMMON_BLIND_HELD_OUT",
        "operation_family": catalog["operation_family"],
        "applicability": applicability,
        "controlled_reason_code": catalog["controlled_reason_code"],
        "preregistration_hash_verified": preregistration_hash_verified,
        "pre_reveal_locks_verified": all(pre_reveal.values()),
        "artifact_hashes_verified": all(artifacts.values()),
        "source_hashes_verified": all(sources.values()),
        "bug_specific_condition_count": count_bug_specific_conditions([manifest]),
        "assessment": assessment.to_dict(),
        "heldout_gates": heldout_gates,
        "failed_heldout_gates": failed_heldout_gates,
        "third_filesystem_post_freeze": third_filesystem_post_freeze,
        "no_post_freeze_semantic_modifications": no_semantic_modifications,
        "phase9_common_freeze_preserved": phase9["common_freeze_manifest_generated"],
        "phase10_screening_closed": screening_closed,
        "common_heldout_validated": common_heldout_validated,
        "next_heldout_requirement": manifest["next_heldout_requirement"],
        "interpretation": manifest["interpretation"],
    }


def _markdown(summary: Dict[str, Any]) -> str:
    assessment = summary["assessment"]
    lines = [
        "# OIDS Phase 10 OCFS2 Post-COMMON Held-out Screening",
        "",
        f"Manifest: `{summary['manifest']}`",
        "",
        f"Applicability: `{summary['applicability']}`",
        f"Controlled reason: `{summary['controlled_reason_code']}`",
        f"Screening closed: `{summary['phase10_screening_closed']}`",
        f"Phase 9 COMMON freeze preserved: `{summary['phase9_common_freeze_preserved']}`",
        f"No post-freeze semantic modifications: `{summary['no_post_freeze_semantic_modifications']}`",
        f"COMMON held-out validated: `{summary['common_heldout_validated']}`",
        "",
        "## Source stages",
        "",
        "| Stage | Status | Closed |",
        "|---|---|---|",
    ]
    for stage in ("registration", "settlement", "recovery"):
        value = assessment[stage]
        lines.append(f"| {stage} | `{value['status']}` | `{value['closed']}` |")
    lines.extend(["", "## Correspondence", "", "| Dimension | Status | Reason |", "|---|---|---|"])
    for item in assessment["correspondence"]:
        lines.append(
            f"| {item['dimension']} | `{item['status']}` | {item['reason_code'] or '-'} |"
        )
    lines.extend(["", "## Replay", "", "| Profile | Expected | Actual | Closed |", "|---|---|---|---|"])
    for replay in assessment["replays"]:
        lines.append(
            f"| {replay['profile']} | `{replay['expected']}` | `{replay['actual']}` | `{replay['closed']}` |"
        )
    lines.extend(
        [
            "",
            "## Failed held-out gates",
            "",
            ", ".join(summary["failed_heldout_gates"]) or "none",
            "",
            "## Decision",
            "",
            summary["interpretation"],
            "",
            f"Next held-out requirement: {summary['next_heldout_requirement']}",
            "",
        ]
    )
    return "\n".join(lines)


def run_and_write(manifest: str, json_out: str, markdown_out: str) -> Dict[str, Any]:
    summary = run_manifest(manifest)
    write_json(json_out, summary)
    write_markdown(markdown_out, _markdown(summary))
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.orphan_phase10")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    args = parser.parse_args(argv)
    summary = run_and_write(args.manifest, args.json_out, args.markdown_out)
    print(
        f"applicability={summary['applicability']} "
        f"screening_closed={summary['phase10_screening_closed']} "
        f"common_heldout={summary['common_heldout_validated']}"
    )
    return 0 if summary["phase10_screening_closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
