"""Caller-site provenance for automatic operation descriptor arguments."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from ..frontend.model import FrontendNode, FunctionIR, SourceRange, SymbolIR
from ..parser import compact_ws


@dataclass(frozen=True)
class TransientArgumentProvenance:
    """Proof that one callee parameter always denotes caller stack storage."""

    parameter: str
    parameter_index: int
    pointee_type: str
    caller_function: str
    caller_local: str
    caller_local_type: str
    call_site: SourceRange

    def to_dict(self) -> dict[str, object]:
        return {
            "parameter": self.parameter,
            "parameter_index": self.parameter_index,
            "pointee_type": self.pointee_type,
            "caller_function": self.caller_function,
            "caller_local": self.caller_local,
            "caller_local_type": self.caller_local_type,
            "call_site": self.call_site.to_dict(),
        }


def infer_transient_argument_provenance(
    functions: Iterable[FunctionIR],
) -> dict[str, tuple[TransientArgumentProvenance, ...]]:
    """Infer exact-root transient parameters from all visible call sites.

    The rule is deliberately universal: every visible direct call to a unique
    function must pass the address of a type-compatible automatic aggregate.
    The caller may lend that object to helpers, but it may not return its
    address or write the address into non-local storage. Unique visible helper
    bodies are checked recursively; opaque calls are synchronous borrows rather
    than inferred stores. The callee parameter may be copied into local
    aggregates, but explicit source-visible returns or non-local stores reject.
    """

    function_tuple = tuple(functions)
    definitions: dict[str, list[FunctionIR]] = {}
    for function in function_tuple:
        if function.body_node is not None:
            definitions.setdefault(function.name, []).append(function)
    callsites: dict[str, list[tuple[FunctionIR, object]]] = {}
    for caller in function_tuple:
        for call in caller.calls:
            if call.callee_kind == "direct":
                callsites.setdefault(call.callee_spelling, []).append((caller, call))

    result: dict[str, tuple[TransientArgumentProvenance, ...]] = {}
    escape_cache: dict[tuple[str, str, tuple[str, ...]], bool] = {}
    for name, items in definitions.items():
        if len(items) != 1 or name not in callsites:
            continue
        callee = items[0]
        parameters = sorted(
            (symbol for symbol in callee.symbols if symbol.kind == "parameter"),
            key=lambda symbol: symbol.parameter_index
            if symbol.parameter_index is not None
            else 1 << 30,
        )
        accepted: list[TransientArgumentProvenance] = []
        for parameter in parameters:
            if parameter.parameter_index is None:
                continue
            pointee_type = _aggregate_pointee_type(parameter.type_spelling)
            if not pointee_type or _identity_published_or_returned(
                callee,
                parameter.name,
                definitions=definitions,
                cache=escape_cache,
                active=set(),
                tainted_fields=(),
            ):
                continue
            evidence: list[TransientArgumentProvenance] = []
            valid = True
            for caller, call in callsites[name]:
                if parameter.parameter_index >= len(call.arguments):
                    valid = False
                    break
                local_name = _addressed_identifier(call.arguments[parameter.parameter_index])
                local_symbol = next(
                    (
                        symbol
                        for symbol in caller.symbols
                        if symbol.kind == "local" and symbol.name == local_name
                    ),
                    None,
                )
                if (
                    not local_name
                    or local_symbol is None
                    or not _local_symbol_is_automatic(caller, local_symbol)
                    or _aggregate_value_type(local_symbol.type_spelling) != pointee_type
                    or _identity_published_or_returned(
                        caller,
                        local_name,
                        definitions=definitions,
                        cache=escape_cache,
                        active=set(),
                        tainted_fields=(),
                    )
                ):
                    valid = False
                    break
                evidence.append(
                    TransientArgumentProvenance(
                        parameter=parameter.name,
                        parameter_index=parameter.parameter_index,
                        pointee_type=pointee_type,
                        caller_function=caller.name,
                        caller_local=local_name,
                        caller_local_type=_clean_type(local_symbol.type_spelling),
                        call_site=call.source_range,
                    )
                )
            if valid and evidence:
                accepted.extend(evidence)
        if accepted:
            result[callee.function_id] = tuple(accepted)
    return result


def _identity_published_or_returned(
    function: FunctionIR,
    seed: str,
    *,
    definitions: dict[str, list[FunctionIR]],
    cache: dict[tuple[str, str, tuple[str, ...]], bool],
    active: set[tuple[str, str, tuple[str, ...]]],
    tainted_fields: tuple[str, ...],
) -> bool:
    """Track direct local aliases/containers until no new identity carrier exists.

    This is an escape proof, not general points-to analysis.  A local pointer or
    aggregate initialized from the seed becomes another identity carrier.  If
    any carrier is returned or copied into non-local storage, the proof fails.
    Unique visible callees are checked recursively. Opaque calls remain
    synchronous borrows: a call is not itself evidence that an automatic
    object's address was stored. Explicit source-visible stores and returns
    still reject the proof.
    """

    if function.body_node is None:
        return True
    proof_key = (function.function_id, seed, tuple(sorted(tainted_fields)))
    if proof_key in cache:
        return cache[proof_key]
    if proof_key in active:
        return False
    active.add(proof_key)
    local_names = {symbol.name for symbol in function.symbols if symbol.kind == "local"}
    symbols = {symbol.name: symbol for symbol in function.symbols}
    carriers = set() if tainted_fields else {seed}
    containers: dict[str, set[str]] = (
        {seed: set(tainted_fields)} if tainted_fields else {}
    )
    nodes = tuple(function.body_node.walk())
    changed = True
    while changed:
        changed = False
        for node in nodes:
            if node.type not in {"assignment_expression", "init_declarator"}:
                continue
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right") or node.child_by_field_name("value")
            if right is None:
                continue
            target = compact_ws(left.text) if left is not None else _declared_name(node)
            target_root = _leading_identifier(target)
            direct_source = _simple_direct_identity(right.text, carriers) or bool(
                _tainted_field_identity(right.text, containers)
            )
            if node.type == "init_declarator" and target_root in local_names:
                fields = _compound_initializer_identity_fields(
                    right.text, carriers, containers
                )
                if fields - containers.get(target_root, set()):
                    containers.setdefault(target_root, set()).update(fields)
                    changed = True
            if not direct_source:
                continue
            target_field = _member_field(target)
            target_symbol = symbols.get(target_root)
            if not target or target_root not in local_names or target_symbol is None:
                active.remove(proof_key)
                cache[proof_key] = True
                return True
            if target_field:
                if _aggregate_value_type(target_symbol.type_spelling):
                    if target_field not in containers.setdefault(target_root, set()):
                        containers[target_root].add(target_field)
                        changed = True
                    continue
                active.remove(proof_key)
                cache[proof_key] = True
                return True
            if "*" not in _clean_type(target_symbol.type_spelling):
                continue
            if target_root not in carriers:
                carriers.add(target_root)
                changed = True
    for node in nodes:
        if node.type == "return_statement" and (
            any(_returns_identity(node.text, carrier) for carrier in carriers)
            or _simple_container_identity(node.text, containers) is not None
            or bool(_tainted_field_identity(node.text, containers))
        ):
            active.remove(proof_key)
            cache[proof_key] = True
            return True
    for call in function.calls:
        for index, argument in enumerate(call.arguments):
            direct_identity = any(
                _argument_carries_identity(argument, carrier)
                for carrier in carriers
            ) or bool(_tainted_field_identity(argument, containers))
            container_identity = _simple_container_identity(argument, containers)
            if not direct_identity and container_identity is None:
                continue
            if _is_observer_call(call.callee_spelling):
                continue
            if call.callee_kind != "direct":
                continue
            targets = definitions.get(call.callee_spelling, ())
            if len(targets) != 1:
                continue
            target_parameter = _parameter_at_index(targets[0], index)
            if target_parameter is None or not _type_can_carry_pointer_identity(
                target_parameter.type_spelling
            ):
                continue
            if _identity_published_or_returned(
                targets[0],
                target_parameter.name,
                definitions=definitions,
                cache=cache,
                active=active,
                tainted_fields=(
                    tuple(sorted(containers[container_identity]))
                    if container_identity is not None and not direct_identity
                    else ()
                ),
            ):
                active.remove(proof_key)
                cache[proof_key] = True
                return True
    active.remove(proof_key)
    cache[proof_key] = False
    return False


def _contains_pointer_identity(text: str, symbol: str) -> bool:
    value = compact_ws(text)
    return bool(
        re.search(
            rf"(?<![.*>])&?\s*\b{re.escape(symbol)}\b(?!\s*(?:->|\.))",
            value,
        )
    )


def _argument_carries_identity(argument: str, carrier: str) -> bool:
    return _contains_pointer_identity(argument, carrier)


def _simple_direct_identity(text: str, carriers: set[str]) -> bool:
    value = compact_ws(text).strip().rstrip(";").strip()
    return any(
        re.fullmatch(
            rf"(?:\([^)]*\)\s*)?[&*()\s]*{re.escape(carrier)}[()\s]*",
            value,
        )
        is not None
        for carrier in carriers
    )


def _tainted_field_identity(
    text: str, containers: dict[str, set[str]]
) -> tuple[str, str] | None:
    value = compact_ws(text).strip().rstrip(";").strip()
    value = re.sub(r"^return\s+", "", value).strip()
    for container, fields in containers.items():
        for field in fields:
            if re.fullmatch(
                rf"(?:\([^)]*\)\s*)?[&*()\s]*{re.escape(container)}\s*"
                rf"(?:->|\.)\s*{re.escape(field)}[()\s]*",
                value,
            ):
                return container, field
    return None


def _simple_container_identity(
    text: str, containers: dict[str, set[str]]
) -> str | None:
    value = compact_ws(text).strip().rstrip(";").strip()
    value = re.sub(r"^return\s+", "", value).strip()
    for container in containers:
        if re.fullmatch(
            rf"(?:\([^)]*\)\s*)?[&*()\s]*{re.escape(container)}[()\s]*",
            value,
        ):
            return container
    return None


def _compound_initializer_identity_fields(
    text: str,
    carriers: set[str],
    containers: dict[str, set[str]],
) -> set[str]:
    result: set[str] = set()
    for match in re.finditer(
        r"\.\s*([A-Za-z_]\w*)\s*=\s*([^,}]+)", compact_ws(text)
    ):
        if _simple_direct_identity(match.group(2), carriers) or _tainted_field_identity(
            match.group(2), containers
        ):
            result.add(match.group(1))
    return result


def _member_field(text: str) -> str:
    match = re.fullmatch(
        r"[&*()\s]*[A-Za-z_]\w*\s*(?:->|\.)\s*([A-Za-z_]\w*)",
        compact_ws(text),
    )
    return match.group(1) if match else ""


def _is_observer_call(name: str) -> bool:
    return name.startswith("trace_")


def _parameter_at_index(function: FunctionIR, index: int) -> SymbolIR | None:
    return next(
        (
            symbol
            for symbol in function.symbols
            if symbol.kind == "parameter" and symbol.parameter_index == index
        ),
        None,
    )


def _local_symbol_is_automatic(function: FunctionIR, symbol: SymbolIR) -> bool:
    if function.body_node is None:
        return False
    for node in function.body_node.walk():
        if node.type != "declaration":
            continue
        if not (node.start_byte <= symbol.declaration_range.start_byte <= node.end_byte):
            continue
        storage = {
            compact_ws(child.text)
            for child in node.children
            if child.type == "storage_class_specifier"
        }
        return not bool(storage & {"static", "extern", "_Thread_local", "thread_local"})
    return False


def _type_can_carry_pointer_identity(type_spelling: str) -> bool:
    value = _clean_type(type_spelling)
    return "*" in value or bool(re.search(r"\b(?:struct|union)\s+[A-Za-z_]\w*", value))


def _returns_identity(text: str, symbol: str) -> bool:
    value = re.sub(r"^\s*return\s+", "", compact_ws(text)).rstrip(";").strip()
    return re.fullmatch(rf"[&*()\s]*{re.escape(symbol)}[()\s]*", value) is not None


def _addressed_identifier(argument: str) -> str:
    value = compact_ws(argument).strip()
    match = re.fullmatch(r"&\s*\(?\s*([A-Za-z_]\w*)\s*\)?", value)
    return match.group(1) if match else ""


def _aggregate_pointee_type(type_spelling: str) -> str:
    value = _clean_type(type_spelling)
    if "*" not in value:
        return ""
    match = re.search(r"\b(struct|union)\s+([A-Za-z_]\w*)", value)
    return f"{match.group(1)} {match.group(2)}" if match else ""


def _aggregate_value_type(type_spelling: str) -> str:
    value = _clean_type(type_spelling)
    if "*" in value or "[" in value:
        return ""
    match = re.search(r"\b(struct|union)\s+([A-Za-z_]\w*)", value)
    return f"{match.group(1)} {match.group(2)}" if match else ""


def _clean_type(value: str) -> str:
    return compact_ws(value).strip().rstrip(";,").strip()


def _declared_name(node: FrontendNode) -> str:
    declarator = node.child_by_field_name("declarator")
    if declarator is None:
        return ""
    identifiers = [child.text for child in declarator.walk() if child.type == "identifier"]
    return compact_ws(identifiers[-1]) if identifiers else ""


def _leading_identifier(text: str) -> str:
    match = re.match(r"[&*()\s]*([A-Za-z_]\w*)", compact_ws(text))
    return match.group(1) if match else ""
