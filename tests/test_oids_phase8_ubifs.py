import hashlib
import json
import unittest
from pathlib import Path

from src.fmpca.frontend_orphan_common import load_orphan_binding
from src.fmpca.model import AnalysisResult
from src.fmpca.orphan_phase8 import (
    APPLICABLE,
    DEFERRED_PROFILE,
    analyze_phase8,
    analyze_recovery,
    analyze_registration,
    analyze_settlement,
    run_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
LINUX = ROOT / "linux-sources/linux-v6.14-fs"
MANIFEST = ROOT / "configs/evaluation/oids-phase8-ubifs-validation-v0.1.json"
PREREGISTRATION = ROOT / "configs/evaluation/oids-phase8-ubifs-preregistration-v0.1.json"
AMENDMENT = ROOT / "configs/evaluation/oids-phase8-ubifs-preregistration-amendment-v0.1.json"
BINDING = ROOT / "configs/bindings/common/orphan-inode-ubifs-v0.1.json"
PROTOCOL = ROOT / "configs/protocols/common/orphan-inode-deletion-settlement-v0.1-candidate.json"


def config():
    return {
        "source_root": str(LINUX),
        "binding": str(BINDING),
        "protocol": str(PROTOCOL),
        "replays": [
            {
                "profile": profile,
                "fixture": str(ROOT / f"tests/fixtures/events/{fixture}"),
            }
            for profile, fixture in (
                ("LIVE_NO_INTERVENING_COMMIT", "oids-ubifs-live-no-commit-v0.1.json"),
                ("LIVE_POST_COMMIT", "oids-ubifs-live-post-commit-v0.1.json"),
                ("SUCCESSFUL_RW_RECOVERY_EXPOSURE", "oids-ubifs-rw-recovery-v0.1.json"),
                (DEFERRED_PROFILE, "oids-ubifs-ro-recovery-deferred-v0.1.json"),
            )
        ],
    }


class OIDSPhase8UBIFSTests(unittest.TestCase):
    def test_preregistration_and_amendment_are_immutable(self):
        preregistration_hash = hashlib.sha256(PREREGISTRATION.read_bytes()).hexdigest()
        amendment_hash = hashlib.sha256(AMENDMENT.read_bytes()).hexdigest()
        self.assertEqual(
            preregistration_hash,
            "9923997a1a885dccb7c2356d63c302d0c9512fd604084d59a8cad596d3d24e49",
        )
        self.assertEqual(
            amendment_hash,
            "981602b0bc1df6fd1fed5f5a120f76182191a73da110136efd2a08744ad1c17e",
        )

    def test_ubifs_binding_is_generic_and_loadable(self):
        binding = load_orphan_binding(str(BINDING))
        self.assertEqual(binding.filesystem, "ubifs")
        self.assertIn("ubifs_add_orphan", binding.registry_insert_primitives)
        self.assertIn("ubifs_tnc_remove_ino", binding.terminal_deletion_primitives)

    def test_registration_partitions_close(self):
        proof = analyze_registration(str(LINUX))
        self.assertTrue(proof.closed, proof.blockers)
        self.assertEqual(
            set(proof.partitions),
            {
                "pre_write_failure_rollback",
                "successful_journal_group",
                "post_write_failure_read_only_failstop",
                "commit_generation_persistence",
            },
        )

    def test_settlement_commit_generation_partitions_close(self):
        proof = analyze_settlement(str(LINUX))
        self.assertTrue(proof.closed, proof.blockers)
        facts = {item.fact for item in proof.evidence}
        self.assertIn("same-generation removal retires orphan only after TNC removal", facts)
        self.assertIn("post-commit path writes a replayable deletion inode", facts)
        self.assertIn("commit-owned deleted entries are erased after orphan write", facts)

    def test_successful_rw_recovery_dominates_root_exposure(self):
        proof = analyze_recovery(str(LINUX))
        self.assertTrue(proof.closed, proof.blockers)
        facts = {item.fact for item in proof.evidence}
        self.assertIn("successful RW recovery commits before mount completion", facts)
        self.assertIn("root is constructed only after mount_ubifs succeeds", facts)
        self.assertIn("read-only recovery is explicitly deferred", facts)

    def test_five_correspondence_dimensions_close(self):
        assessment = analyze_phase8(config())
        self.assertTrue(assessment.correspondence_closed, assessment.blockers)
        self.assertEqual(
            {item.dimension for item in assessment.correspondence},
            {"object", "relation", "lifecycle", "authority", "deadline"},
        )

    def test_replays_close_rw_and_preserve_read_only_deferred_boundary(self):
        assessment = analyze_phase8(config())
        by_profile = {item.profile: item for item in assessment.replays}
        self.assertEqual(
            by_profile["SUCCESSFUL_RW_RECOVERY_EXPOSURE"].actual,
            AnalysisResult.CONFORMANT.value,
        )
        self.assertEqual(
            by_profile[DEFERRED_PROFILE].actual,
            AnalysisResult.INCOMPLETE.value,
        )
        self.assertTrue(all(item.closed for item in assessment.replays))

    def test_manifest_closes_without_broadening_phase7_scope(self):
        summary = run_manifest(str(MANIFEST))
        self.assertEqual(summary["applicability"], APPLICABLE)
        self.assertTrue(summary["candidate_validation_closed"])
        self.assertTrue(summary["pre_reveal_locks_verified"])
        self.assertTrue(summary["source_hashes_verified"])
        self.assertEqual(summary["bug_specific_condition_count"], 0)
        self.assertTrue(summary["phase7_scope_unchanged"])
        self.assertTrue(summary["blind_held_out_claim_allowed"])
        self.assertFalse(summary["common_heldout_validated"])
        self.assertFalse(summary["common_freeze_manifest_generated"])
        phase7 = json.loads(
            (ROOT / "outputs/fmpca-oids-phase7-v0.1/summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            phase7["assessment"]["scope"]["applicable_filesystems"], ["ext4"]
        )


if __name__ == "__main__":
    unittest.main()
