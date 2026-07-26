"""Compare residual runs with source-stable, per-effect witnesses.

Reports intentionally omit CLOSED and PROTECTED slices.  This tool therefore
reads file-level ``evaluation.json`` artifacts when they are available and
falls back to ``all_reports.json`` for older outputs.  A source effect retained
only in ``reaching_effects`` is ``RETAINED_REACHING``; a truly missing current
witness is ``UNMATCHED`` and is never treated as a fix.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.unknown_triage import (
    unknown_cause_category,
    unknown_cause_proof_gap,
    unknown_cause_taxonomy,
)


SCHEMA_VERSION = 4
KNOWN_CLASSES = (
    "CANDIDATE",
    "LIVE_METADATA_RESIDUAL",
    "UNKNOWN",
    "REVIEW",
)
TERMINAL_CLASSES = (
    "CLOSED",
    "PROTECTED",
    "CONTAINED_METADATA_RESIDUAL",
    "OUT_OF_SCOPE",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare residual runs using per-effect source witnesses."
    )
    parser.add_argument("baseline", help="baseline output directory or JSON artifact")
    parser.add_argument("current", help="current output directory or JSON artifact")
    parser.add_argument(
        "--output",
        help="optional path for report_transition_matrix.json",
    )
    parser.add_argument(
        "--output-dir",
        help="directory for the transition artifacts (defaults to --output parent)",
    )
    args = parser.parse_args(argv)

    comparison = compare_runs(Path(args.baseline), Path(args.current))
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path(args.output).parent
        if args.output
        else None
    )
    if output_dir is not None:
        write_comparison_artifacts(comparison, output_dir)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(comparison["report_transition_matrix"], indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
    print(json.dumps(comparison["report_transition_matrix"], indent=2, sort_keys=True))
    return 0


def compare_runs(baseline_path: Path, current_path: Path) -> dict[str, object]:
    """Return report-level transitions, retaining unmatched evidence explicitly."""

    baseline = _load_witnesses(baseline_path)
    current = _load_witnesses(current_path)
    current_slice_states = _load_slice_states(current_path)
    current_by_key = {witness["stable_key"]: witness for witness in current}
    current_by_effect_identity: dict[str, tuple[dict[str, Any], str]] = {}
    for witness in current:
        for match_kind, key in _typed_witness_effect_identity_keys(witness):
            current_by_effect_identity.setdefault(key, (witness, match_kind))
    current_by_slice_identity: dict[str, list[dict[str, Any]]] = {}
    for witness in current:
        current_by_slice_identity.setdefault(_witness_slice_identity_key(witness), []).append(
            witness
        )
    baseline_by_key = {witness["stable_key"]: witness for witness in baseline}
    baseline_effect_identities = {
        key for witness in baseline for key in _witness_effect_identity_keys(witness)
    }
    baseline_by_slice_identity: dict[str, list[dict[str, Any]]] = {}
    for witness in baseline:
        baseline_by_slice_identity.setdefault(_witness_slice_identity_key(witness), []).append(
            witness
        )
    transitions = [
        _transition(
            baseline_witness,
            _current_match(
                baseline_witness,
                current_by_key,
                current_by_effect_identity,
                current_by_slice_identity,
                current_slice_states,
            ),
        )
        for baseline_witness in baseline
    ]
    retained_reviewed_boundary_slices = {
        _witness_slice_identity_key(item["stable_witness"])
        for item in transitions
        if item["old_state"] == "CANDIDATE"
        and item["new_state"] in {"CANDIDATE", "LIVE_METADATA_RESIDUAL"}
    }
    new_candidates: list[dict[str, Any]] = []
    candidate_compatibility_exceptions: list[dict[str, Any]] = []
    for witness in current:
        if witness["classification"] not in {
            "CANDIDATE",
            "LIVE_METADATA_RESIDUAL",
        }:
            continue
        if witness["stable_key"] in baseline_by_key or any(
            key in baseline_effect_identities
            for key in _witness_effect_identity_keys(witness)
        ):
            continue
        compatibility_reason = _candidate_baseline_compatibility_reason(
            witness,
            baseline_by_slice_identity,
            retained_reviewed_boundary_slices,
        )
        if compatibility_reason:
            candidate_compatibility_exceptions.append(
                {
                    "stable_witness": witness["stable_witness"],
                    "match_kind": compatibility_reason,
                    "typed_reason": compatibility_reason.lower(),
                }
            )
        else:
            new_candidates.append(witness)
    lost_known_witnesses = [
        item
        for item in transitions
        if item["old_state"] in KNOWN_CLASSES and item["new_state"] == "UNMATCHED"
    ]
    matrix = Counter((item["old_state"], item["new_state"]) for item in transitions)
    matrix_rows = [
        {"old_state": old_state, "new_state": new_state, "count": count}
        for (old_state, new_state), count in sorted(matrix.items())
    ]
    match_counts = Counter(item["match_kind"] for item in transitions)
    compatibility_match_count = sum(
        count
        for kind, count in match_counts.items()
        if kind not in {"EXACT_WITNESS", "UNMATCHED"}
    ) + len(candidate_compatibility_exceptions)
    family_counts = Counter(
        family
        for item in transitions
        for family in item.get("semantic_families", ())
    )

    report_transition_matrix = {
        "schema_version": SCHEMA_VERSION,
        "baseline": baseline_path.as_posix(),
        "current": current_path.as_posix(),
        "baseline_witness_count": len(baseline),
        "current_witness_count": len(current),
        "transition_matrix": matrix_rows,
        "match_counts": [
            {"match_kind": kind, "count": count}
            for kind, count in sorted(match_counts.items())
        ],
        "compatibility_match_count": compatibility_match_count,
        "candidate_compatibility_exception_count": len(
            candidate_compatibility_exceptions
        ),
        "semantic_family_yield": dict(sorted(family_counts.items())),
        "unmatched_baseline_witness_count": sum(
            item["new_state"] == "UNMATCHED" for item in transitions
        ),
        "new_candidate_count": len(new_candidates),
        "transition_policy": (
            "A missing current witness is UNMATCHED, not CLOSED, PROTECTED, or "
            "OUT_OF_SCOPE. CLOSED and PROTECTED require an exact current "
            "failure/effect witness from a full evaluation artifact. An effect "
            "still present only in reaching_effects is RETAINED_REACHING, not "
            "resolved. A disappeared effect witness whose failure/exit slice "
            "is still visible is RETAINED_SLICE, not resolved or unmatched."
        ),
    }
    return {
        "report_transition_matrix": report_transition_matrix,
        "resolved_candidates": [
            item
            for item in transitions
            if item["old_state"] == "CANDIDATE"
            and item["new_state"] in TERMINAL_CLASSES
        ],
        "resolved_unknowns": [
            item
            for item in transitions
            if item["old_state"] == "UNKNOWN"
            and item["new_state"] in TERMINAL_CLASSES
        ],
        "new_candidates": new_candidates,
        "candidate_compatibility_exceptions": candidate_compatibility_exceptions,
        "lost_known_witnesses": lost_known_witnesses,
        "transitions": transitions,
        # Retained for M31 consumers, but generated from the full transition set.
        **_unknown_resolution_compatibility(transitions),
    }


def write_comparison_artifacts(comparison: dict[str, object], output_dir: Path) -> dict[str, Path]:
    """Write stable, reviewable artifacts without placing generated data in Git."""

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "report_transition_matrix": output_dir / "report_transition_matrix.json",
        "resolved_candidates": output_dir / "resolved_candidates.json",
        "resolved_unknowns": output_dir / "resolved_unknowns.json",
        "new_candidates": output_dir / "new_candidates.json",
        "lost_known_witnesses": output_dir / "lost_known_witnesses.json",
        "candidate_compatibility_exceptions": (
            output_dir / "candidate_compatibility_exceptions.json"
        ),
        "report_level_transition_matrix": (
            output_dir / "report_level_transition_matrix.json"
        ),
        "comparison_match_audit": output_dir / "comparison_match_audit.json",
    }
    payloads = {
        **comparison,
        "report_level_transition_matrix": comparison["transitions"],
        "comparison_match_audit": {
            "schema_version": SCHEMA_VERSION,
            "baseline": comparison["report_transition_matrix"]["baseline"],
            "current": comparison["report_transition_matrix"]["current"],
            "compatibility_match_count": comparison["report_transition_matrix"][
                "compatibility_match_count"
            ],
            "match_counts": comparison["report_transition_matrix"]["match_counts"],
            "matches": [
                {
                    "stable_witness": item["stable_witness"],
                    "old_state": item["old_state"],
                    "new_state": item["new_state"],
                    "match_kind": item["match_kind"],
                    "typed_reason": item["match_reason"],
                }
                for item in comparison["transitions"]
            ]
            + [
                {
                    **item,
                    "old_state": "CANDIDATE",
                    "new_state": "CANDIDATE",
                }
                for item in comparison["candidate_compatibility_exceptions"]
            ],
        },
    }
    for name, path in paths.items():
        path.write_text(
            json.dumps(payloads[name], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return paths


def _load_witnesses(path: Path) -> list[dict[str, Any]]:
    evaluations = _evaluation_paths(path)
    if evaluations:
        witnesses = [
            witness
            for evaluation_path in evaluations
            for witness in _witnesses_from_evaluation(evaluation_path)
        ]
        return _dedupe_witnesses(witnesses)
    return _dedupe_witnesses(_witnesses_from_reports(_load_reports(_reports_path(path))))


def _load_slice_states(path: Path) -> dict[str, dict[str, Any]]:
    evaluations = _evaluation_paths(path)
    if not evaluations:
        return {}
    result: dict[str, dict[str, Any]] = {}
    for evaluation_path in evaluations:
        payload = json.loads(evaluation_path.read_text(encoding="utf-8"))
        for analysis in payload.get("analyses", ()):
            function = str(analysis.get("function", ""))
            for residual_slice in (analysis.get("slicing_result") or {}).get("slices", ()):
                if not isinstance(residual_slice, dict):
                    continue
                key = _slice_identity_key(
                    filesystem=_filesystem_for_site(residual_slice.get("failure_site") or {}),
                    function=function,
                    failure_site=_site(residual_slice.get("failure_site")),
                    exit_site=_site(residual_slice.get("exit_site")),
                )
                result[key] = {
                    "classification": _classification_from_slice_state(residual_slice),
                    "kind": _kind_from_slice_state(residual_slice),
                    "slice_state": str(residual_slice.get("state", "")),
                    "rationale": str(residual_slice.get("rationale", "")),
                }
    return result


def _evaluation_paths(path: Path) -> tuple[Path, ...]:
    if path.is_file():
        return (path,) if path.name == "evaluation.json" else ()
    if not path.is_dir():
        return ()
    file_evaluations = tuple(sorted((path / "files").glob("*/evaluation.json")))
    if file_evaluations:
        return file_evaluations
    direct = path / "evaluation.json"
    return (direct,) if direct.is_file() else ()


def _witnesses_from_evaluation(path: Path) -> Iterable[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for analysis in payload.get("analyses", ()):  # file-level EvaluationResult only
        function = str(analysis.get("function", ""))
        for residual_slice in (analysis.get("slicing_result") or {}).get("slices", ()):
            yield from _witnesses_from_slice(function, residual_slice)


def _witnesses_from_reports(reports: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for report in reports:
        function = str(report.get("function", ""))
        residual_slice = report.get("residual_slice") or {}
        kind = str(report.get("kind", "OUT_OF_SCOPE"))
        witnesses = list(_witnesses_from_slice(function, residual_slice))
        if not witnesses:
            witnesses = [_legacy_report_witness(function, residual_slice)]
        for witness in witnesses:
            witness["classification"] = _classification_from_kind(kind)
            witness["kind"] = kind
            witness["unknown_causes"] = list(report.get("unknown_causes") or ())
            yield witness


def _legacy_report_witness(
    function: str, residual_slice: dict[str, Any]
) -> dict[str, Any]:
    """Keep pre-M32 report-only comparisons usable without inventing an effect."""

    witness = {
        "filesystem": _filesystem_for_site(residual_slice.get("failure_site") or {}),
        "function": function,
        "failure_site": _site(residual_slice.get("failure_site")),
        "exit_site": _site(residual_slice.get("exit_site")),
        "effect": {"legacy_report_without_effect": True},
        "classification": "OUT_OF_SCOPE",
        "kind": "OUT_OF_SCOPE",
        "slice_state": str(residual_slice.get("state", "")),
        "unknown_causes": [],
        "cancellations": [],
        "protections": [],
        "rationale": str(residual_slice.get("rationale", "")),
    }
    witness["stable_witness"] = {
        "filesystem": witness["filesystem"],
        "function": function,
        "failure_site": witness["failure_site"],
        "exit_site": witness["exit_site"],
        "effect": witness["effect"],
    }
    witness["stable_key"] = json.dumps(
        witness["stable_witness"], sort_keys=True, separators=(",", ":")
    )
    return witness


def _witnesses_from_slice(function: str, residual_slice: dict[str, Any]) -> Iterable[dict[str, Any]]:
    residuals = tuple(residual_slice.get("residuals") or ())
    reaching = tuple(residual_slice.get("reaching_effects") or ())
    out_of_scope = tuple(residual_slice.get("out_of_scope_effects") or ())
    effects = (reaching or residuals) + out_of_scope
    slice_classification, slice_kind = _slice_classification(residual_slice, residuals)
    review_owners = _owner_scope_review_owners(residual_slice)
    residual_keys = {_effect_key(effect) for effect in residuals}
    cancellations = tuple(residual_slice.get("cancellations") or ())
    protections = tuple(residual_slice.get("protections") or ())
    teardown_closed_keys = {
        _effect_key(effect)
        for proof in residual_slice.get("owner_teardown_proofs", ())
        for effect in (proof.get("closed_effects") or ())
    }
    containment_covered_keys = {
        _effect_key(effect)
        for proof in residual_slice.get("containment_proofs", ())
        for effect in (proof.get("covered_effects") or ())
    }
    containment_proofs = tuple(residual_slice.get("containment_proofs", ()))
    out_of_scope_keys = {_effect_key(effect) for effect in out_of_scope}
    for effect in effects:
        if _effect_key(effect) in out_of_scope_keys:
            classification, kind, causes = "OUT_OF_SCOPE", "OUT_OF_SCOPE", []
        else:
            classification, kind, causes = _effect_classification(
                effect,
                residual_keys=residual_keys,
                cancellations=cancellations,
                protections=protections,
                slice_classification=slice_classification,
                slice_kind=slice_kind,
                slice_causes=_slice_unknown_causes(residual_slice),
                teardown_closed_keys=teardown_closed_keys,
                containment_covered_keys=containment_covered_keys,
                review_owners=review_owners,
            )
        if classification is None:
            continue
        witness = {
            "filesystem": _filesystem_for_site(residual_slice.get("failure_site") or {}),
            "function": function,
            "failure_site": _site(residual_slice.get("failure_site")),
            "exit_site": _site(residual_slice.get("exit_site")),
            "effect": _effect(effect),
            "classification": classification,
            "kind": kind,
            "slice_state": str(residual_slice.get("state", "")),
            "unknown_causes": causes,
            "cancellations": [_effect(item) for item in cancellations],
            "protections": [_effect(item) for item in protections],
            "containment_proofs": list(containment_proofs),
            "owner_teardown_proofs": list(
                residual_slice.get("owner_teardown_proofs", ())
            ),
            "owner_scope_proofs": list(
                residual_slice.get("owner_scope_proofs", ())
            ),
            "owner_liveness_proofs": list(
                residual_slice.get("owner_liveness_proofs", ())
            ),
            "demand_summary_requests": list(
                residual_slice.get("demand_summary_requests", ())
            ),
            "lexical_suppressions": list(
                residual_slice.get("lexical_suppressions", ())
            ),
            "rationale": str(residual_slice.get("rationale", "")),
            "out_of_scope_evidence": (
                list(effect.get("transient_provenance") or ())
                if _effect_key(effect) in out_of_scope_keys
                else []
            ),
        }
        witness["stable_witness"] = {
            "filesystem": witness["filesystem"],
            "function": function,
            "failure_site": witness["failure_site"],
            "exit_site": witness["exit_site"],
            "effect": witness["effect"],
        }
        witness["stable_key"] = json.dumps(
            witness["stable_witness"], sort_keys=True, separators=(",", ":")
        )
        yield witness


def _effect_classification(
    effect: dict[str, Any],
    *,
    residual_keys: set[str],
    cancellations: tuple[dict[str, Any], ...],
    protections: tuple[dict[str, Any], ...],
    slice_classification: str,
    slice_kind: str,
    slice_causes: list[str],
    teardown_closed_keys: set[str],
    containment_covered_keys: set[str],
    review_owners: set[str],
) -> tuple[str | None, str, list[str]]:
    if _effect_key(effect) in teardown_closed_keys:
        return "CLOSED", "OUT_OF_SCOPE", []
    if _effect_key(effect) in residual_keys:
        if _effect_key(effect) in containment_covered_keys:
            return "CONTAINED_METADATA_RESIDUAL", "CONTAINED_METADATA_RESIDUAL", []
        if (
            slice_classification == "CANDIDATE"
            and _leading_effect_owner(str(effect.get("root", ""))) in review_owners
        ):
            return "REVIEW", "METADATA_RESIDUAL_REVIEW", []
        return slice_classification, slice_kind, slice_causes
    if any(_cancellation_covers(effect, candidate) for candidate in cancellations):
        return "CLOSED", "OUT_OF_SCOPE", []
    if any(_protection_covers(effect, candidate) for candidate in protections):
        return "PROTECTED", "OUT_OF_SCOPE", []
    if _effect_key(effect) in containment_covered_keys:
        return "CONTAINED_METADATA_RESIDUAL", "CONTAINED_METADATA_RESIDUAL", []
    if slice_classification in {"CLOSED", "PROTECTED", "OUT_OF_SCOPE"}:
        return slice_classification, slice_kind, []
    # The effect still exists in the full slice, but the residual projection
    # omitted it. Preserve that fact without inventing a fix or a candidate.
    return "RETAINED_REACHING", "OUT_OF_SCOPE", []


def _cancellation_covers(effect: dict[str, Any], candidate: dict[str, Any]) -> bool:
    if not _same_effect_identity(effect, candidate):
        return False
    if candidate.get("delta") == "RESTORE":
        return effect.get("delta") == "SET" and bool(candidate.get("snapshot_relation"))
    inverse = {
        "INC": "DEC",
        "DEC": "INC",
        "SET": "CLEAR",
        "CLEAR": "SET",
        "ADD": "REMOVE",
        "REMOVE": "ADD",
        "RESERVE": "RELEASE",
        "RELEASE": "RESERVE",
    }
    if inverse.get(effect.get("delta")) != candidate.get("delta"):
        return False
    left = _normalized_value(effect.get("value"))
    right = _normalized_value(candidate.get("value"))
    if effect.get("delta") in {"SET", "CLEAR"}:
        return left in _CLEAR_VALUES or right in _CLEAR_VALUES or left == right
    return left == right


def _protection_covers(effect: dict[str, Any], candidate: dict[str, Any]) -> bool:
    if candidate.get("delta") != "PROTECT" or not _same_effect_identity(effect, candidate):
        return False
    left = _normalized_value(effect.get("value"))
    right = _normalized_value(candidate.get("value"))
    return not left or not right or left == right


def _same_effect_identity(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return all(
        _normalized_value(left.get(name)) == _normalized_value(right.get(name))
        for name in ("root", "key", "plane")
    )


def _effect_key(effect: dict[str, Any]) -> str:
    return json.dumps(_effect(effect), sort_keys=True, separators=(",", ":"))


def _current_match(
    baseline_witness: dict[str, Any],
    current_by_key: dict[str, dict[str, Any]],
    current_by_effect_identity: dict[str, tuple[dict[str, Any], str]],
    current_by_slice_identity: dict[str, list[dict[str, Any]]],
    current_slice_states: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    exact = current_by_key.get(baseline_witness["stable_key"])
    if exact is not None:
        return {
            **exact,
            "_match_kind": "EXACT_WITNESS",
            "_match_reason": "complete_stable_witness_identity",
        }
    return (
        _matching_current_witness(
            baseline_witness,
            current_by_effect_identity,
        )
        or _same_slice_retention_witness(
            baseline_witness,
            current_by_slice_identity,
        )
        or _slice_state_retention_witness(
            baseline_witness,
            current_slice_states,
        )
    )


def _matching_current_witness(
    baseline_witness: dict[str, Any],
    current_by_effect_identity: dict[str, tuple[dict[str, Any], str]],
) -> dict[str, Any] | None:
    for _, key in _typed_witness_effect_identity_keys(baseline_witness):
        matched = current_by_effect_identity.get(key)
        if matched is not None:
            witness, match_kind = matched
            return {
                **witness,
                "_match_kind": match_kind,
                "_match_reason": _match_reason(match_kind),
            }
    return None


def _same_slice_retention_witness(
    baseline_witness: dict[str, Any],
    current_by_slice_identity: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    matches = current_by_slice_identity.get(_witness_slice_identity_key(baseline_witness), [])
    if not matches:
        return None
    visible = [witness for witness in matches if witness.get("classification") in KNOWN_CLASSES]
    if not visible:
        return None
    return {
        **visible[0],
        "classification": "RETAINED_SLICE",
        "kind": "OUT_OF_SCOPE",
        "_match_kind": "RETAINED_SLICE",
        "_match_reason": "same_failure_exit_slice_with_different_effect_projection",
        "slice_retention_evidence": {
            "classification": visible[0].get("classification"),
            "kind": visible[0].get("kind"),
            "effect": visible[0].get("effect"),
        },
    }


def _slice_state_retention_witness(
    baseline_witness: dict[str, Any],
    current_slice_states: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if _effect(baseline_witness.get("effect")).get("evidence") != "NAME_INFERRED":
        return None
    state = current_slice_states.get(_witness_slice_identity_key(baseline_witness))
    if state is None:
        return None
    classification = str(state.get("classification") or "RETAINED_SLICE")
    if classification == "CANDIDATE":
        classification = "RETAINED_SLICE"
    return {
        **baseline_witness,
        "classification": classification,
        "kind": str(state.get("kind") or "OUT_OF_SCOPE"),
        "slice_state": str(state.get("slice_state") or ""),
        "unknown_causes": (
            [str(state.get("rationale"))]
            if classification == "UNKNOWN" and state.get("rationale")
            else []
        ),
        "cancellations": [],
        "protections": [],
        "containment_proofs": [],
        "out_of_scope_evidence": [],
        "slice_retention_evidence": state,
        "_match_kind": f"NAME_INFERRED_REMOVED_{classification}",
        "_match_reason": (
            "name_inferred_effect_removed_but_exact_failure_exit_slice_retained"
        ),
    }


def _candidate_baseline_compatibility_reason(
    witness: dict[str, Any],
    baseline_by_slice_identity: dict[str, list[dict[str, Any]]],
    retained_reviewed_boundary_slices: set[str],
) -> str:
    slice_key = _witness_slice_identity_key(witness)
    baseline_slice = [
        item
        for item in baseline_by_slice_identity.get(slice_key, [])
        if item.get("classification") == "CANDIDATE"
    ]
    if not baseline_slice or slice_key not in retained_reviewed_boundary_slices:
        return ""
    effect = _effect(witness.get("effect"))
    if effect.get("evidence") == "NAME_INFERRED":
        return "NAME_INFERRED_SAME_SLICE"
    if any(
        _compatible_effect_projection(effect, _effect(item.get("effect")))
        for item in baseline_slice
    ):
        return "SOURCE_PROJECTION_SAME_SLICE"
    return ""


def _compatible_effect_projection(left: dict[str, object], right: dict[str, object]) -> bool:
    left_site = _site(left.get("site"))
    right_site = _site(right.get("site"))
    return (
        left.get("key") == right.get("key")
        and left.get("plane") == right.get("plane")
        and left.get("delta") == right.get("delta")
        and left_site.get("file") == right_site.get("file")
        and left_site.get("line") == right_site.get("line")
    )


def _witness_effect_identity_keys(witness: dict[str, Any]) -> tuple[str, ...]:
    return tuple(key for _, key in _typed_witness_effect_identity_keys(witness))


def _typed_witness_effect_identity_keys(
    witness: dict[str, Any],
) -> tuple[tuple[str, str], ...]:
    effect = _effect(witness.get("effect"))
    site = _site(effect.get("site"))
    keys = [
        (
            "EFFECT_IDENTITY",
            json.dumps(
            [
                witness.get("filesystem", ""),
                witness.get("function", ""),
                effect.get("root", ""),
                effect.get("key", ""),
                effect.get("plane", ""),
                effect.get("delta", ""),
                site.get("file", ""),
                site.get("line", ""),
            ],
            separators=(",", ":"),
            ),
        )
    ]
    semantic = _transaction_alloc_bookkeeping_identity(witness, effect, site)
    if semantic is not None:
        keys.append(("XFS_TRANSACTION_ALLOC_BOOKKEEPING", semantic))
    source_projection = _source_projection_identity(witness, effect, site)
    if source_projection is not None:
        keys.append(("SOURCE_PROJECTION", source_projection))
    return tuple(keys)


def _match_reason(match_kind: str) -> str:
    return {
        "EFFECT_IDENTITY": (
            "same filesystem, function, effect root/key/plane/delta, and source site"
        ),
        "XFS_TRANSACTION_ALLOC_BOOKKEEPING": (
            "source-audited XFS transaction allocation bookkeeping projection"
        ),
        "SOURCE_PROJECTION": (
            "same effect key/plane/delta and source, failure, and exit sites"
        ),
    }.get(match_kind, match_kind.lower())


def _source_projection_identity(
    witness: dict[str, Any],
    effect: dict[str, object],
    site: dict[str, object],
) -> str | None:
    if not site.get("file") or not site.get("line"):
        return None
    failure = _site(witness.get("failure_site"))
    exit_site = _site(witness.get("exit_site"))
    return json.dumps(
        [
            witness.get("filesystem", ""),
            witness.get("function", ""),
            "source_projection",
            effect.get("key", ""),
            effect.get("plane", ""),
            effect.get("delta", ""),
            site.get("file", ""),
            site.get("line", ""),
            failure.get("file", ""),
            failure.get("line", ""),
            exit_site.get("file", ""),
            exit_site.get("line", ""),
        ],
        separators=(",", ":"),
    )


def _witness_slice_identity_key(witness: dict[str, Any]) -> str:
    failure = _site(witness.get("failure_site"))
    exit_site = _site(witness.get("exit_site"))
    return _slice_identity_key(
        filesystem=str(witness.get("filesystem", "")),
        function=str(witness.get("function", "")),
        failure_site=failure,
        exit_site=exit_site,
    )


def _slice_identity_key(
    *,
    filesystem: str,
    function: str,
    failure_site: dict[str, object],
    exit_site: dict[str, object],
) -> str:
    return json.dumps(
        [
            filesystem,
            function,
            failure_site.get("file", ""),
            failure_site.get("line", ""),
            exit_site.get("file", ""),
            exit_site.get("line", ""),
        ],
        separators=(",", ":"),
    )


def _transaction_alloc_bookkeeping_identity(
    witness: dict[str, Any],
    effect: dict[str, object],
    site: dict[str, object],
) -> str | None:
    if witness.get("filesystem") != "xfs":
        return None
    if effect.get("key") not in {
        "xfs_trans_alloc",
        "xfs_trans_set_context",
        "xfs_trans_reserve",
    }:
        return None
    failure = _site(witness.get("failure_site"))
    exit_site = _site(witness.get("exit_site"))
    return json.dumps(
        [
            witness.get("filesystem", ""),
            witness.get("function", ""),
            "xfs_trans_alloc_bookkeeping",
            site.get("file", ""),
            site.get("line", ""),
            failure.get("file", ""),
            failure.get("line", ""),
            exit_site.get("file", ""),
            exit_site.get("line", ""),
        ],
        separators=(",", ":"),
    )


_CLEAR_VALUES = {"", "0", "0L", "0UL", "NULL", "false", "FALSE"}


def _normalized_value(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def _slice_classification(
    residual_slice: dict[str, Any], residuals: tuple[dict[str, Any], ...]
) -> tuple[str, str]:
    state = str(residual_slice.get("state", ""))
    if state == "CLOSED":
        return "CLOSED", "OUT_OF_SCOPE"
    if state == "PROTECTED":
        return "PROTECTED", "OUT_OF_SCOPE"
    if state == "CONTAINED" and residuals:
        return "CONTAINED_METADATA_RESIDUAL", "CONTAINED_METADATA_RESIDUAL"
    if state == "LIVE" and residuals:
        return "LIVE_METADATA_RESIDUAL", "UNCLOSED_METADATA_RESIDUAL"
    if state == "UNKNOWN":
        return (
            ("UNKNOWN", "METADATA_RESIDUAL_UNKNOWN")
            if residuals
            else ("DIAGNOSTIC_UNKNOWN", "OUT_OF_SCOPE")
        )
    if state == "EXPOSED" and residuals:
        review_owners = _owner_scope_review_owners(residual_slice)
        if review_owners and all(
            _leading_effect_owner(str(item.get("root", ""))) in review_owners
            for item in residuals
        ):
            return "REVIEW", "METADATA_RESIDUAL_REVIEW"
        containment_covered_keys = {
            _effect_key(effect)
            for proof in residual_slice.get("containment_proofs", ())
            for effect in (proof.get("covered_effects") or ())
        }
        uncontained = tuple(
            effect
            for effect in residuals
            if _effect_key(effect) not in containment_covered_keys
        )
        if all(item.get("evidence") == "NAME_INFERRED" for item in uncontained):
            return "REVIEW", "METADATA_RESIDUAL_REVIEW"
        return "CANDIDATE", "UNCLOSED_METADATA_RESIDUAL"
    return "OUT_OF_SCOPE", "OUT_OF_SCOPE"


def _owner_scope_review_owners(residual_slice: dict[str, Any]) -> set[str]:
    prefix = "owner_scope_escape_review:"
    return {
        str(item).removeprefix(prefix)
        for item in residual_slice.get("semantic_blockers", ())
        if str(item).startswith(prefix)
    }


def _leading_effect_owner(root: str) -> str:
    match = re.match(r"[&*()\s]*([A-Za-z_]\w*)", root)
    return match.group(1) if match else ""


def _classification_from_slice_state(residual_slice: dict[str, Any]) -> str:
    residuals = tuple(residual_slice.get("residuals") or ())
    classification, _ = _slice_classification(residual_slice, residuals)
    if classification == "DIAGNOSTIC_UNKNOWN":
        return "RETAINED_SLICE"
    if classification == "OUT_OF_SCOPE":
        return "RETAINED_SLICE"
    return classification


def _kind_from_slice_state(residual_slice: dict[str, Any]) -> str:
    residuals = tuple(residual_slice.get("residuals") or ())
    classification, kind = _slice_classification(residual_slice, residuals)
    return "OUT_OF_SCOPE" if classification == "DIAGNOSTIC_UNKNOWN" else kind


def _classification_from_kind(kind: str) -> str:
    return {
        "UNCLOSED_METADATA_RESIDUAL": "CANDIDATE",
        "METADATA_RESIDUAL_UNKNOWN": "UNKNOWN",
        "METADATA_RESIDUAL_REVIEW": "REVIEW",
        "CONTAINED_METADATA_RESIDUAL": "CONTAINED_METADATA_RESIDUAL",
    }.get(kind, "OUT_OF_SCOPE")


def _transition(
    old: dict[str, Any], new: dict[str, Any] | None
) -> dict[str, Any]:
    new_state = str(new["classification"]) if new is not None else "UNMATCHED"
    record = {
        "stable_witness": old["stable_witness"],
        "old_state": old["classification"],
        "new_state": new_state,
        "old_kind": old["kind"],
        "new_kind": new["kind"] if new is not None else None,
        "old_slice_state": old["slice_state"],
        "new_slice_state": new["slice_state"] if new is not None else None,
        "old_unknown_causes": old["unknown_causes"],
        "new_unknown_causes": new["unknown_causes"] if new is not None else [],
        "match_kind": (
            str(new.get("_match_kind", "EFFECT_IDENTITY"))
            if new is not None
            else "UNMATCHED"
        ),
        "match_reason": (
            str(new.get("_match_reason", "effect_identity_compatibility"))
            if new is not None
            else "current_witness_unmatched"
        ),
        "semantic_families": _semantic_families(new),
        "resolution_reason": _resolution_reason(old, new),
        "new_cancellation_evidence": (
            [
                item
                for item in new["cancellations"]
                if _cancellation_covers(old["effect"], item)
            ]
            if new is not None
            else []
        ),
        "new_protection_evidence": (
            [
                item
                for item in new["protections"]
                if _protection_covers(old["effect"], item)
            ]
            if new is not None
            else []
        ),
        "new_containment_evidence": (
            [
                proof
                for proof in new.get("containment_proofs", [])
                if any(
                    _effect_key(effect) == _effect_key(old["effect"])
                    for effect in (proof.get("covered_effects") or ())
                )
            ]
            if new is not None
            else []
        ),
        "new_out_of_scope_evidence": (
            new.get("out_of_scope_evidence", []) if new is not None else []
        ),
        "new_slice_retention_evidence": (
            new.get("slice_retention_evidence", {}) if new is not None else {}
        ),
        "new_owner_scope_evidence": (
            new.get("owner_scope_proofs", []) if new is not None else []
        ),
        "new_owner_liveness_evidence": (
            new.get("owner_liveness_proofs", []) if new is not None else []
        ),
        "new_demand_summary_evidence": (
            new.get("demand_summary_requests", []) if new is not None else []
        ),
    }
    return record


def _semantic_families(new: dict[str, Any] | None) -> list[str]:
    if new is None:
        return []
    families: set[str] = set()
    if new.get("owner_teardown_proofs"):
        families.add("owner_teardown")
    for proof in new.get("owner_scope_proofs", []):
        kind = str(proof.get("kind", ""))
        families.add(
            "mount_teardown"
            if kind == "UNPUBLISHED_MOUNT_CONSTRUCTION"
            else "owner_scope"
        )
    for proof in new.get("containment_proofs", []):
        families.add("failure_domain_scope")
        if proof.get("kind") == "TRANSACTION_ABORT":
            families.add("transaction_ownership")
    if new.get("owner_liveness_proofs"):
        families.add("owner_liveness")
    if new.get("demand_summary_requests"):
        families.add("demand_summary")
    if new.get("lexical_suppressions"):
        families.add("lexical_suppression_audit")
    effect = _effect(new.get("effect"))
    for proof in effect.get("semantic_provenance") or ():
        kind = str(proof.get("kind", "")).lower()
        if kind:
            families.add(kind)
    return sorted(families)


def _resolution_reason(old: dict[str, Any], new: dict[str, Any] | None) -> list[str]:
    if new is None:
        return ["current_witness_unmatched"]
    if old["classification"] == new["classification"]:
        return ["classification_unchanged"]
    reasons = [f"classification:{old['classification']}->{new['classification']}"]
    if new["classification"] == "CLOSED":
        reasons.append(
            "source_visible_cancellation"
            if new["cancellations"]
            else "no_residual_after_normalization"
        )
    elif new["classification"] == "PROTECTED":
        reasons.append(
            "source_visible_protection"
            if new["protections"]
            else "protected_state_without_effect_witness"
        )
    elif new["classification"] == "CONTAINED_METADATA_RESIDUAL":
        reasons.append("effect_scoped_failure_domain_proof")
    elif new["classification"] == "OUT_OF_SCOPE":
        reasons.append("source_classified_out_of_scope")
    elif new["classification"] == "RETAINED_SLICE":
        reasons.append("same_failure_exit_slice_still_visible")
    removed_causes = sorted(set(old["unknown_causes"]) - set(new["unknown_causes"]))
    if removed_causes:
        reasons.append("unknown_causes_removed")
    return reasons


def _unknown_resolution_compatibility(
    transitions: Iterable[dict[str, Any]],
) -> dict[str, list[dict[str, object]]]:
    rows: dict[str, dict[str, int]] = defaultdict(
        lambda: {"to_candidate": 0, "to_unknown": 0, "to_out_of_scope_or_removed": 0}
    )
    taxonomy_rows: dict[str, dict[str, int]] = defaultdict(
        lambda: {"to_candidate": 0, "to_unknown": 0, "to_out_of_scope_or_removed": 0}
    )
    proof_gap_rows: dict[str, dict[str, int]] = defaultdict(
        lambda: {"to_candidate": 0, "to_unknown": 0, "to_out_of_scope_or_removed": 0}
    )
    for transition in transitions:
        if transition["old_state"] != "UNKNOWN":
            continue
        bucket = {
            "CANDIDATE": "to_candidate",
            "UNKNOWN": "to_unknown",
        }.get(transition["new_state"], "to_out_of_scope_or_removed")
        for cause in transition["old_unknown_causes"] or ("uncategorized",):
            reason = unknown_cause_category(str(cause))
            taxonomy = unknown_cause_taxonomy(str(cause))
            proof_gap = unknown_cause_proof_gap(str(cause))
            rows[reason][bucket] += 1
            taxonomy_rows[taxonomy][bucket] += 1
            proof_gap_rows[proof_gap][bucket] += 1
    return {
        "unknown_taxonomy_resolution": [
            {"taxonomy": taxonomy, **counts}
            for taxonomy, counts in sorted(taxonomy_rows.items())
        ],
        "unknown_proof_gap_resolution": [
            {"proof_gap": proof_gap, **counts}
            for proof_gap, counts in sorted(proof_gap_rows.items())
        ],
        "unknown_resolution_matrix": [
            {
                "taxonomy": unknown_cause_taxonomy(reason),
                "proof_gap": unknown_cause_proof_gap(reason),
                "reason": reason,
                **counts,
            }
            for reason, counts in sorted(rows.items())
        ],
    }


def _reports_path(value: Path) -> Path:
    return value if value.is_file() else value / "reports" / "all_reports.json"


def _load_reports(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _dedupe_witnesses(witnesses: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return list({witness["stable_key"]: witness for witness in witnesses}.values())


def _site(value: Any) -> dict[str, object]:
    source = value if isinstance(value, dict) else {}
    return {
        "file": str(source.get("file", "")),
        "line": source.get("line", ""),
        "expression": str(source.get("expression", "")),
    }


def _effect(value: Any) -> dict[str, object]:
    source = value if isinstance(value, dict) else {}
    effect = {
        "root": str(source.get("root", "")),
        "key": str(source.get("key", "")),
        "plane": str(source.get("plane", "")),
        "delta": str(source.get("delta", "")),
        "value": str(source.get("value", "")),
        "evidence": str(source.get("evidence", "")),
        "site": _site(source.get("site")),
    }
    if isinstance(source.get("snapshot_relation"), dict):
        relation = source["snapshot_relation"]
        effect["snapshot_relation"] = {
            "snapshot_root": str(relation.get("snapshot_root", "")),
            "owner_root": str(relation.get("owner_root", "")),
            "aggregate_key": str(relation.get("aggregate_key", "")),
            "capture_site": _site(relation.get("capture_site")),
            "capture_block": relation.get("capture_block"),
            "source_identity": str(relation.get("source_identity", "")),
        }
    return effect


def _slice_unknown_causes(residual_slice: dict[str, Any]) -> list[str]:
    if residual_slice.get("state") != "UNKNOWN":
        return []
    return [
        item.strip()
        for item in str(residual_slice.get("rationale", "")).split(";")
        if item.strip()
    ]


def _filesystem_for_site(site: dict[str, Any]) -> str:
    match = re.search(r"(?:^|[\\/])fs[\\/](btrfs|ext4|xfs|f2fs)(?:[\\/]|$)", str(site.get("file", "")))
    return match.group(1) if match else ""


if __name__ == "__main__":
    raise SystemExit(main())
