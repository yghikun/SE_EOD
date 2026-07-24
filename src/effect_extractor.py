"""Raw metadata effect extraction from visible C syntax."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from .frontend.model import FrontendNode, FunctionIR
from .metadata_residual import (
    MetadataDelta,
    MetadataEffect,
    MetadataPlane,
    SourceSite,
)
from .parser import call_name_and_args, compact_ws


ACCOUNTING_TERMS = {
    "account",
    "alloc",
    "block",
    "blocks",
    "byte",
    "bytes",
    "count",
    "counter",
    "dquot",
    "free",
    "i_blocks",
    "i_bytes",
    "i_count",
    "i_nlink",
    "nlink",
    "quota",
    "qgroup",
    "ref",
    "refcount",
    "refs",
    "reserve",
    "reserved",
    "reservation",
    "rsv",
    "space",
    "used",
}
RECOVERY_TERMS = {
    "abort",
    "cancel",
    "commit",
    "defer",
    "deferred",
    "delayed",
    "dirty",
    "journal",
    "log",
    "orphan",
    "ordered",
    "pending",
    "post_commit",
    "recover",
    "recovery",
    "reloc",
    "replay",
    "trans",
    "transaction",
}
STRUCTURAL_TERMS = {
    "block_group",
    "chunk",
    "dev",
    "device",
    "dir",
    "entry",
    "extent",
    "fs_devices",
    "inode",
    "link",
    "list",
    "mapping",
    "name",
    "namespace",
    "node",
    "root",
    "tree",
    "xarray",
    "xa",
}
FIELD_SCOPE_TERMS = ACCOUNTING_TERMS | RECOVERY_TERMS | STRUCTURAL_TERMS
OUT_OF_SCOPE_ROOTS = {
    "bh",
    "bh2",
    "buffer",
    "dentry_folio",
    "folio",
    "fname",
    "iloc",
    "name",
    "path",
    "tmp",
}
TRANSIENT_CONTEXT_SUFFIXES = {
    "arg",
    "args",
    "check",
    "context",
    "control",
    "ctl",
    "ctx",
    "cache_entry",
    "key",
    "option",
    "options",
    "param",
    "params",
    "path",
    "ref",
    "request",
    "spec",
}
TRANSIENT_OPERATION_TYPE_TOKENS = {
    "scrub",
}
VFS_WIRING_FIELDS = {
    "a_ops",
    "i_fop",
    "i_mapping",
    "i_op",
}
RECOVERY_CONTEXT_TERMS = {
    "commit",
    "delayed",
    "journal",
    "orphan",
    "ordered",
    "recover",
    "recovery",
    "reloc",
    "replay",
    "trans",
    "transaction",
}
METADATA_READER_SUFFIXES = (
    "_bytes",
    "_count",
    "_ctransid",
    "_flags",
    "_generation",
    "_gid",
    "_in_tree",
    "_id",
    "_item",
    "_level",
    "_len",
    "_length",
    "_mode",
    "_name",
    "_nlink",
    "_node",
    "_offset",
    "_owner",
    "_parent",
    "_refs",
    "_rdev",
    "_root",
    "_size",
    "_state",
    "_transid",
    "_type",
    "_uid",
)
NON_METADATA_OBSERVER_PREFIXES = (
    "trace_",
)
NON_METADATA_OBSERVER_SUFFIXES = (
    "_lock",
    "_unlock",
)
ACCESSOR_VALIDATOR_TOKENS = {
    "can",
    "check",
    "enabled",
    "find",
    "full",
    "get",
    "has",
    "is",
    "should",
    "valid",
}
MUTATING_HELPER_PREFIXES = (
    "abort_",
    "add_",
    "alloc_",
    "clear_",
    "clone_",
    "commit_",
    "create_",
    "del_",
    "delete_",
    "drop_",
    "end_",
    "free_",
    "init_",
    "insert_",
    "load_",
    "mark_",
    "put_",
    "read_",
    "record_",
    "release_",
    "remove_",
    "reserve_",
    "set_",
    "start_",
    "stop_",
    "update_",
    "write_",
)
MUTATING_HELPER_TOKENS = {
    "abort",
    "add",
    "alloc",
    "clear",
    "clone",
    "commit",
    "copy",
    "create",
    "dec",
    "del",
    "delete",
    "drop",
    "end",
    "free",
    "inc",
    "init",
    "insert",
    "link",
    "load",
    "mark",
    "put",
    "record",
    "release",
    "remove",
    "reserve",
    "set",
    "start",
    "stop",
    "unlink",
    "update",
    "write",
}

LIST_ADD_CALLS = {
    "list_add",
    "list_add_tail",
    "hlist_add_head",
    "hlist_add_before",
    "hlist_add_behind",
}
LIST_REMOVE_CALLS = {
    "list_del",
    "list_del_init",
    "hlist_del",
    "hlist_del_init",
    "hlist_del_rcu",
}
BIT_SET_CALLS = {"set_bit", "__set_bit", "test_and_set_bit"}
BIT_CLEAR_CALLS = {"clear_bit", "__clear_bit", "test_and_clear_bit"}
TREE_ADD_CALLS = {
    "rb_link_node",
    "rb_insert_color",
    "rb_add",
    "radix_tree_insert",
    "xa_insert",
    "xa_store",
    "xas_store",
    "xas_create",
}
TREE_REMOVE_CALLS = {
    "rb_erase",
    "radix_tree_delete",
    "xa_erase",
    "xa_release",
    "xas_erase",
    "xas_store_null",
}


@dataclass(frozen=True)
class EffectExtractionResult:
    effects: tuple[MetadataEffect, ...]
    skipped_expressions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "effects": [item.to_dict() for item in self.effects],
            "skipped_expressions": list(self.skipped_expressions),
        }


def extract_metadata_effects(function: FunctionIR) -> tuple[MetadataEffect, ...]:
    """Extract source-visible metadata effects from one function.

    M2 deliberately performs only raw extraction.  It rejects ordinary local or
    generic helper temporaries by requiring a recognizable metadata term or a
    known metadata mutation idiom, then leaves identity-aware cancellation and
    failure-local slicing to later modules.
    """

    return extract_metadata_effects_with_skips(function).effects


def effect_targets_transient_object(
    function: FunctionIR,
    effect: MetadataEffect,
) -> bool:
    """Return whether an instantiated effect targets caller-local state."""

    root = _normalized_path(effect.root)
    scope = _transient_field_scope(function)
    return root in scope.automatic_objects or root in scope.context_roots


def looks_like_metadata_reader(name: str) -> bool:
    """Recognize metadata-named accessors that do not mutate state."""

    lowered = name.lower()
    if lowered.startswith(NON_METADATA_OBSERVER_PREFIXES):
        return True
    if lowered.endswith(NON_METADATA_OBSERVER_SUFFIXES):
        return True
    if _looks_like_accessor_or_validator(lowered):
        return True
    if lowered.startswith(MUTATING_HELPER_PREFIXES):
        return False
    tokens = set(part for part in lowered.split("_") if part)
    if tokens & MUTATING_HELPER_TOKENS:
        return False
    return lowered.endswith(METADATA_READER_SUFFIXES)


def extract_metadata_effects_with_skips(function: FunctionIR) -> EffectExtractionResult:
    if function.body_node is None:
        return EffectExtractionResult(())

    aliases = _local_aliases(function)
    transient_fields = _transient_field_scope(function)
    effects: list[MetadataEffect] = []
    skipped: list[str] = []
    for node in function.body_node.walk():
        if node.type == "assignment_expression":
            effect = _effect_from_assignment(function, node, aliases, transient_fields)
            if effect is not None:
                effects.append(effect)
        elif node.type == "update_expression":
            effect = _effect_from_update(function, node, aliases, transient_fields)
            if effect is not None:
                effects.append(effect)
        elif node.type == "call_expression":
            call_effects = _effects_from_call(function, node, aliases)
            call_effects = tuple(
                effect
                for effect in call_effects
                if not transient_fields.excludes_call_root(effect.root)
            )
            if call_effects:
                effects.extend(call_effects)
            elif _call_name(node) in {"kfree", "kvfree", "brelse", "folio_put"}:
                skipped.append(compact_ws(node.text))

    return EffectExtractionResult(tuple(_dedupe(effects)), tuple(skipped))


def _effect_from_assignment(
    function: FunctionIR,
    node: FrontendNode,
    aliases: dict[str, str],
    transient_fields: "_TransientFieldScope",
) -> MetadataEffect | None:
    if len(node.children) < 3:
        return None
    target = node.children[0]
    operator = compact_ws(node.children[1].text)
    value_node = node.children[-1]
    if target.type != "field_expression":
        return None

    path = _path_parts(target.text, aliases)
    if _out_of_scope_path(path) or transient_fields.excludes(path):
        return None
    plane = _plane_for_path(path)
    if plane is None:
        return None

    if operator == "+=":
        delta = MetadataDelta.INC
    elif operator == "-=":
        delta = MetadataDelta.DEC
    elif operator == "=":
        delta = (
            MetadataDelta.CLEAR
            if _is_clear_value(value_node.text)
            else MetadataDelta.SET
        )
    else:
        return None

    return _effect(
        function,
        node,
        root=path.root,
        key=path.key,
        plane=plane,
        delta=delta,
        value=_replace_aliases(compact_ws(value_node.text), aliases),
    )


def _effect_from_update(
    function: FunctionIR,
    node: FrontendNode,
    aliases: dict[str, str],
    transient_fields: "_TransientFieldScope",
) -> MetadataEffect | None:
    target = next((child for child in node.children if child.type == "field_expression"), None)
    if target is None:
        return None
    path = _path_parts(target.text, aliases)
    if _out_of_scope_path(path) or transient_fields.excludes(path):
        return None
    plane = _plane_for_path(path)
    if plane is None:
        return None
    text = compact_ws(node.text)
    if "++" in text:
        delta = MetadataDelta.INC
    elif "--" in text:
        delta = MetadataDelta.DEC
    else:
        return None
    return _effect(
        function,
        node,
        root=path.root,
        key=path.key,
        plane=plane,
        delta=delta,
        value="1",
    )


def _effects_from_call(
    function: FunctionIR,
    node: FrontendNode,
    aliases: dict[str, str],
) -> tuple[MetadataEffect, ...]:
    name, args = call_name_and_args(compact_ws(node.text))
    if looks_like_metadata_reader(name):
        return ()
    if name in LIST_ADD_CALLS and args:
        return (
            _effect(
                function,
                node,
                root=_normalized_path(args[1], aliases) if len(args) > 1 else _normalized_path(args[0], aliases),
                key="list_membership",
                plane=_plane_for_text(" ".join([name, *args])) or MetadataPlane.STRUCTURAL,
                delta=MetadataDelta.ADD,
                value=_normalized_path(args[0], aliases),
            ),
        )
    if name in LIST_REMOVE_CALLS and args:
        return (
            _effect(
                function,
                node,
                root=_normalized_path(args[0], aliases),
                key="list_membership",
                plane=_plane_for_text(" ".join([name, *args])) or MetadataPlane.STRUCTURAL,
                delta=MetadataDelta.REMOVE,
                value=_list_owner(args[0], aliases),
            ),
        )

    if name in BIT_SET_CALLS and len(args) >= 2:
        return (
            _effect(
                function,
                node,
                root=_normalized_path(args[1], aliases),
                key=f"bit:{compact_ws(args[0])}",
                plane=_plane_for_text(" ".join([name, *args])) or MetadataPlane.STRUCTURAL,
                delta=MetadataDelta.SET,
                value=compact_ws(args[0]),
            ),
        )
    if name in BIT_CLEAR_CALLS and len(args) >= 2:
        return (
            _effect(
                function,
                node,
                root=_normalized_path(args[1], aliases),
                key=f"bit:{compact_ws(args[0])}",
                plane=_plane_for_text(" ".join([name, *args])) or MetadataPlane.STRUCTURAL,
                delta=MetadataDelta.CLEAR,
                value=compact_ws(args[0]),
            ),
        )

    if name in TREE_ADD_CALLS and args:
        return (_tree_effect(function, node, name, args, MetadataDelta.ADD, aliases),)
    if name in TREE_REMOVE_CALLS and args:
        return (_tree_effect(function, node, name, args, MetadataDelta.REMOVE, aliases),)

    reservation = _reservation_effect(function, node, name, args, aliases)
    if reservation is not None:
        return (reservation,)
    quota = _quota_effect(function, node, name, args, aliases)
    if quota is not None:
        return (quota,)
    transaction = _transaction_effect(function, node, name, args, aliases)
    if transaction is not None:
        return (transaction,)
    return ()


def _tree_effect(
    function: FunctionIR,
    node: FrontendNode,
    name: str,
    args: list[str],
    delta: MetadataDelta,
    aliases: dict[str, str],
) -> MetadataEffect:
    root = _normalized_path(args[0], aliases)
    key = "tree_membership"
    value = _list_owner(args[0], aliases)
    if name.startswith(("xa_", "xas_")) and len(args) >= 2:
        key = f"xarray:{compact_ws(args[1])}"
        value = _normalized_path(args[2], aliases) if len(args) >= 3 else compact_ws(args[1])
    elif name.startswith("radix_tree") and len(args) >= 2:
        key = f"radix_tree:{compact_ws(args[1])}"
        value = _normalized_path(args[2], aliases) if len(args) >= 3 else compact_ws(args[1])
    return _effect(
        function,
        node,
        root=root,
        key=key,
        plane=_plane_for_text(" ".join([name, *args])) or MetadataPlane.STRUCTURAL,
        delta=delta,
        value=value,
    )


def _reservation_effect(
    function: FunctionIR,
    node: FrontendNode,
    name: str,
    args: list[str],
    aliases: dict[str, str],
) -> MetadataEffect | None:
    lowered = name.lower()
    if not any(term in lowered for term in ("reserv", "rsv", "space_info")):
        return None
    if any(term in lowered for term in ("release", "unreserve", "free", "drop", "clear")):
        delta = MetadataDelta.RELEASE
    elif any(term in lowered for term in ("reserve", "reserv", "rsv_add", "charge", "alloc")):
        delta = MetadataDelta.RESERVE
    else:
        return None
    return _effect(
        function,
        node,
        root=_normalized_path(args[0], aliases) if args else name,
        key=name,
        plane=MetadataPlane.ACCOUNTING,
        delta=delta,
        value=_value_args(args[1:], aliases),
    )


def _quota_effect(
    function: FunctionIR,
    node: FrontendNode,
    name: str,
    args: list[str],
    aliases: dict[str, str],
) -> MetadataEffect | None:
    lowered = name.lower()
    if not any(term in lowered for term in ("quota", "dquot", "qgroup")):
        return None
    if any(term in lowered for term in ("release", "free", "uncharge", "drop", "put", "detach")):
        delta = MetadataDelta.RELEASE
    elif any(term in lowered for term in ("reserve", "alloc", "charge", "get", "attach", "hold")):
        delta = MetadataDelta.RESERVE
    else:
        delta = MetadataDelta.INC
    return _effect(
        function,
        node,
        root=_normalized_path(args[0], aliases) if args else name,
        key=name,
        plane=MetadataPlane.ACCOUNTING,
        delta=delta,
        value=_value_args(args[1:], aliases),
    )


def _transaction_effect(
    function: FunctionIR,
    node: FrontendNode,
    name: str,
    args: list[str],
    aliases: dict[str, str],
) -> MetadataEffect | None:
    lowered = name.lower()
    if looks_like_metadata_reader(name):
        return None
    if not any(term in lowered for term in ("trans", "transaction", "journal", "orphan", "recovery", "replay", "delayed")):
        return None
    if any(term in lowered for term in ("cancel", "abort", "stop", "end", "release", "forget", "del")):
        delta = MetadataDelta.CLOSE
    elif any(term in lowered for term in ("start", "join", "attach", "record", "add", "reserve", "pin", "protect")):
        delta = MetadataDelta.PROTECT
    else:
        delta = MetadataDelta.ADD
    return _effect(
        function,
        node,
        root=_normalized_path(args[0], aliases) if args else name,
        key=name,
        plane=MetadataPlane.RECOVERY,
        delta=delta,
        value=_value_args(args[1:], aliases),
    )


@dataclass(frozen=True)
class _PathParts:
    root: str
    key: str
    text: str


@dataclass(frozen=True)
class _TransientFieldScope:
    automatic_objects: frozenset[str]
    context_roots: frozenset[str]
    ephemeral_roots: frozenset[str]

    def excludes(self, path: _PathParts) -> bool:
        root = _leading_symbol(path.text)
        if not root:
            return False
        pointer_hops = path.text.count("->")
        if root in self.automatic_objects:
            return pointer_hops == 0
        if root in self.context_roots:
            return pointer_hops <= 1
        if root in self.ephemeral_roots:
            return pointer_hops <= 1
        return False

    def excludes_call_root(self, root: str) -> bool:
        return root in self.context_roots or root in self.ephemeral_roots


def _path_parts(text: str, aliases: dict[str, str] | None = None) -> _PathParts:
    normalized = _normalized_path(text, aliases)
    pieces = re.split(r"\s*(?:->|\.)\s*", normalized)
    if len(pieces) >= 2:
        separator_matches = list(re.finditer(r"\s*(?:->|\.)\s*", normalized))
        last_separator = separator_matches[-1]
        return _PathParts(root=normalized[: last_separator.start()], key=pieces[-1], text=normalized)
    return _PathParts(root=normalized, key=normalized, text=normalized)


def _out_of_scope_root(root: str) -> bool:
    normalized = root.strip().lower()
    return normalized in OUT_OF_SCOPE_ROOTS or normalized.endswith("_path")


def _out_of_scope_path(path: _PathParts) -> bool:
    """Exclude generic VFS operation-table wiring from metadata residual scope."""

    return _out_of_scope_root(path.root) or path.key in VFS_WIRING_FIELDS


def _transient_field_scope(function: FunctionIR) -> _TransientFieldScope:
    return _TransientFieldScope(
        automatic_objects=frozenset(_automatic_object_symbols(function)),
        context_roots=frozenset(
            _transient_context_parameters(function)
            | _transient_context_locals(function)
        ),
        ephemeral_roots=frozenset(_explicitly_ephemeral_aggregate_symbols(function)),
    )


def _automatic_object_symbols(function: FunctionIR) -> set[str]:
    if function.body_node is None:
        return set()
    symbols: set[str] = set()
    for node in function.body_node.walk():
        if node.type != "declaration":
            continue
        for declarator in _declaration_declarators(node):
            if _contains_node_type(declarator, "pointer_declarator"):
                continue
            name = _declarator_name(declarator)
            if name:
                symbols.add(name)
    return symbols


def _transient_context_parameters(function: FunctionIR) -> set[str]:
    if function.ast_node is None:
        return set()
    symbols: set[str] = set()
    for node in function.ast_node.walk():
        if node.type not in {"parameter_declaration", "optional_parameter_declaration"}:
            continue
        declarator = node.child_by_field_name("declarator")
        type_node = node.child_by_field_name("type")
        name = _declarator_name(declarator)
        if not name or type_node is None:
            continue
        is_aggregate_value = (
            type_node.type in {"struct_specifier", "union_specifier"}
            and not _contains_node_type(declarator, "pointer_declarator")
        )
        if is_aggregate_value or _is_transient_context_type(type_node.text):
            symbols.add(name)
    return symbols


def _transient_context_locals(function: FunctionIR) -> set[str]:
    if function.body_node is None:
        return set()
    symbols: set[str] = set()
    for node in function.body_node.walk():
        if node.type != "declaration":
            continue
        type_node = node.child_by_field_name("type")
        if type_node is None or not _is_transient_context_type(type_node.text):
            continue
        for declarator in _declaration_declarators(node):
            if not _contains_node_type(declarator, "pointer_declarator"):
                continue
            name = _declarator_name(declarator)
            if name:
                symbols.add(name)
    return symbols


def _explicitly_ephemeral_aggregate_symbols(function: FunctionIR) -> set[str]:
    """Find local/parameter objects whose aggregate declaration documents reuse."""

    type_names = _explicitly_reused_aggregate_types(function.file)
    if not type_names:
        return set()

    symbols: set[str] = set()
    nodes: Iterable[FrontendNode] = ()
    if function.ast_node is not None:
        nodes = function.ast_node.walk()
    for node in nodes:
        if node.type not in {
            "declaration",
            "parameter_declaration",
            "optional_parameter_declaration",
        }:
            continue
        type_node = node.child_by_field_name("type")
        if type_node is None or _aggregate_type_name(type_node.text) not in type_names:
            continue
        if node.type == "declaration":
            declarators = _declaration_declarators(node)
        else:
            declarator = node.child_by_field_name("declarator")
            declarators = (declarator,) if declarator is not None else ()
        for declarator in declarators:
            name = _declarator_name(declarator)
            if name:
                symbols.add(name)
    return symbols


@lru_cache(maxsize=128)
def _explicitly_reused_aggregate_types(file: Path) -> frozenset[str]:
    try:
        source = file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return frozenset()
    matches = re.findall(
        r"/\*\s*reused\s+for\s+each\s+[^*]+\*/\s*"
        r"struct\s+([A-Za-z_]\w*)\s*\{",
        source,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return frozenset(matches)


def _aggregate_type_name(text: str) -> str:
    match = re.search(r"\b(?:struct|union)\s+([A-Za-z_]\w*)\b", text)
    return match.group(1) if match else ""


def _declaration_declarators(node: FrontendNode) -> tuple[FrontendNode, ...]:
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


def _contains_node_type(node: FrontendNode | None, node_type: str) -> bool:
    return node is not None and any(child.type == node_type for child in node.walk())


def _is_transient_context_type(text: str) -> bool:
    identifiers = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text.lower())
    if not identifiers:
        return False
    type_name = identifiers[-1]
    parts = {part for part in type_name.split("_") if part}
    has_transient_suffix = any(
        type_name == suffix or type_name.endswith(f"_{suffix}")
        for suffix in TRANSIENT_CONTEXT_SUFFIXES
    )
    has_transient_operation = bool(parts & TRANSIENT_OPERATION_TYPE_TOKENS)
    if not parts or not (has_transient_suffix or has_transient_operation):
        return False
    return not bool(parts & RECOVERY_CONTEXT_TERMS)


def _leading_symbol(text: str) -> str:
    match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*(?=(?:->|\.|\[|$))", text)
    return match.group(1) if match else ""


def _normalized_path(text: str, aliases: dict[str, str] | None = None) -> str:
    value = compact_ws(text)
    value = re.sub(r"^\(+", "", value)
    value = re.sub(r"\)+$", "", value)
    while value.startswith("&"):
        value = value[1:].strip()
    while value.startswith("*"):
        value = value[1:].strip()
    value = _replace_aliases(value, aliases or {})
    return compact_ws(value)


def _list_owner(text: str, aliases: dict[str, str] | None = None) -> str:
    path = _path_parts(text, aliases)
    return path.root


def _plane_for_path(path: _PathParts) -> MetadataPlane | None:
    return _plane_for_text(f"{path.root} {path.key} {path.text}")


def _plane_for_text(text: str) -> MetadataPlane | None:
    tokens = set(_tokens(text))
    if tokens & RECOVERY_TERMS:
        return MetadataPlane.RECOVERY
    if tokens & ACCOUNTING_TERMS:
        return MetadataPlane.ACCOUNTING
    if tokens & STRUCTURAL_TERMS:
        return MetadataPlane.STRUCTURAL
    return None


def _tokens(text: str) -> Iterable[str]:
    for item in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text.lower()):
        yield item
        for part in item.split("_"):
            if part:
                yield part


def _looks_like_accessor_or_validator(name: str) -> bool:
    lowered = name.lower()
    tokens = set(_tokens(lowered))
    if not tokens & ACCESSOR_VALIDATOR_TOKENS:
        return False
    if lowered.startswith(MUTATING_HELPER_PREFIXES):
        return False
    if re.search(r"(?:^|_)is_", lowered):
        return True
    return not bool(tokens & MUTATING_HELPER_TOKENS)


def _is_clear_value(text: str) -> bool:
    return compact_ws(text) in {"NULL", "0", "0L", "0UL", "false", "FALSE"}


def _value_args(args: list[str], aliases: dict[str, str] | None = None) -> str:
    return ", ".join(_replace_aliases(compact_ws(arg), aliases or {}) for arg in args)


def _local_aliases(function: FunctionIR) -> dict[str, str]:
    aliases: dict[str, str] = {}
    if function.body_node is None:
        return aliases
    pointer_locals = _local_pointer_symbols(function)
    parameter_symbols = set(function.parameters)
    for node in function.body_node.walk():
        if node.type == "init_declarator":
            name = _declarator_name(node.child_by_field_name("declarator"))
            value_node = node.child_by_field_name("value")
            if name and value_node is not None:
                _record_alias(
                    name,
                    value_node.text,
                    aliases,
                    pointer_locals=pointer_locals,
                    parameter_symbols=parameter_symbols,
                )
        elif node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is not None and right is not None and left.type == "identifier":
                _record_alias(
                    left.text,
                    right.text,
                    aliases,
                    pointer_locals=pointer_locals,
                    parameter_symbols=parameter_symbols,
                )
    return aliases


def _record_alias(
    name: str,
    value: str,
    aliases: dict[str, str],
    *,
    pointer_locals: set[str],
    parameter_symbols: set[str],
) -> None:
    name = compact_ws(name)
    raw_value = compact_ws(value).strip()
    alias = _replace_aliases(_normalized_path(value), aliases)
    direct_parameter_alias = (
        name in pointer_locals
        and re.fullmatch(r"[A-Za-z_]\w*", raw_value) is not None
        and raw_value in parameter_symbols
    )
    if not _looks_like_alias_target(alias) and not direct_parameter_alias:
        return
    aliases[name] = alias


def _local_pointer_symbols(function: FunctionIR) -> set[str]:
    if function.body_node is None:
        return set()
    symbols: set[str] = set()
    for node in function.body_node.walk():
        if node.type != "declaration":
            continue
        for declarator in _declaration_declarators(node):
            if not _contains_node_type(declarator, "pointer_declarator"):
                continue
            name = _declarator_name(declarator)
            if name:
                symbols.add(name)
    return symbols


def _declarator_name(node: FrontendNode | None) -> str | None:
    if node is None:
        return None
    if node.type == "identifier":
        return compact_ws(node.text)
    nested = node.child_by_field_name("declarator")
    if nested is not None:
        return _declarator_name(nested)
    identifiers = [child for child in node.walk() if child.type == "identifier"]
    return compact_ws(identifiers[-1].text) if identifiers else None


def _looks_like_alias_target(text: str) -> bool:
    if any(marker in text for marker in ("{", "}", ",")):
        return False
    if "(" in text or ")" in text:
        return False
    return bool(re.search(r"(?:->|\.)", text)) and _plane_for_text(text) is not None


def _replace_aliases(text: str, aliases: dict[str, str]) -> str:
    result = text
    for source, target in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
        pieces: list[str] = []
        last = 0
        for match in re.finditer(rf"\b{re.escape(source)}\b", result):
            if _is_field_component(result, match.start()):
                continue
            pieces.append(result[last:match.start()])
            pieces.append(target)
            last = match.end()
        if pieces:
            pieces.append(result[last:])
            result = "".join(pieces)
    return compact_ws(result)


def _is_field_component(text: str, start: int) -> bool:
    return text[max(0, start - 2) : start] == "->" or text[max(0, start - 1) : start] == "."


def _call_name(node: FrontendNode) -> str:
    name, _ = call_name_and_args(compact_ws(node.text))
    return name


def _effect(
    function: FunctionIR,
    node: FrontendNode,
    *,
    root: str,
    key: str,
    plane: MetadataPlane,
    delta: MetadataDelta,
    value: str,
) -> MetadataEffect:
    return MetadataEffect(
        root=root,
        key=key,
        plane=plane,
        delta=delta,
        value=compact_ws(value),
        site=SourceSite(function.file.as_posix(), node.start_line, compact_ws(node.text)),
    )


def _dedupe(effects: list[MetadataEffect]) -> list[MetadataEffect]:
    result: list[MetadataEffect] = []
    seen: set[tuple[str, str, str, str, str, int, str]] = set()
    for effect in effects:
        key = (
            effect.root,
            effect.key,
            effect.plane.value,
            effect.delta.value,
            effect.value,
            effect.site.line,
            effect.site.expression,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(effect)
    return result
