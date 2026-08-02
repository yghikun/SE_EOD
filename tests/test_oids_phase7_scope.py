import hashlib
import json
import unittest
from pathlib import Path

from src.fmpca.orphan_phase7 import analyze_phase7, run_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs/evaluation/oids-phase7-scope-freeze-v0.1.json"


class OIDSPhase7ScopeTests(unittest.TestCase):
    def test_qualified_scope_is_valid_fs_specific_narrow_freeze(self):
        summary = run_manifest(str(MANIFEST))
        assessment = summary["assessment"]
        scope = assessment["scope"]
        self.assertTrue(summary["qualified_scope_closed"])
        self.assertTrue(scope["declaration_valid"])
        self.assertEqual(scope["declared_semantic_scope"], "FS_SPECIFIC")
        self.assertEqual(scope["freeze_boundary"], "NARROW_FREEZE")
        self.assertEqual(scope["applicable_filesystems"], ["ext4"])

    def test_errors_cont_is_an_explicit_applicability_exclusion(self):
        declaration = json.loads(
            (ROOT / "configs/evaluation/oids-phase7-ext4-failstop-scope-v0.1.json").read_text(
                encoding="utf-8"
            )
        )
        predicate = declaration["applicability_predicate"]
        self.assertEqual(predicate["excluded_error_policies"], ["ERRORS_CONT"])
        self.assertIn(
            "EXCLUDED_BY_EXPLICIT_PREDICATE",
            [item["status"] for item in declaration["excluded_configurations"]],
        )

    def test_phase6_gates_and_heldout_policy_are_preserved(self):
        summary = run_manifest(str(MANIFEST))
        assessment = summary["assessment"]
        self.assertTrue(assessment["phase6_failstop_closed"])
        self.assertTrue(assessment["phase6_negative_witnesses_closed"])
        self.assertFalse(summary["common_freeze_manifest_generated"])
        self.assertFalse(summary["blind_held_out_claim_allowed"])
        self.assertEqual(assessment["independent_family_status"], "NOT_A_BLIND_HELD_OUT")

    def test_historical_hashes_remain_unchanged(self):
        semantics = hashlib.sha256((ROOT / "src/fmpca/semantics.py").read_bytes()).hexdigest()
        source = hashlib.sha256(
            (ROOT / "linux-sources/linux-v6.14-fs/SOURCE_MANIFEST.json").read_bytes()
        ).hexdigest()
        taxonomy = hashlib.sha256(
            (ROOT / "configs/catalog/protocol-scope-taxonomy-v0.1.json").read_bytes()
        ).hexdigest()
        self.assertEqual(
            semantics,
            "526ebf1c1a4342fc461d5d635baefeb06c8293e48c1648e93c7020248884999b",
        )
        self.assertEqual(
            source,
            "302223b94530376b980c082621ec2a9c34b05dcfb27bfa45a3adf776e669918c",
        )
        self.assertEqual(taxonomy, "c4c1055e1c90b9c47ecf56a6f1d09331129f3d1a07c1555a14cf4b53c50119a4")


if __name__ == "__main__":
    unittest.main()
