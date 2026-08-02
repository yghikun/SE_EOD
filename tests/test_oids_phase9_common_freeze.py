import hashlib
import json
import unittest
from pathlib import Path

from src.fmpca.orphan_phase9 import COMMON_FREEZE, run_manifest
from src.fmpca.scope import assess_scope_files


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs/evaluation/oids-phase9-common-freeze-v0.1.json"
DECLARATION = ROOT / "configs/evaluation/oids-phase9-common-scope-v0.1.json"
TAXONOMY = ROOT / "configs/catalog/protocol-scope-taxonomy-v0.1.json"


class OIDSPhase9CommonFreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = run_manifest(str(MANIFEST))
        cls.declaration = json.loads(DECLARATION.read_text(encoding="utf-8"))

    def test_common_scope_closes_every_candidate_and_freeze_gate(self):
        scope = assess_scope_files(str(TAXONOMY), str(DECLARATION))
        self.assertTrue(scope.declaration_valid)
        self.assertTrue(scope.common_candidate_ready)
        self.assertTrue(scope.common_freeze_ready)
        self.assertTrue(scope.cross_filesystem_claim_allowed)
        self.assertEqual(scope.failed_candidate_gates, [])
        self.assertEqual(scope.failed_freeze_gates, [])

    def test_three_independent_filesystem_members_close(self):
        assessment = self.summary["assessment"]
        by_fs = {item["filesystem"]: item for item in assessment["filesystems"]}
        self.assertEqual(set(by_fs), {"btrfs", "ext4", "ubifs"})
        self.assertTrue(all(item["closed"] for item in by_fs.values()))
        self.assertEqual(
            len({item["operation_family"] for item in by_fs.values()}), 3
        )
        self.assertTrue(assessment["independent_operation_families"])

    def test_configuration_predicates_are_explicit(self):
        by_fs = {item["filesystem"]: item for item in self.declaration["filesystems"]}
        self.assertIn("successful_rw_recovery_exposure", by_fs["btrfs"]["applicability_predicate"])
        self.assertIn("error_policy != ERRORS_CONT", by_fs["ext4"]["applicability_predicate"])
        self.assertIn("successful_rw_recovery_exposure", by_fs["ubifs"]["applicability_predicate"])
        self.assertEqual(
            by_fs["ubifs"]["excluded_profile"],
            "RECOVERY_DEFERRED_OUTSIDE_VALIDATED_RW_EXPOSURE",
        )

    def test_ext4_errors_cont_and_ubifs_read_only_remain_excluded(self):
        exclusions = {
            (item["filesystem"], item["configuration"]): item["status"]
            for item in self.declaration["excluded_configurations"]
        }
        self.assertEqual(
            exclusions[("ext4", "ERRORS_CONT")],
            "EXCLUDED_BY_EXPLICIT_PREDICATE",
        )
        self.assertEqual(
            exclusions[("ubifs", "READ_ONLY_RECOVERY_EXPOSURE")],
            "RECOVERY_DEFERRED_OUTSIDE_VALIDATED_RW_EXPOSURE",
        )

    def test_ubifs_is_freeze_evidence_not_post_common_heldout(self):
        assessment = self.summary["assessment"]
        self.assertTrue(assessment["ubifs_is_freeze_member_not_post_common_heldout"])
        self.assertFalse(self.summary["common_heldout_validated"])
        self.assertIn("different unrevealed filesystem", self.summary["next_heldout_requirement"])

    def test_historical_phase7_and_taxonomy_hashes_are_preserved(self):
        hashes = {
            "phase7": hashlib.sha256(
                (ROOT / "configs/evaluation/oids-phase7-ext4-failstop-scope-v0.1.json").read_bytes()
            ).hexdigest(),
            "taxonomy": hashlib.sha256(TAXONOMY.read_bytes()).hexdigest(),
            "protocol": hashlib.sha256(
                (ROOT / "configs/protocols/common/orphan-inode-deletion-settlement-v0.1-candidate.json").read_bytes()
            ).hexdigest(),
        }
        self.assertEqual(
            hashes["phase7"],
            "ee1f54519ef66077a3e99ed1306bbf01661de9ff7d6bbc6764b9a02a7a7bda85",
        )
        self.assertEqual(
            hashes["taxonomy"],
            "c4c1055e1c90b9c47ecf56a6f1d09331129f3d1a07c1555a14cf4b53c50119a4",
        )
        self.assertEqual(
            hashes["protocol"],
            "c95135df0a9c916cd863d557aedebf64f06ae7bfee5bcf81692ce56f3c263122",
        )
        self.assertTrue(self.summary["phase7_scope_unchanged"])

    def test_common_freeze_manifest_is_generated(self):
        self.assertEqual(
            json.loads(
                (ROOT / "configs/catalog/oids-phase9-common-qualification-v0.1.json").read_text(
                    encoding="utf-8"
                )
            )["decision"],
            COMMON_FREEZE,
        )
        self.assertTrue(self.summary["artifact_hashes_verified"])
        self.assertEqual(self.summary["bug_specific_condition_count"], 0)
        self.assertTrue(self.summary["common_freeze_manifest_generated"])
        self.assertTrue(self.summary["cross_filesystem_claim_allowed"])


if __name__ == "__main__":
    unittest.main()
