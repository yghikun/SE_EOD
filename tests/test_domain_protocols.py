import json
import unittest
from pathlib import Path

from src.fmpca.dsl import load_protocol
from src.fmpca.frontend import (
    analyze_source,
    load_binding,
)
from src.fmpca.model import AnalysisResult, EvidenceEvent
from src.fmpca.proof import analyze_state
from src.fmpca.semantics import ProtocolEngine


ROOT = Path(__file__).resolve().parents[1]


def run_fixture(protocol_name: str, fixture_name: str):
    protocol = load_protocol(str(ROOT / "configs/protocols" / protocol_name))
    fixture = json.loads((ROOT / "tests/fixtures/events" / fixture_name).read_text(encoding="utf-8"))
    state = ProtocolEngine(protocol).run(EvidenceEvent.from_dict(item) for item in fixture["events"])
    closure = fixture["closure"]
    return state, analyze_state(
        state,
        path_model_closed=closure["path_model_closed"],
        all_paths_closed=closure["all_paths_closed"],
        repair_slice_closed=closure["repair_slice_closed"],
        alias_closed=closure["alias_closed"],
    )


class DomainProtocolTests(unittest.TestCase):
    def test_recovery_attachment_bug_fixed_and_delegated_paths(self):
        _, bug = run_fixture("recovery-attachment-settlement-v0.2.json", "ras-bug.json")
        _, fixed = run_fixture("recovery-attachment-settlement-v0.2.json", "ras-fixed.json")
        _, delegated = run_fixture("recovery-attachment-settlement-v0.2.json", "ras-safe-delegated.json")
        self.assertEqual(bug.result, AnalysisResult.VIOLATION)
        self.assertEqual(fixed.result, AnalysisResult.CONFORMANT)
        self.assertEqual(delegated.result, AnalysisResult.CONFORMANT)

    def test_device_topology_bug_fixed_and_exposure_paths(self):
        _, bug = run_fixture("device-topology-rollback-v0.2.json", "dtr-bug.json")
        _, fixed = run_fixture("device-topology-rollback-v0.2.json", "dtr-fixed.json")
        _, exposure = run_fixture("device-topology-rollback-v0.2.json", "dtr-exposure.json")
        self.assertEqual(bug.result, AnalysisResult.VIOLATION)
        self.assertEqual(fixed.result, AnalysisResult.CONFORMANT)
        self.assertEqual(exposure.result, AnalysisResult.VIOLATION)
        self.assertEqual(exposure.state.irreversible_violation_evidence[0]["code"], "INVALID_DEVICE_TARGET_EXPOSED")

    def test_domain_delegation_and_unknown_paths(self):
        _, ras_delegated = run_fixture("recovery-attachment-settlement-v0.2.json", "ras-safe-delegated.json")
        _, ras_unknown = run_fixture("recovery-attachment-settlement-v0.2.json", "ras-unknown.json")
        _, dtr_delegated = run_fixture("device-topology-rollback-v0.2.json", "dtr-delegated-safe.json")
        _, dtr_unknown = run_fixture("device-topology-rollback-v0.2.json", "dtr-unknown.json")
        self.assertEqual(ras_delegated.result, AnalysisResult.CONFORMANT)
        self.assertEqual(dtr_delegated.result, AnalysisResult.CONFORMANT)
        self.assertEqual(ras_unknown.result, AnalysisResult.INCOMPLETE)
        self.assertEqual(dtr_unknown.result, AnalysisResult.INCOMPLETE)

    def test_domain_specific_release_and_owner_deadlines(self):
        ras_state, ras = run_fixture("recovery-attachment-settlement-v0.2.json", "ras-owner-termination-violation.json")
        dtr_state, dtr = run_fixture("device-topology-rollback-v0.2.json", "dtr-release-violation.json")
        fixed_state, fixed = run_fixture("device-topology-rollback-v0.2.json", "dtr-release-fixed.json")
        self.assertEqual(ras.result, AnalysisResult.VIOLATION)
        self.assertIn("AT_SETTLEMENT", ras_state.reached_deadlines)
        self.assertIn("BEFORE_OWNER_TERMINATION", ras_state.reached_deadlines)
        self.assertEqual(dtr.result, AnalysisResult.VIOLATION)
        self.assertIn("DTR-I3", dtr.violation_rules)
        self.assertIn("BEFORE_RELEASE", dtr_state.reached_deadlines)
        self.assertEqual(fixed.result, AnalysisResult.CONFORMANT)
        self.assertIn("BEFORE_RELEASE", fixed_state.reached_deadlines)

    def test_recovery_attachment_source_is_domain_bound(self):
        protocol = load_protocol(str(ROOT / "configs/protocols/recovery-attachment-settlement-v0.2.json"))
        binding = load_binding(str(ROOT / "configs/bindings/recovery-attachment-settlement-v0.2.json"))
        analysis = analyze_source(
            binding,
            str(ROOT / "linux-sources/linux-v6.8-fs/fs/btrfs/relocation.c"),
            "btrfs_recover_relocation",
            "linux-v6.8",
        )
        state = ProtocolEngine(protocol).run(analysis.events)
        report = analyze_state(state, path_model_closed=analysis.path_model_closed, repair_slice_closed=analysis.repair_slice_closed)
        self.assertEqual(report.result, AnalysisResult.VIOLATION)
        self.assertEqual([event.event for event in analysis.events], ["RecoveryPrestate", "RecoveryAttachment", "RecoveryFailure", "OperationReturn"])
        self.assertEqual(analysis.evidence[0]["field_path"], "root.reloc_root")

    def test_device_topology_source_reports_relation_witnesses(self):
        protocol = load_protocol(str(ROOT / "configs/protocols/device-topology-rollback-v0.2.json"))
        binding = load_binding(str(ROOT / "configs/bindings/device-topology-rollback-v0.2.json"))
        analysis = analyze_source(
            binding,
            str(ROOT / "linux-sources/linux-v6.14-fs/fs/btrfs/volumes.c"),
            "btrfs_init_new_device",
            "linux-v6.14",
        )
        state = ProtocolEngine(protocol).run(analysis.events)
        report = analyze_state(state, path_model_closed=analysis.path_model_closed, repair_slice_closed=analysis.repair_slice_closed)
        self.assertEqual(report.result, AnalysisResult.VIOLATION)
        relations = {item["relation"] for item in analysis.evidence if item["kind"] == "domain_relation_mutation"}
        self.assertEqual(relations, {"topology.device_membership", "topology.active_device", "topology.fsid_identity"})
        self.assertTrue(any(item["restore_found"] for item in analysis.evidence if item["kind"] == "domain_repair_slice"))
        self.assertTrue(any(not item["restore_found"] for item in analysis.evidence if item["kind"] == "domain_repair_slice"))

    def test_domain_bindings_have_no_bug_or_function_specific_keys(self):
        for name in [
            "recovery-attachment-settlement-v0.2.json",
            "device-topology-rollback-v0.2.json",
        ]:
            binding_path = ROOT / "configs/bindings" / name
            binding = load_binding(str(binding_path))
            text = binding_path.read_text(encoding="utf-8").lower()
            self.assertNotIn("bug_id", binding.raw)
            self.assertNotIn("target_function", binding.raw)
            self.assertNotIn("btrfs_recover_relocation", text)
            self.assertNotIn("btrfs_init_new_device", text)


if __name__ == "__main__":
    unittest.main()
