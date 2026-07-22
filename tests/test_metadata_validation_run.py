from pathlib import Path

from src.metadata_validation_labels import AdjudicationEntry, AdjudicationSet
from src.metadata_validation_run import _metrics, run_validation


ROOT = Path(__file__).parents[1]


def test_current_blind_batch_reports_protocol_applicability_without_metrics():
    payload = run_validation(workspace=ROOT)

    assert payload["result_semantics"] == "frozen_protocol_predictions_not_bug_claims"
    assert payload["summary"]["samples"] == 10
    assert payload["summary"]["analyzable_samples"] == 2
    assert payload["summary"]["prediction_counts"]["out_of_scope"] == 8
    assert payload["summary"]["prediction_counts"]["legal"] == 2
    assert payload["summary"]["prediction_counts"]["analysis_unknown"] == 0
    assert payload["summary"]["by_protocol"][
        "mocc.protocol_b.device_topology_rollback"
    ]["analyzable"] == 1
    assert payload["summary"]["by_protocol"][
        "mocc.protocol_e.allocation_lifecycle"
    ]["analyzable"] == 1
    assert payload["coverage_gate"]["status"] == "insufficient_protocol_applicability"
    assert payload["label_gate"]["metrics_available"] is False
    assert payload["metrics"] is None


def test_metrics_exclude_unknown_and_out_of_scope_predictions():
    predictions = (
        {"sample_id": "sample.tp", "prediction": "violation"},
        {"sample_id": "sample.tn", "prediction": "legal"},
        {"sample_id": "sample.abstain", "prediction": "analysis_unknown"},
        {"sample_id": "sample.out", "prediction": "out_of_scope"},
        {"sample_id": "sample.reference_unknown", "prediction": "legal"},
    )
    truth = {
        "sample.tp": "violation",
        "sample.tn": "legal",
        "sample.abstain": "violation",
        "sample.out": "legal",
        "sample.reference_unknown": "analysis_unknown",
    }
    adjudication = AdjudicationSet(
        schema_version=1,
        adjudication_id="test.adjudication",
        manifest_id="test.manifest",
        freeze_id="test.freeze",
        status="complete",
        label_set_ids=("test.a", "test.b"),
        entries=tuple(
            AdjudicationEntry(
                sample_id=sample_id,
                final_verdict=verdict,
                adjudicator="reviewer_c",
                rationale="fixture",
                reviewer_verdicts={"reviewer_a": verdict, "reviewer_b": verdict},
            )
            for sample_id, verdict in truth.items()
        ),
    )

    metrics = _metrics(predictions, adjudication)

    assert metrics is not None
    assert metrics["evaluated_samples"] == 2
    assert metrics["abstained_predictions"] == 2
    assert metrics["excluded_reference_samples"] == 1
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["f1"] == 1.0
    assert metrics["prediction_coverage"] == 0.4


def test_metrics_use_null_when_precision_is_undefined():
    predictions = ({"sample_id": "sample.legal", "prediction": "legal"},)
    adjudication = AdjudicationSet(
        schema_version=1,
        adjudication_id="test.adjudication",
        manifest_id="test.manifest",
        freeze_id="test.freeze",
        status="complete",
        label_set_ids=("test.a", "test.b"),
        entries=(
            AdjudicationEntry(
                sample_id="sample.legal",
                final_verdict="legal",
                adjudicator="reviewer_c",
                rationale="fixture",
                reviewer_verdicts={"reviewer_a": "legal", "reviewer_b": "legal"},
            ),
        ),
    )

    metrics = _metrics(predictions, adjudication)

    assert metrics is not None
    assert metrics["precision"] is None
    assert metrics["recall"] is None
    assert metrics["f1"] is None
    assert metrics["accuracy"] == 1.0
