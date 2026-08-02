import hashlib
import json
import unittest
from pathlib import Path

from src.fmpca.orphan_phase11 import (
    APPLICABLE,
    BLOCKED,
    CLOSED,
    NON_CONFORMANT_HELDOUT,
    run_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs/evaluation/oids-phase11-reiserfs-heldout-v0.1.json"
PREREGISTRATION = ROOT / "configs/evaluation/oids-phase11-reiserfs-preregistration-v0.1.json"
SOURCE_MANIFEST = ROOT / "linux-sources/linux-v6.8-fs/PHASE11_REISERFS_SUPPLEMENTARY_MANIFEST.json"


class OIDSPhase11ReiserFSHeldoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = run_manifest(str(MANIFEST.relative_to(ROOT)))

    def test_preregistration_precedes_source_and_locks_prior_results(self):
        prereg = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
        source_manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(prereg["candidate_filesystem"], "ReiserFS")
        self.assertEqual(
            prereg["candidate_status_before_reveal"],
            "UNREVEALED_POST_COMMON_HELDOUT",
        )
        self.assertEqual(
            hashlib.sha256(PREREGISTRATION.read_bytes()).hexdigest(),
            source_manifest["preregistration_sha256"],
        )
        self.assertTrue(self.summary["preregistration_hash_verified"])
        self.assertTrue(self.summary["pre_reveal_locks_verified"])
        self.assertTrue(self.summary["third_filesystem_post_freeze"])

    def test_registered_source_set_is_exact_and_hash_verified(self):
        prereg = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
        source_manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
        acquired = {item["path"] for item in source_manifest["supplementary_source_files"]}
        self.assertEqual(acquired, set(prereg["registered_target_sources"]))
        self.assertTrue(self.summary["registered_sources_exact"])
        self.assertTrue(self.summary["source_hashes_verified"])

    def test_normal_registration_settlement_and_recovery_close(self):
        assessment = self.summary["assessment"]
        for stage in ("registration", "settlement", "recovery"):
            self.assertEqual(assessment[stage]["status"], CLOSED)
            self.assertTrue(assessment[stage]["closed"])
        self.assertTrue(assessment["normal_source_paths_closed"])
        self.assertIn("synchronous", assessment["recovery"]["conclusion"])

    def test_all_five_correspondence_dimensions_close(self):
        dimensions = {
            item["dimension"]: item for item in self.summary["assessment"]["correspondence"]
        }
        self.assertEqual(
            set(dimensions), {"object", "relation", "lifecycle", "authority", "deadline"}
        )
        self.assertTrue(all(item["status"] == CLOSED for item in dimensions.values()))
        self.assertTrue(all(item["closed"] for item in dimensions.values()))
        self.assertEqual(self.summary["applicability"], APPLICABLE)

    def test_failure_partitions_are_source_decided_without_narrowing(self):
        partitions = {
            item["profile"]: item
            for item in self.summary["assessment"]["failure_partitions"]
        }
        self.assertEqual(
            set(partitions),
            {
                "SAVE_LINK_ENOSPC_UNPROPAGATED",
                "SAVE_LINK_REMOVAL_ERROR_IGNORED",
                "RECOVERY_ERROR_EXPOSURE_REACHABLE",
            },
        )
        self.assertTrue(all(item["status"] == BLOCKED for item in partitions.values()))
        self.assertTrue(all(item["decided"] for item in partitions.values()))
        self.assertTrue(self.summary["assessment"]["failure_partitions_decided"])
        self.assertTrue(self.summary["outcome_dependent_narrowing_rejected"])

    def test_positive_and_negative_replays_match_registered_expectations(self):
        assessment = self.summary["assessment"]
        replays = {item["profile"]: item for item in assessment["replays"]}
        self.assertEqual(len(replays), 5)
        self.assertEqual(
            replays["SUCCESSFUL_LIVE_DELETION"]["actual"],
            "CONFORMANT_UNDER_LOADED_SPEC",
        )
        self.assertEqual(
            replays["SUCCESSFUL_RW_RECOVERY_EXPOSURE"]["actual"],
            "CONFORMANT_UNDER_LOADED_SPEC",
        )
        self.assertEqual(
            replays["SAVE_LINK_ENOSPC_UNPROPAGATED"]["actual"],
            "VIOLATION_UNDER_LOADED_SPEC",
        )
        self.assertIn("OIDS-O1", replays["SAVE_LINK_ENOSPC_UNPROPAGATED"]["violation_rules"])
        self.assertEqual(
            replays["RECOVERY_ERROR_EXPOSURE_REACHABLE"]["actual"],
            "VIOLATION_UNDER_LOADED_SPEC",
        )
        self.assertIn("OIDS-O3", replays["RECOVERY_ERROR_EXPOSURE_REACHABLE"]["violation_rules"])
        self.assertEqual(
            replays["SAVE_LINK_REMOVAL_ERROR_IGNORED"]["actual"],
            "INCOMPLETE_UNDER_LOADED_SPEC",
        )
        self.assertTrue(all(item["closed"] for item in replays.values()))

    def test_applicable_candidate_closes_as_nonconformant_heldout(self):
        assessment = self.summary["assessment"]
        self.assertTrue(assessment["source_witness_closed"])
        self.assertTrue(assessment["replay_expectations_closed"])
        self.assertTrue(assessment["violation_proof_closed"])
        self.assertTrue(assessment["nonconformance_proof_closed"])
        self.assertFalse(assessment["candidate_conformant"])
        self.assertEqual(self.summary["conformance_decision"], NON_CONFORMANT_HELDOUT)
        self.assertFalse(self.summary["candidate_conformant"])
        self.assertFalse(self.summary["common_heldout_validated"])

    def test_common_freeze_is_preserved_and_screening_closes(self):
        expected = {
            "configs/evaluation/oids-phase9-common-freeze-v0.1.json": "2b044c5498e0c157a62d0f0d48a11e984a3412d0530fbd5a9fb2534a3bf46082",
            "configs/protocols/common/orphan-inode-deletion-settlement-v0.1-candidate.json": "c95135df0a9c916cd863d557aedebf64f06ae7bfee5bcf81692ce56f3c263122",
            "src/fmpca/proof.py": "7d9f3af3f4e54b61ac9dbd05b938d3febaf8cbe34f1a7064fef0d42767009b8d",
        }
        for relative, digest in expected.items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), digest)
        self.assertTrue(self.summary["phase9_common_freeze_preserved"])
        self.assertTrue(self.summary["no_post_freeze_semantic_modifications"])
        self.assertTrue(self.summary["artifact_hashes_verified"])
        self.assertEqual(self.summary["bug_specific_condition_count"], 0)
        self.assertTrue(self.summary["phase11_screening_closed"])
        self.assertEqual(
            set(self.summary["failed_heldout_gates"]),
            {"heldout_replay_closed", "heldout_proof_closure_closed"},
        )


if __name__ == "__main__":
    unittest.main()
