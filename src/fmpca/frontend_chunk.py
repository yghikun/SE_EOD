from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .frontend import FORBIDDEN_BINDING_KEYS, SourceBindingError, extract_function


@dataclass(frozen=True)
class ChunkReservationBinding:
    raw: Dict[str, Any]
    path: Path

    def __getattr__(self, name: str) -> Any:
        try:
            return self.raw[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


@dataclass(frozen=True)
class ChunkReservationSourceWitness:
    operation_family: str
    selected_bug_path_closed: bool
    chunk_publication_found: bool
    activation_call_found: bool
    positive_success_possible: bool
    success_result_reused_as_reservation_guard: bool
    success_result_normalized_before_guard: bool
    reservation_call_found: bool
    reservation_accounting_found: bool
    evidence: List[Dict[str, Any]]

    @property
    def source_semantic_footprint_closed(self) -> bool:
        return (
            self.chunk_publication_found
            and self.activation_call_found
            and self.reservation_call_found
            and self.reservation_accounting_found
        )


@dataclass(frozen=True)
class ChunkReleaseSourceWitness:
    operation_family: str
    selected_release_path_closed: bool
    guarded_by_reserved_bytes: bool
    release_call_found: bool
    reserved_bytes_zeroed: bool
    evidence: List[Dict[str, Any]]


@dataclass(frozen=True)
class ChunkUpdateSourceWitness:
    operation_family: str
    selected_update_path_closed: bool
    reservation_wrapper_found: bool
    metadata_update_found: bool
    release_wrapper_found: bool
    order_closed: bool
    evidence: List[Dict[str, Any]]


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            key in FORBIDDEN_BINDING_KEYS or _contains_forbidden_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def load_chunk_binding(path: str) -> ChunkReservationBinding:
    binding_path = Path(path)
    raw = json.loads(binding_path.read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "binding_id",
        "binding_version",
        "protocol_id",
        "kinds",
        "role_kinds",
        "semantic_footprint",
        "chunk_publication_primitives",
        "reservation_primitives",
        "metadata_reservation_primitives",
        "reservation_accounting_fields",
        "release_primitives",
        "transaction_release_primitives",
        "chunk_update_primitives",
        "positive_success_primitives",
        "negative_error_guards",
        "reservation_success_guards",
    }
    missing = required - set(raw)
    if missing:
        raise SourceBindingError(f"missing chunk binding keys: {sorted(missing)}")
    extra = set(raw) - required
    if extra:
        raise SourceBindingError(f"unknown chunk binding keys: {sorted(extra)}")
    if raw["schema_version"] != 1:
        raise SourceBindingError("chunk binding schema_version must be 1")
    if raw["protocol_id"] != "fmpca.chunk_metadata_reservation_completion":
        raise SourceBindingError("chunk binding has the wrong protocol_id")
    if _contains_forbidden_key(raw):
        raise SourceBindingError("chunk binding contains a case-specific key")
    return ChunkReservationBinding(raw, binding_path)


def _call_found(text: str, names: List[str]) -> bool:
    return any(
        re.search(r"\b" + re.escape(name) + r"\s*\(", text)
        for name in names
    )


def _call_offsets(text: str, names: List[str]) -> List[Dict[str, Any]]:
    offsets: List[Dict[str, Any]] = []
    for name in names:
        pattern = re.compile(r"\b" + re.escape(name) + r"\s*\(", re.MULTILINE)
        for match in pattern.finditer(text):
            offsets.append({"name": name, "offset": match.start()})
    return sorted(offsets, key=lambda item: item["offset"])


def _assignment_to_call(text: str, names: List[str]) -> Optional[re.Match[str]]:
    calls = "|".join(re.escape(name) for name in names)
    if not calls:
        return None
    return re.search(
        r"\b(?P<var>[A-Za-z_]\w*)\s*=\s*(?P<call>" + calls + r")\s*\(",
        text,
        re.MULTILINE,
    )


def _positive_success_possible(source_path: str, function_name: str) -> Dict[str, Any]:
    source = Path(source_path).read_text(encoding="utf-8", errors="replace")
    function = extract_function(source, function_name)
    one = re.search(r"\breturn\s+1\s*;", function.masked_text)
    zero = re.search(r"\breturn\s+0\s*;", function.masked_text)
    return {
        "found": bool(one and zero),
        "function": function.name,
        "return_one_line": function.line_for_offset(one.start()) if one else None,
        "return_zero_line": function.line_for_offset(zero.start()) if zero else None,
    }


def analyze_chunk_reservation_source(
    binding: ChunkReservationBinding,
    source_path: str,
    function_name: str,
    *,
    positive_success_source: Optional[str] = None,
    positive_success_function: Optional[str] = None,
) -> ChunkReservationSourceWitness:
    source = Path(source_path).read_text(encoding="utf-8", errors="replace")
    function = extract_function(source, function_name)
    text = function.masked_text

    publication = _call_found(text, list(binding.chunk_publication_primitives))
    reservation_call = _call_found(text, list(binding.reservation_primitives))
    accounting = all(field in text for field in binding.reservation_accounting_fields)
    activation = _assignment_to_call(text, list(binding.positive_success_primitives))

    positive = {"found": False, "function": positive_success_function}
    if positive_success_source and positive_success_function:
        positive = _positive_success_possible(
            positive_success_source,
            positive_success_function,
        )

    reused_guard = False
    normalized = False
    activation_line = None
    reservation_guard_line = None
    if activation:
        var = activation.group("var")
        activation_line = function.line_for_offset(activation.start())
        tail = text[activation.end() :]
        negative_guard = re.search(
            r"if\s*\(\s*" + re.escape(var) + r"\s*<\s*0\s*\)\s*return\s*;",
            tail,
            re.MULTILINE,
        )
        guard_pattern = "|".join(
            re.escape(guard).replace(r"\$ret", re.escape(var))
            for guard in binding.reservation_success_guards
        )
        reservation_guard = re.search(
            r"if\s*\(\s*(?:" + guard_pattern + r")\s*\)\s*\{(?P<body>.*?)"
            + r"\b(?:" + "|".join(re.escape(name) for name in binding.reservation_primitives) + r")\s*\(",
            tail,
            re.MULTILINE | re.DOTALL,
        )
        if reservation_guard:
            reservation_guard_line = function.line_for_offset(
                activation.end() + reservation_guard.start()
            )
            between = tail[: reservation_guard.start()]
            normalized = bool(re.search(r"\b" + re.escape(var) + r"\s*=\s*0\s*;", between))
            reused_guard = bool(negative_guard and not normalized)

    selected_bug_path_closed = bool(
        publication
        and activation
        and positive["found"]
        and reused_guard
        and reservation_call
        and accounting
    )
    evidence = [
        {
            "kind": "operation_family",
            "value": "btrfs-chunk-metadata-reservation",
            "function": function.name,
        },
        {
            "kind": "chunk_publication",
            "found": publication,
            "primitives": list(binding.chunk_publication_primitives),
        },
        {
            "kind": "positive_success_activation_call",
            "found": bool(activation),
            "line": activation_line,
            "primitives": list(binding.positive_success_primitives),
        },
        {
            "kind": "positive_success_possible",
            **positive,
        },
        {
            "kind": "reservation_guard_reuses_positive_success",
            "found": reused_guard,
            "success_result_normalized_before_guard": normalized,
            "line": reservation_guard_line,
            "guards": list(binding.reservation_success_guards),
        },
        {
            "kind": "chunk_block_reservation",
            "found": reservation_call,
            "primitives": list(binding.reservation_primitives),
        },
        {
            "kind": "transaction_reservation_accounting",
            "found": accounting,
            "fields": list(binding.reservation_accounting_fields),
        },
    ]
    return ChunkReservationSourceWitness(
        operation_family="btrfs-chunk-metadata-reservation",
        selected_bug_path_closed=selected_bug_path_closed,
        chunk_publication_found=publication,
        activation_call_found=bool(activation),
        positive_success_possible=bool(positive["found"]),
        success_result_reused_as_reservation_guard=reused_guard,
        success_result_normalized_before_guard=normalized,
        reservation_call_found=reservation_call,
        reservation_accounting_found=accounting,
        evidence=evidence,
    )


def analyze_chunk_release_source(
    binding: ChunkReservationBinding,
    source_path: str,
    function_name: str,
) -> ChunkReleaseSourceWitness:
    source = Path(source_path).read_text(encoding="utf-8", errors="replace")
    function = extract_function(source, function_name)
    text = function.masked_text
    guarded = bool(re.search(r"if\s*\(\s*!\s*trans->chunk_bytes_reserved\s*\)\s*return\s*;", text))
    release_call = _call_found(text, list(binding.release_primitives))
    zeroed = bool(re.search(r"\btrans->chunk_bytes_reserved\s*=\s*0\s*;", text))
    selected = guarded and release_call and zeroed
    evidence = [
        {
            "kind": "reserved_bytes_guard",
            "found": guarded,
            "field": "trans->chunk_bytes_reserved",
        },
        {
            "kind": "chunk_metadata_release",
            "found": release_call,
            "primitives": list(binding.release_primitives),
        },
        {
            "kind": "reservation_counter_zeroed",
            "found": zeroed,
            "field": "trans->chunk_bytes_reserved",
        },
    ]
    return ChunkReleaseSourceWitness(
        operation_family="btrfs-chunk-metadata-reservation-release",
        selected_release_path_closed=selected,
        guarded_by_reserved_bytes=guarded,
        release_call_found=release_call,
        reserved_bytes_zeroed=zeroed,
        evidence=evidence,
    )


def analyze_chunk_update_source(
    binding: ChunkReservationBinding,
    source_path: str,
    function_name: str,
    *,
    operation_family: str,
) -> ChunkUpdateSourceWitness:
    source = Path(source_path).read_text(encoding="utf-8", errors="replace")
    function = extract_function(source, function_name)
    text = function.masked_text

    reservations = _call_offsets(text, list(binding.metadata_reservation_primitives))
    updates = _call_offsets(text, list(binding.chunk_update_primitives))
    releases = _call_offsets(text, list(binding.transaction_release_primitives))

    order_closed = False
    ordered_triple: Optional[Dict[str, Any]] = None
    for reservation in reservations:
        for update in updates:
            if update["offset"] <= reservation["offset"]:
                continue
            for release in releases:
                if release["offset"] <= update["offset"]:
                    continue
                order_closed = True
                ordered_triple = {
                    "reservation": {
                        **reservation,
                        "line": function.line_for_offset(reservation["offset"]),
                    },
                    "metadata_update": {
                        **update,
                        "line": function.line_for_offset(update["offset"]),
                    },
                    "release": {
                        **release,
                        "line": function.line_for_offset(release["offset"]),
                    },
                }
                break
            if order_closed:
                break
        if order_closed:
            break

    selected = bool(reservations and updates and releases and order_closed)
    evidence = [
        {
            "kind": "operation_family",
            "value": operation_family,
            "function": function.name,
        },
        {
            "kind": "metadata_reservation_wrapper",
            "found": bool(reservations),
            "primitives": list(binding.metadata_reservation_primitives),
            "lines": [
                function.line_for_offset(item["offset"])
                for item in reservations
            ],
        },
        {
            "kind": "chunk_tree_metadata_update",
            "found": bool(updates),
            "primitives": list(binding.chunk_update_primitives),
            "lines": [
                function.line_for_offset(item["offset"])
                for item in updates
            ],
        },
        {
            "kind": "transaction_chunk_metadata_release",
            "found": bool(releases),
            "primitives": list(binding.transaction_release_primitives),
            "lines": [
                function.line_for_offset(item["offset"])
                for item in releases
            ],
        },
        {
            "kind": "reservation_update_release_order",
            "found": order_closed,
            "ordered_triple": ordered_triple,
        },
    ]
    return ChunkUpdateSourceWitness(
        operation_family=operation_family,
        selected_update_path_closed=selected,
        reservation_wrapper_found=bool(reservations),
        metadata_update_found=bool(updates),
        release_wrapper_found=bool(releases),
        order_closed=order_closed,
        evidence=evidence,
    )
