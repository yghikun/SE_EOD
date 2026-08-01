import json
import unittest
from pathlib import Path

from src.fmpca.dsl import load_protocol
from src.fmpca.model import AnalysisResult, EvidenceEvent, ObligationStatus
from src.fmpca.proof import analyze_state
from src.fmpca.semantics import ProtocolEngine


ROOT = Path(__file__).resolve().parents[1]


def run_fixture(protocol_name, fixture_name):
    spec = load_protocol(str(ROOT / "configs/protocols" / protocol_name))
    fixture = json.loads((ROOT / "tests/fixtures/events" / fixture_name).read_text(encoding="utf-8"))
    state = ProtocolEngine(spec).run(EvidenceEvent.from_dict(item) for item in fixture["events"])
    closure = fixture["closure"]
    return state, analyze_state(
        state,
        path_model_closed=closure["path_model_closed"],
        all_paths_closed=closure["all_paths_closed"],
        repair_slice_closed=closure["repair_slice_closed"],
        alias_closed=closure["alias_closed"],
    )


class OutcomeSemanticsTests(unittest.TestCase):
    PROTOCOL = "metadata-transition-outcome-v0.1.json"

    def test_bug_and_stale_retry_are_violations(self):
        for fixture in ["mto-bug.json", "mto-stale-retry.json"]:
            with self.subTest(fixture=fixture):
                _, report = run_fixture(self.PROTOCOL, fixture)
                self.assertEqual(report.result, AnalysisResult.VIOLATION)

    def test_fixed_and_normal_paths_are_conformant(self):
        for fixture in ["mto-fixed-error.json", "mto-normal-success.json"]:
            with self.subTest(fixture=fixture):
                _, report = run_fixture(self.PROTOCOL, fixture)
                self.assertEqual(report.result, AnalysisResult.CONFORMANT)

    def test_unknown_helper_cannot_prove_conformance(self):
        _, report = run_fixture(self.PROTOCOL, "mto-unknown-helper.json")
        self.assertEqual(report.result, AnalysisResult.INCOMPLETE)


class RollbackSemanticsTests(unittest.TestCase):
    PROTOCOL = "failure-rollback-conformance-v0.1.json"

    def test_transaction_abort_does_not_clear_update_list_obligation(self):
        state, report = run_fixture(self.PROTOCOL, "frc-bug-16-partial-cleanup.json")
        self.assertEqual(report.result, AnalysisResult.VIOLATION)
        obligation = state.obligations["FRC-O1:device.post_commit_list"]
        self.assertNotEqual(obligation.status, ObligationStatus.DISCHARGED)

    def test_delegation_requires_authority_completion(self):
        safe_state, safe_report = run_fixture(self.PROTOCOL, "frc-delegated-safe.json")
        bad_state, bad_report = run_fixture(self.PROTOCOL, "frc-delegated-incomplete.json")
        self.assertEqual(safe_report.result, AnalysisResult.CONFORMANT)
        self.assertEqual(bad_report.result, AnalysisResult.VIOLATION)
        self.assertTrue(all(claim.completed for claim in safe_state.authority_claims))
        self.assertTrue(any(not claim.completed for claim in bad_state.authority_claims))

    def test_exposure_records_irreversible_evidence(self):
        state, report = run_fixture(self.PROTOCOL, "frc-bug-17-exposure.json")
        self.assertEqual(report.result, AnalysisResult.VIOLATION)
        self.assertEqual(
            state.irreversible_violation_evidence[0]["code"],
            "INVALID_ACTIVE_TARGET_EXPOSED",
        )

    def test_full_rollback_is_conformant(self):
        state, report = run_fixture(self.PROTOCOL, "frc-full-rollback.json")
        self.assertEqual(report.result, AnalysisResult.CONFORMANT)
        self.assertTrue(
            all(item.status == ObligationStatus.DISCHARGED for item in state.obligations.values())
        )

    def test_unknown_restore_is_incomplete(self):
        _, report = run_fixture(self.PROTOCOL, "frc-unknown-helper.json")
        self.assertEqual(report.result, AnalysisResult.INCOMPLETE)


class MembershipFixtureTests(unittest.TestCase):
    PROTOCOL = "membership-synthetic-fixture-v0.1.json"

    def test_fixture_exercises_bug_and_fixed_vectors(self):
        _, bug = run_fixture(self.PROTOCOL, "membership-bug.json")
        _, fixed = run_fixture(self.PROTOCOL, "membership-fixed.json")
        self.assertEqual(bug.result, AnalysisResult.VIOLATION)
        self.assertEqual(fixed.result, AnalysisResult.CONFORMANT)


if __name__ == "__main__":
    unittest.main()

