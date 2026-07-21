"""Versioned, serializable metadata protocol definitions for MOCC-SE."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Type, TypeVar


METADATA_PROTOCOL_SCHEMA_VERSION = 1


class EffectKind(str, Enum):
    METADATA_UPDATE = "METADATA_UPDATE"
    POINTER_UPDATE = "POINTER_UPDATE"
    MEMBERSHIP_ADD = "MEMBERSHIP_ADD"
    MEMBERSHIP_REMOVE = "MEMBERSHIP_REMOVE"
    FLAG_SET = "FLAG_SET"
    FLAG_CLEAR = "FLAG_CLEAR"
    COUNTER_UPDATE = "COUNTER_UPDATE"
    RESERVATION_UPDATE = "RESERVATION_UPDATE"


class EffectScope(str, Enum):
    LOCAL = "LOCAL"
    IN_MEMORY_GLOBAL = "IN_MEMORY_GLOBAL"
    TRANSACTION_SCOPED = "TRANSACTION_SCOPED"
    PERSISTENT = "PERSISTENT"
    RECOVERY_OWNED = "RECOVERY_OWNED"
    DEFERRED_OWNED = "DEFERRED_OWNED"


class EffectStatus(str, Enum):
    OPEN = "OPEN"
    COMPENSATED = "COMPENSATED"
    TRANSFERRED = "TRANSFERRED"
    COMMITTED = "COMMITTED"
    UNKNOWN = "UNKNOWN"


class CompletionMode(str, Enum):
    COMMITTED = "COMMITTED"
    ROLLED_BACK = "ROLLED_BACK"
    ABORTED = "ABORTED"
    RECOVERY_DELEGATED = "RECOVERY_DELEGATED"
    DEFERRED = "DEFERRED"
    PARTIAL_UNRESOLVED = "PARTIAL_UNRESOLVED"
    ANALYSIS_UNKNOWN = "ANALYSIS_UNKNOWN"


class ReturnOutcome(str, Enum):
    FAILURE = "failure"
    SUCCESS = "success"
    SUCCESS_NO_CHANGE = "success_no_change"
    SUCCESS_CHANGED = "success_changed"
    RETRYABLE_FAILURE = "retryable_failure"
    EXPECTED_SENTINEL = "expected_sentinel"


class ViolationType(str, Enum):
    FAILURE_REPORTED_AS_SUCCESS = "failure_reported_as_success"
    INCOMPLETE_FAILURE_COMPLETION = "incomplete_failure_completion"
    METADATA_STATE_DIVERGENCE = "metadata_state_divergence"


class LegalExitKind(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"


class MetadataProtocolValidationError(ValueError):
    """A schema or cross-reference error with a precise configuration path."""

    def __init__(self, path: str, message: str) -> None:
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


@dataclass(frozen=True)
class ObjectRef:
    role: str
    selector: str
    container_role: str = ""
    field_or_member: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], path: str = "object") -> "ObjectRef":
        value = _mapping(data, path)
        _known_keys(value, {"role", "selector", "container_role", "field_or_member"}, path)
        return cls(
            role=_identifier(value, "role", path),
            selector=_text(value, "selector", path),
            container_role=_optional_identifier(value, "container_role", path),
            field_or_member=_optional_text(value, "field_or_member", path),
        )

    def to_dict(self) -> dict[str, Any]:
        data = {"role": self.role, "selector": self.selector}
        if self.container_role:
            data["container_role"] = self.container_role
        if self.field_or_member:
            data["field_or_member"] = self.field_or_member
        return data


@dataclass(frozen=True)
class CalleeRoleSpec:
    role_id: str
    callees: tuple[str, ...]
    necessary: bool = True
    return_contract_ids: tuple[str, ...] = ()

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], path: str = "callee_role"
    ) -> "CalleeRoleSpec":
        value = _mapping(data, path)
        _known_keys(
            value,
            {"role_id", "callees", "necessary", "return_contract_ids"},
            path,
        )
        return cls(
            role_id=_identifier(value, "role_id", path),
            callees=_string_tuple(value, "callees", path, nonempty=True),
            necessary=_boolean(value, "necessary", path, default=True),
            return_contract_ids=_string_tuple(value, "return_contract_ids", path),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "role_id": self.role_id,
            "callees": list(self.callees),
            "necessary": self.necessary,
            "return_contract_ids": list(self.return_contract_ids),
        }


@dataclass(frozen=True)
class OperationEntry:
    operation_id: str
    entry_functions: tuple[str, ...]
    principal_objects: tuple[ObjectRef, ...]
    callee_roles: tuple[CalleeRoleSpec, ...] = ()

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], path: str = "operation"
    ) -> "OperationEntry":
        value = _mapping(data, path)
        _known_keys(
            value,
            {"operation_id", "entry_functions", "principal_objects", "callee_roles"},
            path,
        )
        objects = _object_list(value, "principal_objects", path, ObjectRef.from_dict)
        roles = _object_list(value, "callee_roles", path, CalleeRoleSpec.from_dict)
        _unique((item.role for item in objects), f"{path}.principal_objects", "role")
        _unique((item.role_id for item in roles), f"{path}.callee_roles", "role_id")
        return cls(
            operation_id=_identifier(value, "operation_id", path),
            entry_functions=_string_tuple(value, "entry_functions", path, nonempty=True),
            principal_objects=objects,
            callee_roles=roles,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "entry_functions": list(self.entry_functions),
            "principal_objects": [item.to_dict() for item in self.principal_objects],
            "callee_roles": [item.to_dict() for item in self.callee_roles],
        }


@dataclass(frozen=True)
class ReturnContract:
    contract_id: str
    operation_id: str
    guard: str
    outcome: ReturnOutcome
    priority: int | None = None

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], path: str = "return_contract"
    ) -> "ReturnContract":
        value = _mapping(data, path)
        _known_keys(
            value,
            {"contract_id", "operation_id", "guard", "outcome", "priority"},
            path,
        )
        priority = value.get("priority")
        if priority is not None and (isinstance(priority, bool) or not isinstance(priority, int)):
            raise MetadataProtocolValidationError(f"{path}.priority", "expected an integer or null")
        return cls(
            contract_id=_identifier(value, "contract_id", path),
            operation_id=_identifier(value, "operation_id", path),
            guard=_text(value, "guard", path),
            outcome=_enum(value, "outcome", path, ReturnOutcome),
            priority=priority,
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "contract_id": self.contract_id,
            "operation_id": self.operation_id,
            "guard": self.guard,
            "outcome": self.outcome.value,
        }
        if self.priority is not None:
            data["priority"] = self.priority
        return data


@dataclass(frozen=True)
class EffectSpec:
    event_id: str
    effect_id: str
    operation_id: str
    kind: EffectKind
    object_ref: ObjectRef
    scope: EffectScope
    owner: str
    phase: str
    required: bool = True
    description: str = ""
    match_callees: tuple[str, ...] = ()
    match_fields: tuple[str, ...] = ()
    match_rhs: tuple[str, ...] = ()
    match_results: tuple[str, ...] = ()
    match_arguments: tuple[str, ...] = ()
    strength: str = "must"
    guard: str = "always"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], path: str = "effect") -> "EffectSpec":
        value = _mapping(data, path)
        _known_keys(
            value,
            {
                "event_id", "effect_id", "operation_id", "kind", "object",
                "scope", "owner", "phase", "required", "description", "match_callees", "match_fields", "match_rhs", "match_results", "match_arguments", "strength", "guard",
            },
            path,
        )
        return cls(
            event_id=_identifier(value, "event_id", path),
            effect_id=_identifier(value, "effect_id", path),
            operation_id=_identifier(value, "operation_id", path),
            kind=_enum(value, "kind", path, EffectKind),
            object_ref=ObjectRef.from_dict(_required(value, "object", path), f"{path}.object"),
            scope=_enum(value, "scope", path, EffectScope),
            owner=_identifier(value, "owner", path),
            phase=_identifier(value, "phase", path),
            required=_boolean(value, "required", path, default=True),
            description=_optional_text(value, "description", path),
            match_callees=_string_tuple(value, "match_callees", path, optional=True),
            match_fields=_string_tuple(value, "match_fields", path, optional=True),
            match_rhs=_string_tuple(value, "match_rhs", path, optional=True),
            match_results=_string_tuple(value, "match_results", path, optional=True),
            match_arguments=_string_tuple(value, "match_arguments", path, optional=True),
            strength=_strength(value, path),
            guard=_optional_text(value, "guard", path) or "always",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "effect_id": self.effect_id,
            "operation_id": self.operation_id,
            "kind": self.kind.value,
            "object": self.object_ref.to_dict(),
            "scope": self.scope.value,
            "owner": self.owner,
            "phase": self.phase,
            "required": self.required,
            "description": self.description,
            "match_callees": list(self.match_callees),
            "match_fields": list(self.match_fields),
            "match_rhs": list(self.match_rhs),
            "match_results": list(self.match_results),
            "match_arguments": list(self.match_arguments),
            "strength": self.strength,
            "guard": self.guard,
        }


@dataclass(frozen=True)
class CompensationSpec:
    event_id: str
    compensation_id: str
    operation_id: str
    target_effect_id: str
    object_ref: ObjectRef
    guard: str
    phase: str
    match_callees: tuple[str, ...] = ()
    match_fields: tuple[str, ...] = ()
    match_rhs: tuple[str, ...] = ()
    match_results: tuple[str, ...] = ()
    match_arguments: tuple[str, ...] = ()

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], path: str = "compensation"
    ) -> "CompensationSpec":
        value = _mapping(data, path)
        _known_keys(
            value,
            {
                "event_id", "compensation_id", "operation_id", "target_effect_id",
                "object", "guard", "phase", "match_callees", "match_fields", "match_rhs", "match_results", "match_arguments",
            },
            path,
        )
        return cls(
            event_id=_identifier(value, "event_id", path),
            compensation_id=_identifier(value, "compensation_id", path),
            operation_id=_identifier(value, "operation_id", path),
            target_effect_id=_identifier(value, "target_effect_id", path),
            object_ref=ObjectRef.from_dict(_required(value, "object", path), f"{path}.object"),
            guard=_text(value, "guard", path),
            phase=_identifier(value, "phase", path),
            match_callees=_string_tuple(value, "match_callees", path, optional=True),
            match_fields=_string_tuple(value, "match_fields", path, optional=True),
            match_rhs=_string_tuple(value, "match_rhs", path, optional=True),
            match_results=_string_tuple(value, "match_results", path, optional=True),
            match_arguments=_string_tuple(value, "match_arguments", path, optional=True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "compensation_id": self.compensation_id,
            "operation_id": self.operation_id,
            "target_effect_id": self.target_effect_id,
            "object": self.object_ref.to_dict(),
            "guard": self.guard,
            "phase": self.phase,
            "match_callees": list(self.match_callees),
            "match_fields": list(self.match_fields),
            "match_rhs": list(self.match_rhs),
            "match_results": list(self.match_results),
            "match_arguments": list(self.match_arguments),
        }


@dataclass(frozen=True)
class HandlerSpec:
    event_id: str
    handler_id: str
    operation_id: str
    completion_mode: CompletionMode
    object_ref: ObjectRef
    owner: str
    guard: str
    handles_effect_ids: tuple[str, ...]
    match_callees: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], path: str = "handler") -> "HandlerSpec":
        value = _mapping(data, path)
        _known_keys(
            value,
            {
                "event_id", "handler_id", "operation_id", "completion_mode",
                "object", "owner", "guard", "handles_effect_ids", "match_callees",
            },
            path,
        )
        return cls(
            event_id=_identifier(value, "event_id", path),
            handler_id=_identifier(value, "handler_id", path),
            operation_id=_identifier(value, "operation_id", path),
            completion_mode=_enum(value, "completion_mode", path, CompletionMode),
            object_ref=ObjectRef.from_dict(_required(value, "object", path), f"{path}.object"),
            owner=_identifier(value, "owner", path),
            guard=_text(value, "guard", path),
            handles_effect_ids=_string_tuple(value, "handles_effect_ids", path, nonempty=True),
            match_callees=_string_tuple(value, "match_callees", path, optional=True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "handler_id": self.handler_id,
            "operation_id": self.operation_id,
            "completion_mode": self.completion_mode.value,
            "object": self.object_ref.to_dict(),
            "owner": self.owner,
            "guard": self.guard,
            "handles_effect_ids": list(self.handles_effect_ids),
            "match_callees": list(self.match_callees),
        }


@dataclass(frozen=True)
class AccountingConstraint:
    constraint_id: str
    operation_id: str
    subject: ObjectRef
    expression: str
    phases: tuple[str, ...]
    description: str = ""
    kind: str = "reservation"
    trigger_effect_ids: tuple[str, ...] = ()
    satisfying_effect_ids: tuple[str, ...] = ()

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], path: str = "accounting_constraint"
    ) -> "AccountingConstraint":
        value = _mapping(data, path)
        _known_keys(
            value,
            {
                "constraint_id", "operation_id", "subject", "expression", "phases",
                "description", "kind", "trigger_effect_ids", "satisfying_effect_ids",
            },
            path,
        )
        return cls(
            constraint_id=_identifier(value, "constraint_id", path),
            operation_id=_identifier(value, "operation_id", path),
            subject=ObjectRef.from_dict(_required(value, "subject", path), f"{path}.subject"),
            expression=_text(value, "expression", path),
            phases=_string_tuple(value, "phases", path, nonempty=True),
            description=_optional_text(value, "description", path),
            kind=_identifier(value, "kind", path) if "kind" in value else "reservation",
            trigger_effect_ids=_string_tuple(value, "trigger_effect_ids", path, optional=True),
            satisfying_effect_ids=_string_tuple(value, "satisfying_effect_ids", path, optional=True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "constraint_id": self.constraint_id,
            "operation_id": self.operation_id,
            "subject": self.subject.to_dict(),
            "expression": self.expression,
            "phases": list(self.phases),
            "description": self.description,
            "kind": self.kind,
            "trigger_effect_ids": list(self.trigger_effect_ids),
            "satisfying_effect_ids": list(self.satisfying_effect_ids),
        }


@dataclass(frozen=True)
class LegalExitSpec:
    exit_id: str
    operation_id: str
    kind: LegalExitKind
    phases: tuple[str, ...]
    completion_modes: tuple[CompletionMode, ...]
    return_outcomes: tuple[ReturnOutcome, ...]

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], path: str = "legal_exit"
    ) -> "LegalExitSpec":
        value = _mapping(data, path)
        _known_keys(
            value,
            {"exit_id", "operation_id", "kind", "phases", "completion_modes", "return_outcomes"},
            path,
        )
        return cls(
            exit_id=_identifier(value, "exit_id", path),
            operation_id=_identifier(value, "operation_id", path),
            kind=_enum(value, "kind", path, LegalExitKind),
            phases=_string_tuple(value, "phases", path, nonempty=True),
            completion_modes=_enum_tuple(value, "completion_modes", path, CompletionMode),
            return_outcomes=_enum_tuple(value, "return_outcomes", path, ReturnOutcome),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "exit_id": self.exit_id,
            "operation_id": self.operation_id,
            "kind": self.kind.value,
            "phases": list(self.phases),
            "completion_modes": [item.value for item in self.completion_modes],
            "return_outcomes": [item.value for item in self.return_outcomes],
        }


@dataclass(frozen=True)
class MetadataProtocol:
    schema_version: int
    protocol_version: str
    protocol_id: str
    filesystems: tuple[str, ...]
    linux_versions: tuple[str, ...]
    phases: tuple[str, ...]
    operations: tuple[OperationEntry, ...]
    return_contracts: tuple[ReturnContract, ...]
    effects: tuple[EffectSpec, ...]
    compensations: tuple[CompensationSpec, ...]
    handlers: tuple[HandlerSpec, ...]
    accounting_constraints: tuple[AccountingConstraint, ...]
    legal_exits: tuple[LegalExitSpec, ...]
    description: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MetadataProtocol":
        value = _mapping(data, "protocol")
        _known_keys(
            value,
            {
                "schema_version", "protocol_version", "protocol_id", "filesystems",
                "linux_versions", "phases", "operations", "return_contracts",
                "effects", "compensations", "handlers", "accounting_constraints",
                "legal_exits", "description",
            },
            "protocol",
        )
        schema_version = _integer(value, "schema_version", "protocol")
        if schema_version != METADATA_PROTOCOL_SCHEMA_VERSION:
            raise MetadataProtocolValidationError(
                "protocol.schema_version",
                f"unsupported metadata protocol schema version {schema_version}; "
                f"expected {METADATA_PROTOCOL_SCHEMA_VERSION}",
            )
        protocol_version = _text(value, "protocol_version", "protocol")
        if not _SEMVER.fullmatch(protocol_version):
            raise MetadataProtocolValidationError(
                "protocol.protocol_version",
                "expected semantic version MAJOR.MINOR.PATCH",
            )
        protocol = cls(
            schema_version=schema_version,
            protocol_version=protocol_version,
            protocol_id=_identifier(value, "protocol_id", "protocol"),
            filesystems=_string_tuple(value, "filesystems", "protocol", nonempty=True),
            linux_versions=_string_tuple(value, "linux_versions", "protocol", nonempty=True),
            phases=_string_tuple(value, "phases", "protocol", nonempty=True),
            operations=_object_list(value, "operations", "protocol", OperationEntry.from_dict, nonempty=True),
            return_contracts=_object_list(value, "return_contracts", "protocol", ReturnContract.from_dict, nonempty=True),
            effects=_object_list(value, "effects", "protocol", EffectSpec.from_dict),
            compensations=_object_list(value, "compensations", "protocol", CompensationSpec.from_dict),
            handlers=_object_list(value, "handlers", "protocol", HandlerSpec.from_dict),
            accounting_constraints=_object_list(
                value, "accounting_constraints", "protocol", AccountingConstraint.from_dict
            ),
            legal_exits=_object_list(value, "legal_exits", "protocol", LegalExitSpec.from_dict, nonempty=True),
            description=_optional_text(value, "description", "protocol"),
        )
        protocol.validate()
        return protocol

    @classmethod
    def from_json(cls, payload: str) -> "MetadataProtocol":
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise MetadataProtocolValidationError(
                "protocol", f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc
        return cls.from_dict(data)

    @classmethod
    def read_json(cls, path: str | Path) -> "MetadataProtocol":
        source = Path(path)
        try:
            payload = source.read_text(encoding="utf-8")
        except OSError as exc:
            raise MetadataProtocolValidationError(str(source), f"cannot read protocol: {exc}") from exc
        try:
            return cls.from_json(payload)
        except MetadataProtocolValidationError as exc:
            raise MetadataProtocolValidationError(str(source), str(exc)) from exc

    def validate(self) -> None:
        _unique(self.phases, "protocol.phases", "phase")
        _unique((item.operation_id for item in self.operations), "protocol.operations", "operation_id")
        _unique((item.contract_id for item in self.return_contracts), "protocol.return_contracts", "contract_id")
        _unique((item.effect_id for item in self.effects), "protocol.effects", "effect_id")
        _unique((item.compensation_id for item in self.compensations), "protocol.compensations", "compensation_id")
        _unique((item.handler_id for item in self.handlers), "protocol.handlers", "handler_id")
        _unique((item.constraint_id for item in self.accounting_constraints), "protocol.accounting_constraints", "constraint_id")
        _unique((item.exit_id for item in self.legal_exits), "protocol.legal_exits", "exit_id")
        _unique(
            (item.event_id for item in (*self.effects, *self.compensations, *self.handlers)),
            "protocol.events",
            "event_id",
        )

        operations = {item.operation_id: item for item in self.operations}
        phases = set(self.phases)
        effects = {item.effect_id: item for item in self.effects}
        contracts = {item.contract_id: item for item in self.return_contracts}

        referenced = [
            *self.return_contracts,
            *self.effects,
            *self.compensations,
            *self.handlers,
            *self.accounting_constraints,
            *self.legal_exits,
        ]
        for item in referenced:
            if item.operation_id not in operations:
                raise MetadataProtocolValidationError(
                    f"protocol.{type(item).__name__}.{item.operation_id}",
                    f"references undefined operation {item.operation_id!r}",
                )

        for operation in self.operations:
            known_roles = {item.role for item in operation.principal_objects}
            for obj in operation.principal_objects:
                if obj.container_role and obj.container_role not in known_roles:
                    raise MetadataProtocolValidationError(
                        f"protocol.operations.{operation.operation_id}.principal_objects.{obj.role}",
                        f"references undefined container role {obj.container_role!r}",
                    )
            for role in operation.callee_roles:
                for contract_id in role.return_contract_ids:
                    contract = contracts.get(contract_id)
                    if contract is None:
                        raise MetadataProtocolValidationError(
                            f"protocol.operations.{operation.operation_id}.callee_roles.{role.role_id}",
                            f"references undefined return contract {contract_id!r}",
                        )
                    if contract.operation_id != operation.operation_id:
                        raise MetadataProtocolValidationError(
                            f"protocol.operations.{operation.operation_id}.callee_roles.{role.role_id}",
                            f"return contract {contract_id!r} belongs to another operation",
                        )

        for item in self.effects:
            self._validate_object(item.operation_id, item.object_ref, f"protocol.effects.{item.effect_id}")
            self._validate_phase(item.phase, phases, f"protocol.effects.{item.effect_id}.phase")

        effect_ids = {item.effect_id: item for item in self.effects}
        for item in self.accounting_constraints:
            self._validate_object(item.operation_id, item.subject, f"protocol.accounting_constraints.{item.constraint_id}")
            for effect_id in (*item.trigger_effect_ids, *item.satisfying_effect_ids):
                effect = effect_ids.get(effect_id)
                if effect is None:
                    raise MetadataProtocolValidationError(
                        f"protocol.accounting_constraints.{item.constraint_id}",
                        f"references undefined effect {effect_id!r}",
                    )
                if effect.operation_id != item.operation_id:
                    raise MetadataProtocolValidationError(
                        f"protocol.accounting_constraints.{item.constraint_id}",
                        f"effect {effect_id!r} belongs to another operation",
                    )
            if item.trigger_effect_ids and not item.satisfying_effect_ids:
                raise MetadataProtocolValidationError(
                    f"protocol.accounting_constraints.{item.constraint_id}",
                    "a trigger effect requires at least one satisfying effect",
                )

        for item in self.compensations:
            self._validate_object(item.operation_id, item.object_ref, f"protocol.compensations.{item.compensation_id}")
            self._validate_phase(item.phase, phases, f"protocol.compensations.{item.compensation_id}.phase")
            target = effects.get(item.target_effect_id)
            if target is None:
                raise MetadataProtocolValidationError(
                    f"protocol.compensations.{item.compensation_id}.target_effect_id",
                    f"references undefined effect {item.target_effect_id!r}",
                )
            if target.operation_id != item.operation_id:
                raise MetadataProtocolValidationError(
                    f"protocol.compensations.{item.compensation_id}.target_effect_id",
                    "target effect belongs to another operation",
                )
            if target.object_ref.role != item.object_ref.role:
                raise MetadataProtocolValidationError(
                    f"protocol.compensations.{item.compensation_id}.object",
                    "compensation object role does not match its target effect",
                )

        allowed_handler_modes = {
            CompletionMode.ABORTED,
            CompletionMode.RECOVERY_DELEGATED,
            CompletionMode.DEFERRED,
        }
        for item in self.handlers:
            self._validate_object(item.operation_id, item.object_ref, f"protocol.handlers.{item.handler_id}")
            if item.completion_mode not in allowed_handler_modes:
                raise MetadataProtocolValidationError(
                    f"protocol.handlers.{item.handler_id}.completion_mode",
                    "handler must transfer to ABORTED, RECOVERY_DELEGATED, or DEFERRED",
                )
            for effect_id in item.handles_effect_ids:
                effect = effects.get(effect_id)
                if effect is None:
                    raise MetadataProtocolValidationError(
                        f"protocol.handlers.{item.handler_id}.handles_effect_ids",
                        f"references undefined effect {effect_id!r}",
                    )
                if effect.operation_id != item.operation_id:
                    raise MetadataProtocolValidationError(
                        f"protocol.handlers.{item.handler_id}.handles_effect_ids",
                        f"effect {effect_id!r} belongs to another operation",
                    )
                if effect.object_ref.role != item.object_ref.role:
                    raise MetadataProtocolValidationError(
                        f"protocol.handlers.{item.handler_id}.object",
                        f"handler object role does not match effect {effect_id!r}",
                    )
                if (
                    item.completion_mode is CompletionMode.ABORTED
                    and effect.scope is not EffectScope.TRANSACTION_SCOPED
                ):
                    raise MetadataProtocolValidationError(
                        f"protocol.handlers.{item.handler_id}.handles_effect_ids",
                        f"ABORTED handler cannot own non-transaction effect {effect_id!r}",
                    )

        for item in self.accounting_constraints:
            self._validate_object(item.operation_id, item.subject, f"protocol.accounting_constraints.{item.constraint_id}")
            for phase in item.phases:
                self._validate_phase(phase, phases, f"protocol.accounting_constraints.{item.constraint_id}.phases")

        exit_kinds: dict[str, set[LegalExitKind]] = {item: set() for item in operations}
        outcomes_by_operation: dict[str, set[ReturnOutcome]] = {item: set() for item in operations}
        for contract in self.return_contracts:
            outcomes_by_operation[contract.operation_id].add(contract.outcome)
        for item in self.legal_exits:
            exit_kinds[item.operation_id].add(item.kind)
            for phase in item.phases:
                self._validate_phase(phase, phases, f"protocol.legal_exits.{item.exit_id}.phases")
            missing = set(item.return_outcomes) - outcomes_by_operation[item.operation_id]
            if missing:
                values = ", ".join(sorted(value.value for value in missing))
                raise MetadataProtocolValidationError(
                    f"protocol.legal_exits.{item.exit_id}.return_outcomes",
                    f"outcomes have no return contract in this operation: {values}",
                )
        for operation_id, kinds in exit_kinds.items():
            missing = {LegalExitKind.SUCCESS, LegalExitKind.FAILURE} - kinds
            if missing:
                values = ", ".join(sorted(item.value for item in missing))
                raise MetadataProtocolValidationError(
                    f"protocol.operations.{operation_id}",
                    f"missing legal exit kind(s): {values}",
                )

        by_operation: dict[str, list[ReturnContract]] = {item: [] for item in operations}
        for contract in self.return_contracts:
            by_operation[contract.operation_id].append(contract)
        for operation_id, operation_contracts in by_operation.items():
            if not operation_contracts:
                raise MetadataProtocolValidationError(
                    f"protocol.operations.{operation_id}", "has no return contracts"
                )
            _validate_return_contract_overlap(operation_id, operation_contracts)

    def _validate_object(self, operation_id: str, obj: ObjectRef, path: str) -> None:
        operation = next(item for item in self.operations if item.operation_id == operation_id)
        declared = {item.role: item for item in operation.principal_objects}
        expected = declared.get(obj.role)
        if expected is None:
            raise MetadataProtocolValidationError(
                f"{path}.object", f"references undefined principal object role {obj.role!r}"
            )
        if expected != obj:
            raise MetadataProtocolValidationError(
                f"{path}.object", f"does not match declared principal object role {obj.role!r}"
            )

    @staticmethod
    def _validate_phase(phase: str, phases: set[str], path: str) -> None:
        if phase not in phases:
            raise MetadataProtocolValidationError(path, f"references undefined phase {phase!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "protocol_version": self.protocol_version,
            "protocol_id": self.protocol_id,
            "filesystems": list(self.filesystems),
            "linux_versions": list(self.linux_versions),
            "phases": list(self.phases),
            "operations": [item.to_dict() for item in self.operations],
            "return_contracts": [item.to_dict() for item in self.return_contracts],
            "effects": [item.to_dict() for item in self.effects],
            "compensations": [item.to_dict() for item in self.compensations],
            "handlers": [item.to_dict() for item in self.handlers],
            "accounting_constraints": [item.to_dict() for item in self.accounting_constraints],
            "legal_exits": [item.to_dict() for item in self.legal_exits],
            "description": self.description,
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True) + "\n"

    def write_json(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_json(), encoding="utf-8")


def load_metadata_protocols(directory: str | Path) -> tuple[MetadataProtocol, ...]:
    """Load every JSON protocol in a directory and reject duplicate protocol IDs."""

    root = Path(directory)
    if not root.is_dir():
        raise MetadataProtocolValidationError(str(root), "metadata protocol directory does not exist")
    paths = sorted(root.glob("*.json"))
    if not paths:
        raise MetadataProtocolValidationError(str(root), "contains no .json protocol files")
    protocols = tuple(MetadataProtocol.read_json(path) for path in paths)
    _unique((item.protocol_id for item in protocols), str(root), "protocol_id")
    return protocols


EnumT = TypeVar("EnumT", bound=Enum)
ParserT = TypeVar("ParserT")
_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*")
_SEMVER = re.compile(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:[-+][0-9A-Za-z.-]+)?"
)
_RETURN_GUARD = re.compile(r"ret(?:urn)?\s*(==|!=|<=|>=|<|>)\s*(-?\d+|-[A-Z][A-Z0-9_]*)", re.IGNORECASE)


def _mapping(data: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise MetadataProtocolValidationError(path, "expected an object")
    return data


def _known_keys(data: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise MetadataProtocolValidationError(path, f"unknown field(s): {', '.join(unknown)}")


def _required(data: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in data:
        raise MetadataProtocolValidationError(f"{path}.{key}", "required field is missing")
    return data[key]


def _text(data: Mapping[str, Any], key: str, path: str) -> str:
    value = _required(data, key, path)
    if not isinstance(value, str) or not value.strip():
        raise MetadataProtocolValidationError(f"{path}.{key}", "expected a non-empty string")
    return value.strip()


def _optional_text(data: Mapping[str, Any], key: str, path: str) -> str:
    value = data.get(key, "")
    if not isinstance(value, str):
        raise MetadataProtocolValidationError(f"{path}.{key}", "expected a string")
    return value.strip()


def _identifier(data: Mapping[str, Any], key: str, path: str) -> str:
    value = _text(data, key, path)
    if not _IDENTIFIER.fullmatch(value):
        raise MetadataProtocolValidationError(
            f"{path}.{key}", "expected a stable identifier using letters, digits, '.', '_', or '-'"
        )
    return value


def _optional_identifier(data: Mapping[str, Any], key: str, path: str) -> str:
    value = _optional_text(data, key, path)
    if value and not _IDENTIFIER.fullmatch(value):
        raise MetadataProtocolValidationError(f"{path}.{key}", "invalid identifier")
    return value


def _integer(data: Mapping[str, Any], key: str, path: str) -> int:
    value = _required(data, key, path)
    if isinstance(value, bool) or not isinstance(value, int):
        raise MetadataProtocolValidationError(f"{path}.{key}", "expected an integer")
    return value


def _boolean(data: Mapping[str, Any], key: str, path: str, *, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise MetadataProtocolValidationError(f"{path}.{key}", "expected a boolean")
    return value


def _strength(data: Mapping[str, Any], path: str) -> str:
    value = data.get("strength", "must")
    if value not in {"must", "may"}:
        raise MetadataProtocolValidationError(
            f"{path}.strength", "expected 'must' or 'may'"
        )
    return value


def _string_tuple(
    data: Mapping[str, Any],
    key: str,
    path: str,
    *,
    nonempty: bool = False,
    optional: bool = False,
) -> tuple[str, ...]:
    raw = data.get(key, []) if optional else _required(data, key, path)
    if not isinstance(raw, list):
        raise MetadataProtocolValidationError(f"{path}.{key}", "expected a list")
    values: list[str] = []
    for index, value in enumerate(raw):
        if not isinstance(value, str) or not value.strip():
            raise MetadataProtocolValidationError(f"{path}.{key}[{index}]", "expected a non-empty string")
        values.append(value.strip())
    if nonempty and not values:
        raise MetadataProtocolValidationError(f"{path}.{key}", "must not be empty")
    _unique(values, f"{path}.{key}", "value")
    return tuple(values)


def _enum(
    data: Mapping[str, Any], key: str, path: str, enum_type: Type[EnumT]
) -> EnumT:
    raw = _text(data, key, path)
    try:
        return enum_type(raw)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise MetadataProtocolValidationError(
            f"{path}.{key}", f"unknown {enum_type.__name__} {raw!r}; expected one of: {allowed}"
        ) from exc


def _enum_tuple(
    data: Mapping[str, Any], key: str, path: str, enum_type: Type[EnumT]
) -> tuple[EnumT, ...]:
    raw = _required(data, key, path)
    if not isinstance(raw, list) or not raw:
        raise MetadataProtocolValidationError(f"{path}.{key}", "expected a non-empty list")
    values: list[EnumT] = []
    for index, value in enumerate(raw):
        item_path = f"{path}.{key}[{index}]"
        if not isinstance(value, str) or not value.strip():
            raise MetadataProtocolValidationError(item_path, "expected a non-empty string")
        try:
            values.append(enum_type(value.strip()))
        except ValueError as exc:
            allowed = ", ".join(item.value for item in enum_type)
            raise MetadataProtocolValidationError(
                item_path,
                f"unknown {enum_type.__name__} {value.strip()!r}; expected one of: {allowed}",
            ) from exc
    _unique((item.value for item in values), f"{path}.{key}", "value")
    return tuple(values)


def _object_list(
    data: Mapping[str, Any],
    key: str,
    path: str,
    parser: Any,
    *,
    nonempty: bool = False,
) -> tuple[Any, ...]:
    raw = _required(data, key, path)
    if not isinstance(raw, list):
        raise MetadataProtocolValidationError(f"{path}.{key}", "expected a list")
    if nonempty and not raw:
        raise MetadataProtocolValidationError(f"{path}.{key}", "must not be empty")
    return tuple(parser(item, f"{path}.{key}[{index}]") for index, item in enumerate(raw))


def _unique(values: Iterable[str], path: str, label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise MetadataProtocolValidationError(path, f"duplicate {label} {value!r}")
        seen.add(value)


def _validate_return_contract_overlap(
    operation_id: str, contracts: list[ReturnContract]
) -> None:
    for index, left in enumerate(contracts):
        for right in contracts[index + 1 :]:
            if not _guards_may_overlap(left.guard, right.guard):
                continue
            if (
                left.priority is None
                or right.priority is None
                or left.priority == right.priority
            ):
                raise MetadataProtocolValidationError(
                    f"protocol.operations.{operation_id}.return_contracts",
                    f"overlapping guards {left.contract_id!r} and {right.contract_id!r} "
                    "require distinct priorities",
                )


def _guards_may_overlap(left: str, right: str) -> bool:
    left_constraint = _parse_return_guard(left)
    right_constraint = _parse_return_guard(right)
    if left_constraint is None or right_constraint is None:
        # Unknown guard languages are conservatively considered overlapping.
        return True
    left_op, left_value = left_constraint
    right_op, right_value = right_constraint
    if isinstance(left_value, str) or isinstance(right_value, str):
        if left_value != right_value:
            if left_op == "==" and right_op == "==":
                return False
            return True
        return not ({left_op, right_op} == {"==", "!="})
    candidates = {left_value, right_value, left_value - 1, left_value + 1, right_value - 1, right_value + 1}
    return any(
        _comparison(value, left_op, left_value) and _comparison(value, right_op, right_value)
        for value in candidates
    )


def _parse_return_guard(guard: str) -> tuple[str, int | str] | None:
    match = _RETURN_GUARD.fullmatch(_normalize_guard(guard))
    if match is None:
        return None
    operator, raw = match.groups()
    try:
        value: int | str = int(raw)
    except ValueError:
        value = raw.upper()
    return operator, value


def _normalize_guard(guard: str) -> str:
    return " ".join(guard.strip().split())


def _comparison(actual: int, operator: str, expected: int) -> bool:
    return {
        "==": actual == expected,
        "!=": actual != expected,
        "<": actual < expected,
        "<=": actual <= expected,
        ">": actual > expected,
        ">=": actual >= expected,
    }[operator]
