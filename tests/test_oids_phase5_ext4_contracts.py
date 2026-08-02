import hashlib
import json
import unittest
from pathlib import Path

from src.fmpca.c_cfg_extensions import build_phase5_function_cfg
from src.fmpca.orphan_ext4_contracts import (
    BLOCKED,
    CLOSED,
    NOT_APPLICABLE,
    UNSAFE,
    analyze_ext4_contracts,
    run_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
LINUX = ROOT / "linux-sources/linux-v6.14-fs"
MANIFEST = ROOT / "configs/evaluation/oids-phase5-ext4-contracts-v0.1.json"


def assessment():
    return analyze_ext4_contracts({"source_root": str(LINUX)})


class OIDSPhase5Ext4ContractTests(unittest.TestCase):
    def test_phase5_cfg_normalizes_kernel_syntax_without_parse_errors(self):
        fill = build_phase5_function_cfg(
            str(LINUX / "fs/ext4/super.c"), "__ext4_fill_super"
        )
        orphan_del = build_phase5_function_cfg(
            str(LINUX / "fs/ext4/orphan.c"), "ext4_orphan_del"
        )
        reserve = build_phase5_function_cfg(
            str(LINUX / "fs/ext4/inode.c"), "ext4_reserve_inode_write"
        )
        self.assertFalse(fill.parse_has_error)
        self.assertFalse(orphan_del.parse_has_error)
        self.assertFalse(reserve.parse_has_error)
        self.assertIn("label_before_preprocessor", fill.normalized_attributes)
        self.assertIn("kernel_macro_type_argument", orphan_del.normalized_attributes)
        self.assertIn("split_return_type", reserve.normalized_attributes)

    def test_jbd2_handle_abort_is_not_journal_abort(self):
        abort_handle = build_phase5_function_cfg(
            str(LINUX / "include/linux/jbd2.h"), "jbd2_journal_abort_handle"
        )
        journal_stop = build_phase5_function_cfg(
            str(LINUX / "fs/jbd2/transaction.c"), "jbd2_journal_stop"
        )
        handle_error = build_phase5_function_cfg(
            str(LINUX / "fs/ext4/super.c"), "ext4_handle_error"
        )
        self.assertTrue(abort_handle.find_text(["handle->h_aborted = 1"]))
        self.assertTrue(journal_stop.find_text(["is_handle_aborted(handle)"]))
        self.assertEqual(journal_stop.find_calls(["jbd2_journal_abort"]), [])
        self.assertTrue(handle_error.find_calls(["jbd2_journal_abort"]))
        self.assertTrue(handle_error.find_text(["ERRORS_CONT"]))

    def test_registration_contract_is_guarded_by_error_policy(self):
        stage = assessment().registration
        statuses = {item.summary_id: item.status for item in stage.summaries}
        self.assertEqual(statuses["EXT4-RC-1"], CLOSED)
        self.assertEqual(statuses["EXT4-RC-2"], CLOSED)
        self.assertEqual(statuses["EXT4-RC-3"], CLOSED)
        self.assertEqual(statuses["EXT4-RC-4"], UNSAFE)
        self.assertFalse(stage.universal_closed)
        self.assertTrue(stage.failstop_closed)

    def test_settlement_success_and_failstop_close_but_errors_cont_does_not(self):
        stage = assessment().settlement
        statuses = {item.summary_id: item.status for item in stage.summaries}
        self.assertEqual(statuses["EXT4-SC-1"], CLOSED)
        self.assertEqual(statuses["EXT4-SC-2"], CLOSED)
        self.assertEqual(statuses["EXT4-SC-3"], UNSAFE)
        self.assertIn(
            "EXT4_ERRORS_CONT_REMOVAL_ONLY_COMMIT_NOT_EXCLUDED", stage.blockers
        )

    def test_recovery_partitions_nonapplicable_dispatch_and_error_paths(self):
        stage = assessment().recovery
        statuses = {item.summary_id: item.status for item in stage.summaries}
        self.assertEqual(statuses["EXT4-CC-1"], NOT_APPLICABLE)
        self.assertEqual(statuses["EXT4-CC-2"], CLOSED)
        self.assertEqual(statuses["EXT4-CC-3"], BLOCKED)
        self.assertEqual(statuses["EXT4-CC-4"], UNSAFE)
        self.assertIn(
            "EXT4_RECOVERY_FAILSTOP_FLUSH_CONTRACT_NOT_LOCKED", stage.blockers
        )

    def test_supplementary_jbd2_sources_match_manifest_hashes(self):
        source_manifest = json.loads(
            (LINUX / "PHASE5_SUPPLEMENTARY_MANIFEST.json").read_text(
                encoding="utf-8"
            )
        )
        base_hash = hashlib.sha256((LINUX / "SOURCE_MANIFEST.json").read_bytes()).hexdigest()
        self.assertEqual(base_hash, source_manifest["base_source_manifest_sha256"])
        for item in source_manifest["supplementary_source_files"]:
            actual = hashlib.sha256((LINUX / item["path"]).read_bytes()).hexdigest()
            self.assertEqual(actual, item["sha256"])

    def test_phase5_manifest_refuses_universal_and_common_freeze(self):
        summary = run_manifest(str(MANIFEST))
        self.assertTrue(summary["artifact_hashes_verified"])
        self.assertEqual(summary["bug_specific_condition_count"], 0)
        self.assertFalse(summary["universal_all_path_closed"])
        self.assertFalse(summary["failstop_profile_closed"])
        self.assertFalse(summary["common_freeze_manifest_generated"])


if __name__ == "__main__":
    unittest.main()
