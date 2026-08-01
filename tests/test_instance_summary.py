import json
import unittest
from pathlib import Path

from src.fmpca.analyzer import ProtocolAnalyzer
from src.fmpca.dsl import load_protocol
from src.fmpca.instance import AliasDecision, InstanceStore
from src.fmpca.model import EvidenceEvent, Fact, Precision
from src.fmpca.semantics import ProtocolEngine
from src.fmpca.summary import GuardedSummary, SummaryRow, apply_summary, join_states


ROOT = Path(__file__).resolve().parents[1]


class InstanceReconstructionTests(unittest.TestCase):
    def setUp(self):
        self.spec = load_protocol(
            str(ROOT / "configs/protocols/metadata-transition-outcome-v0.1.json")
        )

    def test_exact_anchor_reuses_instance(self):
        event = EvidenceEvent.from_dict(
            json.loads((ROOT / "tests/fixtures/events/mto-bug.json").read_text())["events"][0]
        )
        store = InstanceStore(self.spec)
        first = store.select_or_create(event)
        second = store.select_or_create(event)
        self.assertIs(first.candidates[0], second.candidates[0])
        self.assertEqual(store.resolve_alias("inode:1", "inode:1"), AliasDecision.MUST_ALIAS)

    def test_missing_anchor_is_incomplete_candidate_set(self):
        event = EvidenceEvent("Begin", {"operation": "op"}, {"operation_root": "op", "retry_generation": 0})
        selected = InstanceStore(self.spec).select_or_create(event)
        self.assertTrue(selected.overflowed)
        self.assertEqual(selected.candidates, [])

    def test_interleaved_instances_are_not_merged(self):
        bug = json.loads((ROOT / "tests/fixtures/events/mto-bug.json").read_text())["events"]
        safe = json.loads((ROOT / "tests/fixtures/events/mto-normal-success.json").read_text())["events"]
        interleaved = []
        for index in range(max(len(bug), len(safe))):
            if index < len(bug):
                interleaved.append(EvidenceEvent.from_dict(bug[index]))
            if index < len(safe):
                interleaved.append(EvidenceEvent.from_dict(safe[index]))
        run = ProtocolAnalyzer(self.spec).run(interleaved, all_paths_closed=True)
        self.assertEqual(run.result.value, "VIOLATION_UNDER_LOADED_SPEC")
        self.assertEqual(len(run.reports), 2)


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.spec = load_protocol(
            str(ROOT / "configs/protocols/metadata-transition-outcome-v0.1.json")
        )
        self.engine = ProtocolEngine(self.spec)

    def test_unknown_summary_marks_footprint_unknown(self):
        state = self.engine.initial_state(
            {"operation": "op", "metadata_subject": "inode", "outcome_owner": "op"}
        )
        state.relation_facts["completion"] = Fact("PARTIAL")
        summary = GuardedSummary(
            "helper",
            [
                SummaryRow(
                    guard={"op": "literal", "value": True},
                    outcome="UNKNOWN",
                    events=[],
                    footprint=["completion"],
                    precision=Precision.UNKNOWN,
                )
            ],
        )
        output = apply_summary(self.engine, state, summary)[0]
        self.assertEqual(output.relation_facts["completion"].precision, Precision.UNKNOWN)

    def test_join_preserves_equal_fact_and_widens_conflict(self):
        left = self.engine.initial_state()
        right = self.engine.initial_state()
        left.relation_facts["x"] = Fact(1)
        right.relation_facts["x"] = Fact(1)
        equal = join_states(left, right)
        self.assertEqual(equal.relation_facts["x"].precision, Precision.JOIN_PRESERVED)
        right.relation_facts["x"] = Fact(2)
        conflict = join_states(left, right)
        self.assertEqual(conflict.relation_facts["x"].precision, Precision.WIDENED)


if __name__ == "__main__":
    unittest.main()
