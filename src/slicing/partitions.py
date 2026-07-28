"""Exact return-partition matching for residual slicing."""

from __future__ import annotations

import re

from ..failure_points import FailurePoint
from ..function_summary import ErrorExitPartition
from ..metadata_residual import MetadataEffect
from ..parser import call_name_and_args, compact_ws


def _select_exact_error_partition(
    partitions: tuple[ErrorExitPartition, ...],
    point: FailurePoint,
    *,
    exhaustive: bool,
) -> ErrorExitPartition | None:
    """Select one source-proven callee exit, or preserve aggregate MUST semantics."""

    if not exhaustive or not partitions:
        return None
    classifications = tuple(
        _partition_matches_failure_check(partition, point)
        for partition in partitions
    )
    if any(value is None for value in classifications):
        return None
    matches = tuple(
        partition
        for partition, matches in zip(partitions, classifications)
        if matches
    )
    if len(matches) != 1 or not matches[0].complete:
        return None
    return matches[0]


def _partition_matches_failure_check(
    partition: ErrorExitPartition,
    point: FailurePoint,
) -> bool | None:
    constraint = partition.return_constraint
    if constraint in {"IS_ERR", "IS_ERR_OR_NULL", "IS_ERR_VALUE"}:
        if point.check_kind not in {"IS_ERR", "IS_ERR_OR_NULL", "IS_ERR_VALUE"}:
            return None
        return point.error_edge.kind != "false"
    abstract = _abstract_constraint_matches(constraint, point.check_kind)
    if abstract is not None:
        return abstract if point.error_edge.kind != "false" else not abstract
    if constraint.startswith("EXACT:"):
        value = constraint[6:]
    else:
        value = _partition_return_value(partition.return_expression)
    if value is None:
        return None
    check_kind = point.check_kind
    predicate_true = point.error_edge.kind != "false"
    if check_kind == "nonzero":
        result = _constant_not_equal(value, "0")
    elif check_kind.startswith("eq:"):
        result = _constant_equal(value, check_kind[3:])
    elif check_kind.startswith("ne:"):
        equal = _constant_equal(value, check_kind[3:])
        result = None if equal is None else not equal
    elif check_kind in {"<0", "<=0", ">0", ">=0"}:
        result = _constant_order_test(value, check_kind)
    elif check_kind in {"0<", "0<=", "0>", "0>="}:
        reverse = {"0<": ">0", "0<=": ">=0", "0>": "<0", "0>=": "<=0"}
        result = _constant_order_test(value, reverse[check_kind])
    else:
        return None
    if result is None:
        return None
    return result if predicate_true else not result


def _abstract_constraint_matches(
    constraint: str,
    check_kind: str,
) -> bool | None:
    known: dict[str, dict[str, bool]] = {
        "NEGATIVE": {
            "nonzero": True,
            "ne:0": True,
            "eq:0": False,
            "<0": True,
            "<=0": True,
            ">0": False,
            ">=0": False,
        },
        "POSITIVE": {
            "nonzero": True,
            "ne:0": True,
            "eq:0": False,
            "<0": False,
            "<=0": False,
            ">0": True,
            ">=0": True,
        },
        "NONZERO": {
            "nonzero": True,
            "ne:0": True,
            "eq:0": False,
        },
        "NONPOSITIVE": {
            "<=0": True,
            ">0": False,
        },
        "NONNEGATIVE": {
            ">=0": True,
            "<0": False,
        },
    }
    return known.get(constraint, {}).get(check_kind)


def _selected_partition_opens(
    partition: ErrorExitPartition,
) -> tuple[MetadataEffect, ...]:
    """Expose selected branch-local opens only when branch evidence can resolve them."""

    return partition.opens


def _selected_partition_needs_identity_proof(
    partition: ErrorExitPartition,
) -> bool:
    return bool(
        partition.opens
        and not partition.cancels
        and not partition.protects
        and not partition.terminal_actions
    )


def _partition_return_value(expression: str) -> str | None:
    value = compact_ws(expression).strip()
    while value.startswith("(") and value.endswith(")"):
        value = value[1:-1].strip()
    name, args = call_name_and_args(value)
    if name in {"ERR_PTR", "PTR_ERR"} and len(args) == 1:
        value = compact_ws(args[0]).strip("() ")
    if value in {"NULL", "0L", "0UL"}:
        return "0"
    return value if re.fullmatch(r"-?(?:[A-Z_]\w*|\d+)", value) else None


def _constant_equal(left: str, right: str) -> bool | None:
    left_value = _partition_return_value(left)
    right_value = _partition_return_value(right)
    if left_value is None or right_value is None:
        return None
    return left_value == right_value


def _constant_not_equal(left: str, right: str) -> bool | None:
    equal = _constant_equal(left, right)
    return None if equal is None else not equal


def _constant_order_test(value: str, operation: str) -> bool | None:
    numeric = _signed_constant_value(value)
    if numeric is None:
        return None
    return {
        "<0": numeric < 0,
        "<=0": numeric <= 0,
        ">0": numeric > 0,
        ">=0": numeric >= 0,
    }[operation]


def _signed_constant_value(value: str) -> int | None:
    normalized = _partition_return_value(value)
    if normalized is None:
        return None
    if re.fullmatch(r"-\d+", normalized):
        return int(normalized)
    if normalized.isdigit():
        return int(normalized)
    if re.fullmatch(r"-[A-Z_]\w*", normalized):
        return -1
    return None
