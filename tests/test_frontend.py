import unittest
from pathlib import Path

from src.fmpca.dsl import load_protocol
from src.fmpca.frontend import (
    analyze_outcome_source,
    analyze_rollback_source,
    extract_function,
    load_binding,
)
from src.fmpca.model import AnalysisResult
from src.fmpca.proof import analyze_state
from src.fmpca.semantics import ProtocolEngine


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "configs/protocols/metadata-transition-outcome-v0.1.json"
BINDING = ROOT / "configs/bindings/outcome-return-v0.1.json"
BTRFS_PROTOCOL = ROOT / "configs/protocols/failure-rollback-conformance-v0.1.json"
BTRFS_BINDING = ROOT / "configs/bindings/btrfs-active-attachment-v0.1.json"


def analyze(path, version, function):
    spec = load_protocol(str(PROTOCOL))
    binding = load_binding(str(BINDING))
    source = analyze_outcome_source(binding, str(path), function, version)
    state = ProtocolEngine(spec).run(source.events)
    return source, analyze_state(
        state,
        path_model_closed=source.path_model_closed,
        all_paths_closed=source.all_paths_closed,
        repair_slice_closed=source.repair_slice_closed,
    )


class CFrontendTests(unittest.TestCase):
    def test_function_extractor_ignores_comment_braces(self):
        source = """
static int wanted(struct thing *item)
{
    /* } not a function end */
    if (item) { return 0; }
    return -1;
}
"""
        function = extract_function(source, "wanted")
        self.assertIn("return -1", function.text)
        self.assertEqual(function.first_parameter_identity, "parameter:0:struct/thing:item")

    def test_ext4_bug_and_fixed_version_differential(self):
        bug_source, bug = analyze(
            ROOT / "linux-sources/linux-v6.8-fs/fs/ext4/fast_commit.c",
            "linux-v6.8",
            "ext4_fc_replay_inode",
        )
        fixed_source, fixed = analyze(
            ROOT / "linux-sources/linux-v7.1-fs/fs/ext4/fast_commit.c",
            "linux-v7.1",
            "ext4_fc_replay_inode",
        )
        self.assertEqual(bug.result, AnalysisResult.VIOLATION)
        self.assertEqual(fixed.result, AnalysisResult.CONFORMANT)
        self.assertEqual(bug_source.evidence[-1]["expression"], "0")
        self.assertEqual(fixed_source.evidence[-1]["expression"], "ret")

    def test_xfs_held_out_patterns_need_no_function_specific_binding(self):
        summary_source, summary = analyze(
            ROOT / "linux-sources/linux-v6.8-fs/fs/xfs/xfs_rtalloc.c",
            "linux-v6.8",
            "xfs_rtcopy_summary",
        )
        ensure_source, ensure = analyze(
            ROOT / "linux-sources/linux-v6.14-fs/fs/xfs/xfs_rtalloc.c",
            "linux-v6.14",
            "xfs_rtginode_ensure",
        )
        self.assertEqual(summary.result, AnalysisResult.VIOLATION)
        self.assertEqual(ensure.result, AnalysisResult.VIOLATION)
        self.assertEqual(ensure_source.evidence[0]["kind"], "ignored_nonabsence_error")
        binding_text = BINDING.read_text(encoding="utf-8")
        self.assertNotIn("xfs_rtcopy_summary", binding_text)
        self.assertNotIn("xfs_rtginode_ensure", binding_text)

    def test_resource_lifetime_scope_negative_does_not_apply(self):
        _, report = analyze(
            ROOT / "linux-sources/linux-v6.14-fs/fs/ext4/orphan.c",
            "linux-v6.14",
            "ext4_init_orphan_info",
        )
        self.assertEqual(report.result, AnalysisResult.NO_APPLICABLE_PROTOCOL)

    def test_btrfs_relation_binding_finds_real_source_violation(self):
        spec = load_protocol(str(BTRFS_PROTOCOL))
        binding = load_binding(str(BTRFS_BINDING))
        source = analyze_rollback_source(
            binding,
            str(ROOT / "linux-sources/linux-v6.8-fs/fs/btrfs/relocation.c"),
            "btrfs_recover_relocation",
            "linux-v6.8",
        )
        state = ProtocolEngine(spec).run(source.events)
        report = analyze_state(
            state,
            path_model_closed=source.path_model_closed,
            all_paths_closed=source.all_paths_closed,
            repair_slice_closed=source.repair_slice_closed,
        )

        self.assertEqual(report.result, AnalysisResult.VIOLATION)
        self.assertEqual(
            [item["kind"] for item in source.evidence],
            ["active_attachment", "checked_failure_to_label", "repair_slice"],
        )
        self.assertEqual(source.evidence[0]["field_path"], "root.reloc_root")
        self.assertEqual(source.evidence[1]["error_label"], "out_unset")
        self.assertFalse(source.evidence[2]["release_found"])

    def test_btrfs_relation_binding_has_no_bug_or_function_special_case(self):
        binding = load_binding(str(BTRFS_BINDING))
        binding_text = BTRFS_BINDING.read_text(encoding="utf-8")

        self.assertEqual(binding.protocol_id, "fmpca.failure_rollback_conformance")
        self.assertNotIn("target_function", binding.raw)
        self.assertNotIn("bug_id", binding.raw)
        self.assertNotIn("btrfs_recover_relocation", binding_text)
        self.assertNotIn("bug-07", binding_text.lower())


if __name__ == "__main__":
    unittest.main()
