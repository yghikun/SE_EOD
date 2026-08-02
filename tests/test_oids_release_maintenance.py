import unittest
from pathlib import Path

from src.fmpca.orphan_maintenance import verify_release


ROOT = Path(__file__).resolve().parents[1]


class OIDSReleaseMaintenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = verify_release(ROOT)

    def test_historical_phase15_freeze_is_hash_verified_not_rerun(self):
        self.assertTrue(self.result["historical_phase15_freeze_verified"])
        self.assertIn(
            "outputs/fmpca-oids-phase15-v0.1/summary.json",
            self.result["locked_artifacts"],
        )

    def test_phase16_through_phase18_recompute_exactly(self):
        self.assertEqual(
            self.result["recomputed_summaries"],
            {"phase16": True, "phase17": True, "phase18": True},
        )

    def test_final_claim_boundary_is_preserved(self):
        self.assertTrue(self.result["endpoint_preserved"])
        self.assertFalse(self.result["common_v0_2_validated"])

    def test_maintenance_verification_closes(self):
        self.assertTrue(all(self.result["locked_artifacts"].values()))
        self.assertTrue(self.result["maintenance_verification_closed"])


if __name__ == "__main__":
    unittest.main()
