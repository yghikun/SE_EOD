import json
import unittest
from pathlib import Path

from src.fmpca.chunk_candidate import run_manifest
from src.fmpca.dsl import load_protocol
from src.fmpca.frontend import SourceBindingError
from src.fmpca.frontend_chunk import (
    analyze_chunk_release_source,
    analyze_chunk_reservation_source,
    analyze_chunk_update_source,
    load_chunk_binding,
)
from src.fmpca.model import AnalysisResult, EvidenceEvent
from src.fmpca.proof import analyze_state
from src.fmpca.semantics import ProtocolEngine


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "configs/protocols/chunk-metadata-reservation-completion-v0.5.json"
BINDING = ROOT / "configs/bindings/chunk-metadata-reservation-completion-v0.5.json"
MANIFEST = ROOT / "configs/evaluation/cmrc-v0.5-readiness.json"
BLOCK_GROUP = ROOT / "linux-sources/linux-v6.14-fs/fs/btrfs/block-group.c"
ZONED = ROOT / "linux-sources/linux-v6.14-fs/fs/btrfs/zoned.c"
TRANSACTION = ROOT / "linux-sources/linux-v6.14-fs/fs/btrfs/transaction.c"
VOLUMES_V71 = ROOT / "linux-sources/linux-v7.1-fs/fs/btrfs/volumes.c"


def run_fixture(name):
    protocol = load_protocol(str(PROTOCOL))
    fixture = json.loads(
        (ROOT / "tests/fixtures/events" / name).read_text(encoding="utf-8")
    )
    state = ProtocolEngine(protocol).run(
        EvidenceEvent.from_dict(item) for item in fixture["events"]
    )
    closure = fixture["closure"]
    return analyze_state(
        state,
        path_model_closed=closure["path_model_closed"],
        all_paths_closed=closure["all_paths_closed"],
        repair_slice_closed=closure["repair_slice_closed"],
        alias_closed=closure["alias_closed"],
    )


class ChunkMetadataReservationCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = run_manifest(str(MANIFEST))

    def test_protocol_and_binding_load_without_case_specialization(self):
        protocol = load_protocol(str(PROTOCOL))
        binding = load_chunk_binding(str(BINDING))
        self.assertEqual(
            protocol.protocol_id,
            "fmpca.chunk_metadata_reservation_completion",
        )
        self.assertEqual(binding.protocol_id, protocol.protocol_id)
        text = BINDING.read_text(encoding="utf-8").lower()
        self.assertNotIn("bug_id", text)
        self.assertNotIn("target_function", text)
        self.assertNotIn("source_line", text)

    def test_binding_rejects_wrong_protocol_scope(self):
        raw = json.loads(BINDING.read_text(encoding="utf-8"))
        raw["protocol_id"] = "fmpca.wrong_protocol"
        temp = ROOT / "outputs/tmp-invalid-cmrc-binding.json"
        try:
            temp.parent.mkdir(parents=True, exist_ok=True)
            temp.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(SourceBindingError):
                load_chunk_binding(str(temp))
        finally:
            if temp.exists():
                temp.unlink()

    def test_source_witness_closes_bug_path_and_release_settlement(self):
        binding = load_chunk_binding(str(BINDING))
        witness = analyze_chunk_reservation_source(
            binding,
            str(BLOCK_GROUP),
            "reserve_chunk_space",
            positive_success_source=str(ZONED),
            positive_success_function="btrfs_zoned_activate_one_bg",
        )
        self.assertTrue(witness.selected_bug_path_closed)
        self.assertTrue(witness.source_semantic_footprint_closed)
        self.assertTrue(witness.positive_success_possible)
        self.assertTrue(witness.success_result_reused_as_reservation_guard)
        self.assertFalse(witness.success_result_normalized_before_guard)

        release = analyze_chunk_release_source(
            binding,
            str(TRANSACTION),
            "btrfs_trans_release_chunk_metadata",
        )
        self.assertTrue(release.selected_release_path_closed)
        self.assertTrue(release.guarded_by_reserved_bytes)
        self.assertTrue(release.release_call_found)
        self.assertTrue(release.reserved_bytes_zeroed)

    def test_second_family_device_item_update_source_witness_closes(self):
        binding = load_chunk_binding(str(BINDING))
        witness = analyze_chunk_update_source(
            binding,
            str(VOLUMES_V71),
            "btrfs_grow_device",
            operation_family="btrfs-device-item-update",
        )
        self.assertTrue(witness.selected_update_path_closed)
        self.assertTrue(witness.reservation_wrapper_found)
        self.assertTrue(witness.metadata_update_found)
        self.assertTrue(witness.release_wrapper_found)
        self.assertTrue(witness.order_closed)

    def test_bug_fixed_normal_and_unknown_replay(self):
        self.assertEqual(
            run_fixture("cmrc-bug-v0.5.json").result,
            AnalysisResult.VIOLATION,
        )
        self.assertEqual(
            run_fixture("cmrc-fixed-v0.5.json").result,
            AnalysisResult.CONFORMANT,
        )
        self.assertEqual(
            run_fixture("cmrc-normal-v0.5.json").result,
            AnalysisResult.CONFORMANT,
        )
        self.assertEqual(
            run_fixture("cmrc-device-update-normal-v0.5.json").result,
            AnalysisResult.CONFORMANT,
        )
        self.assertEqual(
            run_fixture("cmrc-unknown-v0.5.json").result,
            AnalysisResult.INCOMPLETE,
        )

    def test_candidate_is_now_freeze_eligible_after_second_family_screening(self):
        self.assertTrue(self.summary["candidate_ready"])
        self.assertTrue(self.summary["freeze_eligible"])
        self.assertEqual(
            self.summary["freeze_id"],
            "fmpca-domain-semantic-freeze-v0.5",
        )
        self.assertEqual(self.summary["failed_candidate_gates"], [])
        self.assertEqual(self.summary["failed_freeze_gates"], [])
        self.assertEqual(self.summary["operation_family_count"], 2)
        self.assertEqual(
            self.summary["second_family_screening"]["closed_independent_families"],
            ["btrfs-device-item-update"],
        )
        self.assertEqual(self.summary["replay"]["passed"], 5)
        self.assertEqual(self.summary["bug_specific_condition_count"], 0)


if __name__ == "__main__":
    unittest.main()
