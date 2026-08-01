"""Failure-aware Metadata Protocol Conformance Analyzer."""

from .analyzer import AnalyzerRun, ProtocolAnalyzer
from .dsl import ProtocolSpec, load_protocol
from .model import AnalysisResult, EvidenceEvent, ProtocolState
from .proof import AnalysisReport, analyze_state
from .semantics import ProtocolEngine

__all__ = [
    "AnalysisReport",
    "AnalysisResult",
    "AnalyzerRun",
    "EvidenceEvent",
    "ProtocolEngine",
    "ProtocolAnalyzer",
    "ProtocolSpec",
    "ProtocolState",
    "analyze_state",
    "load_protocol",
]

__version__ = "0.1.0"
