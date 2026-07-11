"""Sparse-download Linux filesystem sources needed by se_eod.

Default result:
  linux-v6.8-fs/
    fs/ext4/*.c

The directory is still a Git checkout, so src.main can record the real Linux
commit and tag via git rev-parse / git describe.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


DEFAULT_REPO = "https://github.com/torvalds/linux.git"
DEFAULT_REF = "v6.8"
DEFAULT_TARGET = "linux-v6.8-fs"
DEFAULT_SPARSE_PATH = "fs/ext4"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sparse-checkout Linux filesystem sources for se_eod."
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
        raise SystemExit(f"target exists but is not a git checkout: {target}")

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
    print(f"scan_command=python -m src.main --linux {target} --out outputs/ext4/error_paths.csv")


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    sparse_paths = args.sparse_path or [DEFAULT_SPARSE_PATH]
    ensure_sparse_checkout(args.repo, args.ref, Path(args.target), sparse_paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
