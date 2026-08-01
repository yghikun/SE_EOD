import hashlib
import json
import unittest
from pathlib import Path

from src.fmpca.evaluation import run_manifest


ROOT = Path(__file__).resolve().parents[1]


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = run_manifest(str(ROOT / "configs/evaluation/e0-v0.1.json"))

    def test_all_e0_cases_pass(self):
        self.assertEqual(self.summary["total"], 23)
        self.assertEqual(self.summary["passed"], 23)
        self.assertEqual(self.summary["failed"], 0)

    def test_held_out_does_not_modify_checker(self):
        held_out = [case for case in self.summary["cases"] if "HELD_OUT" in case["role"]]
        self.assertEqual(len(held_out), 3)
        self.assertTrue(all(case["passed"] for case in held_out))
        self.assertEqual(self.summary["held_out_checker_modifications"], 0)
        self.assertEqual(self.summary["bug_specific_condition_count"], 0)

    def test_fmpca_catches_relation_violation_local_baseline_marks_handled(self):
        case = next(
            item for item in self.summary["cases"]
            if item["id"] == "frc-bug-18-partial-container"
        )
        self.assertEqual(case["actual"], "VIOLATION_UNDER_LOADED_SPEC")
        self.assertEqual(case["baselines"]["B2_LOCAL_FIELD_RESTORATION"], "HANDLED")

    def test_semantic_freeze_hash_matches(self):
        freeze_path = ROOT / "configs/freeze/semantic-freeze-v0.1.json"
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
        for relative, expected in freeze["artifacts"].items():
            actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, expected)


class DomainEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = run_manifest(str(ROOT / "configs/evaluation/e1-v0.2.json"))

    def test_all_e1_cases_pass_without_bug_specific_conditions(self):
        self.assertEqual(self.summary["total"], 14)
        self.assertEqual(self.summary["passed"], 14)
        self.assertEqual(self.summary["failed"], 0)
        self.assertEqual(self.summary["bug_specific_condition_count"], 0)

    def test_e1_does_not_manufacture_held_out_operation_families(self):
        manifest = json.loads(
            (ROOT / "configs/evaluation/e1-v0.2.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["held_out_operation_families"], [])
        self.assertFalse(any("HELD_OUT" in case["role"] for case in self.summary["cases"]))

    def test_domain_semantic_freeze_hash_matches(self):
        freeze_path = ROOT / "configs/freeze/domain-semantic-freeze-v0.2.json"
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
        for relative, expected in freeze["artifacts"].items():
            actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
