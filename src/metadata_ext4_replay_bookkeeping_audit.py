"""Source-fact audit for ext4 fast-commit replay bookkeeping helpers.

This module intentionally does not decide whether a hit is a confirmed bug.
It records source-visible facts needed after a broad batch scan flags
``ext4_ext_replay_set_iblocks()`` or ``ext4_ext_clear_bb()``:

* the helper has a public ``int`` return contract;
* fast-commit replay callers ignore that return;
* an ``ext4_map_blocks()`` negative return can break out to a final
  ``return 0``;
* the surrounding function updates bookkeeping state or can perform partial
  bitmap/region mutations before a later swallowed failure.

The conclusion is therefore conservative: these hits need an independent
ext4 fast-commit replay semantic contract, patch review, or fault-injection
evidence before being promoted into an active MOCC protocol instance or bug
claim.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


EXT4_REPLAY_BOOKKEEPING_AUDIT_SCHEMA_VERSION = 1
DEFAULT_HELPERS = (
    "ext4_ext_replay_set_iblocks",
    "ext4_ext_clear_bb",
)


@dataclass(frozen=True)
class SourceFact:
    kind: str
    file: str
    line: int
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "file": self.file,
            "line": self.line,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class HelperAudit:
    function: str
    definition_file: str
    definition_line: int
    declaration_return_type: str
    definition_return_type: str
    leading_comment: str
    facts: tuple[SourceFact, ...]
    conclusion: str
    recommended_action: str
    bug_claim_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        fact_kinds = {fact.kind for fact in self.facts}
        return {
            "function": self.function,
            "definition_file": self.definition_file,
            "definition_line": self.definition_line,
            "declaration_return_type": self.declaration_return_type,
            "definition_return_type": self.definition_return_type,
            "leading_comment": self.leading_comment,
            "fact_summary": {
                "public_int_return": self.declaration_return_type == "int",
                "definition_int_return": self.definition_return_type == "int",
                "ignored_fast_commit_call": "ignored_fast_commit_call" in fact_kinds,
                "swallowed_ext4_map_blocks_error": (
                    "swallowed_ext4_map_blocks_error" in fact_kinds
                ),
                "metadata_bookkeeping_after_failure": (
                    "metadata_bookkeeping_after_failure" in fact_kinds
                ),
                "partial_metadata_mutation_before_failure": (
                    "partial_metadata_mutation_before_failure" in fact_kinds
                ),
            },
            "facts": [fact.to_dict() for fact in self.facts],
            "conclusion": self.conclusion,
            "recommended_action": self.recommended_action,
            "bug_claim_allowed": self.bug_claim_allowed,
        }


@dataclass(frozen=True)
class Ext4ReplayBookkeepingAudit:
    source_root: str
    source_version: str
    helpers: tuple[HelperAudit, ...]

    def to_dict(self) -> dict[str, Any]:
        helper_payload = [helper.to_dict() for helper in self.helpers]
        return {
            "schema_version": EXT4_REPLAY_BOOKKEEPING_AUDIT_SCHEMA_VERSION,
            "scope": "ext4 fast-commit replay bookkeeping source-fact audit",
            "result_semantics": "source_facts_not_bug_claims",
            "bug_claims_allowed": False,
            "source_root": self.source_root,
            "source_version": self.source_version,
            "summary": _summary(helper_payload),
            "helpers": helper_payload,
        }


def audit_ext4_replay_bookkeeping(
    source_root: str | Path,
    *,
    source_version: str = "",
    helpers: Iterable[str] = DEFAULT_HELPERS,
) -> Ext4ReplayBookkeepingAudit:
    """Audit source-visible facts for ext4 replay bookkeeping helpers."""

    root = Path(source_root).resolve()
    ext4_dir = _resolve_ext4_dir(root)
    extents = ext4_dir / "extents.c"
    fast_commit = ext4_dir / "fast_commit.c"
    header = ext4_dir / "ext4.h"
    _require_files(extents, fast_commit, header)

    extents_lines = _read_lines(extents)
    fast_commit_lines = _read_lines(fast_commit)
    header_lines = _read_lines(header)
    audits = tuple(
        _audit_helper(
            function,
            extents,
            extents_lines,
            fast_commit,
            fast_commit_lines,
            header,
            header_lines,
        )
        for function in helpers
    )
    return Ext4ReplayBookkeepingAudit(root.as_posix(), source_version, audits)


def write_audit_json(report: Ext4ReplayBookkeepingAudit, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_audit_markdown(report: Ext4ReplayBookkeepingAudit, path: str | Path) -> None:
    payload = report.to_dict()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# ext4 Fast-Commit Replay Bookkeeping Audit",
        "",
        "This audit records source-visible facts for batch-scan hits. It is not",
        "a confirmed-bug report and not an active protocol-freeze change.",
        "",
        f"- source root: `{report.source_root}`",
        f"- source version: `{report.source_version}`",
        f"- result semantics: `{payload['result_semantics']}`",
        f"- bug claims allowed: `{payload['bug_claims_allowed']}`",
        "",
        "## Summary",
        "",
    ]
    for key, value in payload["summary"].items():
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    for helper in payload["helpers"]:
        lines.extend(
            [
                f"## {helper['function']}",
                "",
                f"- definition: `{helper['definition_file']}:{helper['definition_line']}`",
                f"- declaration return type: `{helper['declaration_return_type']}`",
                f"- definition return type: `{helper['definition_return_type']}`",
                f"- leading comment: {helper['leading_comment'] or '(none found)'}",
                f"- conclusion: `{helper['conclusion']}`",
                f"- recommended action: {helper['recommended_action']}",
                f"- bug claim allowed: `{helper['bug_claim_allowed']}`",
                "",
                "Facts:",
                "",
            ]
        )
        for fact in helper["facts"]:
            lines.append(
                f"- `{fact['kind']}` at `{fact['file']}:{fact['line']}`: "
                f"{fact['detail']}"
            )
        lines.append("")
    lines.extend(
        [
            "## Interpretation",
            "",
            "The two helpers expose a suspicious failure-to-success shape, but the",
            "missing piece is semantic authority: ext4 fast-commit replay may treat",
            "some bookkeeping repairs as best effort, or it may require aborting",
            "replay when these helpers cannot complete. MOCC-SE should not promote",
            "these hits into an active protocol instance until that obligation is",
            "supported by independent documentation, maintainer review, an accepted",
            "fix, or a reproducible fault-injection experiment.",
        ]
    )
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit ext4 fast-commit replay bookkeeping source facts."
    )
    parser.add_argument(
        "--source-root",
        default="linux-sources/linux-v7.1-fs/fs",
        help="Linux fs/ root or fs/ext4 directory",
    )
    parser.add_argument("--source-version", default="7.1")
    parser.add_argument(
        "--out-json",
        default="outputs/mocc-batch-scan-v1/ext4-replay-bookkeeping-audit.json",
    )
    parser.add_argument(
        "--out-md",
        default="outputs/mocc-batch-scan-v1/ext4-replay-bookkeeping-audit.md",
    )
    args = parser.parse_args(argv)
    report = audit_ext4_replay_bookkeeping(
        args.source_root,
        source_version=args.source_version,
    )
    write_audit_json(report, args.out_json)
    write_audit_markdown(report, args.out_md)
    print(json.dumps(report.to_dict()["summary"], indent=2, sort_keys=True))
    return 0


def _audit_helper(
    function: str,
    extents: Path,
    extents_lines: Sequence[str],
    fast_commit: Path,
    fast_commit_lines: Sequence[str],
    header: Path,
    header_lines: Sequence[str],
) -> HelperAudit:
    declaration_return = _declaration_return_type(header_lines, function)
    declaration_line = _declaration_line(header_lines, function)
    function_slice = _extract_function(extents_lines, function)
    definition_return = _definition_return_type(function_slice.signature, function)
    facts: list[SourceFact] = []
    facts.extend(
        _definition_facts(
            header,
            extents,
            function_slice,
            declaration_return,
            declaration_line,
            definition_return,
        )
    )
    facts.extend(_callsite_facts(fast_commit, fast_commit_lines, function))
    facts.extend(_failure_to_success_facts(extents, function_slice))
    facts.extend(_bookkeeping_facts(extents, function_slice, function))

    return HelperAudit(
        function=function,
        definition_file=_relative_file(extents),
        definition_line=function_slice.start_line,
        declaration_return_type=declaration_return,
        definition_return_type=definition_return,
        leading_comment=_leading_comment(extents_lines, function_slice.start_index),
        facts=tuple(facts),
        conclusion="needs_external_semantics",
        recommended_action=(
            "Keep this as an audited source-review item. Promote it only after "
            "an independent replay bookkeeping obligation is frozen."
        ),
    )


@dataclass(frozen=True)
class FunctionSlice:
    start_index: int
    end_index: int
    start_line: int
    signature: str
    body: tuple[tuple[int, str], ...]


def _resolve_ext4_dir(root: Path) -> Path:
    if (root / "extents.c").is_file() and (root / "fast_commit.c").is_file():
        return root
    if (root / "ext4" / "extents.c").is_file():
        return root / "ext4"
    raise FileNotFoundError(f"cannot find ext4 sources under {root}")


def _require_files(*paths: Path) -> None:
    missing = [path.as_posix() for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing ext4 source files: " + ", ".join(missing))


def _read_lines(path: Path) -> tuple[str, ...]:
    return tuple(path.read_text(encoding="utf-8", errors="replace").splitlines())


def _extract_function(lines: Sequence[str], function: str) -> FunctionSlice:
    pattern = re.compile(rf"\b{re.escape(function)}\s*\(")
    for index, line in enumerate(lines):
        if not pattern.search(line):
            continue
        if line.lstrip().startswith("extern "):
            continue
        signature_start = _signature_start(lines, index)
        signature = "\n".join(lines[signature_start : index + 1]).strip()
        open_index = _find_next_line(lines, index, "{")
        if open_index is None:
            continue
        close_index = _matching_brace_line(lines, open_index)
        return FunctionSlice(
            start_index=signature_start,
            end_index=close_index,
            start_line=signature_start + 1,
            signature=signature,
            body=tuple(
                (line_no + 1, lines[line_no])
                for line_no in range(signature_start, close_index + 1)
            ),
        )
    raise ValueError(f"function definition not found: {function}")


def _signature_start(lines: Sequence[str], function_line_index: int) -> int:
    index = function_line_index
    while index > 0:
        previous = lines[index - 1].strip()
        if not previous:
            break
        if previous.startswith("/*") or previous.startswith("*"):
            break
        if previous.endswith(";") or previous.endswith("}"):
            break
        index -= 1
    return index


def _find_next_line(lines: Sequence[str], start: int, token: str) -> int | None:
    for index in range(start, len(lines)):
        if token in lines[index]:
            return index
    return None


def _matching_brace_line(lines: Sequence[str], open_index: int) -> int:
    depth = 0
    for index in range(open_index, len(lines)):
        depth += lines[index].count("{")
        depth -= lines[index].count("}")
        if depth == 0 and index > open_index:
            return index
    raise ValueError("unterminated function body")


def _declaration_return_type(lines: Sequence[str], function: str) -> str:
    joined = "\n".join(lines)
    match = re.search(
        rf"extern\s+([A-Za-z_][\w\s\*]*?)\s+{re.escape(function)}\s*\(",
        joined,
    )
    if not match:
        return "unknown"
    return " ".join(match.group(1).split())


def _definition_return_type(signature: str, function: str) -> str:
    before_name = signature.split(function, 1)[0]
    return " ".join(before_name.split()) or "unknown"


def _definition_facts(
    header: Path,
    source: Path,
    function_slice: FunctionSlice,
    declaration_return: str,
    declaration_line: int,
    definition_return: str,
) -> tuple[SourceFact, ...]:
    facts = [
        SourceFact(
            "definition_return_contract",
            _relative_file(source),
            function_slice.start_line,
            f"definition returns {definition_return}",
        )
    ]
    if declaration_return != "unknown":
        facts.append(
            SourceFact(
                "public_declaration_return_contract",
                _relative_file(header),
                declaration_line,
                f"extern declaration returns {declaration_return}",
            )
        )
    return tuple(facts)


def _callsite_facts(
    source: Path,
    lines: Sequence[str],
    function: str,
) -> tuple[SourceFact, ...]:
    facts: list[SourceFact] = []
    pattern = re.compile(rf"\b{re.escape(function)}\s*\(")
    for index, line in enumerate(lines):
        if not pattern.search(line):
            continue
        stripped = line.strip()
        if stripped.startswith("extern "):
            continue
        kind = "observed_callsite"
        if re.match(rf"^{re.escape(function)}\s*\(.*\);\s*$", stripped):
            kind = "ignored_fast_commit_call"
        elif stripped.startswith("if ") or stripped.startswith("return "):
            kind = "checked_fast_commit_call"
        elif "=" in stripped.split(function, 1)[0]:
            kind = "assigned_fast_commit_call"
        facts.append(SourceFact(kind, _relative_file(source), index + 1, stripped))
    return tuple(facts)


def _failure_to_success_facts(
    source: Path,
    function_slice: FunctionSlice,
) -> tuple[SourceFact, ...]:
    body = function_slice.body
    final_return_zero = any(line.strip() == "return 0;" for _, line in body[-8:])
    facts: list[SourceFact] = []
    for offset, (line_no, line) in enumerate(body):
        if "ret = ext4_map_blocks" not in line:
            continue
        guard = _lookahead_for_ret_negative_control(body, offset)
        if guard and final_return_zero:
            facts.append(
                SourceFact(
                    "swallowed_ext4_map_blocks_error",
                    _relative_file(source),
                    line_no,
                    f"{line.strip()} then {guard.rstrip(';')}; function has final return 0",
                )
            )
    return tuple(facts)


def _lookahead_for_ret_negative_control(
    body: Sequence[tuple[int, str]],
    offset: int,
) -> str:
    for _, line in body[offset + 1 : offset + 6]:
        stripped = line.strip()
        if not stripped:
            continue
        if "ret < 0" in stripped:
            continue
        if stripped in {"break;", "goto out;", "goto cleanup;", "return ret;"}:
            return stripped
    return ""


def _bookkeeping_facts(
    source: Path,
    function_slice: FunctionSlice,
    function: str,
) -> tuple[SourceFact, ...]:
    facts: list[SourceFact] = []
    if function == "ext4_ext_replay_set_iblocks":
        for _, (line_no, line) in enumerate(function_slice.body):
            stripped = line.strip()
            if stripped.startswith("inode->i_blocks ="):
                facts.append(
                    SourceFact(
                        "metadata_bookkeeping_after_failure",
                        _relative_file(source),
                        line_no,
                        stripped,
                    )
                )
            if stripped.startswith("ext4_mark_inode_dirty(NULL, inode)"):
                facts.append(
                    SourceFact(
                        "metadata_bookkeeping_after_failure",
                        _relative_file(source),
                        line_no,
                        stripped,
                    )
                )
    if function == "ext4_ext_clear_bb":
        for offset, (line_no, line) in enumerate(function_slice.body):
            stripped = line.strip()
            if stripped.startswith(("ext4_mb_mark_bb(", "ext4_fc_record_regions(")):
                facts.append(
                    SourceFact(
                        "partial_metadata_mutation_before_failure",
                        _relative_file(source),
                        line_no,
                        _statement_from(function_slice.body, offset),
                    )
                )
    return tuple(facts)


def _leading_comment(lines: Sequence[str], start_index: int) -> str:
    index = start_index - 1
    while index >= 0 and not lines[index].strip():
        index -= 1
    if index < 0:
        return ""
    if "*/" not in lines[index]:
        return ""
    comment_lines: list[str] = []
    while index >= 0:
        comment_lines.append(lines[index].strip())
        if "/*" in lines[index]:
            break
        index -= 1
    comment_lines.reverse()
    return _clean_comment(" ".join(comment_lines))


def _clean_comment(comment: str) -> str:
    comment = comment.replace("/*", "").replace("*/", "")
    comment = re.sub(r"\s*\*\s?", " ", comment)
    return " ".join(comment.split())


def _declaration_line(lines: Sequence[str], function: str) -> int:
    pattern = re.compile(rf"\b{re.escape(function)}\s*\(")
    for index, line in enumerate(lines):
        if "extern " in line and pattern.search(line):
            return index + 1
    return 0


def _statement_from(body: Sequence[tuple[int, str]], offset: int) -> str:
    parts: list[str] = []
    for _, line in body[offset : offset + 6]:
        stripped = line.strip()
        if not stripped:
            continue
        parts.append(stripped)
        if stripped.endswith(";"):
            break
    return " ".join(parts)


def _relative_file(path: Path) -> str:
    parts = path.parts
    if "fs" in parts:
        index = len(parts) - 1 - tuple(reversed(parts)).index("fs")
        return Path(*parts[index:]).as_posix()
    return path.name


def _summary(helpers: Sequence[dict[str, Any]]) -> dict[str, int]:
    return {
        "audited_helpers": len(helpers),
        "helpers_with_public_int_return": sum(
            helper["fact_summary"]["public_int_return"] for helper in helpers
        ),
        "helpers_with_ignored_fast_commit_calls": sum(
            helper["fact_summary"]["ignored_fast_commit_call"] for helper in helpers
        ),
        "helpers_swallowing_ext4_map_blocks_errors": sum(
            helper["fact_summary"]["swallowed_ext4_map_blocks_error"]
            for helper in helpers
        ),
        "helpers_with_metadata_bookkeeping_after_failure": sum(
            helper["fact_summary"]["metadata_bookkeeping_after_failure"]
            for helper in helpers
        ),
        "helpers_with_partial_metadata_mutation_before_failure": sum(
            helper["fact_summary"]["partial_metadata_mutation_before_failure"]
            for helper in helpers
        ),
        "bug_claims_allowed": 0,
    }


if __name__ == "__main__":
    raise SystemExit(main())
