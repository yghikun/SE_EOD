import copy
import unittest
from pathlib import Path

from src.fmpca.scope import (
    ScopeTaxonomyError,
    assess_scope,
    current_scope_index,
    load_taxonomy,
)


ROOT = Path(__file__).resolve().parents[1]
TAXONOMY = ROOT / "configs/catalog/protocol-scope-taxonomy-v0.1.json"


def applicable(filesystem, role, family):
    return {
        "filesystem": filesystem,
        "applicability": "APPLICABLE",
        "validation_role": role,
        "operation_family": family,
        "correspondence": {
            "object": True,
            "relation": True,
            "lifecycle": True,
            "authority": True,
            "deadline": True,
        },
        "source_witness_closed": True,
        "replay_closed": True,
        "proof_closure_closed": True,
    }


def declaration(filesystems, scope="FS_SPECIFIC", boundary="STANDARD"):
    return {
        "protocol_id": "fmpca.test_protocol",
        "semantic_scope": scope,
        "freeze_boundary": boundary,
        "canonical_dsl_defined": True,
        "bindings_defined": True,
        "source_witness_defined": True,
        "result_partition_closed": True,
        "hashes_locked": {"protocol": True, "binding": True, "test": True},
        "filesystems": filesystems,
    }


class ProtocolScopeTaxonomyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.taxonomy = load_taxonomy(str(TAXONOMY))

    def test_current_catalog_is_conservative_and_has_no_common_claim(self):
        index = current_scope_index(self.taxonomy)
        self.assertEqual(
            index["fmpca.chunk_metadata_reservation_completion"]["semantic_scope"],
            "FS_SPECIFIC",
        )
        self.assertEqual(
            index["fmpca.chunk_metadata_reservation_completion"]["freeze_boundary"],
            "NARROW_FREEZE",
        )
        self.assertEqual(
            index["fmpca.device_topology_capacity_composition"]["semantic_scope"],
            "FS_SPECIFIC",
        )
        self.assertTrue(
            all(item["semantic_scope"] != "COMMON" for item in index.values())
        )
        self.assertEqual(
            index["fmpca.orphan_inode_deletion_settlement"]["semantic_scope"],
            "FS_SPECIFIC",
        )

    def test_one_development_filesystem_can_be_candidate_but_not_common_freeze(self):
        result = assess_scope(
            self.taxonomy,
            declaration([applicable("btrfs", "DEVELOPMENT", "btrfs-orphan-item")]),
        )
        self.assertTrue(result.common_candidate_ready)
        self.assertFalse(result.common_freeze_ready)
        self.assertIn(
            "minimum_two_applicable_filesystems", result.failed_freeze_gates
        )
        self.assertFalse(result.cross_filesystem_claim_allowed)

    def test_two_independent_filesystems_close_common_freeze(self):
        result = assess_scope(
            self.taxonomy,
            declaration(
                [
                    applicable("btrfs", "DEVELOPMENT", "btrfs-orphan-item"),
                    applicable("ext4", "VALIDATION", "ext4-orphan-file"),
                ],
                scope="COMMON",
                boundary="NARROW_FREEZE",
            ),
        )
        self.assertTrue(result.declaration_valid)
        self.assertTrue(result.common_freeze_ready)
        self.assertTrue(result.cross_filesystem_claim_allowed)
        self.assertEqual(result.failed_freeze_gates, [])
        self.assertEqual(result.freeze_boundary, "NARROW_FREEZE")

    def test_missing_semantic_correspondence_blocks_common_declaration(self):
        ext4 = applicable("ext4", "VALIDATION", "ext4-orphan-file")
        ext4["correspondence"]["deadline"] = False
        result = assess_scope(
            self.taxonomy,
            declaration(
                [
                    applicable("btrfs", "DEVELOPMENT", "btrfs-orphan-item"),
                    ext4,
                ],
                scope="COMMON",
            ),
        )
        self.assertFalse(result.declaration_valid)
        self.assertFalse(result.common_freeze_ready)
        self.assertIn(
            "all_correspondence_dimensions_closed", result.failed_freeze_gates
        )
        self.assertEqual(result.failed_scope_gates, ["common_freeze_ready"])

    def test_fs_specific_requires_an_applicable_filesystem(self):
        result = assess_scope(
            self.taxonomy,
            declaration([{"filesystem": "btrfs", "applicability": "UNRESOLVED"}]),
        )
        self.assertFalse(result.declaration_valid)
        self.assertEqual(
            result.failed_scope_gates, ["at_least_one_applicable_filesystem"]
        )

    def test_fs_family_requires_two_members_of_the_named_family(self):
        btrfs = applicable("btrfs", "DEVELOPMENT", "btrfs-orphan-item")
        btrfs["filesystem_family_id"] = "linux-native-journaled"
        ext4 = applicable("ext4", "VALIDATION", "ext4-orphan-file")
        ext4["filesystem_family_id"] = "linux-native-journaled"
        value = declaration([btrfs, ext4], scope="FS_FAMILY")
        value["filesystem_family_id"] = "linux-native-journaled"
        result = assess_scope(self.taxonomy, value)
        self.assertTrue(result.declaration_valid)
        self.assertFalse(result.cross_filesystem_claim_allowed)

        ext4["filesystem_family_id"] = "other-family"
        mismatch = assess_scope(self.taxonomy, value)
        self.assertFalse(mismatch.declaration_valid)
        self.assertIn("all_members_match_named_family", mismatch.failed_scope_gates)

    def test_non_applicable_is_evidence_bearing_and_unresolved_never_counts(self):
        filesystems = [
            applicable("btrfs", "DEVELOPMENT", "btrfs-orphan-item"),
            {
                "filesystem": "xfs",
                "applicability": "NON_APPLICABLE",
                "reason_code": "LIFECYCLE_INCOMPATIBLE",
                "evidence_note": "The source lifecycle lacks the canonical settlement edge.",
            },
            {"filesystem": "f2fs", "applicability": "UNRESOLVED"},
        ]
        result = assess_scope(self.taxonomy, declaration(filesystems))
        self.assertEqual(result.non_applicable_filesystems, ["xfs"])
        self.assertEqual(result.unresolved_filesystems, ["f2fs"])
        self.assertFalse(result.common_freeze_ready)

        invalid = copy.deepcopy(filesystems)
        invalid[1].pop("evidence_note")
        with self.assertRaisesRegex(ScopeTaxonomyError, "needs an evidence note"):
            assess_scope(self.taxonomy, declaration(invalid))

    def test_third_filesystem_validates_only_without_post_freeze_changes(self):
        filesystems = [
            applicable("btrfs", "DEVELOPMENT", "btrfs-orphan-item"),
            applicable("ext4", "VALIDATION", "ext4-orphan-file"),
            applicable("xfs", "HELD_OUT", "xfs-unlinked-list"),
        ]
        filesystems[2]["post_freeze"] = True
        result = assess_scope(
            self.taxonomy, declaration(filesystems, scope="COMMON")
        )
        self.assertTrue(result.common_heldout_validated)
        self.assertEqual(result.failed_heldout_gates, [])

        filesystems[2]["binding_modified_after_freeze"] = True
        changed = assess_scope(
            self.taxonomy, declaration(filesystems, scope="COMMON")
        )
        self.assertFalse(changed.common_heldout_validated)
        self.assertIn(
            "no_post_freeze_semantic_modifications", changed.failed_heldout_gates
        )


if __name__ == "__main__":
    unittest.main()
