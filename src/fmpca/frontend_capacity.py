from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from .frontend import FORBIDDEN_BINDING_KEYS, SourceBindingError, extract_function


@dataclass(frozen=True)
class CapacityBinding:
    raw: Dict[str, Any]
    path: Path

    def __getattr__(self, name: str) -> Any:
        try:
            return self.raw[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


@dataclass(frozen=True)
class CapacitySourceWitness:
    operation_family: str
    eligibility_closed: bool
    aggregate_pair_closed: bool
    same_delta_closed: bool
    membership_coupling_closed: bool
    evidence: List[Dict[str, Any]]

    @property
    def selected_source_path_closed(self) -> bool:
        common = self.eligibility_closed and self.aggregate_pair_closed and self.same_delta_closed
        if self.operation_family == "device-membership-change":
            return common and self.membership_coupling_closed
        return common


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            key in FORBIDDEN_BINDING_KEYS or _contains_forbidden_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def load_capacity_binding(path: str) -> CapacityBinding:
    binding_path = Path(path)
    raw = json.loads(binding_path.read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "binding_id",
        "binding_version",
        "protocol_id",
        "kinds",
        "capacity_fields",
        "eligibility_primitives",
        "membership_mutators",
        "membership_restorers",
        "aggregate_relations",
        "role_kinds",
        "semantic_footprint",
    }
    missing = required - set(raw)
    if missing:
        raise SourceBindingError(f"missing capacity binding keys: {sorted(missing)}")
    if set(raw) != required:
        raise SourceBindingError(f"unknown capacity binding keys: {sorted(set(raw) - required)}")
    if raw["schema_version"] != 1:
        raise SourceBindingError("capacity binding schema_version must be 1")
    if raw["protocol_id"] != "fmpca.writable_device_capacity_contribution":
        raise SourceBindingError("capacity binding has the wrong protocol_id")
    if _contains_forbidden_key(raw):
        raise SourceBindingError("capacity binding contains a case-specific key")
    return CapacityBinding(raw, binding_path)


def _normalize(expression: str) -> str:
    return re.sub(r"\s+", "", expression)


def analyze_capacity_source(
    binding: CapacityBinding,
    source_path: str,
    function_name: str,
) -> CapacitySourceWitness:
    source = Path(source_path).read_text(encoding="utf-8", errors="replace")
    function = extract_function(source, function_name)
    text = function.masked_text
    membership_add = any(
        re.search(r"\b" + re.escape(name) + r"\s*\(", text)
        for name in binding.membership_mutators
    )
    membership_del = any(
        re.search(r"\b" + re.escape(name) + r"\s*\(", text)
        for name in binding.membership_restorers
    )
    resize_formula = all(
        fragment in text
        for fragment in (
            "free_diff",
            "old_size - device->bytes_used",
            "new_size - device->bytes_used",
        )
    )
    if membership_add:
        family = "device-membership-change"
    elif resize_formula:
        family = "device-capacity-resize"
    else:
        family = "unknown-device-capacity-operation"

    writable_evidence = "BTRFS_DEV_STATE_WRITEABLE" in text
    total_updates = re.findall(r"total_rw_bytes\s*([+-])=\s*([^;]+);", text)
    free_updates = re.findall(
        r"atomic64_(add|sub)\s*\(\s*([^,]+),\s*&[^;]*free_chunk_space\s*\)",
        text,
        re.MULTILINE,
    )
    total_directions = {direction for direction, _ in total_updates}
    free_directions = {direction for direction, _ in free_updates}
    aggregate_pair_closed = bool(total_updates and free_updates)
    symmetric_total = total_directions == {"+", "-"}
    symmetric_free = free_directions == {"add", "sub"}
    total_expressions = {_normalize(expr) for _, expr in total_updates}
    free_expressions = {_normalize(expr) for _, expr in free_updates}
    if family == "device-membership-change":
        same_delta_closed = (
            symmetric_total
            and symmetric_free
            and "device->total_bytes" in total_expressions
            and "device->total_bytes" in free_expressions
        )
    else:
        same_delta_closed = (
            symmetric_total
            and symmetric_free
            and "diff" in total_expressions
            and "free_diff" in free_expressions
            and resize_formula
        )
    evidence = [
        {
            "kind": "capacity_operation_family",
            "value": family,
            "function": function.name,
        },
        {
            "kind": "eligibility_state_witness",
            "found": writable_evidence,
            "primitive": "BTRFS_DEV_STATE_WRITEABLE",
        },
        {
            "kind": "aggregate_update_pair",
            "found": aggregate_pair_closed,
            "total_rw_updates": len(total_updates),
            "free_chunk_updates": len(free_updates),
        },
        {
            "kind": "same_delta_restore",
            "found": same_delta_closed,
            "total_expressions": sorted(total_expressions),
            "free_expressions": sorted(free_expressions),
        },
        {
            "kind": "membership_capacity_coupling",
            "found": membership_add and membership_del,
            "membership_add": membership_add,
            "membership_restore": membership_del,
        },
    ]
    return CapacitySourceWitness(
        operation_family=family,
        eligibility_closed=writable_evidence,
        aggregate_pair_closed=aggregate_pair_closed,
        same_delta_closed=same_delta_closed,
        membership_coupling_closed=membership_add and membership_del,
        evidence=evidence,
    )
