import hashlib
import json
import unittest
from pathlib import Path

from src.fmpca.model import AnalysisResult
from src.fmpca.orphan_phase6 import (
    BOUNDARY,
    analyze_failstop_recovery,
    analyze_phase6,
    analyze_transaction_commit,
    run_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
LINUX = ROOT / "linux-sources/linux-v6.14-fs"
MANIFEST = ROOT / "configs/evaluation/oids-phase6-configuration-boundary-v0.1.json"
PROTOCOL = ROOT / "configs/protocols/common/orphan-inode-deletion-settlement-v0.1-candidate.json"


def config():
    return {
        "source_root": str(LINUX),
        "protocol": str(PROTOCOL),
        "negative_witnesses": [
            {
                "stage": stage,
                "fixture": str(
                    ROOT
                    / f"tests/fixtures/events/oids-ext4-errors-cont-{stage}-v0.1.json"
                ),
                "expected_rule": rule,
            }
            for stage, rule in (
                ("registration", "OIDS-O1"),
                ("settlement", "OIDS-O2"),
                ("recovery", "OIDS-O3"),
            )
        ],
    }


class OIDSPhase6ConfigurationBoundaryTests(unittest.TestCase):
    def test_failstop_recovery_propagates_flush_error_to_mount_failure(self):
        proof = analyze_failstop_recovery(str(LINUX))
        self.assertTrue(proof.closed)
        facts = {item.fact for item in proof.evidence}
        self.assertIn("aborted journal flush returns -EIO", facts)
        self.assertIn("marker error selects failed_mount9", facts)
        self.assertIn("mount returns propagated error", facts)

    def test_dirty_metadata_is_filed_on_transaction_metadata_list(self):
        witness = analyze_transaction_commit(str(LINUX))
        self.assertTrue(witness.closed)
        self.assertTrue(witness.metadata_filed_on_transaction)
        self.assertTrue(witness.commit_reads_metadata_list)

    def test_commit_discards_only_for_journal_abort_not_handle_abort(self):
        witness = analyze_transaction_commit(str(LINUX))
        self.assertTrue(witness.discard_requires_journal_abort)
        self.assertTrue(witness.handle_abort_is_not_journal_abort)
        self.assertTrue(witness.handle_abort_does_not_prevent_commit)

    def test_registration_errors_cont_replay_violates_oids_o1(self):
        witness = analyze_phase6(config()).errors_continue[0]
        self.assertTrue(witness.closed)
        self.assertEqual(witness.result, AnalysisResult.VIOLATION.value)
        self.assertIn("OIDS-O1", witness.violation_rules)

    def test_settlement_errors_cont_replay_violates_oids_o2(self):
        witness = analyze_phase6(config()).errors_continue[1]
        self.assertTrue(witness.closed)
        self.assertEqual(witness.result, AnalysisResult.VIOLATION.value)
        self.assertIn("OIDS-O2", witness.violation_rules)

    def test_recovery_errors_cont_replay_violates_oids_o3(self):
        witness = analyze_phase6(config()).errors_continue[2]
        self.assertTrue(witness.closed)
        self.assertEqual(witness.result, AnalysisResult.VIOLATION.value)
        self.assertIn("OIDS-O3", witness.violation_rules)

    def test_errors_cont_is_valid_configuration_boundary(self):
        assessment = analyze_phase6(config())
        self.assertEqual(assessment.configuration_scope_decision, BOUNDARY)
        self.assertTrue(assessment.failstop_profile_closed)
        self.assertTrue(assessment.errors_continue_negative_witness_closed)
        self.assertFalse(assessment.universal_all_path_closed)

    def test_manifest_closes_failstop_but_refuses_universal_and_freeze(self):
        summary = run_manifest(str(MANIFEST))
        self.assertTrue(summary["artifact_hashes_verified"])
        self.assertEqual(summary["bug_specific_condition_count"], 0)
        self.assertTrue(summary["failstop_profile_closed"])
        self.assertTrue(summary["errors_continue_negative_witness_closed"])
        self.assertFalse(summary["universal_all_path_closed"])
        self.assertFalse(summary["common_freeze_manifest_generated"])
        semantics_hash = hashlib.sha256((ROOT / "src/fmpca/semantics.py").read_bytes()).hexdigest()
        source_hash = hashlib.sha256((LINUX / "SOURCE_MANIFEST.json").read_bytes()).hexdigest()
        self.assertEqual(
            semantics_hash,
            "526ebf1c1a4342fc461d5d635baefeb06c8293e48c1648e93c7020248884999b",
        )
        self.assertEqual(
            source_hash,
            "302223b94530376b980c082621ec2a9c34b05dcfb27bfa45a3adf776e669918c",
        )
        phase6_sources = json.loads(
            (LINUX / "PHASE6_SUPPLEMENTARY_MANIFEST.json").read_text(encoding="utf-8")
        )
        for item in phase6_sources["supplementary_source_files"]:
            actual = hashlib.sha256((LINUX / item["path"]).read_bytes()).hexdigest()
            self.assertEqual(actual, item["sha256"])


if __name__ == "__main__":
    unittest.main()
