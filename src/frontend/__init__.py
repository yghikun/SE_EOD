"""Versioned frontend-neutral intermediate representation."""

from .base import Frontend
from .model import (
    FRONTEND_IR_SCHEMA_VERSION,
    AccessPathIR,
    AstPoint,
    BasicBlockIR,
    CallIR,
    CompileCommandIR,
    CFGEdgeIR,
    ControlFlowGraphIR,
    FrontendDiagnostic,
    FrontendNode,
    FunctionIR,
    SourceRange,
    SymbolIR,
    TranslationUnitIR,
)

__all__ = [
    "FRONTEND_IR_SCHEMA_VERSION",
    "AccessPathIR",
    "AstPoint",
    "BasicBlockIR",
    "CallIR",
    "CompileCommandIR",
    "CFGEdgeIR",
    "ControlFlowGraphIR",
    "Frontend",
    "FrontendDiagnostic",
    "FrontendNode",
    "FunctionIR",
    "SourceRange",
    "SymbolIR",
    "TranslationUnitIR",
    "TreeSitterFrontend",
]


def __getattr__(name: str):
    if name == "TreeSitterFrontend":
        from .tree_sitter_frontend import TreeSitterFrontend

        return TreeSitterFrontend
    raise AttributeError(name)
