from __future__ import annotations

import argparse
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Sequence

from .orphan_phase16 import run_manifest as run_phase16_manifest
from .orphan_phase17 import run_manifest as run_phase17_manifest
from .orphan_phase18 import run_manifest as run_phase18_manifest


LOCKED_ARTIFACTS = {
    "configs/evaluation/oids-phase15-jfs-heldout-preregistration-v0.1.json":
        "938f31a9381c8998d3f0aabdc314c38ca775626df559580aff61b1fce4076595",
    "outputs/fmpca-oids-phase15-v0.1/summary.json":
        "f59395580b5c1dc520458b7e8d67455bf1d448e15f6fd534b79c0923888f5334",
    "configs/evaluation/oids-final-release-v0.2.json":
        "6470495535c18a29c46d0c3a452863f7ddbbba7857fc75e4106258bb2b1785a3",
    "outputs/fmpca-oids-final-v0.2/summary.json":
        "40e2010457c1666e6d2cef241d559c3a54faef2460912baccbc3b41e33696e36",
    "outputs/fmpca-oids-final-v0.2/report.md":
        "3f4a55dc386aa4580e2baf6f1c6aff43a1442a9c288fb78278ab77ee402486ce",
}

RECOMPUTABLE_RELEASES = (
    (
        "phase16",
        "configs/evaluation/oids-phase16-jfs-heldout-v0.1.json",
        "outputs/fmpca-oids-phase16-v0.1/summary.json",
        run_phase16_manifest,
    ),
    (
        "phase17",
        "configs/evaluation/oids-phase17-jfs-result-freeze-v0.1.json",
        "outputs/fmpca-oids-phase17-v0.1/summary.json",
        run_phase17_manifest,
    ),
    (
        "phase18",
        "configs/evaluation/oids-final-release-v0.2.json",
        "outputs/fmpca-oids-final-v0.2/summary.json",
        run_phase18_manifest,
    ),
)


def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load(path: str | Path) -> Dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


@contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def verify_release(repo_root: str | Path = ".") -> Dict[str, Any]:
    root = Path(repo_root).resolve()
    if not (root / "configs/evaluation/oids-final-release-v0.2.json").is_file():
        raise ValueError(f"OIDS final release not found under repository root: {root}")

    with _working_directory(root):
        locked_hashes: Dict[str, bool] = {}
        for path, expected in LOCKED_ARTIFACTS.items():
            actual = _sha256(path)
            if actual != expected:
                raise ValueError(f"maintenance hash mismatch for {path}: {actual} != {expected}")
            locked_hashes[path] = True

        phase15 = _load("outputs/fmpca-oids-phase15-v0.1/summary.json")
        historical_freeze_verified = (
            phase15["phase15_preregistration_closed"]
            and phase15["source_unrevealed_at_freeze"]
            and phase15["selected_candidate"] == "JFS"
            and not phase15["candidate_replaced"]
        )

        recomputed: Dict[str, bool] = {}
        for name, manifest, stored_path, runner in RECOMPUTABLE_RELEASES:
            stored = _load(stored_path)
            calculated = runner(manifest)
            if calculated != stored:
                raise ValueError(f"{name} recomputation differs from frozen summary")
            recomputed[name] = True

        final = _load("outputs/fmpca-oids-final-v0.2/summary.json")
        endpoint_preserved = (
            final["project_complete"]
            and final["project_status"] == "COMPLETE"
            and final["hard_endpoint"] == "PHASE_18"
            and not final["further_phase_expansion"]
            and final["maintenance_mode"]
            and not final["common_v0_2_validated"]
        )
        closed = (
            all(locked_hashes.values())
            and historical_freeze_verified
            and all(recomputed.values())
            and endpoint_preserved
        )
        return {
            "schema_version": 1,
            "verification_kind": "OIDS_RELEASE_MAINTENANCE_READ_ONLY",
            "repository_root": str(root),
            "locked_artifacts": locked_hashes,
            "historical_phase15_freeze_verified": historical_freeze_verified,
            "recomputed_summaries": recomputed,
            "endpoint_preserved": endpoint_preserved,
            "common_v0_2_validated": final["common_v0_2_validated"],
            "maintenance_verification_closed": closed,
        }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.orphan_maintenance")
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    result = verify_release(args.root)
    print(
        f"maintenance_closed={result['maintenance_verification_closed']} "
        f"phase15_freeze={result['historical_phase15_freeze_verified']} "
        f"recomputed={sum(result['recomputed_summaries'].values())}/3 "
        f"endpoint={result['endpoint_preserved']}"
    )
    return 0 if result["maintenance_verification_closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
