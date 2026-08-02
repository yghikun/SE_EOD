import tempfile
import unittest
from pathlib import Path

from src.fmpca.c_cfg import build_function_cfg
from src.fmpca.orphan_allpath import (
    BLOCKED,
    CLOSED,
    analyze_filesystem,
    cfg_proof_blockers,
    run_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
LINUX = ROOT / "linux-sources/linux-v6.14-fs"
MANIFEST = ROOT / "configs/evaluation/oids-phase4-allpath-v0.1.json"


def phase4_config(filesystem):
    if filesystem == "btrfs":
        return {
            "filesystem": "btrfs",
            "registration": {
                "source": str(LINUX / "fs/btrfs/inode.c"),
                "caller": "btrfs_unlink",
                "helper": "btrfs_orphan_add",
            },
            "settlement": {
                "source": str(LINUX / "fs/btrfs/inode.c"),
                "function": "btrfs_evict_inode",
            },
            "recovery": {
                "cleanup_source": str(LINUX / "fs/btrfs/inode.c"),
                "cleanup_function": "btrfs_orphan_cleanup",
                "exposure_source": str(LINUX / "fs/btrfs/disk-io.c"),
                "gate_function": "btrfs_start_pre_rw_mount",
                "exposure_function": "open_ctree",
            },
        }
    return {
        "filesystem": "ext4",
        "registration": {
            "source": str(LINUX / "fs/ext4/namei.c"),
            "caller": "__ext4_unlink",
            "helper_source": str(LINUX / "fs/ext4/orphan.c"),
            "helper": "ext4_orphan_add",
        },
        "settlement": {
            "source": str(LINUX / "fs/ext4/inode.c"),
            "function": "ext4_evict_inode",
        },
        "recovery": {
            "cleanup_source": str(LINUX / "fs/ext4/orphan.c"),
            "cleanup_function": "ext4_orphan_cleanup",
            "exposure_source": str(LINUX / "fs/ext4/super.c"),
            "exposure_function": "__ext4_fill_super",
        },
    }


class OIDSPhase4AllPathTests(unittest.TestCase):
    def test_btrfs_registration_settlement_and_recovery_close(self):
        witness = analyze_filesystem(phase4_config("btrfs"))
        self.assertTrue(witness.closed)
        self.assertTrue(witness.registration.closed)
        self.assertTrue(witness.settlement.closed)
        self.assertTrue(witness.recovery.closed)
        self.assertEqual(witness.blockers, ())
        self.assertTrue(
            all(
                clause.status == CLOSED
                for stage in (witness.registration, witness.settlement, witness.recovery)
                for clause in stage.clauses
            )
        )

    def test_ext4_success_structure_closes_but_error_contracts_block(self):
        witness = analyze_filesystem(phase4_config("ext4"))
        self.assertFalse(witness.closed)
        self.assertFalse(witness.registration.closed)
        self.assertFalse(witness.settlement.closed)
        self.assertFalse(witness.recovery.closed)
        self.assertEqual(witness.settlement.clauses[0].status, CLOSED)
        self.assertEqual(witness.settlement.clauses[1].status, BLOCKED)
        self.assertIn("EXT4_REGISTRATION_RETURN_IGNORED", witness.blockers)
        self.assertIn("EXT4_ORPHAN_DEL_RETURN_IGNORED", witness.blockers)
        self.assertIn("EXT4_VOID_CLEANUP_HAS_NO_SUCCESS_OUTCOME", witness.blockers)

    def test_cfg_preserves_label_ownership_and_constant_loop_dominance(self):
        source = """
int sample(int fail) {
    while (1) {
        terminal_delete();
        if (!fail)
            break;
    }
out:
    registry_remove();
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.c"
            path.write_text(source, encoding="utf-8")
            cfg = build_function_cfg(str(path), "sample")
        terminal = cfg.find_calls(["terminal_delete"])[0]
        removal = cfg.find_calls(["registry_remove"])[0]
        label = cfg.labels["out"]
        self.assertTrue(cfg.dominates(terminal, removal))
        self.assertEqual(cfg.nodes[label].calls, ())

    def test_parse_errors_and_unresolved_gotos_are_hard_blockers(self):
        malformed = "int malformed(void) { if (1) return 0 return 1; }"
        unresolved = "int unresolved(void) { goto missing; return 0; }"
        with tempfile.TemporaryDirectory() as directory:
            malformed_path = Path(directory) / "malformed.c"
            unresolved_path = Path(directory) / "unresolved.c"
            malformed_path.write_text(malformed, encoding="utf-8")
            unresolved_path.write_text(unresolved, encoding="utf-8")
            malformed_cfg = build_function_cfg(str(malformed_path), "malformed")
            unresolved_cfg = build_function_cfg(str(unresolved_path), "unresolved")
        self.assertIn("CFG_PARSE_ERROR:malformed", cfg_proof_blockers((malformed_cfg,)))
        self.assertIn("CFG_UNRESOLVED_GOTO:unresolved", cfg_proof_blockers((unresolved_cfg,)))

    def test_phase4_gate_refuses_common_freeze(self):
        summary = run_manifest(str(MANIFEST))
        assessment = summary["scope_assessment"]
        self.assertTrue(summary["artifact_hashes_verified"])
        self.assertEqual(summary["bug_specific_condition_count"], 0)
        self.assertFalse(summary["proof_closure_closed_per_filesystem"])
        self.assertTrue(assessment["common_candidate_ready"])
        self.assertFalse(assessment["common_freeze_ready"])
        self.assertEqual(
            assessment["failed_freeze_gates"],
            ["proof_closure_closed_per_filesystem"],
        )
        self.assertFalse(summary["freeze_manifest_generated"])


if __name__ == "__main__":
    unittest.main()
