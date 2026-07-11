"""Locate C files under a Linux checkout subdirectory."""

from __future__ import annotations

from pathlib import Path


def iter_c_files(linux_path: str | Path, fs_subdir: str | Path = "fs/ext4") -> list[Path]:
    root = Path(linux_path)
    source_dir = root / fs_subdir
    if not source_dir.is_dir():
        return []
    return sorted(source_dir.glob("*.c"))


def iter_ext4_c_files(linux_path: str | Path) -> list[Path]:
    return iter_c_files(linux_path, "fs/ext4")
