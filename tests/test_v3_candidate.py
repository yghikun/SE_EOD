import unittest
import json
from pathlib import Path

from src.fmpca.dsl import load_protocol
from src.fmpca.model import EvidenceEvent
from src.fmpca.frontend_extensions import (
    load_revision_binding,
    require_protocol_scope,
)
from src.fmpca.frontend_v3 import (
    analyze_preexisting_attachment_lifecycle,
    analyze_relocation_revision_source,
)
from src.fmpca.model import AnalysisResult
from src.fmpca.proof import analyze_state
from src.fmpca.readiness import evaluate_readiness
from src.fmpca.semantics import ProtocolEngine


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "linux-sources/linux-v6.14-fs"
BUG_REVISION = "c0041b502e579a5c52e5cae918b90678f03faddd"
FIXED_REVISION = "83201804efa4a5168be754e1dfc9b2faee760cac"


class RelocationRootAttachmentDraftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = load_protocol(str(ROOT / "configs/protocols/relocation-root-attachment-settlement-v0.3-draft.json"))
        cls.binding = load_revision_binding(str(ROOT / "configs/bindings/relocation-root-attachment-settlement-v0.3-draft.json"))
        require_protocol_scope(cls.binding, cls.protocol)

    def analyze(self, revision):
        analysis = analyze_relocation_revision_source(
            self.binding,
            str(REPO),
            revision,
            "fs/btrfs/relocation.c",
            "merge_reloc_roots",
            revision[:12],
        )
        report = analyze_state(
            ProtocolEngine(self.protocol).run(analysis.events),
            path_model_closed=analysis.path_model_closed,
            all_paths_closed=analysis.all_paths_closed,
            repair_slice_closed=analysis.repair_slice_closed,
        )
        return analysis, report

    def test_bug_is_an_exact_draft_violation(self):
        analysis, report = self.analyze(BUG_REVISION)
        self.assertEqual(report.result, AnalysisResult.VIOLATION)
        self.assertIn("RRM-I1", report.violation_rules)
        self.assertFalse(next(item for item in analysis.evidence if item["kind"] == "relation_repair_sequence")["restore_found"])

    def test_fixed_branch_is_closed_but_not_universal_conformance(self):
        analysis, report = self.analyze(FIXED_REVISION)
        self.assertEqual(report.result, AnalysisResult.INCOMPLETE)
        self.assertTrue(next(item for item in analysis.evidence if item["kind"] == "relation_repair_sequence")["restore_found"])

    def test_structured_normal_path_is_conformant_under_draft(self):
        events = json.loads((ROOT / "tests/fixtures/events/rras-normal.json").read_text(encoding="utf-8"))
        state = ProtocolEngine(self.protocol).run(EvidenceEvent.from_dict(item) for item in events)
        report = analyze_state(state, path_model_closed=True, all_paths_closed=True, repair_slice_closed=True)
        self.assertEqual(report.result, AnalysisResult.CONFORMANT)

    def test_fixed_source_closes_selected_origin_to_normal_settlement_chain(self):
        witness = analyze_preexisting_attachment_lifecycle(
            self.binding,
            str(REPO),
            FIXED_REVISION,
            "fs/btrfs/relocation.c",
            {
                "origin": "btrfs_init_reloc_root",
                "merge_driver": "merge_reloc_roots",
                "merge_helper": "merge_reloc_root",
                "handoff": "insert_dirty_subvol",
                "cleanup": "clean_dirty_subvols",
                "caller": "relocate_block_group",
            },
            ["btrfs_drop_snapshot", "btrfs_put_root"],
        )
        self.assertTrue(witness.selected_normal_path_closed)
        self.assertTrue(all(item["found"] for item in witness.evidence))
        order = next(item for item in witness.evidence if item["kind"] == "caller_settlement_order")
        self.assertLess(order["merge_line"], order["cleanup_line"])

    def test_readiness_allows_narrow_freeze_but_blocks_generalization(self):
        readiness = evaluate_readiness(
            str(ROOT / "configs/evaluation/rras-v0.3-readiness.json")
        )
        self.assertTrue(readiness["freeze_eligible"])
        self.assertEqual(readiness["operation_family_count"], 1)
        self.assertEqual(readiness["failed_required_gates"], [])
        self.assertFalse(readiness["generalization_eligible"])
        self.assertEqual(
            readiness["failed_generalization_gates"], ["independent_validation_family"]
        )
        self.assertFalse(readiness["held_out_family_available"])

    def test_draft_binding_is_not_bug_or_function_special_cased(self):
        text = (ROOT / "configs/bindings/relocation-root-attachment-settlement-v0.3-draft.json").read_text(encoding="utf-8").lower()
        self.assertNotIn("bug_id", text)
        self.assertNotIn("target_function", text)
        self.assertNotIn("merge_reloc_roots", text)


if __name__ == "__main__":
    unittest.main()
