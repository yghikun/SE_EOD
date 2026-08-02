import unittest
from dataclasses import replace
from pathlib import Path

from src.fmpca.dsl import load_protocol
from src.fmpca.frontend_orphan_common import (
    analyze_recovery_witness,
    analyze_registration_witness,
    analyze_settlement_witness,
    load_orphan_binding,
)
from src.fmpca.model import AnalysisResult
from src.fmpca.orphan_candidate import run_manifest
from src.fmpca.orphan_composition import (
    OIDSCompositionError,
    OIDSIdentity,
    compose_source_lifecycle,
)


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "configs/protocols/common/orphan-inode-deletion-settlement-v0.1-candidate.json"
MANIFEST = ROOT / "configs/evaluation/oids-phase3-readiness-v0.1.json"
LINUX = ROOT / "linux-sources/linux-v6.14-fs"


def source_evidence(filesystem):
    spec = load_protocol(str(PROTOCOL))
    binding = load_orphan_binding(
        str(ROOT / f"configs/bindings/common/orphan-inode-{filesystem}-v0.1.json")
    )
    if filesystem == "btrfs":
        registration = analyze_registration_witness(
            binding, str(LINUX / "fs/btrfs/inode.c"), "btrfs_unlink"
        )
        settlement = analyze_settlement_witness(
            binding, str(LINUX / "fs/btrfs/inode.c"), "btrfs_evict_inode"
        )
        recovery = analyze_recovery_witness(
            binding,
            str(LINUX / "fs/btrfs/inode.c"),
            "btrfs_orphan_cleanup",
            str(LINUX / "fs/btrfs/disk-io.c"),
            "open_ctree",
        )
    else:
        registration = analyze_registration_witness(
            binding, str(LINUX / "fs/ext4/namei.c"), "__ext4_unlink"
        )
        settlement = analyze_settlement_witness(
            binding, str(LINUX / "fs/ext4/inode.c"), "ext4_evict_inode"
        )
        recovery = analyze_recovery_witness(
            binding,
            str(LINUX / "fs/ext4/orphan.c"),
            "ext4_orphan_cleanup",
            str(LINUX / "fs/ext4/super.c"),
            "__ext4_fill_super",
        )
    identity = OIDSIdentity(
        filesystem=f"{filesystem}:fs",
        inode=f"{filesystem}:inode:7:gen:2",
        namespace_entry=f"{filesystem}:dirent:7",
        orphan_registry=f"{filesystem}:registry",
        filesystem_mount=f"{filesystem}:mount:1",
        inode_allocation_generation="2",
    )
    return spec, binding, registration, settlement, recovery, identity


class OIDSPhase3CompositionTests(unittest.TestCase):
    def test_recovery_ordering_closes_for_btrfs_and_ext4(self):
        for filesystem in ("btrfs", "ext4"):
            with self.subTest(filesystem=filesystem):
                *_, recovery, _identity = source_evidence(filesystem)
                self.assertTrue(recovery.cleanup_dispatch_found)
                self.assertTrue(recovery.zero_link_release_found)
                self.assertTrue(recovery.cleanup_before_exposure)
                self.assertTrue(recovery.recovery_path_closed)

    def test_normal_and_recovery_source_compositions_reach_acceptance(self):
        for filesystem in ("btrfs", "ext4"):
            with self.subTest(filesystem=filesystem):
                spec, binding, registration, settlement, recovery, identity = (
                    source_evidence(filesystem)
                )
                normal = compose_source_lifecycle(
                    spec,
                    binding,
                    registration,
                    settlement,
                    identity,
                    identity,
                )
                recovered = compose_source_lifecycle(
                    spec,
                    binding,
                    registration,
                    settlement,
                    identity,
                    identity,
                    mode="recovery",
                    recovery=recovery,
                )
                for composition in (normal, recovered):
                    self.assertTrue(composition.selected_path_closed)
                    self.assertTrue(composition.acceptance_true)
                    self.assertFalse(composition.all_paths_closed)
                    self.assertEqual(composition.report.result, AnalysisResult.INCOMPLETE)
                    self.assertEqual(composition.report.violation_rules, [])

    def test_inode_epoch_mismatch_is_not_composed(self):
        spec, binding, registration, settlement, _recovery, identity = source_evidence(
            "btrfs"
        )
        reused = replace(identity, inode_allocation_generation="3")
        with self.assertRaisesRegex(OIDSCompositionError, "one inode epoch"):
            compose_source_lifecycle(
                spec,
                binding,
                registration,
                settlement,
                identity,
                reused,
            )

    def test_readiness_closes_candidate_but_not_common_freeze(self):
        summary = run_manifest(str(MANIFEST))
        assessment = summary["scope_assessment"]
        self.assertTrue(summary["artifact_hashes_verified"])
        self.assertEqual(summary["bug_specific_condition_count"], 0)
        self.assertEqual(summary["replay"]["passed"], 6)
        self.assertTrue(assessment["common_candidate_ready"])
        self.assertFalse(assessment["common_freeze_ready"])
        self.assertEqual(
            assessment["failed_freeze_gates"],
            ["proof_closure_closed_per_filesystem"],
        )
        self.assertFalse(assessment["cross_filesystem_claim_allowed"])
        self.assertTrue(
            all(item["source_witness_closed"] for item in summary["filesystems"])
        )


if __name__ == "__main__":
    unittest.main()
