"""Serializable frontend-neutral IR shared by source and compiled frontends."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator


FRONTEND_IR_SCHEMA_VERSION = 1


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def _schema_version(data: dict[str, Any]) -> int:
    version = int(data.get("schema_version", FRONTEND_IR_SCHEMA_VERSION))
    if version != FRONTEND_IR_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported frontend IR schema version {version}; "
            f"expected {FRONTEND_IR_SCHEMA_VERSION}"
        )
    return version


@dataclass(frozen=True)
class AstPoint:
    row: int
    column: int = 0


@dataclass(frozen=True)
class SourceRange:
    file: str
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    start_column: int = 0
    end_column: int = 0
    expansion_file: str = ""
    expansion_start_byte: int = 0
    expansion_end_byte: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceRange":
        return cls(**data)


@dataclass
class FrontendNode:
    """Parser-neutral syntax node with compatibility accessors for existing analyses."""

    type: str
    text: str
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    children: list["FrontendNode"] = field(default_factory=list)
    field_map: dict[str, "FrontendNode"] = field(default_factory=dict)
    start_column: int = 0
    end_column: int = 0
    source_file: str = ""
    normalized_text: str = ""
    frontend_kind: str = "syntax"

    @property
    def kind(self) -> str:
        return self.type

    @property
    def spelling(self) -> str:
        return self.text

    @property
    def start_point(self) -> AstPoint:
        return AstPoint(self.start_line - 1, self.start_column)

    @property
    def end_point(self) -> AstPoint:
        return AstPoint(self.end_line - 1, self.end_column)

    @property
    def source_range(self) -> SourceRange:
        return SourceRange(
            file=self.source_file,
            start_byte=self.start_byte,
            end_byte=self.end_byte,
            start_line=self.start_line,
            end_line=self.end_line,
            start_column=self.start_column,
            end_column=self.end_column,
        )

    def child_by_field_name(self, name: str) -> "FrontendNode | None":
        return self.field_map.get(name)

    def walk(self) -> Iterator["FrontendNode"]:
        pending = [self]
        while pending:
            node = pending.pop()
            yield node
            pending.extend(reversed(node.children))

    def to_dict(self, *, include_spelling: bool = True) -> dict[str, Any]:
        child_indices = {id(child): index for index, child in enumerate(self.children)}
        data = {
            "kind": self.type,
            "frontend_kind": self.frontend_kind,
            "source_range": self.source_range.to_dict(),
            "children": [
                child.to_dict(include_spelling=include_spelling)
                for child in self.children
            ],
            "fields": {
                name: child_indices[id(child)]
                for name, child in sorted(self.field_map.items())
                if id(child) in child_indices
            },
        }
        if include_spelling:
            data["spelling"] = self.text
            data["normalized_text"] = self.normalized_text
        return data

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], source_bytes: bytes = b""
    ) -> "FrontendNode":
        source_range = SourceRange.from_dict(data["source_range"])
        children = [
            cls.from_dict(child, source_bytes=source_bytes)
            for child in data.get("children", [])
        ]
        fields = {
            name: children[index]
            for name, index in data.get("fields", {}).items()
            if 0 <= index < len(children)
        }
        spelling = data.get("spelling")
        if spelling is None and source_bytes:
            spelling = source_bytes[
                source_range.start_byte : source_range.end_byte
            ].decode("utf-8", errors="replace")
        spelling = spelling or ""
        return cls(
            type=data["kind"],
            text=spelling,
            normalized_text=data.get(
                "normalized_text", " ".join(spelling.strip().split())
            ),
            frontend_kind=data.get("frontend_kind", "syntax"),
            start_byte=source_range.start_byte,
            end_byte=source_range.end_byte,
            start_line=source_range.start_line,
            end_line=source_range.end_line,
            start_column=source_range.start_column,
            end_column=source_range.end_column,
            source_file=source_range.file,
            children=children,
            field_map=fields,
        )


@dataclass(frozen=True)
class FrontendDiagnostic:
    code: str
    message: str
    severity: str = "warning"
    recoverable: bool = True
    source_range: SourceRange | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "recoverable": self.recoverable,
            "source_range": self.source_range.to_dict() if self.source_range else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FrontendDiagnostic":
        source_range = data.get("source_range")
        return cls(
            code=data["code"],
            message=data["message"],
            severity=data.get("severity", "warning"),
            recoverable=bool(data.get("recoverable", True)),
            source_range=SourceRange.from_dict(source_range) if source_range else None,
        )


@dataclass(frozen=True)
class CompileCommandIR:
    compile_command_id: str
    directory: str
    file: str
    arguments: tuple[str, ...]
    source: str = "compile-database"

    def to_dict(self) -> dict[str, Any]:
        return {
            "compile_command_id": self.compile_command_id,
            "directory": self.directory,
            "file": self.file,
            "arguments": list(self.arguments),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompileCommandIR":
        return cls(
            compile_command_id=data["compile_command_id"],
            directory=data["directory"],
            file=data["file"],
            arguments=tuple(data.get("arguments", [])),
            source=data.get("source", "compile-database"),
        )


@dataclass(frozen=True)
class SymbolIR:
    symbol_id: str
    name: str
    kind: str
    type_spelling: str
    scope_id: str
    declaration_range: SourceRange
    parameter_index: int | None = None
    type_quality: str = "source-spelling"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["declaration_range"] = self.declaration_range.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SymbolIR":
        copied = dict(data)
        copied["declaration_range"] = SourceRange.from_dict(copied["declaration_range"])
        return cls(**copied)


@dataclass(frozen=True)
class CallIR:
    call_id: str
    callee_spelling: str
    callee_kind: str
    arguments: tuple[str, ...]
    possible_targets: tuple[str, ...]
    source_range: SourceRange
    result_spelling: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "callee_spelling": self.callee_spelling,
            "callee_kind": self.callee_kind,
            "arguments": list(self.arguments),
            "possible_targets": list(self.possible_targets),
            "source_range": self.source_range.to_dict(),
            "result_spelling": self.result_spelling,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CallIR":
        return cls(
            call_id=data["call_id"],
            callee_spelling=data["callee_spelling"],
            callee_kind=data["callee_kind"],
            arguments=tuple(data.get("arguments", [])),
            possible_targets=tuple(data.get("possible_targets", [])),
            source_range=SourceRange.from_dict(data["source_range"]),
            result_spelling=data.get("result_spelling", ""),
        )


@dataclass(frozen=True)
class AccessPathIR:
    spelling: str
    root_kind: str
    root_id: str
    dereference_depth: int
    fields: tuple[str, ...]
    index: str
    precision: str
    source_range: SourceRange
    role: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "spelling": self.spelling,
            "root_kind": self.root_kind,
            "root_id": self.root_id,
            "dereference_depth": self.dereference_depth,
            "fields": list(self.fields),
            "index": self.index,
            "precision": self.precision,
            "role": self.role,
            "source_range": self.source_range.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AccessPathIR":
        return cls(
            spelling=data["spelling"],
            root_kind=data["root_kind"],
            root_id=data["root_id"],
            dereference_depth=int(data.get("dereference_depth", 0)),
            fields=tuple(data.get("fields", [])),
            index=data.get("index", ""),
            precision=data.get("precision", "unknown"),
            source_range=SourceRange.from_dict(data["source_range"]),
            role=data.get("role", "unknown"),
        )


@dataclass
class FunctionIR:
    file: Path
    name: str
    signature: str
    source: str
    body: str
    start_line: int
    end_line: int
    body_start_line: int
    ast_node: FrontendNode | None = None
    body_node: FrontendNode | None = None
    parse_tree: Any | None = None
    source_start_byte: int = 0
    body_start_byte: int = 0
    file_bytes: bytes = b""
    parameters: set[str] = field(default_factory=set)
    analysis_quality: str = "tree-sitter"
    frontend_name: str = "tree-sitter"
    frontend_mode: str = "tree-sitter"
    frontend_schema_version: int = FRONTEND_IR_SCHEMA_VERSION
    translation_unit_id: str = ""
    function_id: str = ""
    return_type: str = ""
    symbols: list[SymbolIR] = field(default_factory=list)
    calls: list[CallIR] = field(default_factory=list)
    access_paths: list[AccessPathIR] = field(default_factory=list)
    diagnostics: list[FrontendDiagnostic] = field(default_factory=list)
    unsupported_features: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.translation_unit_id:
            self.translation_unit_id = _stable_id("tu", self.file.as_posix())
        if not self.function_id:
            self.function_id = _stable_id(
                "fn", self.translation_unit_id, self.name, self.source_start_byte
            )

    @property
    def source_range(self) -> SourceRange:
        end_byte = self.source_start_byte + len(
            self.source.encode("utf-8", errors="replace")
        )
        return SourceRange(
            file=self.file.as_posix(),
            start_byte=self.source_start_byte,
            end_byte=end_byte,
            start_line=self.start_line,
            end_line=self.end_line,
        )

    def to_dict(self, *, include_node_spelling: bool = True) -> dict[str, Any]:
        body_ref = None
        if self.body_node is not None:
            body_ref = {
                "kind": self.body_node.type,
                "start_byte": self.body_node.start_byte,
                "end_byte": self.body_node.end_byte,
            }
        return {
            "function_id": self.function_id,
            "translation_unit_id": self.translation_unit_id,
            "frontend_name": self.frontend_name,
            "frontend_mode": self.frontend_mode,
            "frontend_schema_version": self.frontend_schema_version,
            "file": self.file.as_posix(),
            "name": self.name,
            "signature": self.signature,
            "return_type": self.return_type,
            "source": self.source,
            "body": self.body,
            "source_range": self.source_range.to_dict(),
            "body_start_line": self.body_start_line,
            "body_start_byte": self.body_start_byte,
            "parameters": sorted(self.parameters),
            "analysis_quality": self.analysis_quality,
            "ast_node": (
                self.ast_node.to_dict(include_spelling=include_node_spelling)
                if self.ast_node
                else None
            ),
            "body_node_ref": body_ref,
            "symbols": [symbol.to_dict() for symbol in self.symbols],
            "calls": [call.to_dict() for call in self.calls],
            "access_paths": [path.to_dict() for path in self.access_paths],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
            "unsupported_features": list(self.unsupported_features),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], file_bytes: bytes = b"") -> "FunctionIR":
        version = int(
            data.get("frontend_schema_version", FRONTEND_IR_SCHEMA_VERSION)
        )
        if version != FRONTEND_IR_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported function IR schema version {version}; "
                f"expected {FRONTEND_IR_SCHEMA_VERSION}"
            )
        source_range = SourceRange.from_dict(data["source_range"])
        ast_node = (
            FrontendNode.from_dict(data["ast_node"], source_bytes=file_bytes)
            if data.get("ast_node")
            else None
        )
        body_node = None
        body_ref = data.get("body_node_ref")
        if ast_node is not None and body_ref:
            body_node = next(
                (
                    node
                    for node in ast_node.walk()
                    if node.type == body_ref.get("kind")
                    and node.start_byte == int(body_ref.get("start_byte", -1))
                    and node.end_byte == int(body_ref.get("end_byte", -1))
                ),
                None,
            )
        elif data.get("body_node"):
            body_node = FrontendNode.from_dict(
                data["body_node"], source_bytes=file_bytes
            )
        return cls(
            file=Path(data["file"]),
            name=data["name"],
            signature=data["signature"],
            source=data["source"],
            body=data["body"],
            start_line=source_range.start_line,
            end_line=source_range.end_line,
            body_start_line=int(data["body_start_line"]),
            ast_node=ast_node,
            body_node=body_node,
            source_start_byte=source_range.start_byte,
            body_start_byte=int(data.get("body_start_byte", 0)),
            file_bytes=file_bytes,
            parameters=set(data.get("parameters", [])),
            analysis_quality=data.get("analysis_quality", "tree-sitter"),
            frontend_name=data.get("frontend_name", "unknown"),
            frontend_mode=data.get("frontend_mode", data.get("analysis_quality", "unknown")),
            frontend_schema_version=version,
            translation_unit_id=data.get("translation_unit_id", ""),
            function_id=data.get("function_id", ""),
            return_type=data.get("return_type", ""),
            symbols=[SymbolIR.from_dict(item) for item in data.get("symbols", [])],
            calls=[CallIR.from_dict(item) for item in data.get("calls", [])],
            access_paths=[
                AccessPathIR.from_dict(item) for item in data.get("access_paths", [])
            ],
            diagnostics=[
                FrontendDiagnostic.from_dict(item)
                for item in data.get("diagnostics", [])
            ],
            unsupported_features=list(data.get("unsupported_features", [])),
        )


@dataclass(frozen=True)
class CFGEdgeIR:
    source: int
    target: int
    kind: str = "fallthrough"
    condition: str = ""
    scope_unwind: int = 0

    @property
    def edge_id(self) -> str:
        return f"e{self.source}_{self.target}_{self.kind}_u{self.scope_unwind}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CFGEdgeIR":
        return cls(**data)


@dataclass
class BasicBlockIR:
    id: int
    kind: str
    text: str = ""
    start_line: int = 0
    end_line: int = 0
    label: str = ""
    start_byte: int = 0
    end_byte: int = 0
    condition_start_byte: int = 0
    condition_end_byte: int = 0
    scope_depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BasicBlockIR":
        return cls(**data)


@dataclass
class ControlFlowGraphIR:
    blocks: dict[int, BasicBlockIR]
    edges: list[CFGEdgeIR]
    entry: int
    exit: int
    labels: dict[str, int] = field(default_factory=dict)
    unsupported_nodes: list[str] = field(default_factory=list)
    unsupported_blocks: dict[int, list[str]] = field(default_factory=dict)
    unsupported_ranges: list[dict[str, int | str]] = field(default_factory=list)
    schema_version: int = FRONTEND_IR_SCHEMA_VERSION

    def successors(self, block_id: int) -> list[CFGEdgeIR]:
        return [edge for edge in self.edges if edge.source == block_id]

    def predecessors(self, block_id: int) -> list[CFGEdgeIR]:
        return [edge for edge in self.edges if edge.target == block_id]

    def block_at_line(self, line: int) -> BasicBlockIR | None:
        matches = [
            block
            for block in self.blocks.values()
            if block.start_line <= line <= block.end_line and block.start_line
        ]
        if not matches:
            return None
        return min(
            matches,
            key=lambda block: (block.end_line - block.start_line, block.id),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "entry": self.entry,
            "exit": self.exit,
            "blocks": [self.blocks[key].to_dict() for key in sorted(self.blocks)],
            "edges": [edge.to_dict() for edge in self.edges],
            "labels": dict(sorted(self.labels.items())),
            "unsupported_nodes": list(self.unsupported_nodes),
            "unsupported_blocks": {
                str(key): list(value)
                for key, value in sorted(self.unsupported_blocks.items())
            },
            "unsupported_ranges": list(self.unsupported_ranges),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ControlFlowGraphIR":
        version = _schema_version(data)
        blocks = [BasicBlockIR.from_dict(item) for item in data.get("blocks", [])]
        return cls(
            blocks={block.id: block for block in blocks},
            edges=[CFGEdgeIR.from_dict(item) for item in data.get("edges", [])],
            entry=int(data["entry"]),
            exit=int(data["exit"]),
            labels={key: int(value) for key, value in data.get("labels", {}).items()},
            unsupported_nodes=list(data.get("unsupported_nodes", [])),
            unsupported_blocks={
                int(key): list(value)
                for key, value in data.get("unsupported_blocks", {}).items()
            },
            unsupported_ranges=list(data.get("unsupported_ranges", [])),
            schema_version=version,
        )


@dataclass
class TranslationUnitIR:
    path: Path
    source_text: str
    frontend_name: str
    frontend_mode: str
    functions: list[FunctionIR]
    diagnostics: list[FrontendDiagnostic] = field(default_factory=list)
    compile_command: CompileCommandIR | None = None
    schema_version: int = FRONTEND_IR_SCHEMA_VERSION
    translation_unit_id: str = ""
    identity_path: str = ""

    def __post_init__(self) -> None:
        source_digest = hashlib.sha256(
            self.source_text.encode("utf-8", errors="replace")
        ).hexdigest()
        if not self.translation_unit_id:
            self.translation_unit_id = _stable_id(
                "tu", self.identity_path or self.path.as_posix(), source_digest
            )
        source_bytes = self.source_text.encode("utf-8", errors="replace")
        for function in self.functions:
            function.translation_unit_id = self.translation_unit_id
            function.frontend_name = self.frontend_name
            function.frontend_mode = self.frontend_mode
            function.frontend_schema_version = self.schema_version
            function.file_bytes = source_bytes
            function.function_id = _stable_id(
                "fn",
                self.translation_unit_id,
                function.name,
                function.source_start_byte,
            )

    @property
    def warnings(self) -> list[str]:
        return [diagnostic.message for diagnostic in self.diagnostics]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "translation_unit_id": self.translation_unit_id,
            "path": self.path.as_posix(),
            "identity_path": self.identity_path or self.path.as_posix(),
            "source_text": self.source_text,
            "frontend_name": self.frontend_name,
            "frontend_mode": self.frontend_mode,
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
            "compile_command": (
                self.compile_command.to_dict() if self.compile_command else None
            ),
            "functions": [
                function.to_dict(include_node_spelling=False)
                for function in self.functions
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranslationUnitIR":
        version = _schema_version(data)
        source_text = data.get("source_text", "")
        source_bytes = source_text.encode("utf-8", errors="replace")
        return cls(
            path=Path(data["path"]),
            source_text=source_text,
            frontend_name=data["frontend_name"],
            frontend_mode=data["frontend_mode"],
            functions=[
                FunctionIR.from_dict(item, file_bytes=source_bytes)
                for item in data.get("functions", [])
            ],
            diagnostics=[
                FrontendDiagnostic.from_dict(item)
                for item in data.get("diagnostics", [])
            ],
            compile_command=(
                CompileCommandIR.from_dict(data["compile_command"])
                if data.get("compile_command")
                else None
            ),
            schema_version=version,
            translation_unit_id=data.get("translation_unit_id", ""),
            identity_path=data.get("identity_path", data["path"]),
        )

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, payload: str) -> "TranslationUnitIR":
        return cls.from_dict(json.loads(payload))
