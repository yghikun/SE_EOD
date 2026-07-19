import json
from pathlib import Path

import pytest

from src.cfg import build_cfg
from src.function_extractor import extract_functions
from src.parser import parse_c_file


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "switch_cfg_linux_ext4_v6_14.json"
LINUX_EXT4 = ROOT / "linux-sources" / "linux-v6.14-fs" / "fs" / "ext4"


def test_linux_ext4_switch_cfg_golden():
    if not LINUX_EXT4.is_dir():
        pytest.skip("linux v6.14 ext4 source tree is not available")

    manifest = json.loads(FIXTURE.read_text(encoding="utf-8"))
    by_file = {}
    for expected in manifest["functions"]:
        by_file.setdefault(expected["file"], []).append(expected)

    checked = 0
    for filename, expectations in by_file.items():
        functions = {
            function.name: function
            for function in extract_functions(parse_c_file(LINUX_EXT4 / filename))
        }
        for expected in expectations:
            function = functions[expected["function"]]
            cfg = build_cfg(function)
            assert sum(
                block.kind == "switch_condition" for block in cfg.blocks.values()
            ) == expected["switches"]
            assert sum(
                block.kind == "switch_exit" for block in cfg.blocks.values()
            ) == expected["switches"]
            assert sum(edge.kind == "switch_case" for edge in cfg.edges) == expected[
                "cases"
            ]
            assert sum(edge.kind == "switch_default" for edge in cfg.edges) == expected[
                "defaults"
            ]
            assert "switch_statement" not in cfg.unsupported_nodes
            assert "case_statement" not in cfg.unsupported_nodes
            reachable = {cfg.entry}
            pending = [cfg.entry]
            while pending:
                source = pending.pop()
                for edge in cfg.successors(source):
                    if edge.target not in reachable:
                        reachable.add(edge.target)
                        pending.append(edge.target)
            assert cfg.exit in reachable
            assert all(
                block.id in reachable
                for block in cfg.blocks.values()
                if block.kind in {"switch_case", "switch_default", "switch_exit"}
            )
            checked += 1

    assert checked == 10
