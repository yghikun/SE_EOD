import copy
import json
import tempfile
import unittest
from pathlib import Path

from src.fmpca.dsl import ProtocolValidationError, load_protocol, validate_protocol
from src.fmpca.frontend import SourceBindingError, load_binding


ROOT = Path(__file__).resolve().parents[1]


class ProtocolDslTests(unittest.TestCase):
    def test_frozen_protocols_and_membership_fixture_validate(self):
        paths = [
            ROOT / "configs/protocols/metadata-transition-outcome-v0.1.json",
            ROOT / "configs/protocols/failure-rollback-conformance-v0.1.json",
            ROOT / "configs/protocols/membership-synthetic-fixture-v0.1.json",
        ]
        specs = [load_protocol(str(path)) for path in paths]
        self.assertEqual(
            [spec.protocol_id for spec in specs],
            [
                "fmpca.metadata_transition_outcome",
                "fmpca.failure_rollback_conformance",
                "fixture.membership_consistency",
            ],
        )

    def test_unknown_top_level_key_is_rejected(self):
        path = ROOT / "configs/protocols/metadata-transition-outcome-v0.1.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["typo_semantics"] = []
        with self.assertRaises(ProtocolValidationError):
            validate_protocol(raw)

    def test_bug_specific_predicate_is_rejected(self):
        path = ROOT / "configs/protocols/metadata-transition-outcome-v0.1.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["entry_formula"] = {
            "op": "literal",
            "value": True,
            "bug_id": 5,
        }
        with self.assertRaises(ProtocolValidationError):
            validate_protocol(raw)

    def test_duplicate_rule_id_is_rejected(self):
        path = ROOT / "configs/protocols/metadata-transition-outcome-v0.1.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["invariants"].append(copy.deepcopy(raw["invariants"][0]))
        with self.assertRaises(ProtocolValidationError):
            validate_protocol(raw)

    def test_binding_contains_no_target_function_or_bug_key(self):
        binding = load_binding(str(ROOT / "configs/bindings/outcome-return-v0.1.json"))
        self.assertNotIn("target_function", binding.raw)
        self.assertNotIn("bug_id", binding.raw)
        self.assertEqual(binding.protocol_id, "fmpca.metadata_transition_outcome")

    def test_nested_bug_specific_binding_key_is_rejected(self):
        path = ROOT / "configs/bindings/outcome-return-v0.1.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["role_kinds"]["hidden"] = {"target_function": "special_case"}
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "binding.json"
            candidate.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(SourceBindingError):
                load_binding(str(candidate))

    def test_unknown_binding_key_is_rejected(self):
        path = ROOT / "configs/bindings/outcome-return-v0.1.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["special_case"] = "hidden target selector"
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "binding.json"
            candidate.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(SourceBindingError):
                load_binding(str(candidate))


if __name__ == "__main__":
    unittest.main()
