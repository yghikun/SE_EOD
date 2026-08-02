import copy
import json
import tempfile
import unittest
from pathlib import Path

from src.fmpca.dsl import load_protocol
from src.fmpca.frontend import SourceBindingError
from src.fmpca.frontend_orphan_common import (
    analyze_registration_witness,
    analyze_settlement_witness,
    load_orphan_binding,
)
from src.fmpca.model import AnalysisResult, EvidenceEvent, Truth
from src.fmpca.proof import analyze_state
from src.fmpca.semantics_extensions import ProtocolDeadlineEngine


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = (
    ROOT
    / "configs/protocols/common/orphan-inode-deletion-settlement-v0.1-candidate.json"
)
BTRFS_BINDING = ROOT / "configs/bindings/common/orphan-inode-btrfs-v0.1.json"
EXT4_BINDING = ROOT / "configs/bindings/common/orphan-inode-ext4-v0.1.json"
EVENTS = ROOT / "tests/fixtures/events"
LINUX = ROOT / "linux-sources/linux-v6.14-fs"


def run_fixture(name):
    spec = load_protocol(str(PROTOCOL))
    raw = json.loads((EVENTS / name).read_text(encoding="utf-8"))
    state = ProtocolDeadlineEngine(spec).run(
        EvidenceEvent.from_dict(item) for item in raw["events"]
    )
    closure = raw["closure"]
    report = analyze_state(
        state,
        path_model_closed=closure["path_model_closed"],
        all_paths_closed=closure["all_paths_closed"],
        repair_slice_closed=closure["repair_slice_closed"],
        alias_closed=closure["alias_closed"],
    )
    return state, report


class OIDSPhase2CandidateTests(unittest.TestCase):
    def test_candidate_protocol_declares_protocol_local_deadlines(self):
        spec = load_protocol(str(PROTOCOL))
        self.assertEqual(
            spec.deadline_events["OrphanRegistryRemoval"],
            ["BEFORE_ORPHAN_REGISTRY_REMOVAL"],
        )
        state, report = run_fixture("oids-ext4-fixed-live-v0.1.json")
        self.assertEqual(report.result, AnalysisResult.CONFORMANT)
        self.assertEqual(
            state.reached_deadlines,
            {
                "BEFORE_COMMIT",
                "BEFORE_ORPHAN_REGISTRY_REMOVAL",
                "AT_SETTLEMENT",
            },
        )

    def test_fixed_live_and_normal_recovery_replays_conform(self):
        for name in (
            "oids-btrfs-fixed-live-v0.1.json",
            "oids-ext4-fixed-live-v0.1.json",
            "oids-normal-recovery-v0.1.json",
        ):
            with self.subTest(name=name):
                _, report = run_fixture(name)
                self.assertEqual(report.result, AnalysisResult.CONFORMANT)

    def test_missing_registration_and_unsafe_removal_are_violations(self):
        expectations = {
            "oids-negative-registration-v0.1.json": "OIDS-O1",
            "oids-negative-removal-v0.1.json": "OIDS-O2",
        }
        for name, rule in expectations.items():
            with self.subTest(name=name):
                state, report = run_fixture(name)
                self.assertEqual(report.result, AnalysisResult.VIOLATION)
                self.assertIn(rule, report.violation_rules)
                self.assertTrue(
                    any(
                        check.rule_id == rule and check.truth == Truth.FALSE
                        for check in state.checks
                    )
                )

    def test_unknown_transaction_equivalence_stays_incomplete(self):
        _, report = run_fixture("oids-unknown-settlement-v0.1.json")
        self.assertEqual(report.result, AnalysisResult.INCOMPLETE)

    def test_bindings_are_strict_and_case_independent(self):
        for path, filesystem in (
            (BTRFS_BINDING, "btrfs"),
            (EXT4_BINDING, "ext4"),
        ):
            with self.subTest(filesystem=filesystem):
                binding = load_orphan_binding(str(path))
                self.assertEqual(binding.filesystem, filesystem)
                text = path.read_text(encoding="utf-8")
                self.assertNotIn('"btrfs_unlink"', text)
                self.assertNotIn('"__ext4_unlink"', text)
                self.assertNotIn('"btrfs_evict_inode"', text)
                self.assertNotIn('"ext4_evict_inode"', text)

        raw = json.loads(BTRFS_BINDING.read_text(encoding="utf-8"))
        raw["role_kinds"] = copy.deepcopy(raw["role_kinds"])
        raw["role_kinds"]["hidden"] = {"Target_Function": "special"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "binding.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(SourceBindingError):
                load_orphan_binding(str(path))

    def test_btrfs_real_source_closes_both_witnesses(self):
        binding = load_orphan_binding(str(BTRFS_BINDING))
        source = LINUX / "fs/btrfs/inode.c"
        registration = analyze_registration_witness(
            binding, str(source), "btrfs_unlink"
        )
        settlement = analyze_settlement_witness(
            binding, str(source), "btrfs_evict_inode"
        )
        self.assertTrue(registration.registration_safe)
        self.assertTrue(settlement.removal_safe)
        self.assertTrue(settlement.deletion_durable_before_removal)
        self.assertFalse(settlement.same_transaction_equivalence)

    def test_ext4_real_source_closes_transactional_equivalence(self):
        binding = load_orphan_binding(str(EXT4_BINDING))
        registration = analyze_registration_witness(
            binding, str(LINUX / "fs/ext4/namei.c"), "__ext4_unlink"
        )
        settlement = analyze_settlement_witness(
            binding, str(LINUX / "fs/ext4/inode.c"), "ext4_evict_inode"
        )
        self.assertTrue(registration.registration_safe)
        self.assertTrue(settlement.removal_safe)
        self.assertFalse(settlement.deletion_durable_before_removal)
        self.assertTrue(settlement.same_transaction_equivalence)
        self.assertGreater(
            settlement.evidence_lines["terminal_deletion"],
            settlement.evidence_lines["registry_removal"],
        )

    def test_linked_truncate_path_is_not_selected_as_registration(self):
        binding = load_orphan_binding(str(EXT4_BINDING))
        witness = analyze_registration_witness(
            binding, str(LINUX / "fs/ext4/inode.c"), "ext4_truncate"
        )
        self.assertFalse(witness.zero_link_scoped)
        self.assertFalse(witness.registration_safe)


if __name__ == "__main__":
    unittest.main()
