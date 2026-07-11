"""C source loading and optional tree-sitter parsing.

The rest of the extractor uses conservative text-level analyses so that it can
continue even when a kernel file contains preprocessor-heavy syntax that the
local tree-sitter build cannot parse cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class ParsedFile:
    path: Path
    text: str
    tree: Optional[Any] = None
    parser_kind: str = "text"
    warnings: list[str] = field(default_factory=list)


def _build_tree_sitter_parser() -> tuple[Optional[Any], Optional[str]]:
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_c
    except Exception as exc:  # pragma: no cover - depends on local deps
        return None, f"tree-sitter unavailable: {exc}"

    try:
        c_language_capsule = tree_sitter_c.language()
        try:
            c_language = Language(c_language_capsule)
        except TypeError:
            c_language = c_language_capsule

        parser = Parser()
        if hasattr(parser, "language"):
            parser.language = c_language
        else:  # tree-sitter 0.20 style
            parser.set_language(c_language)
        return parser, None
    except Exception as exc:  # pragma: no cover - depends on local deps
        return None, f"tree-sitter initialization failed: {exc}"


def parse_c_file(path: str | Path) -> ParsedFile:
    source_path = Path(path)
    warnings: list[str] = []
    text = source_path.read_text(encoding="utf-8", errors="replace")

    parser, warning = _build_tree_sitter_parser()
    if warning:
        warnings.append(warning)

    if parser is None:
        return ParsedFile(source_path, text, None, "text", warnings)

    try:
        tree = parser.parse(text.encode("utf-8", errors="replace"))
        return ParsedFile(source_path, text, tree, "tree-sitter+c/text", warnings)
    except Exception as exc:
        warnings.append(f"tree-sitter parse failed: {exc}")
        return ParsedFile(source_path, text, None, "text", warnings)


def mask_comments_and_strings(text: str) -> str:
    """Replace comments and string/char literals with spaces, preserving lines."""
    chars = list(text)
    i = 0
    n = len(chars)
    state = "code"

    while i < n:
        c = chars[i]
        nxt = chars[i + 1] if i + 1 < n else ""

        if state == "code":
            if c == "/" and nxt == "/":
                chars[i] = " "
                chars[i + 1] = " "
                i += 2
                state = "line_comment"
                continue
            if c == "/" and nxt == "*":
                chars[i] = " "
                chars[i + 1] = " "
                i += 2
                state = "block_comment"
                continue
            if c == '"':
                chars[i] = " "
                i += 1
                state = "string"
                continue
            if c == "'":
                chars[i] = " "
                i += 1
                state = "char"
                continue
            i += 1
            continue

        if state == "line_comment":
            if c == "\n":
                state = "code"
            else:
                chars[i] = " "
            i += 1
            continue

        if state == "block_comment":
            if c == "*" and nxt == "/":
                chars[i] = " "
                chars[i + 1] = " "
                i += 2
                state = "code"
                continue
            if c != "\n":
                chars[i] = " "
            i += 1
            continue

        if state in {"string", "char"}:
            quote = '"' if state == "string" else "'"
            if c == "\\":
                chars[i] = " "
                if i + 1 < n and chars[i + 1] != "\n":
                    chars[i + 1] = " "
                    i += 2
                else:
                    i += 1
                continue
            if c == quote:
                chars[i] = " "
                i += 1
                state = "code"
                continue
            if c != "\n":
                chars[i] = " "
            i += 1

    return "".join(chars)


def compact_ws(text: str) -> str:
    return " ".join(text.strip().split())


def split_args(arg_text: str) -> list[str]:
    args: list[str] = []
    current: list[str] = []
    depth = 0
    for ch in arg_text:
        if ch == "(":
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
        if ch == "," and depth == 0:
            arg = "".join(current).strip()
            if arg:
                args.append(arg)
            current = []
            continue
        current.append(ch)
    arg = "".join(current).strip()
    if arg:
        args.append(arg)
    return args


def find_matching_paren(text: str, open_index: int) -> int:
    depth = 0
    for idx in range(open_index, len(text)):
        if text[idx] == "(":
            depth += 1
        elif text[idx] == ")":
            depth -= 1
            if depth == 0:
                return idx
    return -1


def extract_call_expressions(text: str) -> list[str]:
    calls: list[str] = []
    keywords = {
        "if",
        "for",
        "while",
        "switch",
        "return",
        "sizeof",
        "typeof",
        "__builtin_expect",
    }
    i = 0
    while i < len(text):
        if not (text[i].isalpha() or text[i] == "_"):
            i += 1
            continue
        start = i
        i += 1
        while i < len(text) and (text[i].isalnum() or text[i] == "_"):
            i += 1
        name = text[start:i]
        j = i
        while j < len(text) and text[j].isspace():
            j += 1
        if j >= len(text) or text[j] != "(" or name in keywords:
            continue
        close = find_matching_paren(text, j)
        if close == -1:
            continue
        calls.append(compact_ws(text[start : close + 1]))
        i = close + 1
    return calls


def call_name_and_args(call_expr: str) -> tuple[str, list[str]]:
    open_idx = call_expr.find("(")
    close_idx = call_expr.rfind(")")
    if open_idx == -1 or close_idx == -1 or close_idx < open_idx:
        return call_expr.strip(), []
    name = call_expr[:open_idx].strip()
    args = split_args(call_expr[open_idx + 1 : close_idx])
    return name, args


def call_name_and_first_arg(call_expr: str) -> tuple[str, str]:
    name, args = call_name_and_args(call_expr)
    return name, args[0].strip() if args else ""


def extract_return_expr(text: str) -> Optional[str]:
    match = None
    for candidate in __import__("re").finditer(r"\breturn\b", text):
        match = candidate
    if not match:
        return None
    rest = text[match.end() :]
    semi = rest.find(";")
    if semi != -1:
        rest = rest[:semi]
    return compact_ws(rest)
