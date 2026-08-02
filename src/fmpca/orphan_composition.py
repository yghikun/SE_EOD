from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .frontend_orphan_common import (
    OrphanBinding,
    RecoveryWitness,
    RegistrationWitness,
    SettlementWitness,
)
from .model import AnalysisResult, EvidenceEvent, Precision, Truth
from .proof import AnalysisReport, analyze_state
from .semantics_extensions import ProtocolDeadlineEngine
from .dsl import ProtocolSpec


class OIDSCompositionError(ValueError):
    pass


@dataclass(frozen=True)
class OIDSIdentity:
    filesystem: str
    inode: str
    namespace_entry: str
    orphan_registry: str
    filesystem_mount: str
    inode_allocation_generation: str

    @property
    def semantic_key(self) -> Tuple[str, str, str, str]:
        return (
            self.filesystem,
            self.inode,
            self.filesystem_mount,
            self.inode_allocation_generation,
        )


@dataclass(frozen=True)
class OIDSComposition:
    filesystem: str
    mode: str
    semantic_key: Tuple[str, str, str, str]
    events: List[EvidenceEvent]
    selected_path_closed: bool
    all_paths_closed: bool
    acceptance_true: bool
    report: AnalysisReport

    def to_dict(self) -> Dict[str, Any]:
        return {
            "filesystem": self.filesystem,
            "mode": self.mode,
            "semantic_key": list(self.semantic_key),
            "events": [event.to_dict() for event in self.events],
            "selected_path_closed": self.selected_path_closed,
            "all_paths_closed": self.all_paths_closed,
            "acceptance_true": self.acceptance_true,
            "analysis_result": self.report.result.value,
            "violation_rules": list(self.report.violation_rules),
            "unknown_rules": list(self.report.unknown_rules),
            "coverage": dict(self.report.coverage),
        }


def _event(
    name: str,
    roles: Dict[str, str],
    epoch: Dict[str, Any],
    source_path: str,
    line: Optional[int],
    *,
    data: Optional[Dict[str, Any]] = None,
) -> EvidenceEvent:
    return EvidenceEvent(
        event=name,
        roles=roles,
        epoch=epoch,
        data=data or {},
        source={"file": source_path, "line": line or "?"},
        precision=Precision.EXACT,
    )


def compose_source_lifecycle(
    spec: ProtocolSpec,
    binding: OrphanBinding,
    registration: RegistrationWitness,
    settlement: SettlementWitness,
    registration_identity: OIDSIdentity,
    settlement_identity: OIDSIdentity,
    *,
    mode: str = "normal",
    recovery: Optional[RecoveryWitness] = None,
) -> OIDSComposition:
    if mode not in {"normal", "recovery"}:
        raise OIDSCompositionError(f"unsupported OIDS composition mode: {mode}")
    if registration_identity.semantic_key != settlement_identity.semantic_key:
        raise OIDSCompositionError(
            "registration and settlement identities do not denote one inode epoch"
        )
    if registration_identity.orphan_registry != settlement_identity.orphan_registry:
        raise OIDSCompositionError("orphan registry identity changed across operations")
    if mode == "recovery" and recovery is None:
        raise OIDSCompositionError("recovery mode requires a recovery witness")

    identity = registration_identity
    instance = ":".join(identity.semantic_key)
    base_roles = {
        "operation": f"oids-instance:{instance}",
        "filesystem": identity.filesystem,
        "inode": identity.inode,
        "namespace_entry": identity.namespace_entry,
        "orphan_registry": identity.orphan_registry,
    }
    epoch = {
        "filesystem_mount": identity.filesystem_mount,
        "inode_allocation_generation": identity.inode_allocation_generation,
        "operation_root": f"oids-instance:{instance}",
        "retry_generation": 0,
    }
    registration_roles = {
        **base_roles,
        "registration_transaction": f"registration:{instance}",
    }
    settlement_roles = {
        **base_roles,
        "settlement_transaction": f"settlement:{instance}",
    }
    reg_lines = registration.evidence_lines
    settle_lines = settlement.evidence_lines
    events = [
        _event(
            "InitializeOrphanDeletion",
            base_roles,
            epoch,
            registration.source_path,
            reg_lines["namespace_transition"],
        ),
        _event(
            "LastLinkRemoved",
            registration_roles,
            epoch,
            registration.source_path,
            reg_lines["link_count_transition"],
        ),
        _event(
            "OrphanRegistryAccepted",
            registration_roles,
            epoch,
            registration.source_path,
            reg_lines["registry_acceptance"],
        ),
        _event(
            "RegistrationTransactionCommit",
            registration_roles,
            epoch,
            registration.source_path,
            reg_lines["transaction_settlement"],
        ),
    ]

    if mode == "normal":
        events.append(
            _event(
                "FinalReferenceReleased",
                {**base_roles, "deletion_authority": f"{binding.filesystem}:eviction"},
                epoch,
                settlement.source_path,
                settle_lines["terminal_deletion"],
            )
        )
    else:
        assert recovery is not None
        events.append(
            _event(
                "RecoveryAuthorityAccepted",
                {**base_roles, "deletion_authority": f"{binding.filesystem}:recovery"},
                epoch,
                recovery.cleanup_source_path,
                recovery.evidence_lines["cleanup_dispatch"],
            )
        )

    events.append(
        _event(
            "TerminalDeletionPrepared",
            settlement_roles if settlement.same_transaction_equivalence else base_roles,
            epoch,
            settlement.source_path,
            settle_lines["terminal_deletion"],
        )
    )
    if settlement.deletion_durable_before_removal:
        events.append(
            _event(
                "TerminalDeletionDurable",
                base_roles,
                epoch,
                settlement.source_path,
                settle_lines["transaction_settlement"],
            )
        )
    events.extend(
        [
            _event(
                "OrphanRegistryRemoval",
                settlement_roles,
                epoch,
                settlement.source_path,
                settle_lines["registry_removal"],
                data={
                    "same_transaction": settlement.same_transaction_equivalence
                },
            ),
            _event(
                "SettlementTransactionCommit",
                settlement_roles,
                epoch,
                settlement.source_path,
                settle_lines["transaction_settlement"],
            ),
        ]
    )
    if mode == "recovery":
        assert recovery is not None
        events.append(
            _event(
                "RecoveryExposure",
                base_roles,
                epoch,
                recovery.exposure_source_path,
                recovery.evidence_lines["recovery_exposure"],
            )
        )
    events.append(
        _event(
            "OperationReturn",
            base_roles,
            epoch,
            settlement.source_path,
            settle_lines["transaction_settlement"],
        )
    )

    selected_closed = bool(
        registration.registration_safe
        and settlement.removal_safe
        and (mode == "normal" or (recovery and recovery.recovery_path_closed))
    )
    state = ProtocolDeadlineEngine(spec).run(events)
    report = analyze_state(
        state,
        path_model_closed=selected_closed,
        all_paths_closed=False,
        repair_slice_closed=selected_closed,
        alias_closed=True,
    )
    acceptance = [
        check
        for check in state.checks
        if check.rule_id == "ACCEPTANCE@AT_SETTLEMENT"
    ]
    acceptance_true = bool(acceptance) and acceptance[-1].truth == Truth.TRUE
    if selected_closed and report.result not in {
        AnalysisResult.INCOMPLETE,
        AnalysisResult.CONFORMANT,
    }:
        raise OIDSCompositionError("closed source composition violates the candidate spec")
    return OIDSComposition(
        filesystem=binding.filesystem,
        mode=mode,
        semantic_key=identity.semantic_key,
        events=events,
        selected_path_closed=selected_closed,
        all_paths_closed=False,
        acceptance_true=acceptance_true,
        report=report,
    )
