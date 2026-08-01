from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from .dsl import ProtocolSpec
from .instance import InstanceStore
from .model import AnalysisResult, EvidenceEvent
from .proof import AnalysisReport, analyze_state
from .semantics import ProtocolEngine


RESULT_PRIORITY = {
    AnalysisResult.NO_APPLICABLE_PROTOCOL: 0,
    AnalysisResult.CONFORMANT: 1,
    AnalysisResult.INCOMPLETE: 2,
    AnalysisResult.POSSIBLE_VIOLATION: 3,
    AnalysisResult.VIOLATION: 4,
}


@dataclass
class AnalyzerRun:
    result: AnalysisResult
    reports: List[AnalysisReport]
    candidate_overflow: bool
    event_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "result": self.result.value,
            "candidate_overflow": self.candidate_overflow,
            "event_count": self.event_count,
            "instance_count": len(self.reports),
            "instances": [report.to_dict() for report in self.reports],
        }


class ProtocolAnalyzer:
    def __init__(self, spec: ProtocolSpec, *, candidate_budget: int = 8):
        self.spec = spec
        self.engine = ProtocolEngine(spec)
        self.store = InstanceStore(spec, candidate_budget=candidate_budget)

    def run(
        self,
        events: Iterable[EvidenceEvent],
        *,
        path_model_closed: bool = True,
        all_paths_closed: bool = False,
        repair_slice_closed: bool = True,
        alias_closed: bool = True,
    ) -> AnalyzerRun:
        count = 0
        overflow = False
        touched = {}
        for event in events:
            count += 1
            selected = self.store.select_or_create(event)
            overflow = overflow or selected.overflowed
            for instance in selected.candidates:
                instance.state = self.engine.apply_event(instance.state, event)
                touched[instance.instance_id] = instance
        reports = [
            analyze_state(
                instance.state,
                path_model_closed=path_model_closed,
                all_paths_closed=all_paths_closed,
                repair_slice_closed=repair_slice_closed,
                alias_closed=alias_closed and not overflow,
            )
            for instance in touched.values()
        ]
        if not reports:
            state = self.engine.initial_state()
            if overflow:
                state.applicable = True
                state.alias_closed = False
                state.assumptions.append("candidate_instance_identity_incomplete")
                result = AnalysisResult.INCOMPLETE
            else:
                result = AnalysisResult.NO_APPLICABLE_PROTOCOL
            reports = [
                analyze_state(
                    state,
                    path_model_closed=path_model_closed,
                    all_paths_closed=all_paths_closed,
                    repair_slice_closed=repair_slice_closed,
                    alias_closed=not overflow,
                )
            ]
            if overflow:
                reports[0].result = AnalysisResult.INCOMPLETE
                reports[0].reasons = ["required instance anchors are incomplete"]
            return AnalyzerRun(result, reports, overflow, count)
        result = max((report.result for report in reports), key=lambda item: RESULT_PRIORITY[item])
        if overflow and RESULT_PRIORITY[result] < RESULT_PRIORITY[AnalysisResult.INCOMPLETE]:
            result = AnalysisResult.INCOMPLETE
        return AnalyzerRun(result, reports, overflow, count)
