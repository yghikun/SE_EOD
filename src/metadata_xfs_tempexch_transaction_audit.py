"""Source-fact audit for XFS tempfile exchange transaction setup.

This module records source-visible facts for the current top-ranked
MOCC-SE manual review item, ``xrep_tempexch_trans_alloc()``.  It does not
promote the item to a confirmed bug.  The audit captures a narrow question:

* does the helper allocate ``sc->tp`` and then return a callee result that can
  fail without visibly cancelling or committing the transaction?
* do callers that receive that failure visibly cancel/unlock before returning?

The conclusion remains conservative until an independent XFS scrub ownership
contract, maintainer review, accepted fix, or dynamic fault-injection evidence
confirms the obligation.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


XFS_TEMPEXCH_TRANSACTION_AUDIT_SCHEMA_VERSION = 1
TARGET_HELPER = "xrep_tempexch_trans_alloc"
RESERVE_HELPER = "xrep_tempexch_reserve_quota"


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
class FunctionSlice:
    file: Path
    start_index: int
    end_index: int
    start_line: int
    signature: str
    body: tuple[tuple[int, str], ...]


@dataclass(frozen=True)
class CallerAudit:
    function: str
    file: str
    line: int
    call_statement: str
    error_return_without_visible_cleanup: bool
    facts: tuple[SourceFact, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "function": self.function,
            "file": self.file,
            "line": self.line,
            "call_statement": self.call_statement,
            "error_return_without_visible_cleanup": (
                self.error_return_without_visible_cleanup
            ),
            "facts": [fact.to_dict() for fact in self.facts],
        }


@dataclass(frozen=True)
class XfsTempexchTransactionAudit:
    source_root: str
    source_version: str
    target_helper: str
    helper_definition: str
    facts: tuple[SourceFact, ...]
    callers: tuple[CallerAudit, ...]
    conclusion: str
    recommended_action: str
    bug_claim_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        caller_payload = [caller.to_dict() for caller in self.callers]
        fact_kinds = {fact.kind for fact in self.facts}
        callers_without_cleanup = sum(
            1
            for caller in self.callers
            if caller.error_return_without_visible_cleanup
        )
        return {
            "schema_version": XFS_TEMPEXCH_TRANSACTION_AUDIT_SCHEMA_VERSION,
            "scope": "xfs tempfile exchange transaction source-fact audit",
            "result_semantics": "source_facts_not_bug_claims",
            "bug_claims_allowed": False,
            "source_root": self.source_root,
            "source_version": self.source_version,
            "target_helper": self.target_helper,
            "helper_definition": self.helper_definition,
            "summary": {
                "target_helper_allocates_sc_tp": "allocates_sc_tp" in fact_kinds,
                "target_helper_returns_quota_result": (
                    "returns_quota_reserve_result" in fact_kinds
                ),
                "quota_helper_has_failure_return_without_cleanup": (
                    "quota_failure_return_without_cleanup" in fact_kinds
                ),
                "callers": len(self.callers),
                "callers_returning_error_without_visible_cleanup": (
                    callers_without_cleanup
                ),
                "bug_claims_allowed": 0,
            },
            "facts": [fact.to_dict() for fact in self.facts],
            "callers": caller_payload,
            "conclusion": self.conclusion,
            "recommended_action": self.recommended_action,
        }


def audit_xfs_tempexch_transaction(
    source_root: str | Path,
    *,
    source_version: str = "",
) -> XfsTempexchTransactionAudit:
    root = Path(source_root).resolve()
    scrub_dir = _resolve_scrub_dir(root)
    tempfile = scrub_dir / "tempfile.c"
    _require_files(tempfile)

    all_c_files = tuple(sorted(scrub_dir.glob("*.c")))
    tempfile_lines = _read_lines(tempfile)
    target = _extract_function(tempfile, tempfile_lines, TARGET_HELPER)
    reserve = _extract_function(tempfile, tempfile_lines, RESERVE_HELPER)

    facts: list[SourceFact] = []
    facts.extend(_target_helper_facts(target))
    facts.extend(_reserve_helper_facts(reserve))

    callers = tuple(_caller_audits(scrub_dir, all_c_files))
    return XfsTempexchTransactionAudit(
        source_root=root.as_posix(),
        source_version=source_version,
        target_helper=TARGET_HELPER,
        helper_definition=f"{_relative_file(target.file)}:{target.start_line}",
        facts=tuple(facts),
        callers=callers,
        conclusion="strong_manual_review_candidate_not_confirmed_bug",
        recommended_action=(
            "Freeze an XFS scrub transaction ownership contract or obtain "
            "maintainer/patch/fault-injection evidence before promoting this "
            "source-fact pattern to a confirmed bug claim."
        ),
    )


def write_audit_json(report: XfsTempexchTransactionAudit, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_audit_markdown(report: XfsTempexchTransactionAudit, path: str | Path) -> None:
    payload = report.to_dict()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# XFS Tempfile Exchange Transaction Audit",
        "",
        "This audit records source-visible facts for a high-ranked MOCC-SE",
        "manual review item. It is not a confirmed-bug report.",
        "",
        f"- source root: `{report.source_root}`",
        f"- source version: `{report.source_version}`",
        f"- target helper: `{report.target_helper}`",
        f"- helper definition: `{report.helper_definition}`",
        f"- result semantics: `{payload['result_semantics']}`",
        f"- bug claims allowed: `{payload['bug_claims_allowed']}`",
        f"- conclusion: `{report.conclusion}`",
        "",
        "## Summary",
        "",
    ]
    for key, value in payload["summary"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Helper facts", ""])
    for fact in payload["facts"]:
        lines.append(
            f"- `{fact['kind']}` at `{fact['file']}:{fact['line']}`: "
            f"{fact['detail']}"
        )
    lines.extend(["", "## Caller facts", ""])
    for caller in payload["callers"]:
        lines.extend(
            [
                f"### {caller['function']}",
                "",
                f"- callsite: `{caller['file']}:{caller['line']}`",
                f"- call statement: `{caller['call_statement']}`",
                "- error return without visible cleanup: "
                f"`{caller['error_return_without_visible_cleanup']}`",
                "",
            ]
        )
        for fact in caller["facts"]:
            lines.append(
                f"- `{fact['kind']}` at `{fact['file']}:{fact['line']}`: "
                f"{fact['detail']}"
            )
        lines.append("")
    lines.extend(
        [
            "## Interpretation",
            "",
            "The audited source shape is stronger than a generic analyzer gap:",
            "the helper can return quota-reservation errors after creating",
            "`sc->tp`, and the immediate callers often propagate that error",
            "without a visible local cleanup.  This remains a source-fact",
            "audit, not a confirmed bug claim, because the final obligation",
            "depends on XFS scrub transaction ownership semantics outside the",
            "current protocol freeze.",
        ]
    )
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit XFS tempfile exchange transaction source facts."
    )
    parser.add_argument(
        "--source-root",
        default="linux-sources/linux-v7.1-fs/fs",
        help="Linux fs/ root or fs/xfs/scrub directory",
    )
    parser.add_argument("--source-version", default="7.1")
    parser.add_argument(
        "--out-json",
        default="outputs/mocc-batch-scan-v1/xfs-tempexch-transaction-audit.json",
    )
    parser.add_argument(
        "--out-md",
        default="outputs/mocc-batch-scan-v1/xfs-tempexch-transaction-audit.md",
    )
    args = parser.parse_args(argv)
    report = audit_xfs_tempexch_transaction(
        args.source_root,
        source_version=args.source_version,
    )
    write_audit_json(report, args.out_json)
    write_audit_markdown(report, args.out_md)
    print(json.dumps(report.to_dict()["summary"], indent=2, sort_keys=True))
    return 0


def _target_helper_facts(function_slice: FunctionSlice) -> tuple[SourceFact, ...]:
    facts: list[SourceFact] = []
    for offset, (line_no, line) in enumerate(function_slice.body):
        stripped = line.strip()
        statement = _statement_from(function_slice.body, offset)
        if "xfs_trans_alloc" in stripped and "&sc->tp" in statement:
            facts.append(
                SourceFact(
                    "allocates_sc_tp",
                    _relative_file(function_slice.file),
                    line_no,
                    statement,
                )
            )
        if re.search(rf"\breturn\s+{RESERVE_HELPER}\s*\(", stripped):
            facts.append(
                SourceFact(
                    "returns_quota_reserve_result",
                    _relative_file(function_slice.file),
                    line_no,
                    statement,
                )
            )
            if not _visible_cleanup_before(function_slice.body, offset):
                facts.append(
                    SourceFact(
                        "return_after_alloc_without_visible_cleanup",
                        _relative_file(function_slice.file),
                        line_no,
                        statement,
                    )
                )
    return tuple(facts)


def _reserve_helper_facts(function_slice: FunctionSlice) -> tuple[SourceFact, ...]:
    facts: list[SourceFact] = []
    for offset, (line_no, line) in enumerate(function_slice.body):
        stripped = line.strip()
        statement = _statement_from(function_slice.body, offset)
        if stripped == "return error;" and not _visible_cleanup_before(
            function_slice.body,
            offset,
        ):
            facts.append(
                SourceFact(
                    "quota_failure_return_without_cleanup",
                    _relative_file(function_slice.file),
                    line_no,
                    stripped,
                )
            )
        if (
            statement.startswith("return xfs_trans_reserve_quota_nblks(")
            and not _visible_cleanup_before(function_slice.body, offset)
        ):
            facts.append(
                SourceFact(
                    "quota_direct_failure_return_without_cleanup",
                    _relative_file(function_slice.file),
                    line_no,
                    statement,
                )
            )
    return tuple(facts)


def _caller_audits(scrub_dir: Path, files: Iterable[Path]) -> list[CallerAudit]:
    callers: list[CallerAudit] = []
    call_pattern = re.compile(rf"\b{TARGET_HELPER}\s*\(")
    for path in files:
        lines = _read_lines(path)
        for index, line in enumerate(lines):
            if not call_pattern.search(line):
                continue
            function_slice = _enclosing_function(path, lines, index)
            if function_slice is None or function_slice.signature.startswith("int\nxrep_tempexch_trans_alloc"):
                continue
            offset = index - function_slice.start_index
            facts = _callsite_cleanup_facts(function_slice, offset)
            callers.append(
                CallerAudit(
                    function=_function_name(function_slice.signature),
                    file=_relative_file(path),
                    line=index + 1,
                    call_statement=_statement_from(function_slice.body, offset),
                    error_return_without_visible_cleanup=any(
                        fact.kind
                        in {
                            "caller_directly_returns_helper_result",
                            "caller_error_return_without_visible_cleanup",
                        }
                        for fact in facts
                    ),
                    facts=tuple(facts),
                )
            )
    return callers


def _callsite_cleanup_facts(
    function_slice: FunctionSlice,
    call_offset: int,
) -> tuple[SourceFact, ...]:
    facts: list[SourceFact] = []
    body = function_slice.body
    call_line_no, call_line = body[call_offset]
    call_statement = _statement_from(body, call_offset)
    facts.append(
        SourceFact(
            "callsite",
            _relative_file(function_slice.file),
            call_line_no,
            call_statement,
        )
    )
    if call_line.strip().startswith("return "):
        facts.append(
            SourceFact(
                "caller_directly_returns_helper_result",
                _relative_file(function_slice.file),
                call_line_no,
                call_line.strip(),
            )
        )
        return tuple(facts)

    for offset in range(call_offset + 1, min(len(body), call_offset + 8)):
        line_no, line = body[offset]
        stripped = line.strip()
        if not stripped:
            continue
        if _cleanup_statement(stripped):
            facts.append(
                SourceFact(
                    "caller_visible_cleanup_after_call",
                    _relative_file(function_slice.file),
                    line_no,
                    stripped,
                )
            )
            return tuple(facts)
        if stripped.startswith("if (error)") or stripped.startswith("if (ret)"):
            branch = _statement_from(body, offset)
            if _cleanup_statement(branch):
                facts.append(
                    SourceFact(
                        "caller_error_branch_has_visible_cleanup",
                        _relative_file(function_slice.file),
                        line_no,
                        branch,
                    )
                )
                return tuple(facts)
            if "return error;" in branch or "return ret;" in branch:
                facts.append(
                    SourceFact(
                        "caller_error_return_without_visible_cleanup",
                        _relative_file(function_slice.file),
                        line_no,
                        branch,
                    )
                )
                return tuple(facts)
    return tuple(facts)


def _visible_cleanup_before(
    body: Sequence[tuple[int, str]],
    offset: int,
) -> bool:
    start = max(0, offset - 8)
    return any(_cleanup_statement(line.strip()) for _, line in body[start:offset])


def _cleanup_statement(statement: str) -> bool:
    return any(
        token in statement
        for token in (
            "xchk_trans_cancel(",
            "xfs_trans_cancel(",
            "xrep_trans_commit(",
            "xrep_tempfile_iunlock_both(",
            "xrep_tempfile_iunlock(",
            "xchk_iunlock(",
        )
    )


def _resolve_scrub_dir(root: Path) -> Path:
    if (root / "tempfile.c").is_file():
        return root
    if (root / "xfs" / "scrub" / "tempfile.c").is_file():
        return root / "xfs" / "scrub"
    raise FileNotFoundError(f"cannot find xfs scrub sources under {root}")


def _require_files(*paths: Path) -> None:
    missing = [path.as_posix() for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing xfs scrub source files: " + ", ".join(missing))


def _read_lines(path: Path) -> tuple[str, ...]:
    return tuple(path.read_text(encoding="utf-8", errors="replace").splitlines())


def _extract_function(path: Path, lines: Sequence[str], function: str) -> FunctionSlice:
    pattern = re.compile(rf"\b{re.escape(function)}\s*\(")
    for index, line in enumerate(lines):
        if not pattern.search(line):
            continue
        signature_start = _signature_start(lines, index)
        open_index = _find_next_line(lines, index, "{")
        if open_index is None:
            continue
        close_index = _matching_brace_line(lines, open_index)
        return FunctionSlice(
            file=path,
            start_index=signature_start,
            end_index=close_index,
            start_line=signature_start + 1,
            signature="\n".join(lines[signature_start : index + 1]).strip(),
            body=tuple(
                (line_no + 1, lines[line_no])
                for line_no in range(signature_start, close_index + 1)
            ),
        )
    raise ValueError(f"function definition not found: {function}")


def _enclosing_function(
    path: Path,
    lines: Sequence[str],
    line_index: int,
) -> FunctionSlice | None:
    for index in range(line_index, -1, -1):
        open_index = _find_next_line(lines, index, "{")
        if open_index is None or open_index > line_index:
            continue
        try:
            close_index = _matching_brace_line(lines, open_index)
        except ValueError:
            continue
        if close_index < line_index:
            continue
        signature_start = _signature_start(lines, index)
        signature = "\n".join(lines[signature_start : index + 1]).strip()
        if _function_name(signature):
            return FunctionSlice(
                file=path,
                start_index=signature_start,
                end_index=close_index,
                start_line=signature_start + 1,
                signature=signature,
                body=tuple(
                    (line_no + 1, lines[line_no])
                    for line_no in range(signature_start, close_index + 1)
                ),
            )
    return None


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


def _function_name(signature: str) -> str:
    match = re.search(r"\b([A-Za-z_]\w*)\s*\([^;]*$", signature, re.DOTALL)
    if not match:
        return ""
    name = match.group(1)
    if name in {"if", "for", "while", "switch", "return"}:
        return ""
    return name


def _statement_from(body: Sequence[tuple[int, str]], offset: int) -> str:
    parts: list[str] = []
    depth = 0
    for _, line in body[offset : min(len(body), offset + 8)]:
        stripped = line.strip()
        if not stripped:
            continue
        parts.append(stripped)
        depth += stripped.count("(") - stripped.count(")")
        if depth <= 0 and stripped.endswith((";", "{", "}")):
            break
    return " ".join(parts)


def _relative_file(path: Path) -> str:
    parts = path.parts
    if "fs" in parts:
        index = len(parts) - 1 - list(reversed(parts)).index("fs")
        return Path(*parts[index + 1 :]).as_posix()
    return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
