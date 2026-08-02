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
APPLICABLE = "APPLICABLE"
NON_CONFORMANT_HELDOUT = "NON_CONFORMANT_HELDOUT"


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
class FailurePartition:
    profile: str
    stage: str
    status: str
    conclusion: str
    evidence: Tuple[SourceLocation, ...]
    expected_result: str
    expected_rule: Optional[str] = None

    @property
    def decided(self) -> bool:
        return self.status == BLOCKED and bool(self.evidence)


@dataclass(frozen=True)
class CorrespondenceDimension:
    dimension: str
    status: str
    conclusion: str
    evidence: Tuple[SourceLocation, ...]

    @property
    def closed(self) -> bool:
        return self.status == CLOSED and bool(self.evidence)


@dataclass(frozen=True)
class ReplayResult:
    profile: str
    fixture: str
    expected: str
    actual: str
    expected_rule: Optional[str]
    violation_rules: Tuple[str, ...]
    closed: bool


@dataclass(frozen=True)
class Phase11Assessment:
    registration: StageProof
    settlement: StageProof
    recovery: StageProof
    failure_partitions: Tuple[FailurePartition, ...]
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
    def normal_source_paths_closed(self) -> bool:
        return all(
            item.closed for item in (self.registration, self.settlement, self.recovery)
        )

    @property
    def failure_partitions_decided(self) -> bool:
        expected = {
            "SAVE_LINK_ENOSPC_UNPROPAGATED",
            "SAVE_LINK_REMOVAL_ERROR_IGNORED",
            "RECOVERY_ERROR_EXPOSURE_REACHABLE",
        }
        return (
            {item.profile for item in self.failure_partitions} == expected
            and all(item.decided for item in self.failure_partitions)
        )

    @property
    def source_witness_closed(self) -> bool:
        return self.normal_source_paths_closed and self.failure_partitions_decided

    @property
    def replay_expectations_closed(self) -> bool:
        return bool(self.replays) and all(item.closed for item in self.replays)

    @property
    def positive_replays_conform(self) -> bool:
        positives = [
            item
            for item in self.replays
            if item.profile
            in {"SUCCESSFUL_LIVE_DELETION", "SUCCESSFUL_RW_RECOVERY_EXPOSURE"}
        ]
        return len(positives) == 2 and all(
            item.actual == AnalysisResult.CONFORMANT.value for item in positives
        )

    @property
    def violation_proof_closed(self) -> bool:
        expected = {
            "SAVE_LINK_ENOSPC_UNPROPAGATED": "OIDS-O1",
            "RECOVERY_ERROR_EXPOSURE_REACHABLE": "OIDS-O3",
        }
        found = {item.profile: item for item in self.replays}
        return all(
            profile in found
            and found[profile].actual == AnalysisResult.VIOLATION.value
            and rule in found[profile].violation_rules
            for profile, rule in expected.items()
        )

    @property
    def incomplete_partition_closed(self) -> bool:
        item = next(
            (
                replay
                for replay in self.replays
                if replay.profile == "SAVE_LINK_REMOVAL_ERROR_IGNORED"
            ),
            None,
        )
        return bool(item and item.actual == AnalysisResult.INCOMPLETE.value)

    @property
    def candidate_conformant(self) -> bool:
        return (
            self.correspondence_closed
            and self.source_witness_closed
            and self.replay_expectations_closed
            and all(
                item.actual == AnalysisResult.CONFORMANT.value for item in self.replays
            )
        )

    @property
    def nonconformance_proof_closed(self) -> bool:
        return (
            self.correspondence_closed
            and self.source_witness_closed
            and self.replay_expectations_closed
            and self.positive_replays_conform
            and self.violation_proof_closed
            and self.incomplete_partition_closed
            and not self.candidate_conformant
        )

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        for name, source in (
            ("registration", self.registration),
            ("settlement", self.settlement),
            ("recovery", self.recovery),
        ):
            value[name]["closed"] = source.closed
        for item, source in zip(value["failure_partitions"], self.failure_partitions):
            item["decided"] = source.decided
        for item, source in zip(value["correspondence"], self.correspondence):
            item["closed"] = source.closed
        value.update(
            {
                "screening_dimensions_decided": self.screening_dimensions_decided,
                "correspondence_closed": self.correspondence_closed,
                "normal_source_paths_closed": self.normal_source_paths_closed,
                "failure_partitions_decided": self.failure_partitions_decided,
                "source_witness_closed": self.source_witness_closed,
                "replay_expectations_closed": self.replay_expectations_closed,
                "positive_replays_conform": self.positive_replays_conform,
                "violation_proof_closed": self.violation_proof_closed,
                "incomplete_partition_closed": self.incomplete_partition_closed,
                "candidate_conformant": self.candidate_conformant,
                "nonconformance_proof_closed": self.nonconformance_proof_closed,
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
            raise ValueError(f"Phase 11 source hash mismatch for {path}")
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
    offset = function.masked_text.rfind(marker) if last else function.masked_text.find(marker)
    if offset < 0:
        return None
    return SourceLocation(path, function_name, function.line_for_offset(offset), -1, fact)


def _file_loc(path: str, marker: str, fact: str) -> Optional[SourceLocation]:
    source = Path(path).read_text(encoding="utf-8")
    offset = source.find(marker)
    if offset < 0:
        return None
    return SourceLocation(path, "file_scope", source[:offset].count("\n") + 1, -1, fact)


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


def _missing(prefix: str, values: Iterable[Tuple[str, Any]]) -> Tuple[str, ...]:
    return tuple(f"MISSING_PHASE11_{prefix}_{name}" for name, value in values if value is None)


def analyze_registration(source_root: str) -> Tuple[StageProof, FailurePartition]:
    unlink = _cfg(source_root, "fs/reiserfs/namei.c", "reiserfs_unlink")
    add = _cfg(source_root, "fs/reiserfs/super.c", "add_save_link")
    super_path = str(Path(source_root) / "fs/reiserfs/super.c")
    link_drop = _call(unlink, "drop_nlink")
    namespace = _call(unlink, "reiserfs_cut_from_item")
    save_link = _call(unlink, "add_save_link")
    commit = _call(unlink, "journal_end")
    insert = _call(add, "reiserfs_insert_item")
    insert_error = _text(add, "(retval)")
    void_signature = _function_loc(
        super_path,
        "add_save_link",
        "void add_save_link",
        "save-link registration is void and cannot propagate insertion failure",
    )
    ordered = _ordered(
        (unlink, link_drop), (unlink, namespace), (unlink, save_link), (unlink, commit)
    )
    blockers = _health((unlink, add)) + _missing(
        "REGISTRATION",
        (
            ("LINK_DROP", link_drop),
            ("NAMESPACE_CUT", namespace),
            ("SAVE_LINK_ADD", save_link),
            ("JOURNAL_END", commit),
            ("SAVE_LINK_INSERT", insert),
            ("INSERT_ERROR_PARTITION", insert_error),
            ("VOID_SIGNATURE", void_signature),
        ),
    )
    if not ordered and not blockers:
        blockers = ("REISERFS_REGISTRATION_NOT_ORDERED",)
    stage = StageProof(
        "registration",
        CLOSED if ordered and not blockers else BLOCKED,
        "The successful last-link path drops the link count, removes the namespace item, adds a persistent save link, and only then ends the journal transaction.",
        _loc(unlink, link_drop, "the inode reaches its final link transition")
        + _loc(unlink, namespace, "the namespace item is removed in the transaction")
        + _loc(unlink, save_link, "persistent save-link responsibility is requested")
        + _loc(unlink, commit, "the unlink transaction ends after registration"),
        blockers,
    )
    failure_evidence = (
        ((void_signature,) if void_signature else ())
        + _loc(add, insert, "save-link insertion can return ENOSPC")
        + _loc(add, insert_error, "the insertion error branch logs but does not propagate")
        + _loc(unlink, save_link, "the caller cannot inspect add_save_link outcome")
        + _loc(unlink, commit, "journal_end remains reachable after failed registration")
    )
    failure_closed = (
        not blockers
        and void_signature is not None
        and insert is not None
        and insert_error is not None
        and save_link is not None
        and commit is not None
        and add.can_reach(insert, insert_error)
        and unlink.can_reach(save_link, commit)
    )
    failure = FailurePartition(
        "SAVE_LINK_ENOSPC_UNPROPAGATED",
        "registration",
        BLOCKED if failure_closed else CLOSED,
        "add_save_link is void; an insertion error is not propagated, so namespace commit remains reachable without persistent orphan acceptance.",
        failure_evidence if failure_closed else (),
        AnalysisResult.VIOLATION.value,
        "OIDS-O1",
    )
    return stage, failure


def analyze_settlement(source_root: str) -> Tuple[StageProof, FailurePartition]:
    evict = _cfg(source_root, "fs/reiserfs/inode.c", "reiserfs_evict_inode")
    remove = _cfg(source_root, "fs/reiserfs/super.c", "remove_save_link")
    inode_path = str(Path(source_root) / "fs/reiserfs/inode.c")
    terminal = _call(evict, "reiserfs_delete_object")
    terminal_commit = _call(evict, "journal_end")
    retirement = _call(evict, "remove_save_link")
    registry_delete = _call(remove, "reiserfs_delete_solid_item")
    retirement_commit = _call(remove, "journal_end")
    ignored = _function_loc(
        inode_path,
        "reiserfs_evict_inode",
        "remove_save_link(inode, 0",
        "eviction intentionally ignores the save-link removal result",
    )
    ordered = _ordered(
        (evict, terminal), (evict, terminal_commit), (evict, retirement)
    ) and _ordered((remove, registry_delete), (remove, retirement_commit))
    blockers = _health((evict, remove)) + _missing(
        "SETTLEMENT",
        (
            ("TERMINAL_DELETE", terminal),
            ("TERMINAL_COMMIT", terminal_commit),
            ("SAVE_LINK_REMOVE", retirement),
            ("REGISTRY_DELETE", registry_delete),
            ("REMOVAL_COMMIT", retirement_commit),
            ("IGNORED_RESULT", ignored),
        ),
    )
    if not ordered and not blockers:
        blockers = ("REISERFS_SETTLEMENT_NOT_ORDERED",)
    stage = StageProof(
        "settlement",
        CLOSED if ordered and not blockers else BLOCKED,
        "On the successful path, terminal object deletion is committed before a second transaction removes and commits the persistent save link.",
        _loc(evict, terminal, "terminal object items are deleted")
        + _loc(evict, terminal_commit, "terminal deletion is committed")
        + _loc(evict, retirement, "save-link retirement starts after deletion commit")
        + _loc(remove, registry_delete, "the persistent save-link item is deleted")
        + _loc(remove, retirement_commit, "the retirement transaction is committed"),
        blockers,
    )
    failure_closed = not blockers and ignored is not None and retirement_commit is not None
    failure = FailurePartition(
        "SAVE_LINK_REMOVAL_ERROR_IGNORED",
        "settlement",
        BLOCKED if failure_closed else CLOSED,
        "remove_save_link returns the retirement transaction result, but reiserfs_evict_inode discards it; failed retirement therefore remains incomplete.",
        (
            _loc(remove, retirement_commit, "save-link retirement can return journal_end failure")
            + ((ignored,) if ignored else ())
        )
        if failure_closed
        else (),
        AnalysisResult.INCOMPLETE.value,
    )
    return stage, failure


def analyze_recovery(source_root: str) -> Tuple[StageProof, FailurePartition]:
    fill = _cfg(source_root, "fs/reiserfs/super.c", "reiserfs_fill_super")
    journal = _cfg(source_root, "fs/reiserfs/journal.c", "journal_init")
    finish = _cfg(source_root, "fs/reiserfs/super.c", "finish_unfinished")
    super_path = str(Path(source_root) / "fs/reiserfs/super.c")
    journal_init = _call(fill, "journal_init")
    journal_read = _call(journal, "journal_read")
    root = _call(fill, "d_make_root")
    cleanup = _call(fill, "finish_unfinished")
    exposure = _text(fill, "return (0)")
    scan = _text(finish, "MAX_KEY_OBJECTID")
    release = _call(finish, "iput", last=True)
    cleanup_return = _text(finish, "return retval")
    ignored = _function_loc(
        super_path,
        "reiserfs_fill_super",
        "finish_unfinished(s);",
        "fill_super discards the synchronous cleanup return value",
    )
    ordered = _ordered(
        (fill, journal_init), (fill, root), (fill, cleanup), (fill, exposure)
    )
    blockers = _health((fill, journal, finish)) + _missing(
        "RECOVERY",
        (
            ("JOURNAL_INIT", journal_init),
            ("JOURNAL_READ", journal_read),
            ("ROOT", root),
            ("SAVE_LINK_SCAN", scan),
            ("RECOVERY_RELEASE", release),
            ("FINISH_UNFINISHED", cleanup),
            ("SUCCESS_EXPOSURE", exposure),
            ("CLEANUP_RETURN", cleanup_return),
            ("IGNORED_RESULT", ignored),
        ),
    )
    if not ordered and not blockers:
        blockers = ("REISERFS_RECOVERY_NOT_ORDERED_BEFORE_EXPOSURE",)
    stage = StageProof(
        "recovery",
        CLOSED if ordered and not blockers else BLOCKED,
        "Journal replay and the synchronous finish_unfinished save-link scan run before successful RW mount exposure; the normal cleanup path completes through iput-driven eviction.",
        _loc(fill, journal_init, "mount initializes and replays the journal")
        + _loc(journal, journal_read, "journal records are replayed synchronously")
        + _loc(fill, root, "root construction precedes the registered cleanup deadline")
        + _loc(finish, scan, "finish_unfinished enumerates the persistent save-link keyspace")
        + _loc(finish, release, "iput drives terminal deletion of recovered unlinks")
        + _loc(fill, cleanup, "synchronous orphan cleanup runs in fill_super")
        + _loc(fill, exposure, "successful mount return follows cleanup"),
        blockers,
    )
    failure_closed = (
        not blockers
        and cleanup is not None
        and exposure is not None
        and cleanup_return is not None
        and ignored is not None
        and fill.can_reach(cleanup, exposure)
    )
    failure = FailurePartition(
        "RECOVERY_ERROR_EXPOSURE_REACHABLE",
        "recovery",
        BLOCKED if failure_closed else CLOSED,
        "finish_unfinished returns cleanup failure, but reiserfs_fill_super ignores it and can still return success, exposing an unsettled recovered inode.",
        (
            _loc(finish, cleanup_return, "the synchronous recovery scan returns its last cleanup error")
            + ((ignored,) if ignored else ())
            + _loc(fill, exposure, "normal exposure remains reachable after the ignored result")
        )
        if failure_closed
        else (),
        AnalysisResult.VIOLATION.value,
        "OIDS-O3",
    )
    return stage, failure


def assess_correspondence(
    source_root: str,
    registration: StageProof,
    settlement: StageProof,
    recovery: StageProof,
) -> Tuple[CorrespondenceDimension, ...]:
    header = str(Path(source_root) / "fs/reiserfs/reiserfs.h")
    super_path = str(Path(source_root) / "fs/reiserfs/super.c")
    inode_path = str(Path(source_root) / "fs/reiserfs/inode.c")
    object_key = _file_loc(
        header, "MAX_KEY_OBJECTID", "save links occupy a reserved persistent keyspace"
    )
    object_flag = _file_loc(
        header,
        "i_link_saved_unlink_mask",
        "the inode tracks accepted unlink save-link responsibility",
    )
    relation = _function_loc(
        super_path,
        "add_save_link",
        "key.on_disk_key.k_objectid = inode->i_ino",
        "the persistent save-link key carries inode object identity",
    )
    lifecycle = registration.evidence[0] if registration.evidence else None
    live_authority = _function_loc(
        inode_path,
        "reiserfs_evict_inode",
        "reiserfs_delete_object",
        "final eviction is live terminal-deletion authority",
    )
    recovery_authority = _function_loc(
        super_path,
        "finish_unfinished",
        "iput(inode)",
        "the synchronous mount scan releases recovered inodes for deletion",
        last=True,
    )
    deadline_call = next(
        (item for item in recovery.evidence if item.function == "reiserfs_fill_super" and item.line == 2185),
        None,
    )
    deadline_return = next(
        (item for item in recovery.evidence if item.function == "reiserfs_fill_super" and item.line == 2214),
        None,
    )
    return (
        CorrespondenceDimension(
            "object",
            CLOSED if object_key and object_flag else BLOCKED,
            "A reserved persistent save-link keyspace plus the inode save-link flag form the cleanup object.",
            tuple(item for item in (object_key, object_flag) if item),
        ),
        CorrespondenceDimension(
            "relation",
            CLOSED if relation and registration.closed else BLOCKED,
            "The save-link key records the inode object identity and body records its directory identity.",
            (relation,) if relation else (),
        ),
        CorrespondenceDimension(
            "lifecycle",
            CLOSED if registration.closed and settlement.closed and recovery.closed else BLOCKED,
            "Last-link registration, final eviction, journal replay, and mount-time scanning expose the full lifecycle.",
            ((lifecycle,) if lifecycle else ()) + settlement.evidence[:1] + recovery.evidence[3:4],
        ),
        CorrespondenceDimension(
            "authority",
            CLOSED if live_authority and recovery_authority else BLOCKED,
            "reiserfs_evict_inode and synchronous finish_unfinished/iput are explicit deletion authorities.",
            tuple(item for item in (live_authority, recovery_authority) if item),
        ),
        CorrespondenceDimension(
            "deadline",
            CLOSED if recovery.closed and deadline_call and deadline_return else BLOCKED,
            "The synchronous save-link scan is invoked before the successful RW mount return.",
            tuple(item for item in (deadline_call, deadline_return) if item),
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
    expected_rule = fixture.get("expected_rule")
    closed = report.result.value == expected and (
        expected_rule is None or expected_rule in report.violation_rules
    )
    return ReplayResult(
        profile,
        fixture_path,
        expected,
        report.result.value,
        expected_rule,
        tuple(report.violation_rules),
        closed,
    )


def analyze_phase11(manifest: Dict[str, Any]) -> Phase11Assessment:
    load_orphan_binding(manifest["binding"])
    registration, registration_failure = analyze_registration(manifest["source_root"])
    settlement, settlement_failure = analyze_settlement(manifest["source_root"])
    recovery, recovery_failure = analyze_recovery(manifest["source_root"])
    correspondence = assess_correspondence(
        manifest["source_root"], registration, settlement, recovery
    )
    replays = tuple(
        _run_fixture(manifest["protocol"], item["fixture"], item["profile"])
        for item in manifest["replays"]
    )
    return Phase11Assessment(
        registration,
        settlement,
        recovery,
        (registration_failure, settlement_failure, recovery_failure),
        correspondence,
        replays,
    )


def run_manifest(path: str) -> Dict[str, Any]:
    manifest = _load(path)
    preregistration = _load(manifest["preregistration"])
    source_manifest = _load(manifest["source_manifest"])
    preregistration_hash_verified = (
        _sha256(manifest["preregistration"])
        == source_manifest["preregistration_sha256"]
    )
    if not preregistration_hash_verified:
        raise ValueError("Phase 11 preregistration no longer matches source acquisition")
    pre_reveal = _verify_hashes(
        preregistration["pre_reveal_locks"], "Phase 11 pre-reveal"
    )
    artifacts = _verify_hashes(manifest["artifact_hashes"], "Phase 11 artifact")
    sources = _verify_source_manifest(manifest["source_root"], manifest["source_manifest"])
    registered_sources = set(preregistration["registered_target_sources"])
    if set(sources) != registered_sources:
        raise ValueError("Phase 11 source manifest does not match preregistered sources")

    phase9 = run_phase9_manifest(manifest["phase9_manifest"])
    catalog = _load(manifest["heldout_catalog"])
    assessment = analyze_phase11(manifest)
    third_filesystem_post_freeze = (
        preregistration["candidate_status_before_reveal"]
        == "UNREVEALED_POST_COMMON_HELDOUT"
        and manifest["candidate_filesystem"].lower() not in phase9["freeze_members"]
    )
    no_semantic_modifications = all(pre_reveal.values())
    applicability = APPLICABLE if assessment.correspondence_closed else "UNRESOLVED"
    catalog_consistent = (
        catalog["applicability"] == applicability
        and catalog["conformance_decision"] == NON_CONFORMANT_HELDOUT
        and all(
            catalog["correspondence_dimensions"].get(item.dimension) == item.status
            for item in assessment.correspondence
        )
    )
    conformance_decision = (
        NON_CONFORMANT_HELDOUT
        if assessment.nonconformance_proof_closed
        else "UNRESOLVED"
    )
    heldout_gates = {
        "common_freeze_ready": bool(phase9["common_freeze_ready"]),
        "third_filesystem_post_freeze": third_filesystem_post_freeze,
        "heldout_correspondence_closed": assessment.correspondence_closed,
        "heldout_source_witness_closed": assessment.source_witness_closed,
        "heldout_replay_closed": assessment.candidate_conformant,
        "heldout_proof_closure_closed": assessment.candidate_conformant,
        "no_post_freeze_semantic_modifications": no_semantic_modifications,
    }
    common_heldout_validated = all(heldout_gates.values()) and applicability == APPLICABLE
    screening_closed = (
        preregistration_hash_verified
        and all(pre_reveal.values())
        and all(artifacts.values())
        and all(sources.values())
        and phase9["common_freeze_manifest_generated"]
        and assessment.screening_dimensions_decided
        and assessment.source_witness_closed
        and assessment.replay_expectations_closed
        and assessment.nonconformance_proof_closed
        and catalog_consistent
        and applicability == APPLICABLE
        and conformance_decision == NON_CONFORMANT_HELDOUT
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
        "conformance_decision": conformance_decision,
        "preregistration_hash_verified": preregistration_hash_verified,
        "pre_reveal_locks_verified": all(pre_reveal.values()),
        "artifact_hashes_verified": all(artifacts.values()),
        "source_hashes_verified": all(sources.values()),
        "registered_sources_exact": set(sources) == registered_sources,
        "bug_specific_condition_count": count_bug_specific_conditions([manifest]),
        "assessment": assessment.to_dict(),
        "heldout_gates": heldout_gates,
        "failed_heldout_gates": [name for name, closed in heldout_gates.items() if not closed],
        "third_filesystem_post_freeze": third_filesystem_post_freeze,
        "no_post_freeze_semantic_modifications": no_semantic_modifications,
        "phase9_common_freeze_preserved": phase9["common_freeze_manifest_generated"],
        "outcome_dependent_narrowing_rejected": manifest["outcome_dependent_narrowing_rejected"],
        "phase11_screening_closed": screening_closed,
        "candidate_conformant": assessment.candidate_conformant,
        "common_heldout_validated": common_heldout_validated,
        "next_phase_plan": manifest["next_phase_plan"],
        "interpretation": manifest["interpretation"],
    }


def _markdown(summary: Dict[str, Any]) -> str:
    assessment = summary["assessment"]
    lines = [
        "# OIDS Phase 11 ReiserFS Post-COMMON Held-out Evaluation",
        "",
        f"Manifest: `{summary['manifest']}`",
        "",
        f"Applicability: `{summary['applicability']}`",
        f"Conformance decision: `{summary['conformance_decision']}`",
        f"Screening closed: `{summary['phase11_screening_closed']}`",
        f"Candidate conformant: `{summary['candidate_conformant']}`",
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
    lines.extend(["", "## Failure partitions", "", "| Profile | Stage | Result | Rule |", "|---|---|---|---|"])
    for item in assessment["failure_partitions"]:
        lines.append(
            f"| {item['profile']} | {item['stage']} | `{item['expected_result']}` | {item['expected_rule'] or '-'} |"
        )
    lines.extend(["", "## Correspondence", "", "| Dimension | Status | Closed |", "|---|---|---|"])
    for item in assessment["correspondence"]:
        lines.append(f"| {item['dimension']} | `{item['status']}` | `{item['closed']}` |")
    lines.extend(["", "## Replay", "", "| Profile | Expected | Actual | Closed |", "|---|---|---|---|"])
    for item in assessment["replays"]:
        lines.append(
            f"| {item['profile']} | `{item['expected']}` | `{item['actual']}` | `{item['closed']}` |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            summary["interpretation"],
            "",
            "Outcome-dependent narrowing rejected: "
            + summary["outcome_dependent_narrowing_rejected"],
            "",
            "Next phase: " + summary["next_phase_plan"],
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
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.orphan_phase11")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    args = parser.parse_args(argv)
    summary = run_and_write(args.manifest, args.json_out, args.markdown_out)
    print(
        f"applicability={summary['applicability']} "
        f"decision={summary['conformance_decision']} "
        f"screening_closed={summary['phase11_screening_closed']} "
        f"common_heldout={summary['common_heldout_validated']}"
    )
    return 0 if summary["phase11_screening_closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
