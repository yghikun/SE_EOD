import json

from src.main import linux_version


def test_linux_version_reads_source_manifest_without_git(tmp_path):
    (tmp_path / "SOURCE_MANIFEST.json").write_text(
        json.dumps({"git_commit": "abc123", "git_tag": "v6.8"}),
        encoding="utf-8",
    )

    assert linux_version(tmp_path) == ("abc123", "v6.8")
