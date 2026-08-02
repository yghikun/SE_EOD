from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .c_cfg import FunctionCFG, build_function_cfg
from .orphan_candidate import run_manifest as run_phase3_manifest
from .report import count_bug_specific_conditions, write_json, write_markdown
from .scope import assess_scope, load_taxonomy


CLOSED = "CLOSED"
BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class SourceLocation:
    source: str
    function: str
    line: int
    node_id: int
    fact: str


@dataclass(frozen=True)
class ClauseProof:
    clause_id: str
    status: str
    conclusion: str
    evidence: Tuple[SourceLocation, ...] = ()
    assumptions: Tuple[str, ...] = ()
    blockers: Tuple[str, ...] = ()

    @property
    def closed(self) -> bool:
        return self.status == CLOSED and not self.blockers


@dataclass(frozen=True)
class RegistrationCFGProof:
    filesystem: str
    clauses: Tuple[ClauseProof, ...]

    @property
    def closed(self) -> bool:
        return all(clause.closed for clause in self.clauses)


@dataclass(frozen=True)
class SettlementCFGProof:
    filesystem: str
    clauses: Tuple[ClauseProof, ...]

    @property
    def closed(self) -> bool:
        return all(clause.closed for clause in self.clauses)


@dataclass(frozen=True)
class RecoveryCFGProof:
    filesystem: str
    clauses: Tuple[ClauseProof, ...]

    @property
    def closed(self) -> bool:
        return all(clause.closed for clause in self.clauses)


@dataclass(frozen=True)
class OIDSAllPathWitness:
    filesystem: str
    registration: RegistrationCFGProof
    settlement: SettlementCFGProof
    recovery: RecoveryCFGProof

    @property
    def closed(self) -> bool:
        return self.registration.closed and self.settlement.closed and self.recovery.closed

    @property
    def blockers(self) -> Tuple[str, ...]:
        values: List[str] = []
        for stage in (self.registration, self.settlement, self.recovery):
            for clause in stage.clauses:
                for blocker in clause.blockers:
                    if blocker not in values:
                        values.append(blocker)
        return tuple(values)

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        for name, stage in (
            ("registration", self.registration),
            ("settlement", self.settlement),
            ("recovery", self.recovery),
        ):
            result[name]["closed"] = stage.closed
        result["closed"] = self.closed
        result["blockers"] = list(self.blockers)
        return result


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _verify_artifacts(values: Dict[str, str]) -> Dict[str, bool]:
    result: Dict[str, bool] = {}
    for path, expected in values.items():
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(f"OIDS Phase 4 artifact hash mismatch for {path}: {actual} != {expected}")
        result[path] = True
    return result


def cfg_proof_blockers(cfgs: Iterable[FunctionCFG]) -> Tuple[str, ...]:
    blockers: List[str] = []
    for cfg in cfgs:
        if cfg.parse_has_error:
            blockers.append(f"CFG_PARSE_ERROR:{cfg.function_name}")
        if cfg.unresolved_gotos:
            blockers.append(f"CFG_UNRESOLVED_GOTO:{cfg.function_name}")
    return tuple(blockers)


def _node_for_call(
    cfg: FunctionCFG,
    name: str,
    *,
    earliest: bool = True,
    line_at_least: int = 0,
) -> Optional[int]:
    nodes = [node for node in cfg.find_calls([name]) if cfg.nodes[node].line >= line_at_least]
    if not nodes:
        return None
    return min(nodes, key=lambda node: cfg.nodes[node].line) if earliest else max(
        nodes, key=lambda node: cfg.nodes[node].line
    )


def _location(cfg: FunctionCFG, node: int, fact: str) -> SourceLocation:
    return SourceLocation(cfg.source_path, cfg.function_name, cfg.nodes[node].line, node, fact)


def _missing(*values: Tuple[str, Optional[int]]) -> Tuple[str, ...]:
    return tuple(f"CFG_CALL_NOT_FOUND:{name}" for name, node in values if node is None)


def _clause(
    clause_id: str,
    condition: bool,
    conclusion: str,
    evidence: Iterable[SourceLocation] = (),
    assumptions: Iterable[str] = (),
    blockers: Iterable[str] = (),
) -> ClauseProof:
    reasons = tuple(blockers)
    status = CLOSED if condition and not reasons else BLOCKED
    return ClauseProof(
        clause_id=clause_id,
        status=status,
        conclusion=conclusion,
        evidence=tuple(evidence),
        assumptions=tuple(assumptions),
        blockers=reasons,
    )


def _find_condition(cfg: FunctionCFG, markers: Iterable[str]) -> Optional[int]:
    wanted = tuple(markers)
    return next(
        (
            node_id
            for node_id, node in cfg.nodes.items()
            if node.kind in {"condition", "loop_condition"}
            and all(marker in node.text for marker in wanted)
        ),
        None,
    )


def _btrfs_registration(source: str, caller: str, helper: str) -> RegistrationCFGProof:
    unlink = build_function_cfg(source, caller)
    orphan_add = build_function_cfg(source, helper)
    health = cfg_proof_blockers((unlink, orphan_add))
    zero = _find_condition(unlink, ("i_nlink", "== 0"))
    add = _node_for_call(unlink, "btrfs_orphan_add")
    end = _node_for_call(unlink, "btrfs_end_transaction")
    missing = _missing(("zero_link_condition", zero), ("btrfs_orphan_add", add), ("btrfs_end_transaction", end))
    ordering = False
    evidence: List[SourceLocation] = []
    if zero is not None and add is not None and end is not None:
        branch = unlink.branch_successor(zero, "true")
        ordering = bool(
            branch is not None
            and add in unlink.reachable(branch)
            and unlink.dominates(add, end, root=branch)
            and unlink.dominates(end, unlink.exit, root=branch)
        )
        evidence = [
            _location(unlink, zero, "zero-link registration guard"),
            _location(unlink, add, "persistent orphan registration on the zero-link branch"),
            _location(unlink, end, "registration transaction settlement"),
        ]
    caller_clause = _clause(
        "OIDS-BTRFS-R1",
        ordering,
        "Every zero-link unlink path reaches orphan registration before transaction settlement.",
        evidence,
        blockers=(*health, *missing, *( () if ordering else ("ZERO_LINK_DOMINANCE_NOT_PROVEN",) )),
    )

    insert = _node_for_call(orphan_add, "btrfs_insert_orphan_item")
    abort = _node_for_call(orphan_add, "btrfs_abort_transaction")
    failure = _find_condition(orphan_add, ("ret", "-EEXIST"))
    helper_missing = _missing(
        ("btrfs_insert_orphan_item", insert),
        ("btrfs_abort_transaction", abort),
        ("registration_failure_condition", failure),
    )
    contained = False
    helper_evidence: List[SourceLocation] = []
    if insert is not None and abort is not None and failure is not None:
        failure_root = orphan_add.branch_successor(failure, "true")
        contained = bool(
            failure_root is not None
            and abort in orphan_add.reachable(failure_root)
            and orphan_add.dominates(abort, orphan_add.exit, root=failure_root)
        )
        helper_evidence = [
            _location(orphan_add, insert, "persistent orphan item insertion"),
            _location(orphan_add, failure, "non-idempotent insertion failure partition"),
            _location(orphan_add, abort, "failed registration aborts the transaction"),
        ]
    containment_clause = _clause(
        "OIDS-BTRFS-R2",
        contained,
        "A non-EEXIST registration failure cannot settle as a successful transaction.",
        helper_evidence,
        assumptions=("-EEXIST denotes an already accepted root-scoped orphan item",),
        blockers=(*health, *helper_missing, *( () if contained else ("REGISTRATION_ABORT_DOMINANCE_NOT_PROVEN",) )),
    )
    return RegistrationCFGProof("btrfs", (caller_clause, containment_clause))


def _btrfs_settlement(source: str, function: str) -> SettlementCFGProof:
    cfg = build_function_cfg(source, function)
    health = cfg_proof_blockers((cfg,))
    truncate = _node_for_call(cfg, "btrfs_truncate_inode_items")
    orphan_del = _node_for_call(cfg, "btrfs_orphan_del")
    end_nodes = cfg.find_calls(["btrfs_end_transaction"])
    prior = next((node for node in end_nodes if orphan_del is not None and cfg.nodes[node].line < cfg.nodes[orphan_del].line), None)
    removal_end = next((node for node in end_nodes if orphan_del is not None and cfg.nodes[node].line > cfg.nodes[orphan_del].line), None)
    missing = _missing(
        ("btrfs_truncate_inode_items", truncate),
        ("btrfs_orphan_del", orphan_del),
        ("prior_btrfs_end_transaction", prior),
        ("removal_btrfs_end_transaction", removal_end),
    )
    ordered = bool(
        truncate is not None
        and prior is not None
        and orphan_del is not None
        and removal_end is not None
        and cfg.dominates(truncate, orphan_del)
        and cfg.dominates(prior, orphan_del)
        and cfg.dominates(orphan_del, removal_end)
        and cfg.dominates(removal_end, cfg.exit, root=orphan_del)
    )
    evidence = []
    if all(node is not None for node in (truncate, prior, orphan_del, removal_end)):
        evidence = [
            _location(cfg, truncate, "terminal inode-item truncation"),
            _location(cfg, prior, "terminal deletion transaction settles before registry removal"),
            _location(cfg, orphan_del, "persistent orphan item removal attempt"),
            _location(cfg, removal_end, "orphan removal transaction settlement"),
        ]
    clause = _clause(
        "OIDS-BTRFS-S1",
        ordered,
        "Every persistent orphan-removal attempt is preceded by settled terminal deletion and is transaction bounded.",
        evidence,
        assumptions=("A failed orphan deletion retains the registry item for mount-time retry.",),
        blockers=(*health, *missing, *( () if ordered else ("SETTLEMENT_DOMINANCE_NOT_PROVEN",) )),
    )
    return SettlementCFGProof("btrfs", (clause,))


def _btrfs_recovery(
    cleanup_source: str,
    cleanup_function: str,
    exposure_source: str,
    gate_function: str,
    exposure_function: str,
) -> RecoveryCFGProof:
    cleanup = build_function_cfg(cleanup_source, cleanup_function)
    gate = build_function_cfg(exposure_source, gate_function)
    exposure = build_function_cfg(exposure_source, exposure_function)
    health = cfg_proof_blockers((cleanup, gate, exposure))
    dispatch = _node_for_call(cleanup, "iput")
    cleanup_calls = gate.find_calls(["btrfs_orphan_cleanup"])
    cleanup_invocations = (
        [call for call in gate.nodes[cleanup_calls[0]].calls if call.name == "btrfs_orphan_cleanup"]
        if len(cleanup_calls) == 1
        else []
    )
    cleanup_arguments = {call.arguments[0] for call in cleanup_invocations if call.arguments}
    both_roots_gated = cleanup_arguments == {"fs_info->fs_root", "fs_info->tree_root"}
    gate_call = _node_for_call(exposure, gate_function)
    exposure_nodes = [
        node
        for node in exposure.find_calls(["set_bit"])
        if "BTRFS_FS_OPEN" in exposure.nodes[node].text
    ]
    marker = exposure_nodes[0] if len(exposure_nodes) == 1 else None
    missing = _missing(
        ("iput", dispatch),
        ("btrfs_orphan_cleanup", cleanup_calls[0] if cleanup_calls else None),
        (gate_function, gate_call),
        ("set_bit(BTRFS_FS_OPEN)", marker),
    )
    ordered = bool(
        dispatch is not None
        and len(cleanup_calls) == 1
        and both_roots_gated
        and gate_call is not None
        and marker is not None
        and exposure.dominates(gate_call, marker)
    )
    evidence: List[SourceLocation] = []
    if dispatch is not None:
        evidence.append(_location(cleanup, dispatch, "zero-link inode dispatches final eviction"))
    if cleanup_calls:
        evidence.append(_location(gate, cleanup_calls[0], "both Btrfs roots are cleaned before successful gate return"))
    if gate_call is not None:
        evidence.append(_location(exposure, gate_call, "pre-RW mount gate"))
    if marker is not None:
        evidence.append(_location(exposure, marker, "successful RW exposure marker"))
    clause = _clause(
        "OIDS-BTRFS-C1",
        ordered,
        "Successful RW exposure is dominated by a successful orphan-cleanup gate.",
        evidence,
        assumptions=("The exposure scope is the RW BTRFS_FS_OPEN transition, not the read-only early return.",),
        blockers=(*health, *missing, *( () if ordered else ("RECOVERY_EXPOSURE_DOMINANCE_NOT_PROVEN",) )),
    )
    return RecoveryCFGProof("btrfs", (clause,))


def _ext4_registration(source: str, caller: str, helper_source: str, helper: str) -> RegistrationCFGProof:
    unlink = build_function_cfg(source, caller)
    orphan_add = build_function_cfg(helper_source, helper)
    health = cfg_proof_blockers((unlink, orphan_add))
    zero = _find_condition(unlink, ("!inode->i_nlink",))
    add = _node_for_call(unlink, "ext4_orphan_add")
    stop = _node_for_call(unlink, "ext4_journal_stop")
    structural = bool(zero is not None and add is not None and stop is not None)
    evidence = []
    if structural:
        evidence = [
            _location(unlink, zero, "zero-link registration guard"),
            _location(unlink, add, "orphan registration return value is discarded"),
            _location(unlink, stop, "caller stops the unlink handle"),
        ]
    clause = _clause(
        "OIDS-EXT4-R1",
        False,
        "The zero-link call is present, but every ignored registration error is not yet proven to abort the same handle.",
        evidence,
        blockers=(
            *health,
            *_missing(("zero_link_condition", zero), ("ext4_orphan_add", add), ("ext4_journal_stop", stop)),
            "EXT4_REGISTRATION_RETURN_IGNORED",
            "EXT4_ORPHAN_ADD_ERROR_CONTAINMENT_NOT_CLOSED",
        ),
    )
    return RegistrationCFGProof("ext4", (clause,))


def _ext4_settlement(source: str, function: str) -> SettlementCFGProof:
    cfg = build_function_cfg(source, function)
    health = cfg_proof_blockers((cfg,))
    persistent_del = next(
        (
            node
            for node in cfg.find_calls(["ext4_orphan_del"])
            if cfg.nodes[node].calls
            and any(call.name == "ext4_orphan_del" and call.arguments and call.arguments[0] == "handle" for call in cfg.nodes[node].calls)
        ),
        None,
    )
    free_inode = _node_for_call(cfg, "ext4_free_inode")
    final_stop = _node_for_call(cfg, "ext4_journal_stop", earliest=False)
    same_handle = False
    evidence: List[SourceLocation] = []
    if persistent_del is not None and free_inode is not None and final_stop is not None:
        same_handle = bool(
            cfg.dominates(persistent_del, free_inode)
            and cfg.dominates(persistent_del, final_stop)
            and all(
                any(call.name == name and call.arguments and call.arguments[0] == "handle" for call in cfg.nodes[node].calls)
                for node, name in (
                    (persistent_del, "ext4_orphan_del"),
                    (free_inode, "ext4_free_inode"),
                    (final_stop, "ext4_journal_stop"),
                )
            )
        )
        evidence = [
            _location(cfg, persistent_del, "persistent orphan removal uses handle"),
            _location(cfg, free_inode, "terminal inode free uses the same handle"),
            _location(cfg, final_stop, "settlement uses the same handle"),
        ]
    structure_clause = _clause(
        "OIDS-EXT4-S1",
        same_handle,
        "The successful free branch co-settles registry removal and inode free on one handle.",
        evidence,
        blockers=(*health, *_missing(("ext4_orphan_del(handle)", persistent_del), ("ext4_free_inode", free_inode), ("ext4_journal_stop", final_stop)), *( () if same_handle else ("EXT4_SAME_HANDLE_DOMINANCE_NOT_PROVEN",) )),
    )
    error_clause = _clause(
        "OIDS-EXT4-S2",
        False,
        "Ignored orphan-del and mark-dirty errors are not yet proven to prevent a removal-only commit on every helper branch.",
        evidence,
        blockers=(
            *health,
            "EXT4_ORPHAN_DEL_RETURN_IGNORED",
            "EXT4_MARK_DIRTY_FAILURE_ABORT_CONTRACT_NOT_CLOSED",
        ),
    )
    return SettlementCFGProof("ext4", (structure_clause, error_clause))


def _ext4_recovery(
    cleanup_source: str,
    cleanup_function: str,
    exposure_source: str,
    exposure_function: str,
) -> RecoveryCFGProof:
    cleanup = build_function_cfg(cleanup_source, cleanup_function)
    exposure = build_function_cfg(exposure_source, exposure_function)
    health = cfg_proof_blockers((cleanup, exposure))
    dispatch = _node_for_call(cleanup, "ext4_process_orphan")
    cleanup_call = _node_for_call(exposure, cleanup_function)
    marker = _node_for_call(exposure, "ext4_mark_recovery_complete")
    dominance = bool(
        cleanup_call is not None
        and marker is not None
        and exposure.dominates(cleanup_call, marker)
    )
    evidence: List[SourceLocation] = []
    if dispatch is not None:
        evidence.append(_location(cleanup, dispatch, "selected valid orphan dispatch"))
    if cleanup_call is not None:
        evidence.append(_location(exposure, cleanup_call, "void orphan-cleanup call"))
    if marker is not None:
        evidence.append(_location(exposure, marker, "recovery completion marker"))
    clause = _clause(
        "OIDS-EXT4-C1",
        False,
        "Syntactic call dominance does not close per-inode recovery because cleanup is void and contains skip/error exits.",
        evidence,
        assumptions=(f"syntactic_cleanup_dominance={dominance}",),
        blockers=(
            *health,
            *_missing(("ext4_process_orphan", dispatch), (cleanup_function, cleanup_call), ("ext4_mark_recovery_complete", marker)),
            "EXT4_VOID_CLEANUP_HAS_NO_SUCCESS_OUTCOME",
            "EXT4_RECOVERY_SKIP_AND_ERROR_PATHS_UNPARTITIONED",
        ),
    )
    return RecoveryCFGProof("ext4", (clause,))


def analyze_filesystem(config: Dict[str, Any]) -> OIDSAllPathWitness:
    filesystem = config["filesystem"]
    registration = config["registration"]
    settlement = config["settlement"]
    recovery = config["recovery"]
    if filesystem == "btrfs":
        return OIDSAllPathWitness(
            filesystem,
            _btrfs_registration(registration["source"], registration["caller"], registration["helper"]),
            _btrfs_settlement(settlement["source"], settlement["function"]),
            _btrfs_recovery(
                recovery["cleanup_source"],
                recovery["cleanup_function"],
                recovery["exposure_source"],
                recovery["gate_function"],
                recovery["exposure_function"],
            ),
        )
    if filesystem == "ext4":
        return OIDSAllPathWitness(
            filesystem,
            _ext4_registration(
                registration["source"],
                registration["caller"],
                registration["helper_source"],
                registration["helper"],
            ),
            _ext4_settlement(settlement["source"], settlement["function"]),
            _ext4_recovery(
                recovery["cleanup_source"],
                recovery["cleanup_function"],
                recovery["exposure_source"],
                recovery["exposure_function"],
            ),
        )
    raise ValueError(f"unsupported OIDS all-path filesystem: {filesystem}")


def run_manifest(path: str) -> Dict[str, Any]:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    artifact_locks = _verify_artifacts(manifest["artifact_hashes"])
    phase3 = run_phase3_manifest(manifest["phase3_manifest"])
    witnesses = [analyze_filesystem(config) for config in manifest["filesystems"]]
    declaration = json.loads(json.dumps(phase3["scope_declaration"]))
    by_filesystem = {witness.filesystem: witness for witness in witnesses}
    for filesystem in declaration["filesystems"]:
        filesystem["proof_closure_closed"] = by_filesystem[filesystem["filesystem"]].closed
    declaration["hashes_locked"]["test"] = artifact_locks.get(manifest["test_artifact"], False)
    assessment = assess_scope(load_taxonomy(manifest["taxonomy"]), declaration)
    witness_values = [witness.to_dict() for witness in witnesses]
    return {
        "schema_version": 1,
        "evaluation_id": manifest["evaluation_id"],
        "manifest": path,
        "manifest_sha256": _sha256(path),
        "phase3_manifest": manifest["phase3_manifest"],
        "phase3_manifest_sha256": _sha256(manifest["phase3_manifest"]),
        "artifact_hashes_verified": all(artifact_locks.values()),
        "bug_specific_condition_count": count_bug_specific_conditions([manifest]),
        "helper_contract_audit": manifest.get("helper_contract_audit", []),
        "filesystems": witness_values,
        "proof_closure_closed_per_filesystem": all(witness.closed for witness in witnesses),
        "scope_declaration": declaration,
        "scope_assessment": assessment.to_dict(),
        "freeze_manifest_generated": False,
        "interpretation": manifest["interpretation"],
    }


def _markdown(summary: Dict[str, Any]) -> str:
    assessment = summary["scope_assessment"]
    lines = [
        "# OIDS Phase 4 CFG / All-Path Proof Closure",
        "",
        f"Manifest: `{summary['manifest']}`",
        "",
        f"Common candidate ready: `{assessment['common_candidate_ready']}`",
        f"Common freeze ready: `{assessment['common_freeze_ready']}`",
        f"Per-filesystem proof closure: `{summary['proof_closure_closed_per_filesystem']}`",
        "",
        "## Clause results",
        "",
        "| Filesystem | Stage | Clause | Status | Conclusion |",
        "|---|---|---|---|---|",
    ]
    for filesystem in summary["filesystems"]:
        for stage_name in ("registration", "settlement", "recovery"):
            for clause in filesystem[stage_name]["clauses"]:
                lines.append(
                    f"| {filesystem['filesystem']} | {stage_name} | `{clause['clause_id']}` | `{clause['status']}` | {clause['conclusion']} |"
                )
    lines.extend(["", "## Remaining blockers", ""])
    for filesystem in summary["filesystems"]:
        blockers = filesystem["blockers"]
        lines.append(
            f"- {filesystem['filesystem']}: "
            + (", ".join(f"`{blocker}`" for blocker in blockers) if blockers else "none")
        )
    lines.extend(
        [
            "",
            "## Freeze decision",
            "",
            f"Failed gates: {', '.join(f'`{gate}`' for gate in assessment['failed_freeze_gates']) or 'none'}",
            "",
            summary["interpretation"],
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
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.orphan_allpath")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    args = parser.parse_args(argv)
    summary = run_and_write(args.manifest, args.json_out, args.markdown_out)
    assessment = summary["scope_assessment"]
    print(
        f"candidate_ready={assessment['common_candidate_ready']} "
        f"freeze_ready={assessment['common_freeze_ready']} "
        f"all_filesystems_closed={summary['proof_closure_closed_per_filesystem']}"
    )
    return 0 if assessment["common_candidate_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
