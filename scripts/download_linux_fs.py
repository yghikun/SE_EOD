"""Sparse-download pinned Linux filesystem sources needed by MetaWindow.

Default result:
  linux-sources/linux-v6.8-fs/
    fs/ext4/*.c

The directory remains a Git checkout so scans can record the exact commit and tag.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


DEFAULT_REPO = "https://github.com/torvalds/linux.git"
DEFAULT_REF = "v6.8"
DEFAULT_TARGET = "linux-sources/linux-v6.8-fs"
DEFAULT_SPARSE_PATH = "fs/ext4"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sparse-checkout Linux filesystem sources for MetaWindow."
    )
    parser.add_argument("--repo", default=DEFAULT_REPO, help="Linux git repository URL.")
    parser.add_argument("--ref", default=DEFAULT_REF, help="Git tag/branch/commit.")
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help="Checkout directory, relative to the current directory by default.",
    )
    parser.add_argument(
        "--sparse-path",
        action="append",
        default=None,
        help=(
            "Path to include in sparse checkout. Can be repeated. "
            "Defaults to fs/ext4. Use --sparse-path fs for all Linux filesystems."
        ),
    )
    return parser


def ensure_sparse_checkout(
    repo: str, ref: str, target: Path, sparse_paths: list[str]
) -> None:
    target = target.resolve()

    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                ref,
                "--filter=blob:none",
                "--sparse",
                "--no-checkout",
                repo,
                str(target),
            ]
        )

    if not (target / ".git").exists():
        manifest_path = target / "SOURCE_MANIFEST.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
        if isinstance(manifest, dict) and manifest.get("git_tag") == ref:
            print(f"source_manifest={manifest_path}")
            print(f"downloaded_ref={manifest.get('git_tag', ref)}")
            print(f"linux_git_commit={manifest.get('git_commit', 'unknown')}")
            print(f"linux_git_tag={manifest.get('git_tag', ref)}")
            print(f"linux_path={target}")
            return
        raise SystemExit(f"target exists but is not a git checkout or matching source snapshot: {target}")

    run(["git", "remote", "set-url", "origin", repo], cwd=target)
    run(["git", "fetch", "--depth", "1", "origin", ref], cwd=target)
    run(["git", "sparse-checkout", "init", "--cone"], cwd=target)
    run(["git", "sparse-checkout", "set", *sparse_paths], cwd=target)
    run(["git", "checkout", "FETCH_HEAD"], cwd=target)

    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=target, text=True
    ).strip()
    tag = subprocess.check_output(
        ["git", "describe", "--tags", "--always"], cwd=target, text=True
    ).strip()
    print(f"downloaded_ref={ref}")
    print(f"linux_git_commit={commit}")
    print(f"linux_git_tag={tag}")
    print(f"linux_path={target}")
    print(
        "scan_command=python -m src.metadata_batch_scan "
        f"--source-root {target / 'fs'} --source-version {ref.removeprefix('v')}"
    )


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    sparse_paths = args.sparse_path or [DEFAULT_SPARSE_PATH]
    ensure_sparse_checkout(args.repo, args.ref, Path(args.target), sparse_paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
