import json
import unittest
from pathlib import Path

from src.fmpca.dsl import load_protocol
from src.fmpca.frontend_device_shrink import analyze_patch_evidence
from src.fmpca.model import AnalysisResult, EvidenceEvent
from src.fmpca.proof import analyze_state
from src.fmpca.readiness import evaluate_readiness
from src.fmpca.semantics import ProtocolEngine


ROOT = Path(__file__).resolve().parents[1]


def run_fixture(name):
    protocol = load_protocol(
        str(ROOT / "configs/protocols/device-shrink-space-accounting-v0.3-draft.json")
    )
    values = json.loads(
        (ROOT / "tests/fixtures/events" / name).read_text(encoding="utf-8")
    )
    state = ProtocolEngine(protocol).run(EvidenceEvent.from_dict(item) for item in values)
    return analyze_state(
        state,
        path_model_closed=True,
        all_paths_closed=True,
        repair_slice_closed=True,
    )


class DeviceShrinkSpaceAccountingDraftTests(unittest.TestCase):
    def test_patch_provenance_distinguishes_bug_and_fixed_policies(self):
        evidence = analyze_patch_evidence(
            str(ROOT / "tests/fixtures/patches/btrfs-shrink-free-chunk-space-e9fd2c.json")
        )
        self.assertEqual(
            evidence["provenance"]["fixed_commit"],
            "e9fd2c05239ae423af45f99e2964ad086f800e33",
        )
        self.assertEqual(evidence["bug"], {"delta_valid": False, "rollback_guard_valid": False})
        self.assertEqual(evidence["fixed"], {"delta_valid": True, "rollback_guard_valid": True})

    def test_bug_policy_is_a_violation(self):
        report = run_fixture("dssa-bug.json")
        self.assertEqual(report.result, AnalysisResult.VIOLATION)
        self.assertEqual(set(report.violation_rules), {"DSSA-I1", "DSSA-I2", "ACCEPTANCE@AT_SETTLEMENT"})

    def test_fixed_success_and_failure_paths_conform(self):
        self.assertEqual(run_fixture("dssa-fixed-success.json").result, AnalysisResult.CONFORMANT)
        self.assertEqual(run_fixture("dssa-fixed-failure.json").result, AnalysisResult.CONFORMANT)

    def test_unknown_policy_cannot_prove_conformance(self):
        self.assertEqual(run_fixture("dssa-unknown.json").result, AnalysisResult.INCOMPLETE)

    def test_readiness_gate_keeps_singleton_draft_unfrozen(self):
        readiness = evaluate_readiness(
            str(ROOT / "configs/evaluation/dssa-v0.3-readiness.json")
        )
        self.assertFalse(readiness["freeze_eligible"])
        self.assertEqual(readiness["operation_family_count"], 1)
        self.assertEqual(
            readiness["failed_required_gates"],
            [
                "independent_design_evidence",
                "independent_normal_source",
                "independent_validation_family",
            ],
        )


if __name__ == "__main__":
    unittest.main()
