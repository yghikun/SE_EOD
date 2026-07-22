"""Normalize frontend IR operations into deterministic MOCC-SE events."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from .frontend.model import FunctionIR, SourceRange
from .metadata_protocol import (
    ArgumentNormalization,
    EffectKind,
    EffectTransition,
    MetadataProtocol,
    ObjectRef,
    OperationEntry,
    SummaryBindingSource,
)


class MetadataEventKind(str, Enum):
    METADATA_UPDATE = "METADATA_UPDATE"
    POINTER_UPDATE = "POINTER_UPDATE"
    MEMBERSHIP_ADD = "MEMBERSHIP_ADD"
    MEMBERSHIP_REMOVE = "MEMBERSHIP_REMOVE"
    FLAG_SET = "FLAG_SET"
    FLAG_CLEAR = "FLAG_CLEAR"
    COUNTER_UPDATE = "COUNTER_UPDATE"
    RESERVATION_UPDATE = "RESERVATION_UPDATE"
    COMMIT = "COMMIT"
    COMPENSATE = "COMPENSATE"
    ABORT = "ABORT"
    RECOVERY_DELEGATE = "RECOVERY_DELEGATE"
    DEFER_CLEANUP = "DEFER_CLEANUP"


class ObjectIdentity(str, Enum):
    EXACT = "EXACT"
    NORMALIZED = "NORMALIZED"
    UNKNOWN = "UNKNOWN"


class EventStrength(str, Enum):
    MUST = "must"
    MAY = "may"


@dataclass(frozen=True)
class ResolvedObjectRef:
    role: str
    expression: str
    identity: ObjectIdentity
    symbol_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "expression": self.expression,
            "identity": self.identity.value,
            "symbol_id": self.symbol_id,
        }


@dataclass(frozen=True)
class MetadataEvent:
    event_id: str
    protocol_id: str
    operation_id: str
    kind: MetadataEventKind
    object_ref: ResolvedObjectRef
    container_ref: ResolvedObjectRef | None
    field_or_member: str
    guard: str
    strength: EventStrength
    source_location: SourceRange
    uncertainty_causes: tuple[str, ...] = ()
    callee_role_id: str = ""
    callee: str = ""
    result_symbol: str = ""
    return_contract_ids: tuple[str, ...] = ()
    necessary: bool = False
    effect_spec_id: str = ""
    compensation_spec_id: str = ""
    handler_spec_id: str = ""
    summary_id: str = ""
    effect_transition: EffectTransition | None = None
    target_effect_id: str = ""
    expression: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "protocol_id": self.protocol_id,
            "operation_id": self.operation_id,
            "kind": self.kind.value,
            "object_ref": self.object_ref.to_dict(),
            "container_ref": self.container_ref.to_dict() if self.container_ref else None,
            "field_or_member": self.field_or_member,
            "guard": self.guard,
            "strength": self.strength.value,
            "source_location": self.source_location.to_dict(),
            "uncertainty_causes": list(self.uncertainty_causes),
            "callee_role_id": self.callee_role_id,
            "callee": self.callee,
            "result_symbol": self.result_symbol,
            "return_contract_ids": list(self.return_contract_ids),
            "necessary": self.necessary,
            "effect_spec_id": self.effect_spec_id,
            "compensation_spec_id": self.compensation_spec_id,
            "handler_spec_id": self.handler_spec_id,
            "summary_id": self.summary_id,
            "effect_transition": (
                self.effect_transition.value if self.effect_transition else ""
            ),
            "target_effect_id": self.target_effect_id,
            "expression": self.expression,
        }


_CALL_KIND = {
    "list_add": MetadataEventKind.MEMBERSHIP_ADD,
    "list_add_tail": MetadataEventKind.MEMBERSHIP_ADD,
    "hlist_add_head": MetadataEventKind.MEMBERSHIP_ADD,
    "list_del": MetadataEventKind.MEMBERSHIP_REMOVE,
    "list_del_init": MetadataEventKind.MEMBERSHIP_REMOVE,
    "hlist_del": MetadataEventKind.MEMBERSHIP_REMOVE,
    "set_bit": MetadataEventKind.FLAG_SET,
    "clear_bit": MetadataEventKind.FLAG_CLEAR,
    "atomic_inc": MetadataEventKind.COUNTER_UPDATE,
    "atomic_dec": MetadataEventKind.COUNTER_UPDATE,
    "refcount_inc": MetadataEventKind.COUNTER_UPDATE,
    "refcount_dec": MetadataEventKind.COUNTER_UPDATE,
}


def extract_metadata_events(
    function: FunctionIR,
    protocol: MetadataProtocol,
    *,
    operation_id: str = "",
) -> tuple[MetadataEvent, ...]:
    """Extract events only when the function matches a protocol operation entry."""

    operation = _operation_for_function(
        function.name,
        protocol,
        operation_id=operation_id,
    )
    if operation is None:
        return ()
    events: list[MetadataEvent] = []
    for call in sorted(function.calls, key=lambda item: item.source_range.start_byte):
        role = next(
            (
                candidate
                for candidate in operation.callee_roles
                if call.callee_spelling in candidate.callees
            ),
            None,
        )
        generic_kind = _CALL_KIND.get(call.callee_spelling)
        result_symbol = call.result_spelling or _call_result_symbol(function, call.source_range)
        effect_specs = [
            item
            for item in protocol.effects
            if item.operation_id == operation.operation_id
            and _call_matches(item, call.callee_spelling, result_symbol, call.arguments)
        ]
        compensation_specs = [
            item
            for item in protocol.compensations
            if item.operation_id == operation.operation_id
            and _call_matches(item, call.callee_spelling, result_symbol, call.arguments)
        ]
        effect_spec = effect_specs[0] if effect_specs else None
        compensation_spec = compensation_specs[0] if compensation_specs else None
        handler_spec = next(
            (
                item
                for item in protocol.handlers
                if item.operation_id == operation.operation_id
                and call.callee_spelling in item.match_callees
            ),
            None,
        )
        summary_specs = [
            item
            for item in protocol.callee_summaries
            if item.operation_id == operation.operation_id
            and call.callee_spelling in item.callees
        ]
        if role is None and generic_kind is None and effect_spec is None and compensation_spec is None and handler_spec is None and not summary_specs:
            continue
        uncertainty: list[str] = []
        if call.callee_kind != "direct":
            uncertainty.append("unresolved_indirect_call")
        declared_object = None
        if effect_spec is not None:
            declared_object = effect_spec.object_ref
        elif compensation_spec is not None:
            declared_object = compensation_spec.object_ref
        elif handler_spec is not None:
            declared_object = handler_spec.object_ref
        obj = (
            _resolve_declared_object(function, declared_object)
            if declared_object is not None
            else _resolve_primary_object(function, operation)
        )
        container = None
        if generic_kind is MetadataEventKind.MEMBERSHIP_ADD:
            obj = _resolve_call_argument(function, call.arguments, 0, "member")
            container = _resolve_call_argument(function, call.arguments, 1, "container")
        elif generic_kind is MetadataEventKind.MEMBERSHIP_REMOVE:
            obj = _resolve_call_argument(function, call.arguments, 0, "member")
        elif generic_kind in {
            MetadataEventKind.FLAG_SET,
            MetadataEventKind.FLAG_CLEAR,
            MetadataEventKind.COUNTER_UPDATE,
        }:
            obj = _resolve_call_argument(function, call.arguments, -1, "subject")
        if obj.identity is ObjectIdentity.UNKNOWN:
            uncertainty.append("unknown_object_identity")
        if container is not None and container.identity is ObjectIdentity.UNKNOWN:
            uncertainty.append("unknown_container_identity")
        strength = EventStrength.MUST if not uncertainty else EventStrength.MAY
        if handler_spec is not None:
            kind = {
                "ABORTED": MetadataEventKind.ABORT,
                "RECOVERY_DELEGATED": MetadataEventKind.RECOVERY_DELEGATE,
                "DEFERRED": MetadataEventKind.DEFER_CLEANUP,
            }[handler_spec.completion_mode.value]
        elif compensation_spec is not None:
            kind = MetadataEventKind.COMPENSATE
        elif effect_spec is not None:
            kind = MetadataEventKind(effect_spec.kind.value)
        else:
            kind = generic_kind or MetadataEventKind.METADATA_UPDATE
        matching_specs: list[tuple[object | None, object | None]] = (
            [(item, None) for item in effect_specs]
            + [(None, item) for item in compensation_specs]
        )
        if not matching_specs and (
            role is not None or generic_kind is not None or handler_spec is not None
        ):
            matching_specs = [(None, None)]
        for matched_effect, matched_compensation in matching_specs:
            selected_object = declared_object
            if matched_effect is not None:
                selected_object = matched_effect.object_ref
            elif matched_compensation is not None:
                selected_object = matched_compensation.object_ref
            selected_ref = (
                _resolve_declared_object(function, selected_object)
                if selected_object is not None
                else obj
            )
            selected_kind = kind
            if matched_effect is not None:
                selected_kind = MetadataEventKind(matched_effect.kind.value)
            elif matched_compensation is not None:
                selected_kind = MetadataEventKind.COMPENSATE
            selected_uncertainty = list(uncertainty)
            selected_strength = strength
            if matched_effect is not None and matched_effect.strength == "may":
                selected_strength = EventStrength.MAY
                selected_uncertainty.append("may_effect_summary")
            events.append(MetadataEvent(
                event_id=_event_id(
                    protocol.protocol_id,
                    operation.operation_id,
                    selected_kind.value,
                    call.source_range,
                    call.callee_spelling,
                    getattr(matched_effect, "effect_id", ""),
                    getattr(matched_compensation, "compensation_id", ""),
                ),
                protocol_id=protocol.protocol_id,
                operation_id=operation.operation_id,
                kind=selected_kind,
                object_ref=selected_ref,
                container_ref=container,
                field_or_member="",
                guard=getattr(matched_effect, "guard", "always"),
                strength=selected_strength,
                source_location=call.source_range,
                uncertainty_causes=tuple(selected_uncertainty),
                callee_role_id=role.role_id if role else "",
                callee=call.callee_spelling,
                result_symbol=result_symbol,
                return_contract_ids=role.return_contract_ids if role else (),
                necessary=role.necessary if role else False,
                effect_spec_id=getattr(matched_effect, "effect_id", ""),
                compensation_spec_id=(
                    getattr(matched_compensation, "compensation_id", "")
                ),
                handler_spec_id=handler_spec.handler_id if handler_spec else "",
                expression=call.callee_spelling,
            ))
        for summary in summary_specs:
            summary_object, binding_causes = _resolve_summary_object(
                function,
                call.arguments,
                summary.object_binding.role,
                summary.object_binding.source,
                summary.object_binding.argument_index,
                summary.object_binding.normalization,
                result_symbol,
            )
            summary_causes = list(binding_causes)
            if call.callee_kind != "direct":
                summary_causes.append("summary_requires_direct_call")
            if summary.strength == "may":
                summary_causes.append("may_callee_summary")
            summary_strength = (
                EventStrength.MUST if not summary_causes else EventStrength.MAY
            )
            summary_kind = {
                EffectTransition.OPEN: MetadataEventKind(
                    next(
                        item.kind.value
                        for item in protocol.effects
                        if item.effect_id == summary.target_effect_id
                    )
                ),
                EffectTransition.COMMIT: MetadataEventKind.COMMIT,
                EffectTransition.COMPENSATE: MetadataEventKind.COMPENSATE,
                EffectTransition.TRANSFER: {
                    "ABORTED": MetadataEventKind.ABORT,
                    "RECOVERY_DELEGATED": MetadataEventKind.RECOVERY_DELEGATE,
                    "DEFERRED": MetadataEventKind.DEFER_CLEANUP,
                }[
                    summary.completion_mode.value
                    if summary.completion_mode is not None
                    else "RECOVERY_DELEGATED"
                ],
            }[summary.transition]
            events.append(
                MetadataEvent(
                    event_id=_event_id(
                        protocol.protocol_id,
                        operation.operation_id,
                        summary_kind.value,
                        call.source_range,
                        call.callee_spelling,
                        summary.summary_id,
                    ),
                    protocol_id=protocol.protocol_id,
                    operation_id=operation.operation_id,
                    kind=summary_kind,
                    object_ref=summary_object,
                    container_ref=None,
                    field_or_member="",
                    guard=summary.guard,
                    strength=summary_strength,
                    source_location=call.source_range,
                    uncertainty_causes=tuple(sorted(set(summary_causes))),
                    callee=call.callee_spelling,
                    result_symbol=result_symbol,
                    effect_spec_id=(
                        summary.target_effect_id
                        if summary.transition is EffectTransition.OPEN
                        else ""
                    ),
                    summary_id=summary.summary_id,
                    effect_transition=summary.transition,
                    target_effect_id=summary.target_effect_id,
                    expression=call.callee_spelling,
                )
            )
    events.extend(_assignment_events(function, protocol, operation))
    return tuple(sorted(events, key=lambda item: (item.source_location.start_byte, item.event_id)))


def _assignment_events(
    function: FunctionIR,
    protocol: MetadataProtocol,
    operation: OperationEntry,
) -> list[MetadataEvent]:
    events: list[MetadataEvent] = []
    effect_specs = [item for item in protocol.effects if item.operation_id == operation.operation_id]
    compensation_specs = [item for item in protocol.compensations if item.operation_id == operation.operation_id]
    if function.body_node is None:
        return events
    call_ranges = {
        (call.source_range.start_byte, call.source_range.end_byte) for call in function.calls
    }
    for node in function.body_node.walk():
        if node.type not in {"assignment_expression", "update_expression"}:
            continue
        if any(start <= node.start_byte and node.end_byte <= end for start, end in call_ranges):
            continue
        text = " ".join(node.text.strip().split())
        left = node.child_by_field_name("left")
        lhs = left.text.strip() if left is not None else text.split("=", 1)[0].strip()
        field_match = re.search(r"(?:->|\.)\s*([A-Za-z_]\w*)\s*$", lhs)
        if node.type == "update_expression" or re.search(r"(?:\+\+|--|\+=|-=)", text):
            kind = MetadataEventKind.COUNTER_UPDATE
        elif re.search(r"\b(?:NULL|nullptr)\b|&[A-Za-z_]", text.split("=", 1)[-1]):
            kind = MetadataEventKind.POINTER_UPDATE
        else:
            kind = MetadataEventKind.METADATA_UPDATE
        obj = _resolve_expression_object(function, operation, lhs)
        matched_effects = [item for item in effect_specs if _assignment_matches(item.match_fields, item.match_rhs, field_match.group(1) if field_match else "", text)]
        matched_compensations = [item for item in compensation_specs if _assignment_matches(item.match_fields, item.match_rhs, field_match.group(1) if field_match else "", text)]
        matches: list[tuple[object | None, object | None]] = (
            [(item, None) for item in matched_effects]
            + [(None, item) for item in matched_compensations]
        )
        if not matches:
            matches = [(None, None)]
        location = node.source_range
        for effect_spec, compensation_spec in matches:
            selected_kind = kind
            selected_obj = obj
            if effect_spec is not None:
                selected_kind = MetadataEventKind(effect_spec.kind.value)
                selected_obj = _resolve_declared_object(function, effect_spec.object_ref)
            elif compensation_spec is not None:
                selected_kind = MetadataEventKind.COMPENSATE
                selected_obj = _resolve_declared_object(function, compensation_spec.object_ref)
            uncertainty = () if selected_obj.identity is not ObjectIdentity.UNKNOWN else ("unknown_object_identity",)
            if effect_spec is not None and effect_spec.strength == "may":
                uncertainty = (*uncertainty, "may_effect_summary")
            events.append(MetadataEvent(
                event_id=_event_id(protocol.protocol_id, operation.operation_id, selected_kind.value, location, text, getattr(effect_spec, "effect_id", ""), getattr(compensation_spec, "compensation_id", "")),
                protocol_id=protocol.protocol_id,
                operation_id=operation.operation_id,
                kind=selected_kind,
                object_ref=selected_obj,
                container_ref=None,
                field_or_member=field_match.group(1) if field_match else "",
                guard=getattr(effect_spec, "guard", "always"),
                strength=(EventStrength.MAY if uncertainty else EventStrength.MUST),
                source_location=location,
                uncertainty_causes=uncertainty,
                effect_spec_id=effect_spec.effect_id if effect_spec else "",
                compensation_spec_id=(compensation_spec.compensation_id if compensation_spec else ""),
                expression=text,
            ))
    return events


def _assignment_matches(
    fields: tuple[str, ...], rhs_patterns: tuple[str, ...], field: str, expression: str
) -> bool:
    if fields and field not in fields:
        return False
    if rhs_patterns and not any(pattern in expression for pattern in rhs_patterns):
        return False
    return bool(fields or rhs_patterns)


def _call_matches(spec: object, callee: str, result: str, arguments: tuple[str, ...]) -> bool:
    if callee not in getattr(spec, "match_callees", ()):
        return False
    results = getattr(spec, "match_results", ())
    if results and result not in results:
        return False
    required_arguments = getattr(spec, "match_arguments", ())
    joined = "\x1f".join(arguments)
    if required_arguments and not all(value in joined for value in required_arguments):
        return False
    return True


def _operation_for_function(
    function_name: str,
    protocol: MetadataProtocol,
    *,
    operation_id: str = "",
) -> OperationEntry | None:
    if operation_id:
        return next(
            (
                operation
                for operation in protocol.operations
                if operation.operation_id == operation_id
            ),
            None,
        )
    return next(
        (
            operation
            for operation in protocol.operations
            if function_name in operation.entry_functions
        ),
        None,
    )


def _resolve_primary_object(
    function: FunctionIR, operation: OperationEntry
) -> ResolvedObjectRef:
    if not operation.principal_objects:
        return ResolvedObjectRef("unknown", "", ObjectIdentity.UNKNOWN)
    return _resolve_declared_object(function, operation.principal_objects[0])


def _resolve_expression_object(
    function: FunctionIR, operation: OperationEntry, expression: str
) -> ResolvedObjectRef:
    normalized = " ".join(expression.strip().split())
    for declared in operation.principal_objects:
        resolved = _resolve_declared_object(function, declared)
        selector = resolved.expression
        if selector and re.search(rf"\b{re.escape(selector)}\b", normalized):
            return resolved
    return ResolvedObjectRef("unknown", normalized, ObjectIdentity.UNKNOWN)


def _resolve_declared_object(function: FunctionIR, declared: ObjectRef) -> ResolvedObjectRef:
    selector = declared.selector
    parameters = sorted(
        (item for item in function.symbols if item.kind == "parameter"),
        key=lambda item: item.parameter_index if item.parameter_index is not None else 10**6,
    )
    match = re.fullmatch(r"arg(\d+)", selector)
    if match:
        index = int(match.group(1))
        if index < len(parameters):
            symbol = parameters[index]
            expression = symbol.name
            if declared.field_or_member:
                expression = f"{expression}->{declared.field_or_member}"
            return ResolvedObjectRef(declared.role, expression, ObjectIdentity.EXACT, symbol.symbol_id)
        return ResolvedObjectRef(declared.role, selector, ObjectIdentity.UNKNOWN)
    if selector == "function":
        return ResolvedObjectRef(declared.role, function.name, ObjectIdentity.EXACT, function.function_id)
    symbol = next((item for item in function.symbols if item.name == selector), None)
    if symbol is not None:
        return ResolvedObjectRef(declared.role, selector, ObjectIdentity.EXACT, symbol.symbol_id)
    if selector.startswith("normalized:"):
        return ResolvedObjectRef(
            declared.role, selector.split(":", 1)[1], ObjectIdentity.NORMALIZED
        )
    return ResolvedObjectRef(declared.role, selector, ObjectIdentity.UNKNOWN)


def _resolve_call_argument(
    function: FunctionIR,
    arguments: tuple[str, ...],
    index: int,
    role: str,
) -> ResolvedObjectRef:
    if not arguments or index >= len(arguments) or index < -len(arguments):
        return ResolvedObjectRef(role, "", ObjectIdentity.UNKNOWN)
    expression = " ".join(arguments[index].strip().split())
    root_match = re.search(r"([A-Za-z_]\w*)", expression)
    root = root_match.group(1) if root_match else ""
    symbol = next((item for item in function.symbols if item.name == root), None)
    if symbol is not None:
        return ResolvedObjectRef(role, expression, ObjectIdentity.EXACT, symbol.symbol_id)
    return ResolvedObjectRef(role, expression, ObjectIdentity.UNKNOWN)


def _resolve_summary_object(
    function: FunctionIR,
    arguments: tuple[str, ...],
    role: str,
    source: SummaryBindingSource,
    index: int | None,
    normalization: ArgumentNormalization,
    result_symbol: str,
) -> tuple[ResolvedObjectRef, tuple[str, ...]]:
    if source is SummaryBindingSource.RESULT:
        if not result_symbol:
            return (
                ResolvedObjectRef(role, "", ObjectIdentity.UNKNOWN),
                ("summary_result_not_captured",),
            )
        symbol = next(
            (item for item in function.symbols if item.name == result_symbol), None
        )
        if symbol is None:
            return (
                ResolvedObjectRef(role, result_symbol, ObjectIdentity.UNKNOWN),
                ("summary_object_identity_unknown",),
            )
        return (
            ResolvedObjectRef(
                role, result_symbol, ObjectIdentity.EXACT, symbol.symbol_id
            ),
            (),
        )
    assert index is not None
    if index >= len(arguments):
        return (
            ResolvedObjectRef(role, "", ObjectIdentity.UNKNOWN),
            ("summary_argument_out_of_range",),
        )
    expression = " ".join(arguments[index].strip().split())
    if normalization is ArgumentNormalization.ADDRESS_OF_OUTPUT:
        normalized = _strip_outer_parens(expression)
        if not normalized.startswith("&"):
            return (
                ResolvedObjectRef(role, expression, ObjectIdentity.UNKNOWN),
                ("summary_binding_shape_mismatch",),
            )
        expression = _strip_outer_parens(normalized[1:].strip())
    else:
        expression = _strip_outer_parens(expression)
    root_match = re.fullmatch(r"[A-Za-z_]\w*", expression)
    if root_match is None:
        return (
            ResolvedObjectRef(role, expression, ObjectIdentity.UNKNOWN),
            ("summary_object_identity_unknown",),
        )
    symbol = next((item for item in function.symbols if item.name == expression), None)
    if symbol is None:
        return (
            ResolvedObjectRef(role, expression, ObjectIdentity.UNKNOWN),
            ("summary_object_identity_unknown",),
        )
    return ResolvedObjectRef(role, expression, ObjectIdentity.EXACT, symbol.symbol_id), ()


def _strip_outer_parens(value: str) -> str:
    result = value.strip()
    while result.startswith("(") and result.endswith(")"):
        depth = 0
        encloses_all = True
        for index, char in enumerate(result):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and index != len(result) - 1:
                    encloses_all = False
                    break
        if not encloses_all or depth != 0:
            break
        result = result[1:-1].strip()
    return result


def _call_result_symbol(function: FunctionIR, location: SourceRange) -> str:
    if function.body_node is None:
        return ""
    enclosing = [
        node
        for node in function.body_node.walk()
        if node.start_byte <= location.start_byte
        and location.end_byte <= node.end_byte
        and node.type in {"assignment_expression", "init_declarator"}
    ]
    if not enclosing:
        return ""
    node = min(enclosing, key=lambda item: item.end_byte - item.start_byte)
    left = node.child_by_field_name("left") or node.child_by_field_name("declarator")
    if left is not None:
        match = re.search(r"([A-Za-z_]\w*)\s*$", left.text.strip())
        if match:
            return match.group(1)
    match = re.match(r"\s*([A-Za-z_]\w*)\s*=", node.text)
    return match.group(1) if match else ""


def _event_id(
    protocol_id: str,
    operation_id: str,
    kind: str,
    location: SourceRange,
    *parts: object,
) -> str:
    payload = "\x1f".join(
        str(item)
        for item in (
            protocol_id,
            operation_id,
            kind,
            location.file,
            location.start_byte,
            location.end_byte,
            *parts,
        )
    )
    return "mev_" + hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()[:20]


def events_by_source(events: Iterable[MetadataEvent]) -> dict[int, tuple[MetadataEvent, ...]]:
    grouped: dict[int, list[MetadataEvent]] = {}
    for event in events:
        grouped.setdefault(event.source_location.start_byte, []).append(event)
    return {key: tuple(value) for key, value in grouped.items()}
