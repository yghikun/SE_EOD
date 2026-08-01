import unittest
from pathlib import Path

from src.fmpca.heldout_cmrc_v5 import run_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs/evaluation/e6-v0.5-heldout-screening.json"


class CMRCHeldOutV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = run_manifest(str(MANIFEST))

    def test_e6_closes_one_new_held_out_family_and_rejects_a_frozen_neighbor(self):
        self.assertEqual(self.summary["total_candidates"], 2)
        self.assertEqual(self.summary["passed"], 2)
        self.assertEqual(self.summary["failed"], 0)
        self.assertEqual(self.summary["eligible_candidate_count"], 1)
        self.assertEqual(
            self.summary["held_out_operation_families"],
            ["btrfs-chunk-item-removal"],
        )
        remove = next(
            item for item in self.summary["candidates"]
            if item["id"] == "btrfs-remove-chunk-v7.1"
        )
        self.assertEqual(remove["actual_decision"], "ELIGIBLE_HELD_OUT_REPLAY")
        self.assertEqual(remove["replay"]["passed"], 4)
        self.assertEqual(remove["replay"]["total"], 4)
        self.assertIn("FIXED_OR_REPAIR", remove["replay"]["roles"])

        add_dev = next(
            item for item in self.summary["candidates"]
            if item["id"] == "btrfs-add-dev-item-v7.1"
        )
        self.assertEqual(add_dev["actual_decision"], "REJECT_NOT_INDEPENDENT")
        self.assertFalse(add_dev["eligible"])

    def test_e6_uses_the_frozen_cmrc_lock_and_does_not_modify_checker(self):
        self.assertEqual(
            self.summary["freeze_id"],
            "fmpca-heldout-semantic-freeze-e6-v0.5",
        )
        self.assertEqual(self.summary["protocol_acceptance_modifications"], 0)
        self.assertEqual(self.summary["checker_modifications_after_freeze"], 0)
        self.assertEqual(self.summary["bug_specific_condition_count"], 0)


if __name__ == "__main__":
    unittest.main()
