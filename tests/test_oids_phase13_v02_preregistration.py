import hashlib
import json
import unittest
from pathlib import Path

from src.fmpca.orphan_phase13 import SOURCE_CONFIRMED_BUG, run_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs/evaluation/oids-phase13-v0.2-preregistration-v0.1.json"
PREREGISTRATION = ROOT / "configs/evaluation/oids-phase13-v0.2-revision-preregistration-v0.1.json"


class OIDSPhase13V02PreregistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = run_manifest(str(MANIFEST.relative_to(ROOT)))

    def test_revision_is_preregistered_before_any_semantic_edit(self):
        prereg = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
        self.assertEqual(prereg["planned_protocol_version"], "0.2.0")
        self.assertEqual(prereg["semantic_edits_before_preregistration"], 0)
        self.assertFalse(prereg["base_protocol_mutated"])
        self.assertTrue(prereg["normative_safety_outcomes_preserved"])
        self.assertTrue(self.summary["preregistration_hash_verified"])
        self.assertTrue(self.summary["pre_edit_locks_verified"])

    def test_both_reiserfs_cases_are_source_confirmed_correctness_bugs(self):
        assessments = {item["case_id"]: item for item in self.summary["bug_assessments"]}
        self.assertEqual(
            set(assessments),
            {
                "REISERFS_SAVE_LINK_ENOSPC_UNPROPAGATED",
                "REISERFS_RECOVERY_ERROR_EXPOSURE_REACHABLE",
            },
        )
        for item in assessments.values():
            self.assertEqual(item["evidence_level"], SOURCE_CONFIRMED_BUG)
            self.assertTrue(item["source_anchor_match"])
            self.assertTrue(item["minimal_replay_closed"])
            self.assertTrue(item["unsafe_mechanism_documented"])
            self.assertTrue(item["repair_contract_documented"])
            self.assertTrue(item["bug_claim_allowed"])
            self.assertTrue(item["closed"])
        self.assertEqual(self.summary["source_confirmed_bug_count"], 2)
        self.assertTrue(self.summary["bug_cases_closed"])

    def test_evidence_boundary_does_not_overclaim_external_confirmation(self):
        for item in self.summary["bug_assessments"]:
            self.assertFalse(item["runtime_reproduced"])
            self.assertFalse(item["upstream_acknowledged"])
            self.assertFalse(item["security_impact_established"])
            self.assertFalse(item["cve_claimed"])
            self.assertTrue(item["evidence_boundary_preserved"])
        self.assertEqual(self.summary["runtime_reproduced_bug_count"], 0)
        self.assertEqual(self.summary["upstream_acknowledged_bug_count"], 0)
        self.assertEqual(self.summary["security_bug_count"], 0)
        self.assertTrue(self.summary["terminology_policy_closed"])

    def test_repair_objectives_preserve_o1_and_o3_instead_of_narrowing_scope(self):
        self.assertEqual(self.summary["preserved_violation_rules"], ["OIDS-O1", "OIDS-O3"])
        self.assertTrue(self.summary["repair_objectives_closed"])
        self.assertTrue(self.summary["diagnostic_revision_only"])
        prereg = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
        non_goals = " ".join(prereg["non_goals"])
        self.assertIn("add_save_link_succeeded", non_goals)
        self.assertIn("finish_unfinished_succeeded", non_goals)

    def test_evaluation_split_moves_reiserfs_to_development_and_leaves_heldout_empty(self):
        split = self.summary["split_assessment"]
        self.assertEqual(split["development_case_count"], 2)
        self.assertEqual(split["development_rules"], ["OIDS-O1", "OIDS-O3"])
        self.assertEqual(
            split["regression_validation_filesystems"],
            ["btrfs", "ext4", "ocfs2", "ubifs"],
        )
        self.assertTrue(split["heldout_empty"])
        self.assertEqual(split["heldout_case_count"], 0)
        self.assertEqual(split["heldout_contamination_count"], 0)
        self.assertTrue(split["known_revealed_filesystems_excluded"])
        self.assertTrue(split["split_reset_closed"])

    def test_v01_is_frozen_and_v02_is_not_yet_implemented(self):
        protocol = ROOT / "configs/protocols/common/orphan-inode-deletion-settlement-v0.1-candidate.json"
        self.assertEqual(
            hashlib.sha256(protocol.read_bytes()).hexdigest(),
            "c95135df0a9c916cd863d557aedebf64f06ae7bfee5bcf81692ce56f3c263122",
        )
        self.assertTrue(self.summary["v0_1_frozen"])
        self.assertFalse(self.summary["v0_1_protocol_mutated"])
        self.assertFalse(self.summary["v0_2_protocol_implemented"])
        self.assertTrue(self.summary["phase12_disposition_preserved"])

    def test_no_heldout_or_common_v02_claim_is_allowed_yet(self):
        self.assertFalse(self.summary["heldout_validation_allowed"])
        self.assertFalse(self.summary["common_v0_2_validated"])

    def test_phase13_preregistration_closes(self):
        self.assertTrue(self.summary["artifact_hashes_verified"])
        self.assertTrue(self.summary["phase13_preregistration_closed"])


if __name__ == "__main__":
    unittest.main()
