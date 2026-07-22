"""Compose protocol families, filesystem bindings, and operation instances."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping


PROTOCOL_PACKAGE_SCHEMA_VERSION = 1
PROTOCOL_FAMILY_SCHEMA_VERSION = 1
FILESYSTEM_BINDING_SCHEMA_VERSION = 1
OPERATION_INSTANCE_SCHEMA_VERSION = 1

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_TRANSITIONS = {"OPEN", "COMMIT", "COMPENSATE", "TRANSFER"}


class MetadataProtocolPackageError(ValueError):
    """A package composition error with a precise configuration path."""

    def __init__(self, path: str, message: str) -> None:
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


class _DuplicateJsonKey(ValueError):
    pass


def is_protocol_package(data: Mapping[str, Any]) -> bool:
    return "protocol_package_schema_version" in data


def compose_protocol_package(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    manifest = _read_json(manifest_path, "protocol_package")
    _known_keys(
        manifest,
        {
            "protocol_package_schema_version",
            "runtime_schema_version",
            "protocol_version",
            "protocol_id",
            "family",
            "bindings",
            "operations",
            "description",
        },
        "protocol_package",
    )
    _schema_version(
        manifest,
        "protocol_package_schema_version",
        PROTOCOL_PACKAGE_SCHEMA_VERSION,
        "protocol_package",
    )
    runtime_schema_version = _integer(
        manifest, "runtime_schema_version", "protocol_package"
    )
    if runtime_schema_version != 2:
        raise MetadataProtocolPackageError(
            "protocol_package.runtime_schema_version",
            "composed packages currently require runtime schema version 2",
        )
    protocol_version = _text(manifest, "protocol_version", "protocol_package")
    if not _SEMVER.fullmatch(protocol_version):
        raise MetadataProtocolPackageError(
            "protocol_package.protocol_version",
            "expected semantic version MAJOR.MINOR.PATCH",
        )

    family = _load_family(_resolve(manifest_path, manifest, "family"))
    bindings = tuple(
            _load_binding(
                _resolve_value(
                    manifest_path, item, f"protocol_package.bindings[{index}]"
                )
            )
        for index, item in enumerate(
            _string_list(manifest, "bindings", "protocol_package", nonempty=True)
        )
    )
    operations = tuple(
        _load_operation(
            _resolve_value(
                manifest_path, item, f"protocol_package.operations[{index}]"
            )
        )
        for index, item in enumerate(
            _string_list(manifest, "operations", "protocol_package", nonempty=True)
        )
    )
    binding_by_id = {_text(item, "binding_id", "binding"): item for item in bindings}
    if len(binding_by_id) != len(bindings):
        raise MetadataProtocolPackageError(
            "protocol_package.bindings", "duplicate binding_id"
        )

    runtime_operations: list[dict[str, Any]] = []
    return_contracts: list[dict[str, Any]] = []
    effects: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    legal_exits: list[dict[str, Any]] = []
    filesystems: list[str] = []
    linux_versions: list[str] = []
    phases: list[str] = []

    family_id = _text(family, "family_id", "family")
    family_roles = set(_string_list(family, "abstract_roles", "family", nonempty=True))
    family_actions = {
        _text(action, "action_id", "family.actions"): action
        for action in _mapping_list(family, "actions", "family", nonempty=True)
    }

    for index, binding in enumerate(bindings):
        path_prefix = f"protocol_package.bindings[{index}]"
        if _text(binding, "family_id", path_prefix) != family_id:
            raise MetadataProtocolPackageError(
                f"{path_prefix}.family_id", "does not match the package family"
            )
        role_bindings = _mapping(binding, "role_bindings", path_prefix)
        if set(role_bindings) != family_roles:
            raise MetadataProtocolPackageError(
                f"{path_prefix}.role_bindings",
                "must bind every abstract family role exactly once",
            )
        for role, concrete in role_bindings.items():
            _identifier_value(role, f"{path_prefix}.role_bindings")
            _identifier_value(concrete, f"{path_prefix}.role_bindings.{role}")
        action_ids = [
            _text(item, "action_id", f"{path_prefix}.actions")
            for item in _mapping_list(binding, "actions", path_prefix, nonempty=True)
        ]
        unknown_actions = set(action_ids) - set(family_actions)
        if unknown_actions:
            raise MetadataProtocolPackageError(
                f"{path_prefix}.actions",
                "references undefined family action(s): "
                + ", ".join(sorted(unknown_actions)),
            )
        if len(action_ids) != len(set(action_ids)):
            raise MetadataProtocolPackageError(
                f"{path_prefix}.actions", "duplicate action_id"
            )

    for index, operation in enumerate(operations):
        path_prefix = f"protocol_package.operations[{index}]"
        if _text(operation, "family_id", path_prefix) != family_id:
            raise MetadataProtocolPackageError(
                f"{path_prefix}.family_id", "does not match the package family"
            )
        binding_id = _text(operation, "binding_id", path_prefix)
        binding = binding_by_id.get(binding_id)
        if binding is None:
            raise MetadataProtocolPackageError(
                f"{path_prefix}.binding_id", "references an unloaded binding"
            )
        filesystem = _text(binding, "filesystem", f"binding.{binding_id}")
        _append_unique(filesystems, filesystem)
        for version in _string_list(
            binding, "linux_versions", f"binding.{binding_id}", nonempty=True
        ):
            _append_unique(linux_versions, version)
        operation_phases = _string_list(
            operation, "phases", path_prefix, nonempty=True
        )
        for phase in operation_phases:
            _append_unique(phases, phase)

        operation_id = _text(operation, "operation_id", path_prefix)
        role_bindings = _mapping(binding, "role_bindings", f"binding.{binding_id}")
        role_instances = _mapping_list(
            operation, "role_instances", path_prefix, nonempty=True
        )
        principal_objects: list[dict[str, Any]] = []
        for role_index, role_instance in enumerate(role_instances):
            abstract_role = _text(
                role_instance,
                "abstract_role",
                f"{path_prefix}.role_instances[{role_index}]",
            )
            if abstract_role not in family_roles:
                raise MetadataProtocolPackageError(
                    f"{path_prefix}.role_instances[{role_index}].abstract_role",
                    "references an undefined family role",
                )
            principal_objects.append(
                {
                    "role": role_bindings[abstract_role],
                    "selector": _text(
                        role_instance,
                        "selector",
                        f"{path_prefix}.role_instances[{role_index}]",
                    ),
                }
            )
        discovery = _mapping(operation, "discovery", path_prefix)
        runtime_operations.append(
            {
                "operation_id": operation_id,
                "entry_functions": _string_list(
                    operation, "entry_functions", path_prefix
                ),
                "principal_objects": principal_objects,
                "callee_roles": [],
                "discovery": dict(discovery),
            }
        )

        for contract in _mapping_list(
            operation, "return_contracts", path_prefix, nonempty=True
        ):
            return_contracts.append({**contract, "operation_id": operation_id})

        effect = dict(_mapping(operation, "effect", path_prefix))
        abstract_role = _text(effect, "abstract_role", f"{path_prefix}.effect")
        if abstract_role not in family_roles:
            raise MetadataProtocolPackageError(
                f"{path_prefix}.effect.abstract_role",
                "references an undefined family role",
            )
        effect.pop("abstract_role")
        effect["operation_id"] = operation_id
        effect["object"] = {
            "role": role_bindings[abstract_role],
            "selector": next(
                item["selector"]
                for item in principal_objects
                if item["role"] == role_bindings[abstract_role]
            ),
        }
        effects.append(effect)

        summary_ids = _mapping(operation, "summary_ids", path_prefix)
        binding_actions = _mapping_list(
            binding, "actions", f"binding.{binding_id}", nonempty=True
        )
        if set(summary_ids) != {
            _text(item, "action_id", f"binding.{binding_id}.actions")
            for item in binding_actions
        }:
            raise MetadataProtocolPackageError(
                f"{path_prefix}.summary_ids",
                "must assign one summary_id to every binding action",
            )
        effect_id = _text(effect, "effect_id", f"{path_prefix}.effect")
        for action in binding_actions:
            action_id = _text(action, "action_id", f"binding.{binding_id}.actions")
            family_action = family_actions[action_id]
            object_binding = dict(
                _mapping(action, "object_binding", f"binding.{binding_id}.actions")
            )
            action_role = _text(
                object_binding,
                "abstract_role",
                f"binding.{binding_id}.actions.{action_id}.object_binding",
            )
            if action_role not in family_roles:
                raise MetadataProtocolPackageError(
                    f"binding.{binding_id}.actions.{action_id}.object_binding.abstract_role",
                    "references an undefined family role",
                )
            object_binding.pop("abstract_role")
            object_binding["role"] = role_bindings[action_role]
            summaries.append(
                {
                    "summary_id": _identifier_value(
                        summary_ids[action_id], f"{path_prefix}.summary_ids.{action_id}"
                    ),
                    "operation_id": operation_id,
                    "callees": _string_list(
                        action, "callees", f"binding.{binding_id}.actions", nonempty=True
                    ),
                    "transition": _text(
                        family_action, "transition", f"family.actions.{action_id}"
                    ),
                    "target_effect_id": effect_id,
                    "object_binding": object_binding,
                    "guard": _text(action, "guard", f"binding.{binding_id}.actions"),
                    "strength": _text(
                        action, "strength", f"binding.{binding_id}.actions"
                    ),
                    "max_call_depth": _integer(
                        action, "max_call_depth", f"binding.{binding_id}.actions"
                    ),
                }
            )
        for exit_spec in _mapping_list(
            operation, "legal_exits", path_prefix, nonempty=True
        ):
            legal_exits.append({**exit_spec, "operation_id": operation_id})

    return {
        "schema_version": runtime_schema_version,
        "protocol_version": protocol_version,
        "protocol_id": _text(manifest, "protocol_id", "protocol_package"),
        "filesystems": filesystems,
        "linux_versions": linux_versions,
        "phases": phases,
        "operations": runtime_operations,
        "return_contracts": return_contracts,
        "effects": effects,
        "compensations": [],
        "handlers": [],
        "callee_summaries": summaries,
        "accounting_constraints": [],
        "legal_exits": legal_exits,
        "description": _text(manifest, "description", "protocol_package"),
    }


def _load_family(path: Path) -> dict[str, Any]:
    value = _read_json(path, "family")
    _known_keys(
        value,
        {
            "family_schema_version",
            "family_id",
            "title",
            "description",
            "abstract_roles",
            "actions",
            "obligations",
        },
        "family",
    )
    _schema_version(
        value, "family_schema_version", PROTOCOL_FAMILY_SCHEMA_VERSION, "family"
    )
    _identifier_value(_text(value, "family_id", "family"), "family.family_id")
    abstract_roles = _string_list(
        value, "abstract_roles", "family", nonempty=True
    )
    if len(abstract_roles) != len(set(abstract_roles)):
        raise MetadataProtocolPackageError(
            "family.abstract_roles", "duplicate abstract role"
        )
    for index, role in enumerate(abstract_roles):
        _identifier_value(role, f"family.abstract_roles[{index}]")
    actions = _mapping_list(value, "actions", "family", nonempty=True)
    action_ids: list[str] = []
    for index, action in enumerate(actions):
        action_path = f"family.actions[{index}]"
        _known_keys(action, {"action_id", "transition", "description"}, action_path)
        action_ids.append(_text(action, "action_id", action_path))
        transition = _text(action, "transition", action_path)
        if transition not in _TRANSITIONS:
            raise MetadataProtocolPackageError(
                f"{action_path}.transition", "unsupported effect transition"
            )
    if len(action_ids) != len(set(action_ids)):
        raise MetadataProtocolPackageError("family.actions", "duplicate action_id")
    for index, obligation in enumerate(
        _mapping_list(value, "obligations", "family", nonempty=True)
    ):
        obligation_path = f"family.obligations[{index}]"
        _known_keys(
            obligation,
            {
                "obligation_id",
                "abstract_role",
                "trigger_action",
                "terminal_actions",
                "statement",
                "applicability",
            },
            obligation_path,
        )
        obligation_role = _text(obligation, "abstract_role", obligation_path)
        if obligation_role not in set(abstract_roles):
            raise MetadataProtocolPackageError(
                f"{obligation_path}.abstract_role",
                "references an undefined family role",
            )
        _text(obligation, "statement", obligation_path)
        _string_list(obligation, "applicability", obligation_path, nonempty=True)
        referenced = {
            _text(obligation, "trigger_action", obligation_path),
            *_string_list(
                obligation, "terminal_actions", obligation_path, nonempty=True
            ),
        }
        if not referenced.issubset(set(action_ids)):
            raise MetadataProtocolPackageError(
                obligation_path, "references an undefined family action"
            )
    return value


def _load_binding(path: Path) -> dict[str, Any]:
    value = _read_json(path, "binding")
    _known_keys(
        value,
        {
            "binding_schema_version",
            "binding_id",
            "family_id",
            "filesystem",
            "linux_versions",
            "role_bindings",
            "actions",
            "description",
        },
        "binding",
    )
    _schema_version(
        value,
        "binding_schema_version",
        FILESYSTEM_BINDING_SCHEMA_VERSION,
        "binding",
    )
    for index, action in enumerate(
        _mapping_list(value, "actions", "binding", nonempty=True)
    ):
        action_path = f"binding.actions[{index}]"
        _known_keys(
            action,
            {
                "action_id",
                "callees",
                "object_binding",
                "guard",
                "strength",
                "max_call_depth",
            },
            action_path,
        )
        object_binding = _mapping(action, "object_binding", action_path)
        _known_keys(
            object_binding,
            {"abstract_role", "source", "argument_index", "normalization"},
            f"{action_path}.object_binding",
        )
    return value


def _load_operation(path: Path) -> dict[str, Any]:
    value = _read_json(path, "operation")
    _known_keys(
        value,
        {
            "operation_schema_version",
            "operation_id",
            "family_id",
            "binding_id",
            "entry_functions",
            "phases",
            "role_instances",
            "discovery",
            "return_contracts",
            "effect",
            "summary_ids",
            "legal_exits",
            "description",
        },
        "operation",
    )
    _schema_version(
        value,
        "operation_schema_version",
        OPERATION_INSTANCE_SCHEMA_VERSION,
        "operation",
    )
    return value


def _read_json(path: Path, kind: str) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
        )
    except OSError as exc:
        raise MetadataProtocolPackageError(str(path), f"cannot read {kind}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise MetadataProtocolPackageError(
            str(path), f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except _DuplicateJsonKey as exc:
        raise MetadataProtocolPackageError(str(path), str(exc)) from exc
    if not isinstance(payload, dict):
        raise MetadataProtocolPackageError(str(path), f"{kind} must be a JSON object")
    return payload


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _resolve(manifest_path: Path, value: Mapping[str, Any], key: str) -> Path:
    return _resolve_value(
        manifest_path, _text(value, key, "protocol_package"), f"protocol_package.{key}"
    )


def _resolve_value(manifest_path: Path, value: str, path: str) -> Path:
    target = (manifest_path.parent / value).resolve()
    if not target.is_file():
        raise MetadataProtocolPackageError(path, f"referenced file does not exist: {value}")
    return target


def _schema_version(
    value: Mapping[str, Any], key: str, expected: int, path: str
) -> None:
    actual = _integer(value, key, path)
    if actual != expected:
        raise MetadataProtocolPackageError(
            f"{path}.{key}", f"unsupported schema version {actual}; expected {expected}"
        )


def _mapping(value: Mapping[str, Any], key: str, path: str) -> dict[str, Any]:
    result = value.get(key)
    if not isinstance(result, dict):
        raise MetadataProtocolPackageError(f"{path}.{key}", "expected an object")
    return result


def _mapping_list(
    value: Mapping[str, Any], key: str, path: str, *, nonempty: bool = False
) -> list[dict[str, Any]]:
    result = value.get(key)
    if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
        raise MetadataProtocolPackageError(
            f"{path}.{key}", "expected an array of objects"
        )
    if nonempty and not result:
        raise MetadataProtocolPackageError(f"{path}.{key}", "must not be empty")
    return result


def _string_list(
    value: Mapping[str, Any], key: str, path: str, *, nonempty: bool = False
) -> list[str]:
    result = value.get(key)
    if not isinstance(result, list) or any(
        not isinstance(item, str) or not item.strip() for item in result
    ):
        raise MetadataProtocolPackageError(
            f"{path}.{key}", "expected an array of non-empty strings"
        )
    if nonempty and not result:
        raise MetadataProtocolPackageError(f"{path}.{key}", "must not be empty")
    return result


def _text(value: Mapping[str, Any], key: str, path: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise MetadataProtocolPackageError(f"{path}.{key}", "expected non-empty text")
    return result


def _integer(value: Mapping[str, Any], key: str, path: str) -> int:
    result = value.get(key)
    if isinstance(result, bool) or not isinstance(result, int):
        raise MetadataProtocolPackageError(f"{path}.{key}", "expected an integer")
    return result


def _identifier_value(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise MetadataProtocolPackageError(path, "expected an identifier")
    return value


def _known_keys(value: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise MetadataProtocolPackageError(
            path, "unknown field(s): " + ", ".join(unknown)
        )


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
