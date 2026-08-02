import hashlib
import json
import unittest
from pathlib import Path

from src.fmpca.orphan_phase10 import (
    ASYNC_RECOVERY,
    DEADLINE_NOT_ALIGNED,
    NON_APPLICABLE,
    run_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs/evaluation/oids-phase10-ocfs2-heldout-v0.1.json"
PREREGISTRATION = ROOT / "configs/evaluation/oids-phase10-ocfs2-preregistration-v0.1.json"
AMENDMENT = ROOT / "configs/evaluation/oids-phase10-ocfs2-preregistration-amendment-v0.1.json"
SOURCE_MANIFEST = ROOT / "linux-sources/linux-v6.14-fs/PHASE10_OCFS2_SUPPLEMENTARY_MANIFEST.json"


class OIDSPhase10OCFS2HeldoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = run_manifest(str(MANIFEST))

    def test_preregistration_precedes_source_and_locks_the_common_freeze(self):
        prereg = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
        amendment = json.loads(AMENDMENT.read_text(encoding="utf-8"))
        self.assertEqual(prereg["candidate_filesystem"], "OCFS2")
        self.assertEqual(
            prereg["candidate_status_before_reveal"],
            "UNREVEALED_POST_COMMON_HELDOUT",
        )
        self.assertEqual(
            hashlib.sha256(PREREGISTRATION.read_bytes()).hexdigest(),
            amendment["preregistration_sha256"],
        )
        self.assertTrue(self.summary["preregistration_hash_verified"])
        self.assertTrue(self.summary["pre_reveal_locks_verified"])
        self.assertTrue(self.summary["third_filesystem_post_freeze"])

    def test_path_resolution_amendment_is_structural_only(self):
        amendment = json.loads(AMENDMENT.read_text(encoding="utf-8"))
        source_manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
        sources = {item["path"] for item in source_manifest["supplementary_source_files"]}
        self.assertEqual(sources, set(amendment["effective_target_sources"]))
        self.assertFalse(amendment["pre_reveal_semantics_modified"])
        self.assertFalse(amendment["candidate_modified"])
        self.assertFalse(amendment["source_revision_modified"])
        self.assertTrue(self.summary["source_hashes_verified"])

    def test_registration_and_settlement_close_without_semantic_changes(self):
        assessment = self.summary["assessment"]
        self.assertTrue(assessment["registration"]["closed"])
        self.assertTrue(assessment["settlement"]["closed"])
        self.assertIn("one JBD2 handle", assessment["registration"]["conclusion"])
        self.assertIn("atomically co-settled", assessment["settlement"]["conclusion"])
        self.assertTrue(self.summary["no_post_freeze_semantic_modifications"])

    def test_five_dimensions_are_decided_and_only_deadline_is_blocked(self):
        assessment = self.summary["assessment"]
        by_dimension = {
            item["dimension"]: item for item in assessment["correspondence"]
        }
        self.assertEqual(
            set(by_dimension), {"object", "relation", "lifecycle", "authority", "deadline"}
        )
        self.assertTrue(
            all(by_dimension[name]["closed"] for name in ("object", "relation", "lifecycle", "authority"))
        )
        self.assertFalse(by_dimension["deadline"]["closed"])
        self.assertEqual(by_dimension["deadline"]["reason_code"], DEADLINE_NOT_ALIGNED)
        self.assertTrue(assessment["screening_dimensions_decided"])
        self.assertTrue(assessment["controlled_non_applicable"])

    def test_async_recovery_boundary_is_preserved_as_incomplete(self):
        assessment = self.summary["assessment"]
        self.assertFalse(assessment["recovery"]["closed"])
        self.assertIn(
            "OCFS2_ORPHAN_RECOVERY_NOT_JOINED_BEFORE_MOUNT_EXPOSURE",
            assessment["recovery"]["blockers"],
        )
        replays = {item["profile"]: item for item in assessment["replays"]}
        self.assertEqual(
            replays["SUCCESSFUL_LIVE_DELETION"]["actual"],
            "CONFORMANT_UNDER_LOADED_SPEC",
        )
        self.assertEqual(
            replays[ASYNC_RECOVERY]["actual"],
            "INCOMPLETE_UNDER_LOADED_SPEC",
        )
        self.assertTrue(all(item["closed"] for item in replays.values()))
        self.assertFalse(assessment["heldout_replay_closed"])

    def test_controlled_non_applicable_does_not_validate_common_heldout(self):
        self.assertEqual(self.summary["applicability"], NON_APPLICABLE)
        self.assertEqual(self.summary["controlled_reason_code"], DEADLINE_NOT_ALIGNED)
        self.assertFalse(self.summary["common_heldout_validated"])
        self.assertFalse(self.summary["heldout_gates"]["heldout_correspondence_closed"])
        self.assertFalse(self.summary["heldout_gates"]["heldout_source_witness_closed"])
        self.assertFalse(self.summary["heldout_gates"]["heldout_replay_closed"])
        self.assertFalse(self.summary["heldout_gates"]["heldout_proof_closure_closed"])

    def test_phase9_common_freeze_and_protocol_hashes_are_unchanged(self):
        expected = {
            "configs/evaluation/oids-phase9-common-freeze-v0.1.json": "2b044c5498e0c157a62d0f0d48a11e984a3412d0530fbd5a9fb2534a3bf46082",
            "configs/evaluation/oids-phase9-common-scope-v0.1.json": "5e1c1eabb052c535ab53d932bd7276b7dfe85e9f70d1c7a22eecb91513cab3a5",
            "configs/protocols/common/orphan-inode-deletion-settlement-v0.1-candidate.json": "c95135df0a9c916cd863d557aedebf64f06ae7bfee5bcf81692ce56f3c263122",
        }
        for relative, digest in expected.items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), digest)
        self.assertTrue(self.summary["phase9_common_freeze_preserved"])
        self.assertTrue(self.summary["artifact_hashes_verified"])

    def test_phase10_screening_closes_as_a_negative_heldout_result(self):
        self.assertTrue(self.summary["phase10_screening_closed"])
        self.assertEqual(self.summary["bug_specific_condition_count"], 0)
        self.assertIn(
            "different unrevealed filesystem",
            self.summary["next_heldout_requirement"],
        )


if __name__ == "__main__":
    unittest.main()
