import unittest
from pathlib import Path

from src.fmpca.orphan_phase17 import run_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs/evaluation/oids-phase17-jfs-result-freeze-v0.1.json"


class OIDSPhase17JFSResultFreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = run_manifest(str(MANIFEST.relative_to(ROOT)))

    def test_first_phase16_result_is_preserved(self):
        self.assertTrue(self.summary["phase16_result_preserved"])
        self.assertEqual(
            self.summary["frozen_result"]["controlled_reason_code"],
            "PERSISTENT_CLEANUP_OBJECT_NOT_FOUND",
        )

    def test_candidate_was_not_replaced(self):
        self.assertEqual(self.summary["candidate"], "JFS")
        self.assertFalse(self.summary["candidate_replaced"])
        self.assertTrue(self.summary["stop_policy_honored"])
        self.assertTrue(self.summary["heldout_attempt_final"])

    def test_non_applicable_is_not_conformance(self):
        result = self.summary["frozen_result"]
        self.assertEqual(result["applicability"], "NON_APPLICABLE")
        self.assertEqual(result["conformance"], "NOT_EVALUABLE")
        self.assertEqual(result["diagnostic_disposition"], "NOT_APPLICABLE")

    def test_common_v02_claim_is_not_allowed(self):
        self.assertFalse(self.summary["common_validation_gate_satisfied"])
        self.assertFalse(self.summary["common_v0_2_validated"])
        self.assertEqual(
            self.summary["v0_2_claim_disposition"],
            "HELDOUT_NON_APPLICABLE_NO_COMMON_VALIDATION",
        )

    def test_claim_matrix_and_phase17_close(self):
        self.assertTrue(self.summary["artifact_hashes_verified"])
        self.assertTrue(self.summary["claim_matrix_closed"])
        self.assertTrue(self.summary["phase17_result_freeze_closed"])


if __name__ == "__main__":
    unittest.main()
