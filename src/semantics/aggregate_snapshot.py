"""Source-proven field snapshot restoration for failure-path slices."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from ..frontend.model import ControlFlowGraphIR, FrontendNode, FunctionIR
from ..metadata_residual import (
    AggregateSnapshotRelation,
    MetadataDelta,
    MetadataEffect,
    SourceSite,
)
from ..parser import compact_ws


@dataclass(frozen=True)
class _SnapshotCapture:
    snapshot: str
    owner: str
    site: SourceSite
    block_id: int | None
    end_byte: int


@dataclass(frozen=True)
class _SnapshotRestore:
    snapshot: str
    owner: str
    site: SourceSite
    block_id: int | None
    start_byte: int


def aggregate_snapshot_restore_cancellations(
    function: FunctionIR,
    cfg: ControlFlowGraphIR,
    *,
    reaching_effects: Iterable[MetadataEffect],
    failure_line: int,
    check_line: int,
    must_error_blocks: set[int],
) -> tuple[MetadataEffect, ...]:
    """Create exact RESTORE cancellations for field SET effects.

    A relation is accepted only for a local snapshot copied from an owner,
    restored to that same owner after the failed check, and dominating every
    feasible error exit.  The local may be an aggregate, scalar, or pointer.
    Writes to an aggregate snapshot are checked per field; a whole-object
    write, same-field write, or address escape rejects the relation.
    """

    if function.body_node is None:
        return ()
    macros = _visible_function_macros(function.file)
    captures, restores = _snapshot_assignments(function, cfg, macros)
    dominators = _dominators(cfg)
    effects = tuple(reaching_effects)
    cancellations: list[MetadataEffect] = []
    for restore in restores:
        if restore.site.line < check_line or restore.block_id not in must_error_blocks:
            continue
        capture = next(
            (
                candidate
                for candidate in captures
                if candidate.snapshot == restore.snapshot
                and candidate.owner == restore.owner
                and candidate.end_byte < restore.start_byte
            ),
            None,
        )
        if capture is None:
            continue
        owner_root, aggregate_key = _owner_parts(restore.owner)
        for effect in effects:
            if (
                effect.delta is not MetadataDelta.SET
                or effect.site.line <= capture.site.line
                or effect.site.line > failure_line
                or not _effect_belongs_to_owner(effect, restore.owner, macros)
            ):
                continue
            effect_block = _block_for_effect(cfg, effect)
            if (
                capture.block_id is None
                or effect_block is None
                or capture.block_id not in dominators.get(effect_block, set())
            ):
                continue
            field = _effect_snapshot_field(effect, restore.owner, macros)
            if _snapshot_field_invalidated(
                function,
                capture,
                restore,
                field,
            ):
                continue
            relation = AggregateSnapshotRelation(
                snapshot_root=capture.snapshot,
                owner_root=owner_root,
                aggregate_key=aggregate_key,
                capture_site=capture.site,
                capture_block=capture.block_id,
                source_identity=restore.owner,
            )
            cancellations.append(
                MetadataEffect(
                    root=effect.root,
                    key=effect.key,
                    plane=effect.plane,
                    delta=MetadataDelta.RESTORE,
                    value=capture.snapshot,
                    site=restore.site,
                    evidence=effect.evidence,
                    snapshot_relation=relation,
                )
            )
    return tuple(dict.fromkeys(cancellations))


def _snapshot_assignments(
    function: FunctionIR,
    cfg: ControlFlowGraphIR,
    macros: dict[str, tuple[tuple[str, ...], str]],
) -> tuple[tuple[_SnapshotCapture, ...], tuple[_SnapshotRestore, ...]]:
    local_snapshots = _local_snapshot_symbols(function)
    captures: list[_SnapshotCapture] = []
    restores: list[_SnapshotRestore] = []
    for node in function.body_node.walk() if function.body_node is not None else ():
        if node.type != "assignment_expression":
            continue
        left = node.child_by_field_name("left") or (node.children[0] if node.children else None)
        right = node.child_by_field_name("right") or (node.children[-1] if node.children else None)
        if left is None or right is None or _assignment_operator(node) != "=":
            continue
        site = SourceSite(function.file.as_posix(), node.start_line, compact_ws(node.text))
        block_id = _block_for_node(cfg, node)
        if left.type == "identifier" and compact_ws(left.text) in local_snapshots:
            owner = _canonical_owner(right.text, macros)
            if owner:
                captures.append(
                    _SnapshotCapture(compact_ws(left.text), owner, site, block_id, node.end_byte)
                )
        if right.type == "identifier" and compact_ws(right.text) in local_snapshots:
            owner = _canonical_owner(left.text, macros)
            if owner:
                restores.append(
                    _SnapshotRestore(compact_ws(right.text), owner, site, block_id, node.start_byte)
                )
    return tuple(captures), tuple(restores)


def _local_snapshot_symbols(function: FunctionIR) -> set[str]:
    if function.body_node is None:
        return set()
    symbols: set[str] = set()
    for node in function.body_node.walk():
        if node.type != "declaration":
            continue
        for declarator in node.children:
            if declarator.type in {
                "attribute_specifier",
                "storage_class_specifier",
                "struct_specifier",
                "type_identifier",
                "union_specifier",
            }:
                continue
            name = _declarator_name(declarator)
            if name:
                symbols.add(name)
    return symbols


def _snapshot_field_invalidated(
    function: FunctionIR,
    capture: _SnapshotCapture,
    restore: _SnapshotRestore,
    field: str,
) -> bool:
    """Reject a whole/same-field write or escaped snapshot before restore."""

    if function.body_node is None:
        return True
    for node in function.body_node.walk():
        if not (capture.end_byte < node.start_byte < restore.start_byte):
            continue
        if re.search(rf"&\s*{re.escape(capture.snapshot)}(?:\b|\.)", compact_ws(node.text)):
            return True
        if node.type in {"assignment_expression", "update_expression"}:
            target = node.child_by_field_name("left")
            if target is None and node.children:
                target = node.children[0]
            if target is not None and _writes_snapshot_field(target.text, capture.snapshot, field):
                return True
    return False


def _writes_snapshot_field(target: str, snapshot: str, field: str) -> bool:
    value = compact_ws(target).lstrip("(*")
    if value == snapshot:
        return True
    if not value.startswith(f"{snapshot}."):
        return False
    written_field = value[len(snapshot) + 1 :].split(".", 1)[0].split("[", 1)[0]
    return written_field == field


def _effect_belongs_to_owner(
    effect: MetadataEffect,
    owner: str,
    macros: dict[str, tuple[tuple[str, ...], str]],
) -> bool:
    root = _canonical_effect_root(effect.root, macros)
    if root == owner:
        return True
    return _join_owner(root, effect.key) == owner


def _effect_snapshot_field(
    effect: MetadataEffect,
    owner: str,
    macros: dict[str, tuple[tuple[str, ...], str]],
) -> str:
    root = _canonical_effect_root(effect.root, macros)
    if root == owner:
        return effect.key
    return ""


def _canonical_effect_root(
    expression: str,
    macros: dict[str, tuple[tuple[str, ...], str]],
) -> str:
    owner = _canonical_owner(expression, macros)
    if owner:
        return owner
    value = _expand_macros(compact_ws(expression), macros).strip("&*() ")
    return value if re.fullmatch(r"[A-Za-z_]\w*", value) else ""


def _owner_parts(owner: str) -> tuple[str, str]:
    separator = max(owner.rfind("->"), owner.rfind("."))
    if separator < 0:
        return owner, ""
    width = 2 if owner[separator : separator + 2] == "->" else 1
    return owner[:separator], owner[separator + width :]


def _join_owner(root: str, key: str) -> str:
    return f"{root}->{key}" if root and key else root


def _canonical_owner(
    expression: str,
    macros: dict[str, tuple[tuple[str, ...], str]],
) -> str:
    value = _expand_macros(compact_ws(expression), macros)
    value = value.replace(" ", "")
    value = re.sub(r"\((\w+)\)", r"\1", value)
    value = re.sub(r"\(([^()]+)\)", r"\1", value)
    value = value.replace(".", "->") if "->" not in value and "." in value else value
    while value.startswith("(") and value.endswith(")"):
        inner = value[1:-1]
        if _balanced(inner):
            value = inner
        else:
            break
    return value if re.fullmatch(r"[A-Za-z_]\w*(?:(?:->|\.)[A-Za-z_]\w*)+", value) else ""


def _expand_macros(
    expression: str,
    macros: dict[str, tuple[tuple[str, ...], str]],
) -> str:
    value = expression
    for _ in range(8):
        changed = False
        for name, (parameters, body) in macros.items():
            match = re.search(rf"\b{re.escape(name)}\s*\(", value)
            if match is None:
                continue
            start = value.find("(", match.start())
            end = _matching_paren(value, start)
            if end < 0:
                continue
            args = _split_args(value[start + 1 : end])
            if len(args) != len(parameters):
                continue
            expanded = body
            for parameter, argument in zip(parameters, args):
                expanded = re.sub(
                    rf"\b{re.escape(parameter)}\b",
                    lambda _match, value=argument: value,
                    expanded,
                )
            value = value[: match.start()] + expanded + value[end + 1 :]
            changed = True
            break
        if not changed:
            break
    return value


@lru_cache(maxsize=128)
def _visible_function_macros(source_file: Path) -> dict[str, tuple[tuple[str, ...], str]]:
    paths = _included_header_paths(source_file)
    macros: dict[str, tuple[tuple[str, ...], str]] = {}
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in re.finditer(
            r"^\s*#\s*define\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s+(.+?)\s*$",
            text,
            flags=re.MULTILINE,
        ):
            parameters = tuple(
                part.strip() for part in match.group(2).split(",") if part.strip()
            )
            body = compact_ws(match.group(3))
            if parameters and body:
                macros[match.group(1)] = (parameters, body)
    return macros


def _included_header_paths(source_file: Path) -> tuple[Path, ...]:
    pending = [source_file]
    seen: set[Path] = set()
    result: list[Path] = []
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for include in re.findall(r'^\s*#\s*include\s+"([^"]+)"', text, re.MULTILINE):
            child = path.parent / include
            if child.is_file():
                pending.append(child)
    return tuple(result)


def _assignment_operator(node: FrontendNode) -> str:
    return compact_ws(node.children[1].text) if len(node.children) >= 3 else ""


def _block_for_node(cfg: ControlFlowGraphIR, node: FrontendNode) -> int | None:
    matches = [
        block
        for block in cfg.blocks.values()
        if block.start_byte <= node.start_byte and node.end_byte <= block.end_byte
    ]
    if not matches:
        return None
    return min(matches, key=lambda block: (block.end_byte - block.start_byte, block.id)).id


def _block_for_effect(cfg: ControlFlowGraphIR, effect: MetadataEffect) -> int | None:
    matches = [
        block
        for block in cfg.blocks.values()
        if block.start_line <= effect.site.line <= block.end_line and block.start_line
    ]
    if not matches:
        return None
    exact = [
        block
        for block in matches
        if compact_ws(effect.site.expression) in compact_ws(block.text)
        or compact_ws(block.text) in compact_ws(effect.site.expression)
    ]
    chosen = exact or matches
    return min(chosen, key=lambda block: (block.end_line - block.start_line, block.id)).id


def _dominators(cfg: ControlFlowGraphIR) -> dict[int, set[int]]:
    nodes = set(cfg.blocks)
    dominators = {
        block_id: ({cfg.entry} if block_id == cfg.entry else set(nodes))
        for block_id in nodes
    }
    changed = True
    while changed:
        changed = False
        for block_id in nodes - {cfg.entry}:
            predecessors = [edge.source for edge in cfg.predecessors(block_id)]
            updated = (
                {block_id}
                if not predecessors
                else {block_id}
                | set.intersection(*(dominators[parent] for parent in predecessors))
            )
            if updated != dominators[block_id]:
                dominators[block_id] = updated
                changed = True
    return dominators


def _declarator_name(node: FrontendNode) -> str:
    if node.type == "identifier":
        return compact_ws(node.text)
    declarator = node.child_by_field_name("declarator")
    if declarator is not None:
        return _declarator_name(declarator)
    identifiers = [child for child in node.walk() if child.type == "identifier"]
    return compact_ws(identifiers[-1].text) if identifiers else ""


def _matching_paren(text: str, start: int) -> int:
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _split_args(text: str) -> tuple[str, ...]:
    result: list[str] = []
    start = 0
    depth = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            result.append(text[start:index].strip())
            start = index + 1
    result.append(text[start:].strip())
    return tuple(result)


def _balanced(text: str) -> bool:
    return _matching_paren(f"({text})", 0) == len(text) + 1
