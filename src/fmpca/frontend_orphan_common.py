from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .frontend import SourceBindingError, extract_function


FORBIDDEN_BINDING_KEYS = {
    "bug_id",
    "case_id",
    "function",
    "function_name",
    "patch_id",
    "source_line",
    "target_function",
}

REQUIRED_BINDING_KEYS = {
    "schema_version",
    "binding_id",
    "binding_version",
    "protocol_id",
    "filesystem",
    "role_kinds",
    "semantic_footprint",
    "namespace_transition_primitives",
    "link_count_primitives",
    "zero_link_predicates",
    "registry_insert_primitives",
    "registry_remove_primitives",
    "terminal_deletion_primitives",
    "transaction_settlement_primitives",
    "recovery_primitives",
    "recovery_entry_markers",
    "recovery_exposure_markers",
    "transaction_types",
    "registry_identity_tokens",
}

LIST_KEYS = REQUIRED_BINDING_KEYS - {
    "schema_version",
    "binding_id",
    "binding_version",
    "protocol_id",
    "filesystem",
    "role_kinds",
}


def _forbidden_paths(value: Any, location: str = "$") -> List[str]:
    paths: List[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{location}.{key}"
            if key.lower() in FORBIDDEN_BINDING_KEYS:
                paths.append(child)
            paths.extend(_forbidden_paths(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            paths.extend(_forbidden_paths(item, f"{location}[{index}]"))
    return paths


@dataclass(frozen=True)
class OrphanBinding:
    raw: Dict[str, Any]
    path: Path

    def __getattr__(self, name: str) -> Any:
        try:
            return self.raw[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


@dataclass(frozen=True)
class RegistrationWitness:
    source_path: str
    function_name: str
    namespace_transition_found: bool
    link_count_transition_found: bool
    zero_link_guard_found: bool
    registry_acceptance_found: bool
    transaction_settlement_found: bool
    acceptance_before_settlement: bool
    zero_link_scoped: bool
    registration_safe: bool
    evidence_lines: Dict[str, Optional[int]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SettlementWitness:
    source_path: str
    function_name: str
    terminal_deletion_found: bool
    registry_removal_found: bool
    transaction_settlement_found: bool
    deletion_durable_before_removal: bool
    same_transaction_equivalence: bool
    removal_safe: bool
    evidence_lines: Dict[str, Optional[int]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RecoveryWitness:
    cleanup_source_path: str
    cleanup_function_name: str
    exposure_source_path: str
    exposure_function_name: str
    cleanup_dispatch_found: bool
    zero_link_release_found: bool
    recovery_entry_found: bool
    recovery_exposure_found: bool
    cleanup_before_exposure: bool
    recovery_path_closed: bool
    evidence_lines: Dict[str, Optional[int]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def load_orphan_binding(path: str) -> OrphanBinding:
    binding_path = Path(path)
    raw = json.loads(binding_path.read_text(encoding="utf-8"))
    missing = REQUIRED_BINDING_KEYS - set(raw)
    extra = set(raw) - REQUIRED_BINDING_KEYS
    if missing:
        raise SourceBindingError(f"missing orphan binding keys: {sorted(missing)}")
    if extra:
        raise SourceBindingError(f"unknown orphan binding keys: {sorted(extra)}")
    forbidden = _forbidden_paths(raw)
    if forbidden:
        raise SourceBindingError(
            f"orphan binding contains case-specific keys: {forbidden}"
        )
    if raw["schema_version"] != 1:
        raise SourceBindingError("orphan binding schema_version must be 1")
    if raw["protocol_id"] != "fmpca.orphan_inode_deletion_settlement":
        raise SourceBindingError("orphan binding uses an unsupported protocol_id")
    if not isinstance(raw["role_kinds"], dict) or not raw["role_kinds"]:
        raise SourceBindingError("role_kinds must be a non-empty object")
    for key in LIST_KEYS:
        value = raw[key]
        if not isinstance(value, list) or not value:
            raise SourceBindingError(f"{key} must be a non-empty list")
        if not all(isinstance(item, str) and item for item in value):
            raise SourceBindingError(f"{key} must contain non-empty strings")
    return OrphanBinding(raw=raw, path=binding_path)


def _primitive_occurrences(text: str, primitives: Iterable[str]) -> List[Tuple[int, str]]:
    found: List[Tuple[int, str]] = []
    for primitive in primitives:
        pattern = re.compile(r"\b" + re.escape(primitive) + r"\s*\(")
        found.extend((match.start(), primitive) for match in pattern.finditer(text))
    return sorted(found)


def _persistent_primitive_occurrences(
    text: str, primitives: Iterable[str]
) -> List[Tuple[int, str]]:
    return [
        item
        for item in _primitive_occurrences(text, primitives)
        if not re.match(r"\s*NULL\s*,", text[text.find("(", item[0]) + 1 :])
    ]


def _predicate_occurrences(text: str, predicates: Iterable[str]) -> List[Tuple[int, str]]:
    return sorted(
        (offset, predicate)
        for predicate in predicates
        for offset in [text.find(predicate)]
        if offset >= 0
    )


def _first(items: List[Tuple[int, str]]) -> Optional[Tuple[int, str]]:
    return items[0] if items else None


def _line(function: Any, item: Optional[Tuple[int, str]]) -> Optional[int]:
    return function.line_for_offset(item[0]) if item else None


def _first_argument(text: str, item: Optional[Tuple[int, str]]) -> Optional[str]:
    if item is None:
        return None
    opening = text.find("(", item[0])
    if opening < 0:
        return None
    comma = text.find(",", opening + 1)
    closing = text.find(")", opening + 1)
    end = comma if comma >= 0 and (closing < 0 or comma < closing) else closing
    if end < 0:
        return None
    return " ".join(text[opening + 1 : end].split())


def analyze_registration_witness(
    binding: OrphanBinding,
    source_path: str,
    function_name: str,
) -> RegistrationWitness:
    source = Path(source_path).read_text(encoding="utf-8")
    function = extract_function(source, function_name)
    text = function.masked_text
    namespace = _first(_primitive_occurrences(text, binding.namespace_transition_primitives))
    link_count = _first(_primitive_occurrences(text, binding.link_count_primitives))
    zero_link = _first(_predicate_occurrences(text, binding.zero_link_predicates))
    registry = _first(_primitive_occurrences(text, binding.registry_insert_primitives))
    settlements = _primitive_occurrences(text, binding.transaction_settlement_primitives)
    settlement = next(
        (item for item in settlements if registry and item[0] > registry[0]),
        None,
    )
    ordered_prefix = bool(
        namespace
        and link_count
        and zero_link
        and registry
        and namespace[0] <= link_count[0] < zero_link[0] < registry[0]
    )
    acceptance_before_settlement = bool(
        registry and settlement and registry[0] < settlement[0]
    )
    return RegistrationWitness(
        source_path=source_path,
        function_name=function_name,
        namespace_transition_found=namespace is not None,
        link_count_transition_found=link_count is not None,
        zero_link_guard_found=zero_link is not None,
        registry_acceptance_found=registry is not None,
        transaction_settlement_found=settlement is not None,
        acceptance_before_settlement=acceptance_before_settlement,
        zero_link_scoped=ordered_prefix,
        registration_safe=ordered_prefix and acceptance_before_settlement,
        evidence_lines={
            "namespace_transition": _line(function, namespace),
            "link_count_transition": _line(function, link_count),
            "zero_link_guard": _line(function, zero_link),
            "registry_acceptance": _line(function, registry),
            "transaction_settlement": _line(function, settlement),
        },
    )


def analyze_settlement_witness(
    binding: OrphanBinding,
    source_path: str,
    function_name: str,
) -> SettlementWitness:
    source = Path(source_path).read_text(encoding="utf-8")
    function = extract_function(source, function_name)
    text = function.masked_text
    terminal = _first(_primitive_occurrences(text, binding.terminal_deletion_primitives))
    removal = _first(
        _persistent_primitive_occurrences(text, binding.registry_remove_primitives)
    )
    settlements = _primitive_occurrences(text, binding.transaction_settlement_primitives)

    prior_settlement = next(
        (
            item
            for item in settlements
            if terminal and removal and terminal[0] < item[0] < removal[0]
        ),
        None,
    )
    deletion_durable_before_removal = bool(
        terminal
        and prior_settlement
        and _first_argument(text, terminal)
        == _first_argument(text, prior_settlement)
    )
    common_settlement = next(
        (
            item
            for item in settlements
            if terminal and removal and item[0] > max(terminal[0], removal[0])
        ),
        None,
    )
    same_transaction_equivalence = bool(
        terminal
        and removal
        and common_settlement
        and _first_argument(text, terminal)
        == _first_argument(text, removal)
        == _first_argument(text, common_settlement)
        and not any(
            min(terminal[0], removal[0]) < item[0] < max(terminal[0], removal[0])
            for item in settlements
        )
    )
    removal_safe = deletion_durable_before_removal or same_transaction_equivalence
    relevant_settlement = common_settlement
    if deletion_durable_before_removal:
        relevant_settlement = prior_settlement
    return SettlementWitness(
        source_path=source_path,
        function_name=function_name,
        terminal_deletion_found=terminal is not None,
        registry_removal_found=removal is not None,
        transaction_settlement_found=relevant_settlement is not None,
        deletion_durable_before_removal=deletion_durable_before_removal,
        same_transaction_equivalence=same_transaction_equivalence,
        removal_safe=removal_safe,
        evidence_lines={
            "terminal_deletion": _line(function, terminal),
            "registry_removal": _line(function, removal),
            "transaction_settlement": _line(function, relevant_settlement),
        },
    )


def analyze_recovery_witness(
    binding: OrphanBinding,
    cleanup_source_path: str,
    cleanup_function_name: str,
    exposure_source_path: str,
    exposure_function_name: str,
) -> RecoveryWitness:
    cleanup_source = Path(cleanup_source_path).read_text(encoding="utf-8")
    cleanup_function = extract_function(cleanup_source, cleanup_function_name)
    cleanup_calls = _primitive_occurrences(
        cleanup_function.masked_text, binding.recovery_primitives
    )
    cleanup_dispatch = _first(cleanup_calls)
    release = next(
        (item for item in cleanup_calls if item[1] in {"iput", "ext4_process_orphan"}),
        None,
    )

    exposure_source = Path(exposure_source_path).read_text(encoding="utf-8")
    exposure_function = extract_function(exposure_source, exposure_function_name)
    exposure_text = exposure_function.masked_text
    entries = _predicate_occurrences(exposure_text, binding.recovery_entry_markers)
    exposures = _predicate_occurrences(
        exposure_text, binding.recovery_exposure_markers
    )
    entry = _first(entries)
    exposure = _first(exposures)
    ordered = bool(entry and exposure and entry[0] < exposure[0])
    closed = bool(cleanup_dispatch and release and ordered)
    return RecoveryWitness(
        cleanup_source_path=cleanup_source_path,
        cleanup_function_name=cleanup_function_name,
        exposure_source_path=exposure_source_path,
        exposure_function_name=exposure_function_name,
        cleanup_dispatch_found=cleanup_dispatch is not None,
        zero_link_release_found=release is not None,
        recovery_entry_found=entry is not None,
        recovery_exposure_found=exposure is not None,
        cleanup_before_exposure=ordered,
        recovery_path_closed=closed,
        evidence_lines={
            "cleanup_dispatch": _line(cleanup_function, cleanup_dispatch),
            "zero_link_release": _line(cleanup_function, release),
            "recovery_entry": _line(exposure_function, entry),
            "recovery_exposure": _line(exposure_function, exposure),
        },
    )
