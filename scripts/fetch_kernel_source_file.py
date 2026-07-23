"""Fetch and pin a single Linux source file by version and path.

The main Linux snapshots in this project are intentionally kept under
``linux-sources/`` and ignored by git.  Some source-fact audits need a small
non-fs core file, such as ``kernel/notifier.c``.  This helper downloads one
raw file from the upstream Linux tag, writes it into the matching local source
tree, and records a sidecar manifest with URL and SHA-256.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


RAW_LINUX_URL = "https://raw.githubusercontent.com/torvalds/linux"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch one version-pinned Linux source file."
    )
    parser.add_argument("--version", required=True, help="Linux version, e.g. 7.1")
    parser.add_argument("--source-path", required=True, help="Path inside kernel tree")
    parser.add_argument(
        "--source-tree",
        required=True,
        help="Local Linux source tree root, e.g. linux-sources/linux-v7.1-fs",
    )
    parser.add_argument(
        "--manifest",
        default="",
        help="Optional manifest path; defaults to SOURCE_EXTRA_MANIFEST.json",
    )
    args = parser.parse_args(argv)

    version = args.version.lstrip("v")
    source_path = args.source_path.replace("\\", "/").lstrip("/")
    url = f"{RAW_LINUX_URL}/v{version}/{source_path}"
    source_tree = Path(args.source_tree)
    target = source_tree / source_path
    manifest = (
        Path(args.manifest)
        if args.manifest
        else source_tree / "SOURCE_EXTRA_MANIFEST.json"
    )

    with urlopen(url, timeout=30) as response:
        content = response.read()

    digest = hashlib.sha256(content).hexdigest()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)

    entries = []
    if manifest.exists():
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        entries = [
            entry
            for entry in payload.get("files", [])
            if entry.get("source_path") != source_path
        ]
    entries.append(
        {
            "version": version,
            "source_path": source_path,
            "local_path": target.as_posix(),
            "url": url,
            "sha256": digest,
        }
    )
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps({"files": sorted(entries, key=lambda e: e["source_path"])}, indent=2)
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "local_path": target.as_posix(),
                "url": url,
                "sha256": digest,
                "manifest": manifest.as_posix(),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
