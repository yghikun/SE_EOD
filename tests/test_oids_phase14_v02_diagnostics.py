import hashlib
import unittest
from pathlib import Path

from src.fmpca.diagnostics import diagnose_failure, load_diagnostic_extension
from src.fmpca.orphan_phase14 import run_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs/evaluation/oids-phase14-v0.2-diagnostic-v0.1.json"
EXTENSION = ROOT / "configs/protocols/common/orphan-inode-deletion-settlement-v0.2-diagnostic.json"


class OIDSPhase14V02DiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = run_manifest(str(MANIFEST.relative_to(ROOT)))
        cls.extension = load_diagnostic_extension(str(EXTENSION.relative_to(ROOT)))

    def test_extension_hash_locks_unmodified_v01_protocol_and_rules(self):
        base = self.extension.raw["base_protocol"]
        self.assertEqual(self.extension.raw["extension_version"], "0.2.0")
        self.assertTrue(base["normative_outcomes_preserved"])
        self.assertEqual(self.extension.base_protocol.sha256, base["sha256"])
        self.assertEqual(
            base["sha256"],
            "c95135df0a9c916cd863d557aedebf64f06ae7bfee5bcf81692ce56f3c263122",
        )
        self.assertFalse(self.summary["v0_1_protocol_mutated"])
        self.assertFalse(self.summary["v0_2_normative_protocol_replaced"])

    def test_failure_cause_taxonomy_maps_o1_and_o3(self):
        causes = self.extension.cause_map
        self.assertEqual(
            causes["REGISTRATION_ACCEPTANCE_ERROR_SUPPRESSION"]["rule"], "OIDS-O1"
        )
        self.assertEqual(
            causes["RECOVERY_CLEANUP_ERROR_SUPPRESSION"]["rule"], "OIDS-O3"
        )
        self.assertEqual(
            causes["REGISTRATION_ACCEPTANCE_ERROR_SUPPRESSION"]["unsafe_checkpoint"],
            "RegistrationTransactionCommit",
        )
        self.assertEqual(
            causes["RECOVERY_CLEANUP_ERROR_SUPPRESSION"]["unsafe_checkpoint"],
            "RecoveryExposure",
        )

    def test_repair_obligations_have_three_machine_readable_safe_alternatives(self):
        for repair in self.extension.repair_map.values():
            self.assertEqual(
                repair["selection_policy"],
                "AT_LEAST_ONE_SAFE_ALTERNATIVE_MUST_BE_PROVEN",
            )
            self.assertEqual(len(repair["safe_alternatives"]), 3)
            self.assertTrue(
                all(item["required_facts"] for item in repair["safe_alternatives"])
            )

    def test_evidence_level_is_enforced_by_diagnostic_engine(self):
        complete = diagnose_failure(
            self.extension,
            rule="OIDS-O1",
            cause="REGISTRATION_ACCEPTANCE_ERROR_SUPPRESSION",
            evidence_level="SOURCE_CONFIRMED_CORRECTNESS_BUG",
            trigger_facts=(
                "persistent_registration_failed",
                "failure_not_propagated",
                "namespace_commit_reachable",
            ),
            evidence_facts=(
                "source_anchor",
                "control_flow",
                "rule_specific_replay",
                "unsafe_checkpoint",
            ),
        )
        incomplete = diagnose_failure(
            self.extension,
            rule="OIDS-O1",
            cause="REGISTRATION_ACCEPTANCE_ERROR_SUPPRESSION",
            evidence_level="SOURCE_CONFIRMED_CORRECTNESS_BUG",
            trigger_facts=(
                "persistent_registration_failed",
                "failure_not_propagated",
                "namespace_commit_reachable",
            ),
            evidence_facts=("source_anchor", "control_flow", "rule_specific_replay"),
        )
        self.assertTrue(complete.diagnostic_closed)
        self.assertFalse(incomplete.diagnostic_closed)
        self.assertEqual(incomplete.missing_evidence, frozenset({"unsafe_checkpoint"}))
        self.assertTrue(self.summary["evidence_gate_closed"])

    def test_reiserfs_development_cases_map_but_no_repair_is_falsely_proven(self):
        mappings = {item["rule"]: item for item in self.summary["diagnostic_mappings"]}
        self.assertEqual(set(mappings), {"OIDS-O1", "OIDS-O3"})
        for item in mappings.values():
            self.assertTrue(item["diagnostic_closed"])
            self.assertTrue(item["mapping_closed"])
            self.assertEqual(item["proven_safe_alternatives"], [])
            self.assertEqual(item["repair_status"], "REQUIRED_NOT_IMPLEMENTED")
            self.assertEqual(item["preserved_result"], "VIOLATION_UNDER_LOADED_SPEC")
            self.assertTrue(item["incomplete_evidence_rejected"])
        self.assertTrue(self.summary["diagnostic_mappings_closed"])
        self.assertTrue(self.summary["mapping_policy_closed"])

    def test_v01_o1_and_o3_violation_results_are_preserved(self):
        replays = {item["expected_rule"]: item for item in self.summary["development_replays"]}
        self.assertEqual(set(replays), {"OIDS-O1", "OIDS-O3"})
        for rule, item in replays.items():
            self.assertEqual(item["actual"], "VIOLATION_UNDER_LOADED_SPEC")
            self.assertIn(rule, item["violation_rules"])
            self.assertTrue(item["preserved"])
        self.assertTrue(self.summary["violation_results_preserved"])

    def test_all_registered_regression_boundaries_are_preserved(self):
        regressions = {item["filesystem"]: item for item in self.summary["regression_matrix"]}
        self.assertEqual(set(regressions), {"btrfs", "ext4", "ubifs", "ocfs2"})
        self.assertTrue(all(item["preserved"] for item in regressions.values()))
        self.assertEqual(regressions["btrfs"]["actual"], "CLOSED")
        self.assertEqual(regressions["ext4"]["actual"], "PRESERVED")
        self.assertEqual(regressions["ubifs"]["actual"], "PRESERVED")
        self.assertEqual(regressions["ocfs2"]["actual"], "PRESERVED")
        self.assertTrue(self.summary["regression_boundaries_preserved"])

    def test_applicability_and_heldout_boundaries_remain_closed(self):
        self.assertTrue(self.summary["applicability_unchanged"])
        self.assertTrue(self.summary["heldout_partition_empty"])
        self.assertFalse(self.summary["heldout_validation_allowed"])
        self.assertFalse(self.summary["common_v0_2_validated"])

    def test_phase13_preregistration_hash_is_unchanged(self):
        prereg = ROOT / "configs/evaluation/oids-phase13-v0.2-revision-preregistration-v0.1.json"
        self.assertEqual(
            hashlib.sha256(prereg.read_bytes()).hexdigest(),
            "5262d9db9c2f20b1434ad955de923deaf2df5c5a66267112db2c7c71e573f404",
        )
        self.assertTrue(self.summary["phase13_preregistration_preserved"])

    def test_phase14_diagnostic_implementation_closes(self):
        self.assertTrue(self.summary["artifact_hashes_verified"])
        self.assertTrue(self.summary["v0_2_diagnostic_implemented"])
        self.assertTrue(self.summary["phase14_v0_2_diagnostic_closed"])


if __name__ == "__main__":
    unittest.main()
