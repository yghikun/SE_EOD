"""C/IR syntax helpers shared by summary analysis stages."""

from __future__ import annotations

import re

from ..effect_extractor import looks_like_metadata_reader
from ..frontend.model import FrontendNode, FunctionIR
from ..metadata_residual import MetadataDelta, MetadataEffect
from ..parser import call_name_and_args, compact_ws, extract_return_expr, split_args


UNKNOWN_CALLS = {
    "call_rcu",
    "queue_work",
    "schedule_work",
    "delayed_work",
    "kthread_run",
}


def replace_symbols(text: str, mapping: dict[str, str]) -> str:
    result = text
    for source, target in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
        pieces: list[str] = []
        last = 0
        for match in re.finditer(rf"\b{re.escape(source)}\b", result):
            if is_field_component(result, match.start()):
                continue
            pieces.append(result[last:match.start()])
            pieces.append(target)
            last = match.end()
        if pieces:
            pieces.append(result[last:])
            result = "".join(pieces)
    return compact_ws(result)


def bare_owner_symbol(text: str) -> str:
    value = compact_ws(text).strip()
    while value.startswith("(") and value.endswith(")"):
        value = value[1:-1].strip()
    while value.startswith(("&", "*")):
        value = value[1:].strip()
    return value if re.fullmatch(r"[A-Za-z_]\w*", value) else ""


def plain_local_symbol(text: str, allocations: dict[str, int]) -> str | None:
    value = compact_ws(text).strip("()")
    return value if value in allocations else None


def base_local_symbol(text: str, allocations: dict[str, int]) -> str | None:
    match = re.match(r"^([A-Za-z_]\w*)", compact_ws(text).lstrip("&*()"))
    if match and match.group(1) in allocations:
        return match.group(1)
    return None


def field_path(root: str, key: str) -> str:
    return f"{root}->{key}" if root else key


def parameterize_path(
    path: str,
    parameters: tuple[str, ...],
    owner_aliases: dict[str, str] | None = None,
) -> str:
    mapping = {name: f"arg{index}" for index, name in enumerate(parameters)}
    mapping.update(owner_aliases or {})
    return replace_symbols(path, mapping)


def references_unbound_local(
    effect: MetadataEffect,
    local_symbols: set[str],
) -> bool:
    return bool(unbound_local_tokens(effect, local_symbols))


def references_only_private_fresh(
    effect: MetadataEffect,
    local_symbols: set[str],
    private_fresh_locals: set[str],
) -> bool:
    tokens = unbound_local_tokens(effect, local_symbols)
    if "(" in effect.site.expression:
        tokens.update(unbound_tokens_in_text(effect.site.expression, local_symbols))
    return bool(tokens) and tokens <= private_fresh_locals


def unbound_local_tokens(
    effect: MetadataEffect,
    local_symbols: set[str],
) -> set[str]:
    if not local_symbols:
        return set()
    parts = [effect.root]
    if effect.delta in {MetadataDelta.ADD, MetadataDelta.REMOVE, MetadataDelta.PROTECT}:
        parts.append(effect.value)
    return unbound_tokens_in_text(" ".join(parts), local_symbols)


def unbound_tokens_in_text(text: str, local_symbols: set[str]) -> set[str]:
    result: set[str] = set()
    for match in re.finditer(r"\b[A-Za-z_]\w*\b", text):
        token = match.group(0)
        if token not in local_symbols or is_field_component(text, match.start()):
            continue
        result.add(token)
    return result


def is_field_component(text: str, start: int) -> bool:
    return text[max(0, start - 2) : start] == "->" or text[max(0, start - 1) : start] == "."


def local_symbols(function: FunctionIR) -> set[str]:
    if function.body_node is None:
        return set()
    parameters = set(ordered_parameters(function))
    symbols: set[str] = set()
    for node in function.body_node.walk():
        if node.type != "declaration":
            continue
        for declarator in declaration_declarators(node):
            name = declarator_name(declarator)
            if name:
                symbols.add(name)
    return symbols - parameters


def success_return_symbols(
    function: FunctionIR,
    pointer_local_symbols: set[str],
) -> set[str]:
    return {
        expression
        for expression in success_return_expressions(function)
        if expression in pointer_local_symbols
    }


def local_pointer_symbols(function: FunctionIR) -> set[str]:
    if function.body_node is None:
        return set()
    symbols: set[str] = set()
    for node in function.body_node.walk():
        if node.type != "declaration":
            continue
        for declarator in declaration_declarators(node):
            if not contains_node_type(declarator, "pointer_declarator"):
                continue
            name = declarator_name(declarator)
            if name:
                symbols.add(name)
    return symbols


def declaration_declarators(node: FrontendNode) -> tuple[FrontendNode, ...]:
    declarator_types = {
        "array_declarator",
        "attributed_declarator",
        "identifier",
        "init_declarator",
        "parenthesized_declarator",
        "pointer_declarator",
    }
    result = tuple(child for child in node.children if child.type in declarator_types)
    if result:
        return result
    declarator = node.child_by_field_name("declarator")
    return (declarator,) if declarator is not None else ()


def contains_node_type(node: FrontendNode | None, node_type: str) -> bool:
    return node is not None and any(child.type == node_type for child in node.walk())


def success_return_expressions(function: FunctionIR) -> tuple[str, ...]:
    if function.body_node is not None:
        returns = [
            return_expression(node)
            for node in function.body_node.walk()
            if node.type == "return_statement"
        ]
    else:
        returns = [
            extract_return_expr(line) or ""
            for line in function.body.splitlines()
            if "return" in line
        ]
    returns = [compact_ws(item) for item in returns if compact_ws(item)]
    return (returns[-1],) if returns else ()


def return_expression(node: FrontendNode) -> str:
    for child in node.children:
        if child.type in {"return", ";"}:
            continue
        return compact_ws(child.text)
    return extract_return_expr(node.text) or ""


def ordered_parameters(function: FunctionIR) -> tuple[str, ...]:
    if function.ast_node is not None:
        declarator = find_child_type(function.ast_node, "function_declarator")
        params = find_child_type(declarator, "parameter_list")
        if params is not None:
            names: list[str] = []
            for child in params.children:
                if child.type not in {"parameter_declaration", "optional_parameter_declaration"}:
                    continue
                name = parameter_name(child)
                if name and name != "void":
                    names.append(name)
            if names:
                return tuple(names)
    parsed = parameters_from_signature(function.signature)
    return parsed or tuple(sorted(function.parameters))


def parameter_name(node: FrontendNode) -> str | None:
    identifiers = [
        child.text.strip()
        for child in node.walk()
        if child.type in {"identifier", "field_identifier"}
    ]
    return identifiers[-1] if identifiers else None


def declarator_name(node: FrontendNode | None) -> str | None:
    if node is None:
        return None
    if node.type == "identifier":
        return node.text.strip()
    nested = node.child_by_field_name("declarator")
    if nested is not None:
        return declarator_name(nested)
    identifiers = [
        child.text.strip()
        for child in node.walk()
        if child.type in {"identifier", "field_identifier"}
    ]
    return identifiers[-1] if identifiers else None


def parameters_from_signature(signature: str) -> tuple[str, ...]:
    close_idx = signature.rfind(")")
    open_idx = signature.rfind("(", 0, close_idx)
    if open_idx == -1 or close_idx == -1 or close_idx <= open_idx:
        return ()
    result: list[str] = []
    for arg in split_args(signature[open_idx + 1 : close_idx]):
        arg = arg.strip()
        if not arg or arg == "void" or arg == "...":
            continue
        match = re.search(r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?$", arg.replace("*", " "))
        if match and match.group(1) != "void":
            result.append(match.group(1))
    return tuple(result)


def find_child_type(node: FrontendNode | None, node_type: str) -> FrontendNode | None:
    if node is None:
        return None
    if node.type == node_type:
        return node
    for child in node.children:
        found = find_child_type(child, node_type)
        if found is not None:
            return found
    return None


def is_static_function(function: FunctionIR) -> bool:
    return bool(re.search(r"\bstatic\b", function.signature))


def is_project_summary_candidate(function: FunctionIR) -> bool:
    if not is_static_function(function):
        return True
    return function.file.suffix == ".h" and bool(re.search(r"\binline\b", function.signature))


def unknown_escape_causes(function: FunctionIR) -> tuple[str, ...]:
    if function.body_node is None:
        return ("missing_function_body",)
    causes: list[str] = []
    for node in function.body_node.walk():
        if node.type != "call_expression":
            continue
        name, _ = call_name_and_args(compact_ws(node.text))
        if name in UNKNOWN_CALLS:
            causes.append(f"async_or_deferred_handoff: {name}")
        callee_node = node.child_by_field_name("function")
        if (
            callee_node is not None
            and callee_node.type != "identifier"
            and not looks_like_scalar_cast_call(compact_ws(node.text))
        ):
            causes.append(f"indirect_call: {compact_ws(node.text)}")
        if name in function.parameters:
            causes.append(f"function_pointer_parameter_call: {name}")
    return tuple(sorted(set(causes)))


def looks_like_scalar_cast_call(expression: str) -> bool:
    """Reject tree-sitter call-shaped scalar casts from indirect-call UNKNOWNs."""

    return bool(
        re.match(
            r"^\(\s*(?:(?:u|s)(?:8|16|32|64)|size_t|ssize_t|"
            r"unsigned(?:\s+(?:char|short|int|long))?|"
            r"signed(?:\s+(?:char|short|int|long))?|"
            r"char|short|int|long|bool)\s*\)\s*\(",
            expression,
        )
    )


def unresolved_metadata_helper_names(
    function: FunctionIR,
    raw_effects: tuple[MetadataEffect, ...],
) -> tuple[str, ...]:
    if function.body_node is None:
        return ()
    known_effect_sites = {
        (effect.site.line, compact_ws(effect.site.expression))
        for effect in raw_effects
    }
    names: list[str] = []
    for node in function.body_node.walk():
        if node.type != "call_expression":
            continue
        name, _ = call_name_and_args(compact_ws(node.text))
        if not looks_like_metadata_helper(name):
            continue
        if (node.start_line, compact_ws(node.text)) in known_effect_sites:
            continue
        names.append(name)
    return tuple(sorted(set(names)))


def looks_like_metadata_helper(name: str) -> bool:
    if looks_like_metadata_reader(name):
        return False
    lowered = name.lower()
    return any(
        token in lowered
        for token in (
            "inode", "dquot", "quota", "qgroup", "trans", "journal",
            "orphan", "block_rsv", "reserv", "reloc", "root", "extent",
            "chunk", "device",
        )
    )
