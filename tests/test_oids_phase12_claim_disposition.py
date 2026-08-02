import hashlib
import unittest
from pathlib import Path

from src.fmpca.orphan_phase12 import run_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs/evaluation/oids-phase12-claim-disposition-v0.1.json"


class OIDSPhase12ClaimDispositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = run_manifest(str(MANIFEST.relative_to(ROOT)))

    def test_historical_freeze_and_heldout_results_are_preserved(self):
        self.assertTrue(self.summary["historical_results_preserved"])
        self.assertTrue(self.summary["phase9_common_freeze_preserved"])
        self.assertTrue(self.summary["phase10_controlled_non_applicable_preserved"])
        self.assertTrue(self.summary["phase11_nonconformant_heldout_preserved"])
        self.assertFalse(self.summary["protocol_v0_1_mutated"])
        self.assertTrue(self.summary["artifact_hashes_verified"])

    def test_matrix_separates_formation_screening_and_heldout_roles(self):
        rows = {item["filesystem"]: item for item in self.summary["matrix"]}
        self.assertEqual(set(rows), {"btrfs", "ext4", "ubifs", "ocfs2", "reiserfs"})
        self.assertEqual(rows["btrfs"]["evaluation_role"], "FREEZE_FORMATION_DEVELOPMENT")
        self.assertEqual(rows["ext4"]["evaluation_role"], "FREEZE_FORMATION_VALIDATION")
        self.assertEqual(rows["ubifs"]["heldout_disposition"], "NOT_POST_COMMON_HELDOUT")
        self.assertEqual(rows["ocfs2"]["applicability"], "NON_APPLICABLE")
        self.assertEqual(rows["reiserfs"]["heldout_disposition"], "NON_CONFORMANT_HELDOUT")
        self.assertTrue(self.summary["matrix_matches_catalog"])

    def test_applicability_and_conformance_are_distinct_claims(self):
        rows = {item["filesystem"]: item for item in self.summary["matrix"]}
        self.assertEqual(rows["reiserfs"]["applicability"], "APPLICABLE")
        self.assertEqual(
            rows["reiserfs"]["failure_path_conformance"],
            "REFUTED_BY_OIDS_O1_AND_OIDS_O3",
        )
        self.assertTrue(self.summary["semantic_applicability_supported"])
        self.assertTrue(self.summary["normal_profiles_supported"])
        self.assertTrue(self.summary["failure_path_conformance_refuted"])
        self.assertFalse(self.summary["common_heldout_validated"])

    def test_o1_source_cfg_replay_and_irreducibility_close(self):
        audit = {item["rule"]: item for item in self.summary["counterexample_audits"]}["OIDS-O1"]
        self.assertTrue(audit["source_control_flow_closed"])
        self.assertEqual(
            audit["event_sequence"],
            ["InitializeOrphanDeletion", "LastLinkRemoved", "RegistrationTransactionCommit"],
        )
        self.assertEqual(audit["actual_result"], "VIOLATION_UNDER_LOADED_SPEC")
        self.assertEqual(audit["violation_rules"], ["OIDS-O1"])
        self.assertTrue(audit["rule_specific_irreducible"])
        self.assertTrue(all(item["target_rule_absent"] for item in audit["deletion_trials"]))
        self.assertTrue(audit["source_replay_bridge_closed"])
        self.assertTrue(audit["closed"])

    def test_o3_source_cfg_replay_and_irreducibility_close(self):
        audit = {item["rule"]: item for item in self.summary["counterexample_audits"]}["OIDS-O3"]
        self.assertTrue(audit["source_control_flow_closed"])
        self.assertEqual(
            audit["event_sequence"],
            [
                "InitializeOrphanDeletion",
                "LastLinkRemoved",
                "OrphanRegistryAccepted",
                "RecoveryAuthorityAccepted",
                "RecoveryExposure",
            ],
        )
        self.assertEqual(audit["actual_result"], "VIOLATION_UNDER_LOADED_SPEC")
        self.assertEqual(audit["violation_rules"], ["OIDS-O3"])
        self.assertTrue(audit["rule_specific_irreducible"])
        self.assertTrue(all(item["target_rule_absent"] for item in audit["deletion_trials"]))
        self.assertTrue(audit["source_replay_bridge_closed"])
        self.assertTrue(audit["closed"])

    def test_post_reveal_outcome_narrowing_is_rejected(self):
        self.assertTrue(self.summary["no_outcome_predicates_in_frozen_scope"])
        self.assertTrue(self.summary["narrowing_audit_closed"])
        protocol = ROOT / "configs/protocols/common/orphan-inode-deletion-settlement-v0.1-candidate.json"
        self.assertEqual(
            hashlib.sha256(protocol.read_bytes()).hexdigest(),
            "c95135df0a9c916cd863d557aedebf64f06ae7bfee5bcf81692ce56f3c263122",
        )

    def test_claim_disposition_retains_counterexample_and_requires_new_split(self):
        disposition = self.summary["claim_disposition"]
        self.assertEqual(
            disposition["common_semantic_applicability"],
            "SUPPORTED_UNDER_FROZEN_NARROW_SCOPE",
        )
        self.assertEqual(
            disposition["common_failure_path_conformance"],
            "REFUTED_BY_POST_COMMON_HELDOUT_COUNTEREXAMPLE",
        )
        self.assertEqual(disposition["universal_filesystem_conformance"], "NOT_CLAIMED")
        self.assertEqual(
            disposition["protocol_v0_1_disposition"],
            "FROZEN_WITH_RETAINED_COUNTEREXAMPLE",
        )
        self.assertEqual(
            disposition["revised_protocol_requirement"],
            "NEW_VERSION_AND_NEW_EVALUATION_SPLIT",
        )
        self.assertTrue(self.summary["disposition_matches_catalog"])

    def test_phase12_closes_without_bug_specific_conditions(self):
        self.assertTrue(self.summary["counterexamples_closed"])
        self.assertEqual(self.summary["bug_specific_condition_count"], 0)
        self.assertTrue(self.summary["phase12_claim_disposition_closed"])


if __name__ == "__main__":
    unittest.main()
