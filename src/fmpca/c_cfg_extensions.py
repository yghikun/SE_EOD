from __future__ import annotations

import re
from pathlib import Path
from typing import Tuple

from tree_sitter import Language, Parser
import tree_sitter_c

from .c_cfg import FunctionCFG, _CFGBuilder, _normalize_gnu_attributes
from .frontend import SourceBindingError, extract_function


def _normalize_label_before_preprocessor(text: str) -> Tuple[str, bool]:
    pattern = re.compile(r"(?m)^(\s*[A-Za-z_]\w*\s*:\s*)(?=\n\s*#)")
    normalized, count = pattern.subn(r"\1;", text)
    return normalized, count > 0


def _normalize_kernel_macro_type_arguments(text: str) -> Tuple[str, bool]:
    pattern = re.compile(r"(\blist_entry\([^,]+,\s*)struct\s+([A-Za-z_]\w*)")
    normalized, count = pattern.subn(r"\1struct_\2", text)
    return normalized, count > 0


def build_phase5_function_cfg(source_path: str, function_name: str) -> FunctionCFG:
    source_text = Path(source_path).read_text(encoding="utf-8")
    function = extract_function(source_text, function_name)
    normalized_text, attributes = _normalize_gnu_attributes(function.text)
    leading = len(normalized_text) - len(normalized_text.lstrip())
    split_return_type = normalized_text[leading:].startswith(f"{function_name}(")
    if split_return_type:
        normalized_text = normalized_text[:leading] + "int " + normalized_text[leading:]
    normalized_text, label_normalized = _normalize_label_before_preprocessor(
        normalized_text
    )
    normalized_text, macro_type_normalized = _normalize_kernel_macro_type_arguments(
        normalized_text
    )
    normalizations = attributes + (
        ("label_before_preprocessor",) if label_normalized else ()
    ) + (
        ("kernel_macro_type_argument",) if macro_type_normalized else ()
    ) + (("split_return_type",) if split_return_type else ())
    source = normalized_text.encode("utf-8")
    parser = Parser(Language(tree_sitter_c.language()))
    tree = parser.parse(source)
    definition = next(
        (
            child
            for child in tree.root_node.named_children
            if child.type == "function_definition"
        ),
        None,
    )
    if definition is None:
        raise SourceBindingError(f"tree-sitter function parse failed: {function_name}")
    body = definition.child_by_field_name("body")
    if body is None:
        raise SourceBindingError(f"tree-sitter function body missing: {function_name}")
    return _CFGBuilder(source, function, source_path, normalizations).finish(
        body, tree.root_node.has_error
    )
