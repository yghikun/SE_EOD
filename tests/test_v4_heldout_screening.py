import unittest
from pathlib import Path

from src.fmpca.frontend_capacity import analyze_capacity_source, load_capacity_binding
from src.fmpca.heldout_v4 import run_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs/evaluation/e5-v0.4-heldout-screening.json"
BINDING = ROOT / "configs/bindings/writable-device-capacity-contribution-v0.4.json"
BLOCK_GROUP = ROOT / "linux-sources/linux-v6.14-fs/fs/btrfs/block-group.c"
VOLUMES_V71 = ROOT / "linux-sources/linux-v7.1-fs/fs/btrfs/volumes.c"
DEV_REPLACE_V71 = ROOT / "linux-sources/linux-v7.1-fs/fs/btrfs/dev-replace.c"


class V4HeldOutScreeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = run_manifest(str(MANIFEST))

    def test_e5_rejects_chunk_reservation_as_outside_wdc_dtc(self):
        self.assertEqual(self.summary["total_candidates"], 4)
        self.assertEqual(self.summary["passed"], 4)
        self.assertEqual(self.summary["failed"], 0)
        self.assertEqual(self.summary["eligible_candidate_count"], 0)
        self.assertEqual(self.summary["held_out_operation_families"], [])
        candidate = next(
            item
            for item in self.summary["candidates"]
            if item["id"] == "bug-15-btrfs-chunk-metadata-reservation"
        )
        self.assertEqual(
            candidate["actual_decision"],
            "REJECT_OUTSIDE_WDC_DTC_FOOTPRINT",
        )
        self.assertIn("device", candidate["missing_identity_roles"])
        self.assertIn("chunk_block_reservation", candidate["footprint_gap"])

    def test_e5_screens_device_grow_remove_and_replace_without_admitting_them(self):
        decisions = {
            item["id"]: item["actual_decision"]
            for item in self.summary["candidates"]
        }
        self.assertEqual(decisions["btrfs-device-grow-v7.1"], "REJECT_BINDING_GAP")
        self.assertEqual(decisions["btrfs-device-remove-v7.1"], "REJECT_BINDING_GAP")
        self.assertEqual(
            decisions["btrfs-device-replace-finish-v7.1"],
            "REJECT_OUTSIDE_WDC_DTC_FOOTPRINT",
        )
        replace = next(
            item
            for item in self.summary["candidates"]
            if item["id"] == "btrfs-device-replace-finish-v7.1"
        )
        self.assertIn("device_identity_substitution", replace["footprint_gap"])

    def test_existing_wdc_binding_cannot_close_chunk_reservation_source(self):
        binding = load_capacity_binding(str(BINDING))
        witness = analyze_capacity_source(binding, str(BLOCK_GROUP), "reserve_chunk_space")
        self.assertEqual(
            witness.operation_family,
            "unknown-device-capacity-operation",
        )
        self.assertFalse(witness.selected_source_path_closed)
        self.assertFalse(witness.membership_coupling_closed)

    def test_existing_wdc_binding_explains_device_candidate_rejections(self):
        binding = load_capacity_binding(str(BINDING))
        grow = analyze_capacity_source(binding, str(VOLUMES_V71), "btrfs_grow_device")
        self.assertEqual(grow.operation_family, "unknown-device-capacity-operation")
        self.assertTrue(grow.eligibility_closed)
        self.assertTrue(grow.aggregate_pair_closed)
        self.assertFalse(grow.same_delta_closed)

        remove = analyze_capacity_source(binding, str(VOLUMES_V71), "btrfs_rm_device")
        self.assertEqual(remove.operation_family, "device-membership-change")
        self.assertTrue(remove.membership_coupling_closed)
        self.assertFalse(remove.aggregate_pair_closed)

        replace = analyze_capacity_source(
            binding,
            str(DEV_REPLACE_V71),
            "btrfs_dev_replace_finishing",
        )
        self.assertEqual(replace.operation_family, "device-membership-change")
        self.assertFalse(replace.aggregate_pair_closed)

    def test_e5_does_not_modify_protocol_or_checker_after_freeze(self):
        self.assertEqual(self.summary["protocol_acceptance_modifications"], 0)
        self.assertEqual(self.summary["checker_modifications_after_freeze"], 0)
        self.assertEqual(self.summary["bug_specific_condition_count"], 0)


if __name__ == "__main__":
    unittest.main()
