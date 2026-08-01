import json
import unittest
from pathlib import Path

from src.fmpca.composition import (
    compose_device_topology_capacity,
    load_composition_spec,
    run_composition_manifest,
)
from src.fmpca.dsl import load_protocol
from src.fmpca.frontend_capacity import (
    analyze_capacity_source,
    load_capacity_binding,
)
from src.fmpca.model import AnalysisResult, EvidenceEvent
from src.fmpca.proof import analyze_state
from src.fmpca.readiness_v4 import evaluate_v4_readiness
from src.fmpca.semantics import ProtocolEngine


ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY_PROTOCOL = ROOT / "configs/protocols/device-topology-rollback-v0.2.json"
CAPACITY_PROTOCOL = ROOT / "configs/protocols/writable-device-capacity-contribution-v0.4.json"


def run(protocol_path: Path, fixture_name: str):
    protocol = load_protocol(str(protocol_path))
    fixture = json.loads(
        (ROOT / "tests/fixtures/events" / fixture_name).read_text(encoding="utf-8")
    )
    state = ProtocolEngine(protocol).run(
        EvidenceEvent.from_dict(item) for item in fixture["events"]
    )
    closure = fixture["closure"]
    return analyze_state(
        state,
        path_model_closed=closure["path_model_closed"],
        all_paths_closed=closure["all_paths_closed"],
        repair_slice_closed=closure["repair_slice_closed"],
        alias_closed=closure["alias_closed"],
    )


class WritableDeviceCapacityContributionTests(unittest.TestCase):
    def test_shrink_success_failure_bug_and_unknown(self):
        success = run(CAPACITY_PROTOCOL, "wdc-shrink-success-v0.4.json")
        rollback = run(CAPACITY_PROTOCOL, "wdc-shrink-rollback-v0.4.json")
        bug = run(CAPACITY_PROTOCOL, "wdc-shrink-bug-v0.4.json")
        unknown = run(CAPACITY_PROTOCOL, "wdc-unknown-v0.4.json")
        self.assertEqual(success.result, AnalysisResult.CONFORMANT)
        self.assertEqual(rollback.result, AnalysisResult.CONFORMANT)
        self.assertEqual(bug.result, AnalysisResult.VIOLATION)
        self.assertIn("WDC-I2", bug.violation_rules)
        self.assertEqual(unknown.result, AnalysisResult.INCOMPLETE)

    def test_release_requires_capacity_detachment(self):
        report = run(CAPACITY_PROTOCOL, "wdc-release-violation-v0.4.json")
        self.assertEqual(report.result, AnalysisResult.VIOLATION)
        self.assertIn("WDC-I3", report.violation_rules)
        self.assertIn("BEFORE_RELEASE", report.state.reached_deadlines)

    def test_source_witnesses_cover_add_remove_and_shrink(self):
        binding = load_capacity_binding(
            str(ROOT / "configs/bindings/writable-device-capacity-contribution-v0.4.json")
        )
        source = str(ROOT / "linux-sources/linux-v7.1-fs/fs/btrfs/volumes.c")
        add = analyze_capacity_source(binding, source, "btrfs_init_new_device")
        shrink = analyze_capacity_source(binding, source, "btrfs_shrink_device")
        self.assertEqual(add.operation_family, "device-membership-change")
        self.assertEqual(shrink.operation_family, "device-capacity-resize")
        self.assertTrue(add.selected_source_path_closed)
        self.assertTrue(shrink.selected_source_path_closed)

    def test_binding_has_no_case_specific_selection(self):
        path = ROOT / "configs/bindings/writable-device-capacity-contribution-v0.4.json"
        binding = load_capacity_binding(str(path))
        text = path.read_text(encoding="utf-8").lower()
        self.assertEqual(
            binding.protocol_id, "fmpca.writable_device_capacity_contribution"
        )
        self.assertNotIn("btrfs_init_new_device", text)
        self.assertNotIn("btrfs_shrink_device", text)
        self.assertNotIn("bug_id", text)
        self.assertNotIn("target_function", text)


class DeviceTopologyCapacityCompositionTests(unittest.TestCase):
    def compose(self, topology_fixture: str, capacity_fixture: str):
        return compose_device_topology_capacity(
            run(TOPOLOGY_PROTOCOL, topology_fixture),
            run(CAPACITY_PROTOCOL, capacity_fixture),
        )

    def test_add_success_and_full_rollback_conform(self):
        success = self.compose(
            "dtc-topology-add-success-v0.4.json", "wdc-add-success-v0.4.json"
        )
        rollback = self.compose(
            "dtc-topology-add-rollback-v0.4.json", "wdc-add-rollback-v0.4.json"
        )
        self.assertEqual(success.result, AnalysisResult.CONFORMANT)
        self.assertEqual(rollback.result, AnalysisResult.CONFORMANT)

    def test_partial_capacity_rollback_is_a_composed_violation(self):
        report = self.compose(
            "dtc-topology-add-rollback-v0.4.json",
            "wdc-add-partial-rollback-v0.4.json",
        )
        self.assertEqual(report.result, AnalysisResult.VIOLATION)
        self.assertTrue({"WDC", "DTC-C2"}.intersection(report.rules))

    def test_cross_protocol_eligibility_mismatch_is_detected(self):
        report = self.compose(
            "dtc-topology-add-success-v0.4.json",
            "wdc-add-cross-mismatch-v0.4.json",
        )
        self.assertEqual(report.result, AnalysisResult.VIOLATION)
        self.assertIn("DTC-C1", report.rules)

    def test_composition_requires_shared_operation_and_device_identity(self):
        report = self.compose(
            "dtc-topology-add-success-v0.4.json",
            "wdc-shrink-success-v0.4.json",
        )
        self.assertEqual(report.result, AnalysisResult.INCOMPLETE)
        self.assertIn("DTC-ID", report.rules)

    def test_machine_readable_composition_spec_is_executable(self):
        spec = load_composition_spec(
            str(ROOT / "configs/compositions/device-topology-capacity-v0.4.json")
        )
        report = compose_device_topology_capacity(
            run(TOPOLOGY_PROTOCOL, "dtc-topology-add-success-v0.4.json"),
            run(CAPACITY_PROTOCOL, "wdc-add-success-v0.4.json"),
            spec,
        )
        self.assertEqual(report.result, AnalysisResult.CONFORMANT)
        self.assertEqual(spec.composition_version, "0.4.0")

    def test_readiness_separates_cross_family_from_held_out(self):
        readiness = evaluate_v4_readiness(
            str(ROOT / "configs/evaluation/wdc-v0.4-readiness.json")
        )
        self.assertTrue(readiness["freeze_eligible"])
        self.assertTrue(readiness["cross_operation_family_validated"])
        self.assertFalse(readiness["held_out_generalization_eligible"])
        self.assertEqual(readiness["operation_family_count"], 2)

    def test_frozen_e4_manifest_replays_all_cases(self):
        summary = run_composition_manifest(
            str(ROOT / "configs/evaluation/e4-v0.4.json")
        )
        self.assertEqual(summary["total"], 10)
        self.assertEqual(summary["passed"], 10)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["held_out_operation_families"], [])


if __name__ == "__main__":
    unittest.main()
