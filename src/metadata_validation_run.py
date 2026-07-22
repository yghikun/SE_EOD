"""Run frozen MOCC-SE protocols on validation samples without exposing labels."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .frontend.tree_sitter_frontend import TreeSitterFrontend
from .metadata_protocol import MetadataProtocol
from .metadata_protocol_analyzer import analyze_function
from .metadata_protocol_discovery import operation_applicability
from .metadata_validation_labels import (
    AdjudicationSet,
    ReviewerLabelSet,
    validate_adjudication_set,
    validate_reviewer_label_set,
)
from .metadata_validation_manifest import (
    DEFAULT_FREEZE,
    DEFAULT_MANIFEST,
    ProtocolFreeze,
    ValidationManifest,
    ValidationSample,
    validate_protocol_freeze,
    validate_validation_manifest,
)


VALIDATION_RUN_SCHEMA_VERSION = 1
PREDICTION_VERDICTS = {"legal", "violation", "analysis_unknown", "out_of_scope"}


class MetadataValidationRunError(ValueError):
    """A validation run cannot produce an auditable result."""


def run_validation(
    *,
    workspace: str | Path = ".",
    freeze_path: str | Path = DEFAULT_FREEZE,
    manifest_path: str | Path = DEFAULT_MANIFEST,
    labels: Iterable[str | Path] = (),
    adjudication_path: str | Path = "",
    require_complete_labels: bool = False,
) -> dict[str, Any]:
    root = Path(workspace).resolve()
    freeze = ProtocolFreeze.read_json(root / freeze_path)
    manifest = ValidationManifest.read_json(root / manifest_path)
    validate_protocol_freeze(freeze, root)
    validate_validation_manifest(manifest, freeze, root)

    label_sets = tuple(ReviewerLabelSet.read_json(root / item) for item in labels)
    for label_set in label_sets:
        validate_reviewer_label_set(
            label_set,
            manifest,
            freeze,
            root,
            require_complete=require_complete_labels,
        )

    adjudication = None
    if adjudication_path:
        adjudication = AdjudicationSet.read_json(root / adjudication_path)
        validate_adjudication_set(
            adjudication,
            manifest,
            freeze,
            label_sets,
            root,
            require_complete=require_complete_labels,
        )

    protocols = _frozen_protocols(root, freeze)
    predictions = tuple(
        _predict_sample(root, sample, protocols) for sample in manifest.samples
    )
    summary = _prediction_summary(predictions, manifest)
    metrics = _metrics(predictions, adjudication)
    agreement = _reviewer_agreement(manifest, label_sets)
    return {
        "schema_version": VALIDATION_RUN_SCHEMA_VERSION,
        "result_semantics": "frozen_protocol_predictions_not_bug_claims",
        "freeze_id": freeze.freeze_id,
        "manifest_id": manifest.manifest_id,
        "dataset_split": manifest.dataset_split,
        "label_visibility": manifest.label_visibility,
        "summary": summary,
        "coverage_gate": {
            "status": (
                "ready_for_labeled_evaluation"
                if summary["analyzable_samples"] == summary["samples"]
                else "insufficient_protocol_applicability"
            ),
            "all_samples_analyzable": (
                summary["analyzable_samples"] == summary["samples"]
            ),
            "metrics_must_not_treat_out_of_scope_as_legal": True,
        },
        "label_gate": {
            "reviewer_label_sets": len(label_sets),
            "reviewer_statuses": [item.status for item in label_sets],
            "adjudication_status": adjudication.status if adjudication else "not_supplied",
            "metrics_available": metrics is not None,
        },
        "reviewer_agreement": agreement,
        "metrics": metrics,
        "predictions": list(predictions),
    }


def _frozen_protocols(
    root: Path, freeze: ProtocolFreeze
) -> dict[str, MetadataProtocol]:
    protocols: dict[str, MetadataProtocol] = {}
    for artifact in freeze.artifacts:
        if artifact.artifact_kind != "protocol_manifest":
            continue
        protocol = MetadataProtocol.read_json(root / artifact.path)
        protocols[protocol.protocol_id] = protocol
    return protocols


def _predict_sample(
    root: Path,
    sample: ValidationSample,
    protocols: dict[str, MetadataProtocol],
) -> dict[str, Any]:
    protocol = protocols.get(sample.protocol_id)
    if protocol is None:
        raise MetadataValidationRunError(
            f"{sample.sample_id}: frozen protocol {sample.protocol_id!r} is unavailable"
        )
    source = root / sample.source_path
    unit = TreeSitterFrontend(source_root=source.parent).parse(source)
    functions = {item.name: item for item in unit.functions}
    function_predictions = []
    for function_name in sample.functions:
        function = functions.get(function_name)
        if function is None:
            raise MetadataValidationRunError(
                f"{sample.sample_id}: function {function_name!r} disappeared after manifest validation"
            )
        function_predictions.append(
            _predict_function(function, protocol, sample.source_version)
        )
    verdict = _combine_verdicts(item["prediction"] for item in function_predictions)
    return {
        "sample_id": sample.sample_id,
        "protocol_id": sample.protocol_id,
        "filesystem": sample.filesystem,
        "source_version": sample.source_version,
        "selection_kind": sample.selection_kind,
        "prediction": verdict,
        "analyzable": any(item["analyzable"] for item in function_predictions),
        "functions": function_predictions,
    }


def _predict_function(
    function: Any, protocol: MetadataProtocol, source_version: str
) -> dict[str, Any]:
    evidences = operation_applicability(function, protocol)
    applicable = [item for item in evidences if item.applicable]
    evidence_payload = [item.to_dict() for item in evidences]
    if not applicable:
        return {
            "function": function.name,
            "prediction": "out_of_scope",
            "analyzable": False,
            "applicability_match_kind": "none",
            "operation_id": "",
            "candidate_count": 0,
            "unknown_count": 0,
            "applicability_evidence": evidence_payload,
        }

    ranked = sorted(applicable, key=lambda item: item.score(), reverse=True)
    if len(ranked) > 1 and ranked[0].score() == ranked[1].score():
        return {
            "function": function.name,
            "prediction": "analysis_unknown",
            "analyzable": False,
            "applicability_match_kind": "ambiguous",
            "operation_id": "",
            "candidate_count": 0,
            "unknown_count": 1,
            "unknown_reasons": ["ambiguous_operation_match"],
            "applicability_evidence": evidence_payload,
        }

    selected = ranked[0]
    result = analyze_function(
        function,
        protocol,
        operation_id=selected.operation_id,
        source_version=source_version,
    )
    if result is None:
        raise MetadataValidationRunError(
            f"{function.name}: applicable operation {selected.operation_id!r} was not analyzed"
        )
    if result.candidates:
        prediction = "violation"
    elif result.unknown:
        prediction = "analysis_unknown"
    else:
        prediction = "legal"
    return {
        "function": function.name,
        "prediction": prediction,
        "analyzable": True,
        "applicability_match_kind": selected.match_kind,
        "operation_id": selected.operation_id,
        "candidate_count": len(result.candidates),
        "unknown_count": len(result.unknown),
        "candidate_types": sorted({item.violation_type.value for item in result.candidates}),
        "unknown_reasons": sorted(
            {reason for item in result.unknown for reason in item.reasons}
        ),
        "applicability_evidence": selected.to_dict(),
    }


def _combine_verdicts(verdicts: Iterable[str]) -> str:
    values = tuple(verdicts)
    for verdict in ("violation", "analysis_unknown", "legal", "out_of_scope"):
        if verdict in values:
            return verdict
    raise MetadataValidationRunError("sample produced no function prediction")


def _prediction_summary(
    predictions: tuple[dict[str, Any], ...], manifest: ValidationManifest
) -> dict[str, Any]:
    verdicts = Counter(item["prediction"] for item in predictions)
    analyzable = sum(bool(item["analyzable"]) for item in predictions)
    by_protocol: dict[str, dict[str, int]] = {}
    for protocol_id in sorted({item.protocol_id for item in manifest.samples}):
        selected = [item for item in predictions if item["protocol_id"] == protocol_id]
        by_protocol[protocol_id] = {
            "samples": len(selected),
            "analyzable": sum(bool(item["analyzable"]) for item in selected),
        }
    return {
        "samples": len(predictions),
        "analyzable_samples": analyzable,
        "applicability_rate": analyzable / len(predictions) if predictions else 0.0,
        "prediction_counts": {
            verdict: verdicts[verdict] for verdict in sorted(PREDICTION_VERDICTS)
        },
        "by_protocol": by_protocol,
    }


def _metrics(
    predictions: tuple[dict[str, Any], ...], adjudication: AdjudicationSet | None
) -> dict[str, Any] | None:
    if adjudication is None or adjudication.status != "complete":
        return None
    truth = {item.sample_id: item.final_verdict for item in adjudication.entries}
    comparable = []
    abstained = 0
    excluded_reference = 0
    for item in predictions:
        expected = truth[item["sample_id"]]
        predicted = item["prediction"]
        if expected not in {"legal", "violation"}:
            excluded_reference += 1
            continue
        if predicted not in {"legal", "violation"}:
            abstained += 1
            continue
        comparable.append((predicted, expected))
    tp = sum(predicted == expected == "violation" for predicted, expected in comparable)
    tn = sum(predicted == expected == "legal" for predicted, expected in comparable)
    fp = sum(predicted == "violation" and expected == "legal" for predicted, expected in comparable)
    fn = sum(predicted == "legal" and expected == "violation" for predicted, expected in comparable)
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    return {
        "evaluated_samples": len(comparable),
        "abstained_predictions": abstained,
        "excluded_reference_samples": excluded_reference,
        "confusion_matrix": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "precision": precision,
        "recall": recall,
        "f1": (
            None
            if precision is None or recall is None or precision + recall == 0
            else 2 * precision * recall / (precision + recall)
        ),
        "accuracy": _ratio(tp + tn, len(comparable)),
        "prediction_coverage": _ratio(len(comparable), len(predictions)),
    }


def _reviewer_agreement(
    manifest: ValidationManifest, label_sets: tuple[ReviewerLabelSet, ...]
) -> dict[str, Any] | None:
    if len(label_sets) != 2 or any(item.status != "complete" for item in label_sets):
        return None
    first = {item.sample_id: item.verdict for item in label_sets[0].entries}
    second = {item.sample_id: item.verdict for item in label_sets[1].entries}
    pairs = [(first[item.sample_id], second[item.sample_id]) for item in manifest.samples]
    observed = sum(left == right for left, right in pairs) / len(pairs)
    first_counts = Counter(left for left, _ in pairs)
    second_counts = Counter(right for _, right in pairs)
    expected = sum(
        (first_counts[label] / len(pairs)) * (second_counts[label] / len(pairs))
        for label in set(first_counts) | set(second_counts)
    )
    kappa = None if expected == 1.0 else (observed - expected) / (1.0 - expected)
    return {"samples": len(pairs), "observed_agreement": observed, "cohen_kappa": kappa}


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run frozen MOCC-SE protocols on validation samples."
    )
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--freeze", default=str(DEFAULT_FREEZE))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--labels", action="append", default=[])
    parser.add_argument("--adjudication", default="")
    parser.add_argument("--require-complete-labels", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    payload = run_validation(
        workspace=args.workspace,
        freeze_path=args.freeze,
        manifest_path=args.manifest,
        labels=args.labels,
        adjudication_path=args.adjudication,
        require_complete_labels=args.require_complete_labels,
    )
    rendered = json.dumps(payload, indent=2) + "\n"
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
