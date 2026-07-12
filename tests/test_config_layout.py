import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILESYSTEMS = ("ext4", "btrfs", "xfs", "f2fs")


def test_each_filesystem_has_one_canonical_config_set():
    configs = ROOT / "configs"
    for filesystem in FILESYSTEMS:
        resource_map = configs / f"{filesystem}_resource_map.json"
        protocols = configs / f"{filesystem}_resource_protocols"
        review = configs / f"{filesystem}_review_false_positives.json"
        wrapper = configs / (
            "wrapper_summaries.json"
            if filesystem == "ext4"
            else f"{filesystem}_wrapper_summaries.json"
        )
        assert resource_map.is_file()
        assert protocols.is_dir() and list(protocols.glob("*.json"))
        assert review.is_file()
        assert wrapper.is_file()

        data = json.loads(resource_map.read_text(encoding="utf-8"))
        assert data["review_false_positive_contracts_file"] == review.name


def test_review_config_names_are_not_tied_to_experiment_versions():
    versioned = list((ROOT / "configs").glob("*_v*_false_positives.json"))
    assert versioned == []
