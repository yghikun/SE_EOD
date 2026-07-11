"""Load manual review labels and compute score adjustments."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


TRUE_CANDIDATE = "true_candidate"
FALSE_POSITIVE = "false_positive"
UNCERTAIN = "uncertain"
VALID_VERDICTS = {TRUE_CANDIDATE, FALSE_POSITIVE, UNCERTAIN}
VERDICT_ALIASES = {
    "true_bug": TRUE_CANDIDATE,
    "bug": TRUE_CANDIDATE,
    "fixed": TRUE_CANDIDATE,
    "upstream_fixed": TRUE_CANDIDATE,
    "confirmed_bug": TRUE_CANDIDATE,
    "confirmed_true_positive": TRUE_CANDIDATE,
    "confirmed_false_positive": FALSE_POSITIVE,
    "false_alarm": FALSE_POSITIVE,
    "intended_behavior": FALSE_POSITIVE,
    "not_a_bug": FALSE_POSITIVE,
}

CODEX_STATIC_REVIEW = "codex_static_review"
HUMAN_MANUAL_REVIEW = "human_manual_review"
UPSTREAM_CONFIRMED = "upstream_confirmed"
VALID_REVIEW_SOURCES = {
    CODEX_STATIC_REVIEW,
    HUMAN_MANUAL_REVIEW,
    UPSTREAM_CONFIRMED,
}

SOURCE_ADJUSTMENTS = {
    CODEX_STATIC_REVIEW: {
        TRUE_CANDIDATE: {"high": 25, "medium": 15, "low": 5},
        FALSE_POSITIVE: {"high": -30, "medium": -15, "low": -5},
        UNCERTAIN: {"high": -5, "medium": -5, "low": -5},
    },
    HUMAN_MANUAL_REVIEW: {
        TRUE_CANDIDATE: {"high": 50, "medium": 30, "low": 10},
        FALSE_POSITIVE: {"high": -60, "medium": -30, "low": -10},
        UNCERTAIN: {"high": -5, "medium": -5, "low": -5},
    },
    UPSTREAM_CONFIRMED: {
        TRUE_CANDIDATE: {"high": 100, "medium": 100, "low": 100},
        FALSE_POSITIVE: {"high": -100, "medium": -100, "low": -100},
        UNCERTAIN: {"high": -5, "medium": -5, "low": -5},
    },
}


@dataclass(frozen=True)
class ManualReviewLabel:
    candidate_id: str
    verdict: str
    confidence: str = "medium"
    reason: str = ""
    confirmed_exception: bool = False
    confirmed_exception_type: str | None = None
    suggested_rule_update: str | None = None
    next_action: str | None = None
    validation_hint: str | None = None
    review_source: str = ""
    reviewer: str = "manual"
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "verdict", verdict_for(self.verdict))
        object.__setattr__(
            self,
            "review_source",
            review_source_for(self.review_source, self.reviewer),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ManualReviewLabel":
        exception_type = data.get("confirmed_exception_type")
        rule_update = data.get("suggested_rule_update")
        next_action = data.get("next_action")
        validation_hint = data.get("validation_hint")
        reviewer = str(data.get("reviewer", "manual"))
        return cls(
            candidate_id=str(data.get("candidate_id", "")).strip(),
            verdict=verdict_for(data.get("verdict")),
            confidence=str(data.get("confidence", "medium")).strip() or "medium",
            reason=str(data.get("reason", "")),
            confirmed_exception=bool(data.get("confirmed_exception", False)),
            confirmed_exception_type=str(exception_type).strip()
            if exception_type is not None and str(exception_type).strip()
            else None,
            suggested_rule_update=str(rule_update).strip()
            if rule_update is not None and str(rule_update).strip()
            else None,
            next_action=str(next_action).strip()
            if next_action is not None and str(next_action).strip()
            else None,
            validation_hint=str(validation_hint).strip()
            if validation_hint is not None and str(validation_hint).strip()
            else None,
            review_source=review_source_for(
                data.get("review_source"),
                reviewer,
            ),
            reviewer=reviewer,
            notes=str(data.get("notes", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "reason": self.reason,
            "confirmed_exception": self.confirmed_exception,
            "confirmed_exception_type": self.confirmed_exception_type,
            "suggested_rule_update": self.suggested_rule_update,
            "next_action": self.next_action,
            "validation_hint": self.validation_hint,
            "review_source": self.review_source,
            "reviewer": self.reviewer,
            "notes": self.notes,
        }


@dataclass
class ManualReviewDB:
    labels: dict[str, ManualReviewLabel] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def load_from_file(cls, path: str | Path | None) -> "ManualReviewDB":
        db = cls()
        if not path:
            return db
        source = Path(path)
        if not source.exists() or not source.is_file():
            db.warnings.append(f"manual_review_labels_missing: {source}")
            return db

        try:
            lines = source.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            db.warnings.append(f"{source}: {type(exc).__name__}: {exc}")
            return db

        for line_no, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                db.warnings.append(f"{source}:{line_no}: JSONDecodeError: {exc}")
                continue
            if not isinstance(raw, dict):
                db.warnings.append(f"{source}:{line_no}: expected JSON object")
                continue
            try:
                label = ManualReviewLabel.from_dict(raw)
            except Exception as exc:
                db.warnings.append(f"{source}:{line_no}: {type(exc).__name__}: {exc}")
                continue
            if not label.candidate_id:
                continue
            if label.verdict not in VALID_VERDICTS:
                db.warnings.append(
                    f"{source}:{line_no}: ignored manual review label with "
                    f"unsupported verdict: {label.verdict}"
                )
                continue
            db.labels[label.candidate_id] = label
        return db

    def find(self, candidate_id: str) -> ManualReviewLabel | None:
        return self.labels.get(candidate_id)

    def find_any(self, candidate_ids: list[str]) -> ManualReviewLabel | None:
        for candidate_id in candidate_ids:
            label = self.find(candidate_id)
            if label:
                return label
        return None


def manual_score_adjustment(label: ManualReviewLabel | None) -> tuple[int, list[str]]:
    if label is None:
        return 0, []

    explanation: list[str] = []
    confidence = _confidence_key(label.confidence)
    verdict = verdict_for(label.verdict)
    source = review_source_for(label.review_source, label.reviewer)
    adjustment = SOURCE_ADJUSTMENTS[source][verdict][confidence]

    explanation.append(
        f"{source} {verdict} {confidence} confidence {adjustment:+d}"
    )

    if label.confirmed_exception:
        exception_type = (label.confirmed_exception_type or "").lower()
        if exception_type:
            explanation.append(f"{source} confirmed exception noted: {exception_type}")

    return adjustment, explanation


def review_source_for(source: Any, reviewer: Any = None) -> str:
    explicit = _normalize_source(source)
    if explicit:
        return explicit

    reviewer_text = str(reviewer or "").strip().lower()
    if "upstream" in reviewer_text:
        return UPSTREAM_CONFIRMED
    if "codex" in reviewer_text or "static_review" in reviewer_text:
        return CODEX_STATIC_REVIEW
    return HUMAN_MANUAL_REVIEW


def verdict_for(verdict: Any) -> str:
    value = str(verdict or "").strip().lower()
    return VERDICT_ALIASES.get(value, value)


def _normalize_source(source: Any) -> str | None:
    value = str(source or "").strip().lower()
    if not value:
        return None
    aliases = {
        "codex": CODEX_STATIC_REVIEW,
        "static_review": CODEX_STATIC_REVIEW,
        "llm_static_review": CODEX_STATIC_REVIEW,
        "manual": HUMAN_MANUAL_REVIEW,
        "human": HUMAN_MANUAL_REVIEW,
        "human_review": HUMAN_MANUAL_REVIEW,
        "upstream": UPSTREAM_CONFIRMED,
        "upstream_confirmation": UPSTREAM_CONFIRMED,
    }
    value = aliases.get(value, value)
    return value if value in VALID_REVIEW_SOURCES else None


def _confidence_key(confidence: str) -> str:
    value = str(confidence or "").strip().lower()
    return value if value in {"high", "medium", "low"} else "medium"
