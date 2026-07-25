from __future__ import annotations

import json
from pathlib import Path

from src.semantic_blocker_impact import (
    BODY_IN_ANALYSIS_ROOT,
    BODY_IN_CALLER_TRANSLATION_UNIT,
    BODY_OUTSIDE_ANALYSIS_ROOT,
    HEADER_INLINE_NOT_LOADED,
    INDIRECT_TARGET_BODY_UNKNOWN,
    MACRO_OR_CONDITIONAL_BODY,
    MULTIPLE_DEFINITIONS,
    NO_EXACT_DEFINITION,
    SourceDefinition,
    SourceDefinitionIndex,
    build_semantic_blocker_impact,
    build_source_definition_index,
    semantic_blocker_impact_to_markdown,
    write_semantic_blocker_impact,
)
from src.unknown_triage import (
    ERROR_PARTITION_SELECTION_UNPROVEN,
    INDIRECT_TARGET_SET_UNPROVEN,
    SUMMARY_BODY_UNAVAILABLE,
)


def _site(file: str, line: int, expression: str) -> dict[str, object]:
    return {"file": file, "line": line, "expression": expression}


def _unknown_report(
    function: str,
    causes: list[str],
    *,
    file: str,
    line: int,
) -> dict[str, object]:
    return {
        "kind": "METADATA_RESIDUAL_UNKNOWN",
        "classification": "METADATA_RESIDUAL_UNKNOWN",
        "function": function,
        "unknown_causes": causes,
        "residual_slice": {
            "failure_site": _site(file, line, "ret = fail_metadata()"),
            "exit_site": _site(file, line + 5, "return ret;"),
        },
    }


def _write_run(
    root: Path,
    filesystem: str,
    reports: list[dict[str, object]],
    *,
    source_path: str | None = None,
) -> Path:
    run = root / f"run-{filesystem}"
    reports_path = run / "reports" / "all_reports.json"
    reports_path.parent.mkdir(parents=True, exist_ok=True)
    reports_path.write_text(json.dumps(reports), encoding="utf-8")
    (run / "evaluation.json").write_text(
        json.dumps(
            {
                "summary": {
                    "schema_version": 4,
                    "source_path": source_path or f"linux-sources/fs/{filesystem}",
                }
            }
        ),
        encoding="utf-8",
    )
    return run


def _blocker(impact: dict[str, object], detail: str) -> dict[str, object]:
    return next(item for item in impact["blockers"] if item["detail"] == detail)


def test_profile_distinguishes_mentions_reports_causes_and_proof_gaps(
    tmp_path: Path,
):
    file = "linux-sources/fs/btrfs/example.c"
    reports = [
        _unknown_report(
            "same_gap",
            [
                "unresolved metadata helper on error path: helper_a",
                "unresolved metadata helper on error path: helper_a",
                "unresolved metadata helper on error path: helper_b",
            ],
            file=file,
            line=10,
        ),
        _unknown_report(
            "multi_gap",
            [
                "unresolved metadata helper on error path: helper_a",
                "callee: unclassified_return_exit",
            ],
            file=file,
            line=20,
        ),
        _unknown_report(
            "indirect",
            ["callee: indirect_call: ops->work(ctx)"],
            file=file,
            line=30,
        ),
        {"kind": "FUNCTION_BOUNDARY_RESIDUAL", "function": "ignored"},
    ]
    run = _write_run(tmp_path, "btrfs", reports)
    before = (run / "reports" / "all_reports.json").read_bytes()

    impact = build_semantic_blocker_impact([run])

    assert impact["measurement_only"] is True
    assert "must not change analyzer classification" in impact[
        "non_interference_contract"
    ]
    assert (run / "reports" / "all_reports.json").read_bytes() == before
    assert impact["summary"] == {
        **impact["summary"],
        "evaluation_reports": 4,
        "unknown_reports": 3,
        "unknown_cause_mentions": 6,
        "unknown_single_cause_reports": 1,
        "unknown_sole_gap_reports": 2,
        "unknown_multi_gap_reports": 1,
        "unknown_gap_cardinality_counts": {"1": 2, "2": 1},
    }
    gaps = {item["proof_gap"]: item for item in impact["unknown_proof_gaps"]}
    assert gaps[SUMMARY_BODY_UNAVAILABLE]["report_count"] == 2
    assert gaps[SUMMARY_BODY_UNAVAILABLE]["mention_count"] == 4
    assert gaps[SUMMARY_BODY_UNAVAILABLE]["sole_gap_report_count"] == 1
    assert gaps[ERROR_PARTITION_SELECTION_UNPROVEN]["report_count"] == 1
    assert gaps[INDIRECT_TARGET_SET_UNPROVEN]["sole_gap_report_count"] == 1
    helper_a = _blocker(impact, "helper_a")
    assert helper_a["mention_count"] == 3
    assert helper_a["report_count"] == 2
    assert helper_a["body_availability_counts"] == {"SOURCE_INDEX_UNAVAILABLE": 2}
    assert helper_a["top_functions"] == [
        {"function": "same_gap", "report_count": 1},
        {"function": "multi_gap", "report_count": 1},
    ]


def test_profile_links_exact_oracle_location_and_aggregates_pending_reason(
    tmp_path: Path,
):
    file = "linux-sources/fs/ext4/example.c"
    report = _unknown_report(
        "work",
        ["unresolved metadata helper on error path: helper"],
        file=file,
        line=10,
    )
    run = _write_run(tmp_path, "ext4", [report])
    stable_report = {
        "filesystem": "ext4",
        "function": "work",
        "failure_site": report["residual_slice"]["failure_site"],
        "exit_site": report["residual_slice"]["exit_site"],
    }
    oracle = {
        "oracle_id": "EXT4-001",
        "stable_report": stable_report,
        "expected_final_state": "METADATA_RESIDUAL_UNKNOWN",
        "manual_class": "MANUAL_UNCERTAINTY",
        "root_cause_family": "ONE_SHOT_STATE_SEMANTICS",
    }
    audit = {
        "transitions": [
            {
                "oracle_id": "EXT4-001",
                "status": "RETAINED_FOR_LATER_MILESTONE",
                "reason": "manual_uncertainty_still_visible",
            }
        ]
    }

    impact = build_semantic_blocker_impact(
        [run], oracle_records=[oracle], oracle_audit=audit
    )

    assert impact["summary"]["unknown_oracle_covered_reports"] == 1
    assert impact["summary"]["oracle_pending"] == 1
    assert impact["unknown_reports"][0]["oracle_id"] == "EXT4-001"
    constraint = impact["oracle_pending_constraints"][0]
    assert constraint["constraint"] == "manual_uncertainty_still_visible"
    assert constraint["report_count"] == 1
    unknown_row = next(
        item
        for item in impact["decision_surface"]
        if item["constraint_id"] == f"UNKNOWN:{SUMMARY_BODY_UNAVAILABLE}"
    )
    assert unknown_row["priority_tier"] == "ORACLE_VALIDATED_PENDING"


def test_profile_preserves_duplicate_oracles_and_disambiguates_by_effect(
    tmp_path: Path,
):
    file = "linux-sources/fs/xfs/example.c"
    report = _unknown_report(
        "work",
        ["unresolved metadata helper on error path: helper"],
        file=file,
        line=10,
    )
    effect = {
        "root": "inode",
        "key": "i_flags",
        "plane": "RECOVERY",
        "delta": "SET",
        "value": "flag",
        "site": _site(file, 5, "inode->i_flags = flag"),
    }
    other_effect = {**effect, "key": "i_state", "value": "state"}
    report["residual_slice"]["residuals"] = [effect]
    run = _write_run(tmp_path, "xfs", [report])
    location = {
        "filesystem": "xfs",
        "function": "work",
        "failure_site": report["residual_slice"]["failure_site"],
        "exit_site": report["residual_slice"]["exit_site"],
    }
    matching_report = {**location, "residual_effects": [effect]}
    other_report = {**location, "residual_effects": [other_effect]}
    oracles = [
        {
            "oracle_id": "XFS-001",
            "stable_key": "matching",
            "stable_report": matching_report,
            "expected_final_state": "OUT_OF_SCOPE",
            "manual_class": "PRIVATE_STATE",
        },
        {
            "oracle_id": "XFS-002",
            "stable_key": "matching",
            "stable_report": matching_report,
            "expected_final_state": "OUT_OF_SCOPE",
            "manual_class": "PRIVATE_STATE",
        },
        {
            "oracle_id": "XFS-003",
            "stable_key": "other",
            "stable_report": other_report,
            "expected_final_state": "CLOSED",
            "manual_class": "CLEANED_STATE",
        },
    ]

    impact = build_semantic_blocker_impact([run], oracle_records=oracles)

    row = impact["unknown_reports"][0]
    assert row["oracle_ids"] == ["XFS-001", "XFS-002"]
    assert row["oracle_linkage_status"] == "MATCHED_EFFECTS"
    assert row["oracle_candidate_ids"] == ["XFS-001", "XFS-002", "XFS-003"]
    assert impact["summary"]["unknown_oracle_covered_reports"] == 1
    blocker = _blocker(impact, "helper")
    assert blocker["oracle_covered_report_count"] == 1
    assert blocker["oracle_ids"] == ["XFS-001", "XFS-002"]
    assert blocker["expected_destination_counts"] == {"OUT_OF_SCOPE": 1}

    report["residual_slice"]["residuals"] = [
        {**effect, "key": "unrelated", "value": "unrelated"}
    ]
    _write_run(tmp_path, "xfs", [report])
    ambiguous = build_semantic_blocker_impact([run], oracle_records=oracles)
    ambiguous_row = ambiguous["unknown_reports"][0]
    assert ambiguous_row["oracle_ids"] == []
    assert ambiguous_row["oracle_linkage_status"] == "AMBIGUOUS_LOCATION"
    assert ambiguous["summary"]["unknown_oracle_ambiguous_reports"] == 1


def test_profile_classifies_exact_source_body_availability(tmp_path: Path):
    source_root = tmp_path / "linux" / "fs"
    analysis_root = source_root / "btrfs"
    caller = analysis_root / "caller.c"
    outside = source_root / "xfs" / "shared.c"
    definitions = {
        "helper_tu": (SourceDefinition("helper_tu", caller.as_posix(), 1, False),),
        "helper_root": (
            SourceDefinition(
                "helper_root", (analysis_root / "other.c").as_posix(), 2, False
            ),
        ),
        "helper_outside": (
            SourceDefinition("helper_outside", outside.as_posix(), 3, False),
        ),
        "helper_header": (
            SourceDefinition(
                "helper_header", (source_root / "shared.h").as_posix(), 4, True
            ),
        ),
        "helper_multiple": (
            SourceDefinition(
                "helper_multiple", (analysis_root / "one.c").as_posix(), 5, False
            ),
            SourceDefinition(
                "helper_multiple", (analysis_root / "two.c").as_posix(), 6, False
            ),
        ),
    }
    source_index = SourceDefinitionIndex(
        definitions=definitions,
        macros={"helper_macro": ((source_root / "macros.h").as_posix(),)},
        parse_failures=(),
        source_root=source_root.as_posix(),
    )
    helpers = [
        "helper_tu",
        "helper_root",
        "helper_outside",
        "helper_header",
        "helper_multiple",
        "helper_macro",
        "helper_missing",
    ]
    reports = [
        _unknown_report(
            f"work_{index}",
            [f"unresolved metadata helper on error path: {helper}"],
            file=caller.as_posix(),
            line=10 + index * 10,
        )
        for index, helper in enumerate(helpers)
    ]
    reports.append(
        _unknown_report(
            "work_indirect",
            ["callee: indirect_call: ops->work(ctx)"],
            file=caller.as_posix(),
            line=100,
        )
    )
    run = _write_run(
        tmp_path,
        "btrfs",
        reports,
        source_path=analysis_root.as_posix(),
    )

    impact = build_semantic_blocker_impact([run], source_index=source_index)

    expected = {
        "helper_tu": BODY_IN_CALLER_TRANSLATION_UNIT,
        "helper_root": BODY_IN_ANALYSIS_ROOT,
        "helper_outside": BODY_OUTSIDE_ANALYSIS_ROOT,
        "helper_header": HEADER_INLINE_NOT_LOADED,
        "helper_multiple": MULTIPLE_DEFINITIONS,
        "helper_macro": MACRO_OR_CONDITIONAL_BODY,
        "helper_missing": NO_EXACT_DEFINITION,
        "ops->work(ctx)": INDIRECT_TARGET_BODY_UNKNOWN,
    }
    for detail, availability in expected.items():
        assert _blocker(impact, detail)["body_availability_counts"] == {
            availability: 1
        }
    summary_gap = next(
        item
        for item in impact["unknown_proof_gaps"]
        if item["proof_gap"] == SUMMARY_BODY_UNAVAILABLE
    )
    assert summary_gap["source_available_report_count"] == 4


def test_source_index_finds_exact_functions_and_function_like_macros(tmp_path: Path):
    (tmp_path / "body.c").write_text(
        "int visible_body(void)\n{\n\treturn 0;\n}\n",
        encoding="utf-8",
    )
    (tmp_path / "inline.h").write_text(
        "static inline int inline_body(void) { return 0; }\n"
        "#define FUNCTION_MACRO(arg) ((arg) + 1)\n",
        encoding="utf-8",
    )

    index = build_source_definition_index(tmp_path)

    assert index.definitions["visible_body"][0].in_header is False
    assert index.definitions["inline_body"][0].in_header is True
    assert "FUNCTION_MACRO" in index.macros
    assert index.parse_failures == ()


def test_profile_reports_cross_filesystem_reuse_and_writes_json_and_markdown(
    tmp_path: Path,
):
    runs = []
    for index, filesystem in enumerate(("btrfs", "xfs")):
        file = f"linux-sources/fs/{filesystem}/example.c"
        report = _unknown_report(
            f"{filesystem}_work",
            ["unresolved metadata helper on error path: shared_helper"],
            file=file,
            line=10 + index,
        )
        runs.append(_write_run(tmp_path, filesystem, [report]))

    impact = build_semantic_blocker_impact(runs)
    blocker = _blocker(impact, "shared_helper")

    assert blocker["report_count"] == 2
    assert blocker["filesystem_count"] == 2
    assert blocker["cross_filesystem_reuse"] is True
    outputs = write_semantic_blocker_impact(impact, tmp_path / "profile")
    assert json.loads(outputs["json"].read_text(encoding="utf-8"))[
        "measurement_only"
    ] is True
    markdown = outputs["markdown"].read_text(encoding="utf-8")
    assert markdown == semantic_blocker_impact_to_markdown(impact)
    assert "shared_helper" in markdown
