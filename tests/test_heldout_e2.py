import unittest
import json
from pathlib import Path

from src.fmpca.dsl import load_protocol
from src.fmpca.evaluation import run_manifest
from src.fmpca.frontend import SourceBindingError
from src.fmpca.frontend_extensions import (
    analyze_revision_source,
    load_revision_binding,
    require_protocol_scope,
)


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "linux-sources/linux-v6.14-fs"
BUG_REVISION = "c0041b502e579a5c52e5cae918b90678f03faddd"
FIXED_REVISION = "83201804efa4a5168be754e1dfc9b2faee760cac"


class HeldOutRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = load_protocol(
            str(ROOT / "configs/protocols/recovery-attachment-settlement-v0.2.json")
        )
        cls.binding = load_revision_binding(
            str(ROOT / "configs/bindings/recovery-attachment-merge-v0.2.1.json")
        )

    def extract(self, revision):
        return analyze_revision_source(
            self.binding,
            str(REPO),
            revision,
            "fs/btrfs/relocation.c",
            "merge_reloc_roots",
            revision[:12],
        )

    def test_confirmed_bug_revision_preserves_missing_repair_evidence(self):
        analysis = self.extract(BUG_REVISION)
        repair = next(item for item in analysis.evidence if item["kind"] == "relation_repair_sequence")
        self.assertFalse(repair["restore_found"])

    def test_fixed_revision_preserves_target_repair_evidence(self):
        analysis = self.extract(FIXED_REVISION)
        repair = next(item for item in analysis.evidence if item["kind"] == "relation_repair_sequence")
        self.assertTrue(repair["restore_found"])

    def test_runtime_merge_binding_is_outside_frozen_ras_scope(self):
        with self.assertRaisesRegex(SourceBindingError, "relocation_failure"):
            require_protocol_scope(self.binding, self.protocol)

    def test_extension_binding_has_no_function_or_bug_special_case(self):
        text = (
            ROOT / "configs/bindings/recovery-attachment-merge-v0.2.1.json"
        ).read_text(encoding="utf-8").lower()
        self.assertNotIn("merge_reloc_roots", text)
        self.assertNotIn("bug_id", text)
        self.assertNotIn("target_function", text)


class HeldOutEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = run_manifest(str(ROOT / "configs/evaluation/e2-v0.2.json"))

    def test_e2_screening_closes_without_qualified_detection_cases(self):
        self.assertEqual(self.summary["total"], 0)
        self.assertEqual(self.summary["passed"], 0)
        self.assertEqual(self.summary["failed"], 0)
        self.assertEqual(self.summary["git_artifact_count"], 2)
        self.assertEqual(self.summary["bug_specific_condition_count"], 0)
        self.assertEqual(self.summary["held_out_operation_families"], [])
        self.assertEqual(len(self.summary["screening_rejections"]), 1)

    def test_e2_does_not_modify_or_claim_transfer_for_frozen_protocol(self):
        freeze = json.loads(
            (ROOT / "configs/freeze/heldout-semantic-freeze-e2-v0.2.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(freeze["protocol_acceptance_modifications"], 0)
        self.assertEqual(freeze["held_out_operation_families"], [])


if __name__ == "__main__":
    unittest.main()
