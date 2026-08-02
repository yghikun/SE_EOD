import unittest
from pathlib import Path

from src.fmpca.orphan_phase18 import run_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs/evaluation/oids-final-release-v0.2.json"


class OIDSPhase18FinalReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = run_manifest(str(MANIFEST.relative_to(ROOT)))

    def test_phase1_through_phase17_chain_is_locked(self):
        chain = self.summary["phase_chain"]
        self.assertEqual([item["phase"] for item in chain], list(range(1, 18)))
        self.assertTrue(all(item["sha256_verified"] for item in chain))
        self.assertTrue(self.summary["phase_chain_closed"])

    def test_final_claim_matrix_is_exact_and_closed(self):
        self.assertEqual(len(self.summary["final_claim_matrix"]), 6)
        self.assertTrue(self.summary["claim_matrix_closed"])

    def test_v02_claim_boundary_is_not_overstated(self):
        self.assertEqual(
            self.summary["v0_2_claim_disposition"],
            "HELDOUT_NON_APPLICABLE_NO_COMMON_VALIDATION",
        )
        self.assertFalse(self.summary["common_v0_2_validated"])

    def test_phase18_is_hard_endpoint(self):
        self.assertEqual(self.summary["project_status"], "COMPLETE")
        self.assertEqual(self.summary["hard_endpoint"], "PHASE_18")
        self.assertFalse(self.summary["further_phase_expansion"])
        self.assertTrue(self.summary["maintenance_mode"])
        self.assertTrue(self.summary["endpoint_closed"])

    def test_only_maintenance_work_remains(self):
        self.assertEqual(
            self.summary["allowed_next_work"],
            ["bug fixes", "dependency maintenance", "reproducibility maintenance"],
        )

    def test_final_release_closes(self):
        self.assertTrue(self.summary["artifact_hashes_verified"])
        self.assertTrue(self.summary["project_complete"])


if __name__ == "__main__":
    unittest.main()
