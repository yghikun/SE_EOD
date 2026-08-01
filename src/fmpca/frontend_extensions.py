from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from .frontend import (
    SourceAnalysis,
    SourceBindingError,
    _event,
    _forbidden_binding_key_paths,
    _matching,
    extract_function,
)


@dataclass(frozen=True)
class RevisionSourceBinding:
    raw: Dict[str, Any]
    path: Path

    def __getattr__(self, name: str) -> Any:
        try:
            return self.raw[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def load_revision_binding(path: str) -> RevisionSourceBinding:
    binding_path = Path(path)
    raw = json.loads(binding_path.read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "binding_id",
        "binding_version",
        "protocol_id",
        "kinds",
        "field_paths",
        "attachment_primitives",
        "failure_primitives",
        "error_variables",
        "restore_sequences",
        "event_names",
        "role_kinds",
        "semantic_footprint",
    }
    missing = required - set(raw)
    extra = set(raw) - required
    if missing:
        raise SourceBindingError(f"missing revision binding keys: {sorted(missing)}")
    if extra:
        raise SourceBindingError(f"unknown revision binding keys: {sorted(extra)}")
    forbidden = _forbidden_binding_key_paths(raw)
    if forbidden:
        raise SourceBindingError(
            f"revision binding contains forbidden bug-specific keys: {forbidden}"
        )
    if raw["schema_version"] != 1:
        raise SourceBindingError("revision binding schema_version must be 1")
    if "preexisting_relation_failure_cleanup" not in raw["kinds"]:
        raise SourceBindingError("unsupported revision binding kind")
    return RevisionSourceBinding(raw, binding_path)


def _git_source(repo: str, revision: str, source_path: str) -> str:
    completed = subprocess.run(
        ["git", "-C", repo, "show", f"{revision}:{source_path}"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.decode("utf-8", errors="replace")


def _event_name(binding: RevisionSourceBinding, key: str) -> str:
    return binding.event_names[key]


def require_protocol_scope(binding: RevisionSourceBinding, protocol: Any) -> None:
    """Reject source mappings that introduce semantics absent from the protocol."""
    binding_footprint = set(binding.semantic_footprint)
    protocol_footprint = set(protocol.semantic_footprint)
    unsupported = sorted(binding_footprint - protocol_footprint)
    if unsupported:
        raise SourceBindingError(
            "revision binding exceeds the frozen protocol semantic footprint: "
            + ", ".join(unsupported)
        )


def analyze_revision_source(
    binding: RevisionSourceBinding,
    repo: str,
    revision: str,
    source_path: str,
    function_name: str,
    source_version: str,
) -> SourceAnalysis:
    source = _git_source(repo, revision, source_path)
    function = extract_function(source, function_name)
    operation_id = f"operation:{source_version}:{source_path}:{function_name}"
    relation = binding.field_paths[0]
    field_name = relation.split(".")[-1]
    owner_name = relation.split(".")[0]
    source_id = f"git:{repo}@{revision}:{source_path}"
    roles = {
        "operation": operation_id,
        "fs_root": f"typed-local:{owner_name}",
        "relocation_root": f"typed-field:{owner_name}->{field_name}",
        "recovery_owner": operation_id,
    }
    epoch = {"operation_root": operation_id, "retry_generation": 0}
    assumptions = [
        "the selected failure branch is feasible as established by the confirmed patch record",
        "the entry field equality identifies the attachment created earlier in the same relocation epoch",
        "only the selected failure branch is closed; whole-function conformance is not claimed",
    ]

    field_pattern = re.compile(
        r"\b" + re.escape(owner_name) + r"\s*->\s*" + re.escape(field_name)
    )
    field_match = field_pattern.search(function.masked_text)
    if not field_match:
        return SourceAnalysis([], [], True, False, True, assumptions, function)

    failure = None
    for primitive in binding.failure_primitives:
        for variable in binding.error_variables:
            pattern = re.compile(
                r"\b"
                + re.escape(variable)
                + r"\s*=\s*"
                + re.escape(primitive)
                + r"\s*\([^;]*?\)\s*;",
                re.MULTILINE,
            )
            match = pattern.search(function.masked_text, field_match.start())
            if match:
                failure = (match, variable, primitive)
                break
        if failure:
            break
    if not failure:
        return SourceAnalysis([], [], True, False, True, assumptions, function)

    failure_match, variable, primitive = failure
    branch_pattern = re.compile(
        r"if\s*\(\s*" + re.escape(variable) + r"\s*\)\s*\{",
        re.MULTILINE,
    )
    branch_match = branch_pattern.search(function.masked_text, failure_match.end())
    if not branch_match:
        return SourceAnalysis([], [], True, False, False, assumptions, function)
    brace_start = function.masked_text.find("{", branch_match.start(), branch_match.end())
    brace_end = _matching(function.masked_text, brace_start, "{", "}")
    repair_slice = function.masked_text[brace_start : brace_end + 1]

    sequence = next(
        item for item in binding.restore_sequences if item["relation"] == relation
    )
    found = {
        primitive_name: bool(
            re.search(r"\b" + re.escape(primitive_name) + r"\s*\(", repair_slice)
        )
        for primitive_name in sequence["required_primitives"]
    }
    restored = all(found.values())

    field_line = function.line_for_offset(field_match.start())
    failure_line = function.line_for_offset(failure_match.start())
    repair_line = function.line_for_offset(branch_match.start())
    terminal_line = function.line_for_offset(len(function.text) - 1)
    events = [
        _event(
            _event_name(binding, "snapshot"),
            roles,
            epoch,
            source_id,
            field_line,
            {"relation": relation, "value": None},
        ),
        _event(
            _event_name(binding, "attachment"),
            roles,
            epoch,
            source_id,
            field_line,
            {"relation": relation, "value": "attached:reloc_root", "deadline": "AT_SETTLEMENT"},
        ),
        _event(
            _event_name(binding, "failure"),
            roles,
            epoch,
            source_id,
            failure_line,
            {"error_variable": variable, "callee": primitive},
        ),
    ]
    if restored:
        events.append(
            _event(
                _event_name(binding, "restore"),
                roles,
                epoch,
                source_id,
                repair_line,
                {"relation": relation},
            )
        )
    events.append(
        _event(
            _event_name(binding, "return"),
            roles,
            epoch,
            source_id,
            terminal_line,
        )
    )
    evidence: List[Dict[str, Any]] = [
        {
            "kind": "preexisting_relation_attachment",
            "relation": relation,
            "line": field_line,
            "field_evidence": f"{owner_name}->{field_name}",
        },
        {
            "kind": "checked_failure_branch",
            "callee": primitive,
            "error_variable": variable,
            "line": failure_line,
        },
        {
            "kind": "relation_repair_sequence",
            "relation": relation,
            "required_primitives": list(sequence["required_primitives"]),
            "primitive_evidence": found,
            "restore_found": restored,
            "line": repair_line,
        },
    ]
    return SourceAnalysis(events, evidence, True, False, True, assumptions, function)
