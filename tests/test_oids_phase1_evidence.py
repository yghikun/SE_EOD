import hashlib
import json
import unittest
from pathlib import Path

from src.fmpca.scope import load_taxonomy


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs/evaluation/oids-phase1-evidence-v0.1.json"
TAXONOMY = ROOT / "configs/catalog/protocol-scope-taxonomy-v0.1.json"


class OIDSPhase1EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.taxonomy = load_taxonomy(str(TAXONOMY))

    def test_source_snapshot_and_files_are_hash_locked(self):
        source_manifest = json.loads(
            (ROOT / self.manifest["source_snapshot"]["manifest"]).read_text(
                encoding="utf-8"
            )
        )
        for field in ("git_tag", "git_commit", "archive_sha256"):
            self.assertEqual(source_manifest[field], self.manifest["source_snapshot"][field])
        for relative, expected in self.manifest["source_files"].items():
            actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative)

    def test_all_required_phase1_artifacts_exist(self):
        self.assertEqual(len(self.manifest["artifacts"]), 4)
        for relative in self.manifest["artifacts"]:
            path = ROOT / relative
            self.assertTrue(path.is_file(), relative)
            self.assertGreater(path.stat().st_size, 1000, relative)

    def test_applicability_uses_taxonomy_statuses(self):
        statuses = set(self.taxonomy["applicability"]["statuses"])
        dimensions = set(self.taxonomy["correspondence_dimensions"])
        for filesystem in self.manifest["filesystems"]:
            self.assertIn(filesystem["applicability"], statuses)
            self.assertEqual(set(filesystem["correspondence"]), dimensions)
            self.assertTrue(
                all(value.startswith("CLOSED") for value in filesystem["correspondence"].values())
            )

    def test_phase2_basis_is_btrfs_and_ext4_only(self):
        basis = [
            item["filesystem"]
            for item in self.manifest["filesystems"]
            if item["used_for_phase2_basis"]
        ]
        self.assertEqual(basis, ["btrfs", "ext4"])
        decision = self.manifest["phase1_decision"]
        self.assertTrue(decision["source_correspondence_complete"])
        self.assertTrue(decision["phase2_eligible"])
        self.assertFalse(decision["common_candidate_ready"])
        self.assertFalse(decision["common_freeze_ready"])

    def test_xfs_is_revealed_screening_not_blind_heldout(self):
        xfs = next(
            item for item in self.manifest["filesystems"]
            if item["filesystem"] == "xfs"
        )
        self.assertEqual(xfs["phase1_role"], "PRE_FREEZE_SCREENING")
        self.assertFalse(xfs["used_for_phase2_basis"])
        self.assertFalse(xfs["eligible_as_blind_heldout"])


if __name__ == "__main__":
    unittest.main()
