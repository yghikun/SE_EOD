import unittest
from pathlib import Path

from src.fmpca.orphan_phase16 import run_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs/evaluation/oids-phase16-jfs-heldout-v0.1.json"


class OIDSPhase16JFSHeldoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = run_manifest(str(MANIFEST.relative_to(ROOT)))

    def test_phase15_blind_freeze_is_preserved(self):
        self.assertTrue(self.summary["phase15_preregistration_preserved"])
        self.assertFalse(self.summary["candidate_replaced"])
        self.assertTrue(self.summary["stop_policy_honored"])

    def test_all_registered_sources_are_acquired_and_locked(self):
        self.assertTrue(self.summary["registered_sources_acquired"])
        self.assertTrue(self.summary["source_hashes_verified"])
        self.assertEqual(
            self.summary["source_revision"],
            "38fec10eb60d687e30c8c6b5420d86e8149f7557",
        )

    def test_recovery_path_amendment_is_structural_only(self):
        self.assertTrue(self.summary["structural_amendment_closed"])
        self.assertEqual(
            self.summary["absent_recovery_path"], "fs/jfs/jfs_logredo.c"
        )

    def test_source_anchors_close(self):
        self.assertTrue(self.summary["evidence_anchors_closed"])
        self.assertGreaterEqual(len(self.summary["evidence_anchors"]), 8)

    def test_no_persistent_orphan_registry_is_present(self):
        self.assertTrue(self.summary["persistent_registry_absent"])
        self.assertTrue(
            all(not hits for hits in self.summary["persistent_registry_token_hits"].values())
        )

    def test_first_applicability_dimension_controls_result(self):
        screening = self.summary["screening"]
        self.assertEqual(screening[0]["dimension"], "object")
        self.assertEqual(screening[0]["status"], "NOT_SATISFIED")
        self.assertEqual(
            screening[0]["reason_code"], "PERSISTENT_CLEANUP_OBJECT_NOT_FOUND"
        )
        self.assertTrue(all(item["closed"] for item in screening))

    def test_non_applicable_result_does_not_force_replay_or_diagnostics(self):
        self.assertEqual(self.summary["applicability"], "NON_APPLICABLE")
        self.assertEqual(self.summary["conformance"], "NOT_EVALUABLE")
        self.assertEqual(self.summary["diagnostic_disposition"], "NOT_APPLICABLE")
        self.assertFalse(self.summary["replay_required"])
        self.assertFalse(self.summary["common_v0_2_validated"])

    def test_phase16_evaluation_closes(self):
        self.assertTrue(self.summary["artifact_hashes_verified"])
        self.assertTrue(self.summary["phase16_heldout_evaluation_closed"])


if __name__ == "__main__":
    unittest.main()
