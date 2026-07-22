"""Fault-model validation for ext4 fast-commit replay helper candidates.

The local repository contains fs/ source slices, not a full buildable kernel.
This script therefore validates the source-level bug hypothesis with a small
control-flow model of the relevant helpers.  It is intentionally narrow: it
models only the failure sites observed in linux-v6.8 fs/ext4/extents.c and the
caller behavior in fs/ext4/fast_commit.c.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


EIO = -5


@dataclass(frozen=True)
class ScenarioResult:
    function: str
    injection_site: str
    original_return: int
    original_writes_metadata: bool
    original_error_swallowed: bool
    fixed_return: int
    fixed_writes_metadata: bool
    fixed_error_swallowed: bool
    caller_original_return: int
    caller_fixed_return: int
    caller_original_error_swallowed: bool
    caller_fixed_error_swallowed: bool
    evidence: tuple[str, ...]


def original_set_iblocks(site: str) -> tuple[int, bool]:
    """Model linux-v6.8 ext4_ext_replay_set_iblocks()."""

    if site == "initial_ext4_find_extent":
        return EIO, False
    if site in {
        "data_ext4_map_blocks",
        "first_skip_hole",
        "first_ext4_find_extent",
        "loop_ext4_find_extent",
        "loop_skip_hole",
        "second_ext4_find_extent",
    }:
        return 0, True
    return 0, True


def fixed_set_iblocks(site: str) -> tuple[int, bool]:
    if site == "none":
        return 0, True
    return EIO, False


def original_clear_bb(site: str) -> tuple[int, bool]:
    """Model linux-v6.8 ext4_ext_clear_bb()."""

    if site == "initial_ext4_find_extent":
        return EIO, False
    if site in {"loop_ext4_map_blocks", "inner_ext4_find_extent"}:
        return 0, site == "loop_ext4_map_blocks"
    return 0, True


def fixed_clear_bb(site: str) -> tuple[int, bool]:
    if site == "none":
        return 0, True
    return EIO, False


def original_replay_inode(helper_return: int) -> int:
    """linux-v6.8 ignores both helper returns and returns 0 from out."""

    return 0


def fixed_replay_inode(helper_return: int) -> int:
    return helper_return if helper_return < 0 else 0


def validate() -> list[ScenarioResult]:
    scenarios: list[ScenarioResult] = []
    set_iblocks_sites = (
        "initial_ext4_find_extent",
        "data_ext4_map_blocks",
        "first_skip_hole",
        "first_ext4_find_extent",
        "loop_ext4_find_extent",
        "loop_skip_hole",
        "second_ext4_find_extent",
    )
    for site in set_iblocks_sites:
        original_ret, original_write = original_set_iblocks(site)
        fixed_ret, fixed_write = fixed_set_iblocks(site)
        caller_original = original_replay_inode(original_ret)
        caller_fixed = fixed_replay_inode(fixed_ret)
        scenarios.append(
            ScenarioResult(
                function="ext4_ext_replay_set_iblocks",
                injection_site=site,
                original_return=original_ret,
                original_writes_metadata=original_write,
                original_error_swallowed=site != "initial_ext4_find_extent"
                and original_ret == 0,
                fixed_return=fixed_ret,
                fixed_writes_metadata=fixed_write,
                fixed_error_swallowed=fixed_ret == 0 and site != "none",
                caller_original_return=caller_original,
                caller_fixed_return=caller_fixed,
                caller_original_error_swallowed=caller_original == 0,
                caller_fixed_error_swallowed=caller_fixed == 0 and site != "none",
                evidence=(
                    "extents.c:6015-6017 breaks on ext4_map_blocks() error",
                    "extents.c:6031-6036 sends skip_hole()/find_extent errors to out",
                    "extents.c:6075-6078 writes inode->i_blocks and returns 0",
                    "fast_commit.c:1595-1596 ignores ext4_ext_replay_set_iblocks() return",
                    "fast_commit.c:1605-1610 returns 0 from out",
                ),
            )
        )

    clear_bb_sites = (
        "initial_ext4_find_extent",
        "loop_ext4_map_blocks",
        "inner_ext4_find_extent",
    )
    for site in clear_bb_sites:
        original_ret, original_write = original_clear_bb(site)
        fixed_ret, fixed_write = fixed_clear_bb(site)
        caller_original = original_replay_inode(original_ret)
        caller_fixed = fixed_replay_inode(fixed_ret)
        scenarios.append(
            ScenarioResult(
                function="ext4_ext_clear_bb",
                injection_site=site,
                original_return=original_ret,
                original_writes_metadata=original_write,
                original_error_swallowed=site != "initial_ext4_find_extent"
                and original_ret == 0,
                fixed_return=fixed_ret,
                fixed_writes_metadata=fixed_write,
                fixed_error_swallowed=fixed_ret == 0 and site != "none",
                caller_original_return=caller_original,
                caller_fixed_return=caller_fixed,
                caller_original_error_swallowed=caller_original == 0,
                caller_fixed_error_swallowed=caller_fixed == 0 and site != "none",
                evidence=(
                    "extents.c:6109-6111 breaks on ext4_map_blocks() error",
                    "extents.c:6113-6123 ignores inner ext4_find_extent() failure",
                    "extents.c:6131 returns 0",
                    "fast_commit.c:1535-1536 ignores ext4_ext_clear_bb() return",
                    "fast_commit.c:1605-1610 returns 0 from out",
                ),
            )
        )
    return scenarios


def write_json(results: list[ScenarioResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "scope": "ext4 fast-commit replay helper fault model",
                "results": [asdict(item) for item in results],
                "summary": summary(results),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def write_markdown(results: list[ScenarioResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# ext4 Fast-Commit Replay Helper Fault Validation",
        "",
        "This is a source-level control-flow validation, not a full kernel",
        "fault-injection run. The local workspace contains an fs/ source slice,",
        "not a buildable kernel tree.",
        "",
        "## Summary",
        "",
        "```text",
    ]
    for key, value in summary(results).items():
        lines.append(f"{key:40s} {value}")
    lines.extend(
        [
            "```",
            "",
            "A scenario is counted as swallowed when an injected helper failure",
            "returns 0 from the helper or from the fast-commit replay caller.",
            "",
            "## Results",
            "",
            "| function | injection site | original helper | original writes metadata | original caller | fixed caller |",
            "|---|---|---:|---|---:|---:|",
        ]
    )
    for item in results:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{item.function}`",
                    f"`{item.injection_site}`",
                    str(item.original_return),
                    "yes" if item.original_writes_metadata else "no",
                    str(item.caller_original_return),
                    str(item.caller_fixed_return),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `ext4_ext_replay_set_iblocks()` has six modeled post-initial",
            "  failure sites where the original helper returns 0 and the caller",
            "  also returns 0. These paths still execute the final `i_blocks`",
            "  update in the model.",
            "- `ext4_ext_clear_bb()` has two modeled post-initial failure sites",
            "  where the original helper returns 0 and the caller also returns 0.",
            "- A minimal fixed semantics that preserves the first negative error",
            "  and makes `ext4_fc_replay_inode()` check helper returns changes all",
            "  injected-failure caller outcomes from 0 to `-EIO`.",
            "",
            "Initial conclusion: the hypothesis is reproducible at the source",
            "control-flow level. A full confirmed-bug claim still needs a kernel",
            "fault-injection run or an accepted patch/review showing these helper",
            "failures must abort fast-commit replay.",
        ]
    )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def summary(results: list[ScenarioResult]) -> dict[str, int]:
    return {
        "modeled_injection_scenarios": len(results),
        "original_helper_swallowed_errors": sum(
            item.original_error_swallowed for item in results
        ),
        "original_caller_swallowed_errors": sum(
            item.caller_original_error_swallowed for item in results
        ),
        "original_metadata_write_after_failure": sum(
            item.original_writes_metadata and item.original_return == 0
            for item in results
        ),
        "fixed_caller_swallowed_errors": sum(
            item.caller_fixed_error_swallowed for item in results
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-json",
        default="outputs/mocc-discovery-v2/ext4-fc-helper-fault-validation.json",
    )
    parser.add_argument(
        "--out-md",
        default="outputs/mocc-discovery-v2/ext4-fc-helper-fault-validation.md",
    )
    args = parser.parse_args()
    results = validate()
    write_json(results, Path(args.out_json))
    write_markdown(results, Path(args.out_md))
    for key, value in summary(results).items():
        print(f"{key}={value}")
    print(f"out_json={args.out_json}")
    print(f"out_md={args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
