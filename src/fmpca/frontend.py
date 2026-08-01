from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .model import EvidenceEvent, Precision


class SourceBindingError(ValueError):
    pass


FORBIDDEN_BINDING_KEYS = {"bug_id", "target_function", "source_line", "patch_id"}


def _forbidden_binding_key_paths(value: Any, location: str = "$") -> List[str]:
    paths: List[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{location}.{key}"
            if key in FORBIDDEN_BINDING_KEYS:
                paths.append(child)
            paths.extend(_forbidden_binding_key_paths(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            paths.extend(_forbidden_binding_key_paths(item, f"{location}[{index}]"))
    return paths


@dataclass(frozen=True)
class SourceBinding:
    raw: Dict[str, Any]
    path: Path

    def __getattr__(self, name: str) -> Any:
        try:
            return self.raw[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


@dataclass
class ExtractedFunction:
    name: str
    text: str
    masked_text: str
    start_line: int
    parameter_text: str
    first_parameter_identity: str

    def line_for_offset(self, offset: int) -> int:
        return self.start_line + self.text[:offset].count("\n")


@dataclass
class SourceAnalysis:
    events: List[EvidenceEvent]
    evidence: List[Dict[str, Any]]
    path_model_closed: bool
    all_paths_closed: bool
    repair_slice_closed: bool
    assumptions: List[str]
    function: ExtractedFunction


def load_binding(path: str) -> SourceBinding:
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
    }
    missing = required - set(raw)
    if missing:
        raise SourceBindingError(f"missing binding keys: {sorted(missing)}")
    forbidden_paths = _forbidden_binding_key_paths(raw)
    if forbidden_paths:
        raise SourceBindingError(
            f"binding contains forbidden bug-specific keys: {forbidden_paths}"
        )
    if raw["schema_version"] != 1:
        raise SourceBindingError("binding schema_version must be 1")
    if not raw["kinds"]:
        raise SourceBindingError("binding must declare at least one structural kind")
    if raw["protocol_id"] == "fmpca.metadata_transition_outcome":
        outcome_required = {
            "error_variables",
            "success_literals",
            "allowed_absence_sentinels",
        }
        missing_outcome = outcome_required - set(raw)
        if missing_outcome:
            raise SourceBindingError(f"missing outcome binding keys: {sorted(missing_outcome)}")
        allowed = required | outcome_required
    elif raw["protocol_id"] == "fmpca.failure_rollback_conformance":
        rollback_required = {
            "field_paths",
            "acquire_primitives",
            "release_primitives",
            "failure_primitives",
            "error_variables",
            "relation_deadline",
        }
        missing_rollback = rollback_required - set(raw)
        if missing_rollback:
            raise SourceBindingError(f"missing rollback binding keys: {sorted(missing_rollback)}")
        allowed = required | rollback_required
    elif raw["protocol_id"] == "fmpca.recovery_attachment_settlement":
        recovery_required = {
            "field_paths",
            "acquire_primitives",
            "release_primitives",
            "failure_primitives",
            "error_variables",
            "relation_deadline",
            "event_names",
        }
        missing_recovery = recovery_required - set(raw)
        if missing_recovery:
            raise SourceBindingError(f"missing recovery binding keys: {sorted(missing_recovery)}")
        allowed = required | recovery_required
    elif raw["protocol_id"] == "fmpca.device_topology_rollback":
        topology_required = {"relation_rules", "failure_primitives", "error_variables"}
        missing_topology = topology_required - set(raw)
        if missing_topology:
            raise SourceBindingError(f"missing topology binding keys: {sorted(missing_topology)}")
        allowed = required | topology_required
    else:
        raise SourceBindingError(
            f"unsupported binding protocol_id: {raw['protocol_id']}"
        )
    extra = set(raw) - allowed
    if extra:
        raise SourceBindingError(f"unknown binding keys: {sorted(extra)}")
    return SourceBinding(raw, binding_path)


def _mask_c(text: str) -> str:
    chars = list(text)
    index = 0
    state = "code"
    while index < len(chars):
        current = chars[index]
        nxt = chars[index + 1] if index + 1 < len(chars) else ""
        if state == "code":
            if current == "/" and nxt == "*":
                chars[index] = chars[index + 1] = " "
                state = "block"
                index += 2
                continue
            if current == "/" and nxt == "/":
                chars[index] = chars[index + 1] = " "
                state = "line"
                index += 2
                continue
            if current == '"':
                chars[index] = " "
                state = "string"
            elif current == "'":
                chars[index] = " "
                state = "char"
        elif state == "block":
            if current == "*" and nxt == "/":
                chars[index] = chars[index + 1] = " "
                state = "code"
                index += 2
                continue
            if current != "\n":
                chars[index] = " "
        elif state == "line":
            if current == "\n":
                state = "code"
            else:
                chars[index] = " "
        elif state in {"string", "char"}:
            quote = '"' if state == "string" else "'"
            if current == "\\":
                chars[index] = " "
                if index + 1 < len(chars) and chars[index + 1] != "\n":
                    chars[index + 1] = " "
                index += 2
                continue
            if current == quote:
                chars[index] = " "
                state = "code"
            elif current != "\n":
                chars[index] = " "
        index += 1
    return "".join(chars)


def _matching(text: str, start: int, opening: str, closing: str) -> int:
    depth = 0
    for index in range(start, len(text)):
        if text[index] == opening:
            depth += 1
        elif text[index] == closing:
            depth -= 1
            if depth == 0:
                return index
    raise SourceBindingError(f"unclosed {opening} starting at offset {start}")


def _first_parameter_identity(parameter_text: str) -> str:
    first = parameter_text.split(",", 1)[0].strip()
    if not first or first == "void":
        return "parameter:none"
    names = re.findall(r"[A-Za-z_]\w*", first)
    name = names[-1] if names else "unknown"
    type_tokens = names[:-1]
    return f"parameter:0:{'/'.join(type_tokens) or 'unknown'}:{name}"


def extract_function(source: str, function_name: str) -> ExtractedFunction:
    masked = _mask_c(source)
    pattern = re.compile(r"\b" + re.escape(function_name) + r"\s*\(")
    for match in pattern.finditer(masked):
        open_paren = masked.find("(", match.start())
        close_paren = _matching(masked, open_paren, "(", ")")
        cursor = close_paren + 1
        while cursor < len(masked) and masked[cursor].isspace():
            cursor += 1
        if cursor >= len(masked) or masked[cursor] != "{":
            continue
        close_brace = _matching(masked, cursor, "{", "}")
        signature_start = masked.rfind("\n", 0, match.start()) + 1
        text = source[signature_start : close_brace + 1]
        masked_text = masked[signature_start : close_brace + 1]
        start_line = source[:signature_start].count("\n") + 1
        params = source[open_paren + 1 : close_paren]
        return ExtractedFunction(
            function_name,
            text,
            masked_text,
            start_line,
            params,
            _first_parameter_identity(params),
        )
    raise SourceBindingError(f"function definition not found: {function_name}")


def _event(
    name: str,
    roles: Dict[str, str],
    epoch: Dict[str, Any],
    source_path: str,
    line: int,
    data: Optional[Dict[str, Any]] = None,
    precision: Precision = Precision.EXACT,
) -> EvidenceEvent:
    return EvidenceEvent(
        event=name,
        roles=roles,
        epoch=epoch,
        data=data or {},
        source={"file": source_path, "line": line},
        precision=precision,
    )


def _binding_event(binding: SourceBinding, key: str, default: str) -> str:
    return binding.raw.get("event_names", {}).get(key, default)


def _last_return(function: ExtractedFunction) -> Optional[Tuple[str, int]]:
    matches = list(re.finditer(r"\breturn\s+([^;]+);", function.masked_text, re.MULTILINE))
    if not matches:
        return None
    match = matches[-1]
    return match.group(1).strip(), function.line_for_offset(match.start())


def analyze_outcome_source(
    binding: SourceBinding,
    source_path: str,
    function_name: str,
    source_version: str,
) -> SourceAnalysis:
    source = Path(source_path).read_text(encoding="utf-8", errors="replace")
    function = extract_function(source, function_name)
    operation_id = f"operation:{source_version}:{Path(source_path).name}:{function_name}"
    roles = {
        "operation": operation_id,
        "metadata_subject": function.first_parameter_identity,
        "outcome_owner": operation_id,
    }
    epoch = {"operation_root": operation_id, "retry_generation": 0}
    evidence: List[Dict[str, Any]] = []
    events: List[EvidenceEvent] = []
    assumptions = [
        "binding models checked error-to-return paths within the selected operation root",
        "callee failure feasibility follows explicit source error checks",
    ]
    if "ignored_nonabsence_error" in binding.kinds:
        for variable in binding.error_variables:
            pattern = re.compile(
                r"if\s*\(\s*"
                + re.escape(variable)
                + r"\s*!=\s*([+-]?[A-Za-z_]\w*)\s*\)\s*return\s+([^;]+);",
                re.MULTILINE,
            )
            for match in pattern.finditer(function.masked_text):
                sentinel = match.group(1)
                returned = match.group(2).strip()
                if sentinel not in binding.allowed_absence_sentinels:
                    continue
                if returned not in binding.success_literals:
                    continue
                assignment = re.search(
                    r"\b" + re.escape(variable) + r"\s*=\s*([A-Za-z_]\w*)\s*\(",
                    function.masked_text[: match.start()],
                )
                if not assignment:
                    continue
                begin_line = function.start_line
                failure_line = function.line_for_offset(match.start())
                events.extend(
                    [
                        _event(_binding_event(binding, "begin", "Begin"), roles, epoch, source_path, begin_line),
                        _event(
                            _binding_event(binding, "failure", "FailureObserved"),
                            roles,
                            epoch,
                            source_path,
                            failure_line,
                            {"error_variable": variable, "excluded_sentinel": sentinel},
                        ),
                        _event(_binding_event(binding, "success", "ReportSuccess"), roles, epoch, source_path, failure_line),
                        _event(_binding_event(binding, "return", "OperationReturn"), roles, epoch, source_path, failure_line),
                    ]
                )
                evidence.append(
                    {
                        "kind": "ignored_nonabsence_error",
                        "line": failure_line,
                        "error_variable": variable,
                        "allowed_absence_sentinel": sentinel,
                        "returned": returned,
                    }
                )
                return SourceAnalysis(events, evidence, True, False, True, assumptions, function)
    checked: List[Tuple[str, int, str]] = []
    for variable in binding.error_variables:
        assignment_pattern = re.compile(
            r"\b" + re.escape(variable) + r"\s*=\s*([A-Za-z_]\w*)\s*\(",
            re.MULTILINE,
        )
        for assignment in assignment_pattern.finditer(function.masked_text):
            tail = function.masked_text[assignment.end() :]
            check_pattern = re.compile(
                r"if\s*\(\s*"
                + re.escape(variable)
                + r"(?:\s*<\s*0|\s*!=\s*0)?\s*\)\s*(?:\{\s*)?goto\s+([A-Za-z_]\w*)\s*;",
                re.MULTILINE,
            )
            check = check_pattern.search(tail)
            if check:
                checked.append(
                    (
                        variable,
                        function.line_for_offset(assignment.start()),
                        assignment.group(1),
                    )
                )
    terminal = _last_return(function)
    if not checked or terminal is None:
        return SourceAnalysis([], [], True, False, True, assumptions, function)
    returned, return_line = terminal
    events.append(_event(_binding_event(binding, "begin", "Begin"), roles, epoch, source_path, function.start_line))
    if len(checked) > 1:
        events.append(
            _event(
                _binding_event(binding, "step", "MetadataStep"),
                roles,
                epoch,
                source_path,
                checked[0][1],
                {"checked_operations": len(checked)},
            )
        )
    events.append(
        _event(
            _binding_event(binding, "failure", "FailureObserved"),
            roles,
            epoch,
            source_path,
            checked[-1][1],
            {"error_variable": checked[-1][0], "callee": checked[-1][2]},
        )
    )
    evidence.extend(
        {
            "kind": "checked_error_call",
            "line": line,
            "error_variable": variable,
            "callee": callee,
        }
        for variable, line, callee in checked
    )
    if returned in binding.success_literals:
        events.append(_event(_binding_event(binding, "success", "ReportSuccess"), roles, epoch, source_path, return_line))
        all_paths_closed = False
    elif returned in binding.error_variables:
        events.append(_event(_binding_event(binding, "error", "ReportError"), roles, epoch, source_path, return_line))
        all_paths_closed = True
    else:
        events.append(
            _event(
                _binding_event(binding, "error", "ReportError"),
                roles,
                epoch,
                source_path,
                return_line,
                precision=Precision.UNKNOWN,
            )
        )
        all_paths_closed = False
        assumptions.append(f"unclassified_return_expression:{returned}")
    events.append(_event(_binding_event(binding, "return", "OperationReturn"), roles, epoch, source_path, return_line))
    evidence.append({"kind": "terminal_return", "line": return_line, "expression": returned})
    return SourceAnalysis(events, evidence, True, all_paths_closed, True, assumptions, function)


def analyze_rollback_source(
    binding: SourceBinding,
    source_path: str,
    function_name: str,
    source_version: str,
) -> SourceAnalysis:
    source = Path(source_path).read_text(encoding="utf-8", errors="replace")
    function = extract_function(source, function_name)
    operation_id = f"operation:{source_version}:{Path(source_path).name}:{function_name}"
    container_id = function.first_parameter_identity
    epoch = {"operation_root": operation_id, "retry_generation": 0}
    assumptions = [
        "selected operation return is the settlement deadline for the bound active attachment",
        "the repair slice is the reached common error-label suffix",
    ]
    for field in binding.field_paths:
        field_pattern = re.escape(field).replace(r"\.", r"\s*->\s*")
        for acquire in binding.acquire_primitives:
            assignment = re.search(
                r"\b([A-Za-z_]\w*)\s*->\s*"
                + field_pattern.split(r"\s*->\s*")[-1]
                + r"\s*=\s*"
                + re.escape(acquire)
                + r"\s*\(",
                function.masked_text,
                re.MULTILINE,
            )
            if not assignment:
                continue
            owner = assignment.group(1)
            field_name = field.split(".")[-1]
            relation = f"{owner}.{field_name}"
            failure_match = None
            for failure_call in binding.failure_primitives:
                for variable in binding.error_variables:
                    pattern = re.compile(
                        r"\b"
                        + re.escape(variable)
                        + r"\s*=\s*"
                        + re.escape(failure_call)
                        + r"\s*\([^;]*;\s*if\s*\(\s*"
                        + re.escape(variable)
                        + r"\s*\)\s*goto\s+([A-Za-z_]\w*)\s*;",
                        re.MULTILINE,
                    )
                    match = pattern.search(function.masked_text, assignment.end())
                    if match:
                        failure_match = (match, variable, failure_call, match.group(1))
                        break
                if failure_match:
                    break
            if not failure_match:
                continue
            match, variable, failure_call, label = failure_match
            label_match = re.search(
                r"(?m)^\s*" + re.escape(label) + r"\s*:\s*",
                function.masked_text[match.end() :],
            )
            if not label_match:
                continue
            label_offset = match.end() + label_match.start()
            cleanup = function.masked_text[label_offset:]
            clear_pattern = re.compile(
                r"\b"
                + re.escape(owner)
                + r"\s*->\s*"
                + re.escape(field_name)
                + r"\s*=\s*(?:NULL|0)\s*;"
            )
            release_found = bool(clear_pattern.search(cleanup))
            for release in binding.release_primitives:
                release_pattern = re.compile(
                    re.escape(release)
                    + r"\s*\([^;]*\b"
                    + re.escape(owner)
                    + r"\s*->\s*"
                    + re.escape(field_name)
                )
                release_found = release_found or bool(release_pattern.search(cleanup))
            if binding.protocol_id == "fmpca.recovery_attachment_settlement":
                roles = {
                    "operation": operation_id,
                    "fs_root": container_id,
                    "relocation_root": f"typed-field:{owner}->{field_name}",
                    "recovery_owner": container_id,
                }
            else:
                roles = {
                    "operation": operation_id,
                    "container": container_id,
                    "participant": f"typed-field:{owner}->{field_name}",
                    "owner": container_id,
                }
            assignment_line = function.line_for_offset(assignment.start())
            failure_line = function.line_for_offset(match.start())
            return_match = _last_return(function)
            return_line = return_match[1] if return_match else function.line_for_offset(len(function.text) - 1)
            events = [
                _event(
                    _binding_event(binding, "snapshot", "SnapshotPrestate"),
                    roles,
                    epoch,
                    source_path,
                    assignment_line,
                    {"relation": relation, "value": None},
                ),
                _event(
                    _binding_event(binding, "update", "RelationUpdate"),
                    roles,
                    epoch,
                    source_path,
                    assignment_line,
                    {
                        "relation": relation,
                        "value": f"acquired:{acquire}",
                        "deadline": binding.relation_deadline,
                    },
                ),
                _event(
                    _binding_event(binding, "failure", "FailureObserved"),
                    roles,
                    epoch,
                    source_path,
                    failure_line,
                    {"error_variable": variable, "callee": failure_call},
                ),
            ]
            if release_found:
                events.append(
                    _event(
                        _binding_event(binding, "restore", "RestoreRelation"),
                        roles,
                        epoch,
                        source_path,
                        function.line_for_offset(label_offset),
                        {"relation": relation},
                    )
                )
            events.append(_event(_binding_event(binding, "return", "OperationReturn"), roles, epoch, source_path, return_line))
            evidence = [
                {
                    "kind": "active_attachment",
                    "line": assignment_line,
                    "field_path": field,
                    "acquire_primitive": acquire,
                },
                {
                    "kind": "checked_failure_to_label",
                    "line": failure_line,
                    "failure_primitive": failure_call,
                    "error_label": label,
                },
                {
                    "kind": "repair_slice",
                    "line": function.line_for_offset(label_offset),
                    "release_found": release_found,
                    "release_primitives": list(binding.release_primitives),
                },
            ]
            return SourceAnalysis(events, evidence, True, release_found, True, assumptions, function)
    return SourceAnalysis([], [], True, False, True, assumptions, function)


def analyze_topology_source(
    binding: SourceBinding,
    source_path: str,
    function_name: str,
    source_version: str,
) -> SourceAnalysis:
    source = Path(source_path).read_text(encoding="utf-8", errors="replace")
    function = extract_function(source, function_name)
    operation_id = f"operation:{source_version}:{Path(source_path).name}:{function_name}"
    topology_id = function.first_parameter_identity
    roles = {
        "operation": operation_id,
        "topology": topology_id,
        "seed_container": f"typed-field:{topology_id}->fs_devices",
        "device": "typed-local:device",
        "active_device": f"typed-field:{topology_id}->latest_dev",
        "transaction_owner": f"typed-field:{topology_id}->transaction",
    }
    epoch = {"operation_root": operation_id, "retry_generation": 0}
    assumptions = [
        "relation prestate values are declared semantic entry assumptions in the binding",
        "the selected failure call is a feasible failure boundary after the relation mutations",
        "the reached error label or direct return bounds the repair slice",
    ]
    mutations: List[Dict[str, Any]] = []
    for rule in binding.relation_rules:
        matches: List[Tuple[int, str, re.Match[str]]] = []
        required_fragments = rule.get("mutator_argument_fragments", [])
        for mutator in rule.get("mutators", []):
            pattern = re.compile(
                r"\b" + re.escape(mutator) + r"\s*\([^;]*?\)",
                re.MULTILINE,
            )
            for match in pattern.finditer(function.masked_text):
                if all(fragment in match.group(0) for fragment in required_fragments):
                    matches.append((match.start(), mutator, match))
        if not matches:
            continue
        offset, mutator, match = min(matches, key=lambda item: item[0])
        mutations.append({"rule": rule, "offset": offset, "mutator": mutator, "match": match})
    if not mutations:
        return SourceAnalysis([], [], True, False, True, assumptions, function)
    mutation_end = max(item["match"].end() for item in mutations)
    failure_candidates: List[Tuple[int, str, re.Match[str], Optional[str]]] = []
    for primitive in binding.failure_primitives:
        for match in re.finditer(r"\b" + re.escape(primitive) + r"\s*\(", function.masked_text[mutation_end:], re.MULTILINE):
            absolute_start = mutation_end + match.start()
            absolute_end = mutation_end + match.end()
            tail = function.masked_text[absolute_end:]
            goto = re.search(r"\bgoto\s+([A-Za-z_]\w*)\s*;", tail, re.MULTILINE)
            direct_return = re.search(r"\breturn\s+[^;]+;", tail, re.MULTILINE)
            if goto or direct_return:
                failure_candidates.append((absolute_start, primitive, re.search(r"\b" + re.escape(primitive) + r"\s*\(", function.masked_text[absolute_start:], re.MULTILINE), goto.group(1) if goto else None))
    if not failure_candidates:
        return SourceAnalysis([], [], True, False, True, assumptions, function)
    failure_offset, failure_primitive, _, error_label = min(
        failure_candidates,
        key=lambda item: (item[3] is None, item[0]),
    )
    cleanup = ""
    cleanup_line = function.line_for_offset(failure_offset)
    if error_label:
        label_match = re.search(r"(?m)^\s*" + re.escape(error_label) + r"\s*:\s*", function.masked_text[failure_offset:])
        if label_match:
            label_offset = failure_offset + label_match.start()
            cleanup = function.masked_text[label_offset:]
            cleanup_line = function.line_for_offset(label_offset)
    else:
        tail = function.masked_text[failure_offset:]
        if re.search(r"\breturn\s+[^;]+;", tail, re.MULTILINE):
            cleanup = ""
    events: List[EvidenceEvent] = [
        _event("InitializeTopology", roles, epoch, source_path, function.start_line,
               {"relation": "active_target_valid", "value": True}),
    ]
    evidence: List[Dict[str, Any]] = []
    mutated_relations = set()
    for item in sorted(mutations, key=lambda value: value["offset"]):
        rule = item["rule"]
        relation = rule["relation"]
        mutated_relations.add(relation)
        line = function.line_for_offset(item["offset"])
        prestate = rule.get("prestate", "UNKNOWN")
        deadline = rule.get("deadline", "AT_SETTLEMENT")
        events.extend(
            [
                _event("SnapshotTopology", roles, epoch, source_path, line,
                       {"relation": relation, "value": prestate}),
                _event("TopologyMutation", roles, epoch, source_path, line,
                       {"relation": relation, "value": f"mutated:{item['mutator']}", "deadline": deadline}),
            ]
        )
        evidence.append({
            "kind": "domain_relation_mutation",
            "relation": relation,
            "mutator": item["mutator"],
            "line": line,
            "prestate_assumption": prestate,
        })
    failure_line = function.line_for_offset(failure_offset)
    events.append(_event("FailureObserved", roles, epoch, source_path, failure_line,
                          {"failure_primitive": failure_primitive, "error_label": error_label}))
    evidence.append({
        "kind": "domain_failure_boundary",
        "failure_primitive": failure_primitive,
        "error_label": error_label,
        "line": failure_line,
    })
    for item in sorted(mutations, key=lambda value: value["offset"]):
        rule = item["rule"]
        relation = rule["relation"]
        required_fragments = rule.get("restorer_argument_fragments", [])
        restored = False
        for restorer in rule.get("restorers", []):
            pattern = re.compile(
                r"\b" + re.escape(restorer) + r"\s*\([^;]*?\)",
                re.MULTILINE,
            )
            if any(
                all(fragment in match.group(0) for fragment in required_fragments)
                for match in pattern.finditer(cleanup)
            ):
                restored = True
                break
        if restored:
            events.append(_event("RestoreTopology", roles, epoch, source_path, cleanup_line,
                                  {"relation": relation}))
        evidence.append({
            "kind": "domain_repair_slice",
            "relation": relation,
            "restore_found": restored,
            "restorers": list(rule.get("restorers", [])),
            "line": cleanup_line,
        })
    return_line = _last_return(function)
    terminal_line = return_line[1] if return_line else function.line_for_offset(len(function.text) - 1)
    events.append(_event("OperationReturn", roles, epoch, source_path, terminal_line))
    return SourceAnalysis(events, evidence, True, False, True, assumptions, function)


def analyze_source(
    binding: SourceBinding,
    source_path: str,
    function_name: str,
    source_version: str,
) -> SourceAnalysis:
    if binding.protocol_id == "fmpca.metadata_transition_outcome":
        return analyze_outcome_source(binding, source_path, function_name, source_version)
    if binding.protocol_id == "fmpca.failure_rollback_conformance":
        return analyze_rollback_source(binding, source_path, function_name, source_version)
    if binding.protocol_id == "fmpca.recovery_attachment_settlement":
        return analyze_rollback_source(binding, source_path, function_name, source_version)
    if binding.protocol_id == "fmpca.device_topology_rollback":
        return analyze_topology_source(binding, source_path, function_name, source_version)
    raise SourceBindingError(f"no source analyzer for protocol {binding.protocol_id}")
