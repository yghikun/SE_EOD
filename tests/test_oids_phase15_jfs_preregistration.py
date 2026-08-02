import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "outputs/fmpca-oids-phase15-v0.1/summary.json"
PREREGISTRATION = ROOT / "configs/evaluation/oids-phase15-jfs-heldout-preregistration-v0.1.json"


class OIDSPhase15JFSPreregistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        cls.preregistration = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))

    def test_frozen_summary_closes_before_reveal(self):
        self.assertTrue(self.summary["phase15_preregistration_closed"])
        self.assertTrue(self.summary["source_unrevealed_at_freeze"])
        self.assertTrue(self.summary["pre_reveal_locks_verified"])
        self.assertTrue(self.summary["artifact_hashes_verified"])

    def test_jfs_is_the_only_selected_candidate(self):
        self.assertEqual(self.summary["selected_candidate"], "JFS")
        self.assertEqual(self.summary["registered_source_count"], 10)
        self.assertFalse(self.summary["candidate_replaced"])

    def test_preregistration_is_byte_locked(self):
        self.assertEqual(
            hashlib.sha256(PREREGISTRATION.read_bytes()).hexdigest(),
            "938f31a9381c8998d3f0aabdc314c38ca775626df559580aff61b1fce4076595",
        )
        self.assertEqual(
            self.summary["preregistration_sha256"],
            "938f31a9381c8998d3f0aabdc314c38ca775626df559580aff61b1fce4076595",
        )

    def test_source_revision_and_stop_policy_are_fixed(self):
        self.assertEqual(self.preregistration["source_version"]["git_tag"], "v6.14")
        self.assertEqual(
            self.preregistration["source_version"]["git_commit"],
            "38fec10eb60d687e30c8c6b5420d86e8149f7557",
        )
        self.assertEqual(
            self.preregistration["stop_policy"],
            "ACCEPT_FIRST_COMPLETE_RESULT_WITHOUT_CANDIDATE_REPLACEMENT",
        )

    def test_phase15_makes_no_heldout_result_claim(self):
        self.assertFalse(self.summary["heldout_validation_allowed"])
        self.assertFalse(self.summary["common_v0_2_validated"])


if __name__ == "__main__":
    unittest.main()
