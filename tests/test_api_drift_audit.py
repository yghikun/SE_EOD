import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from src.api_drift_audit import (
    audit_api_drift,
    write_api_drift_csv,
    write_api_drift_json,
)
from src.function_extractor import extract_functions
from src.main import main
from src.parser import parse_c_file
from src.protocol_db import ResourceProtocol, ResourceProtocolDB
from src.wrapper_summary import WrapperSummary, WrapperSummaryDB


def _functions(source: str):
    with TemporaryDirectory() as directory:
        path = Path(directory) / "demo.c"
        path.write_text(source, encoding="utf-8")
        return extract_functions(parse_c_file(path))


def test_api_drift_audit_reports_unconfigured_similar_release_api():
    functions = _functions(
        """
void work(handle_t *handle)
{
    ext4_journal_stop_handle(handle);
}
"""
    )
    resource_map = {
        "acquire_functions": {
            "__ext4_journal_start_sb": {
                "resource_type": "journal_handle",
                "release": ["ext4_journal_stop"],
            }
        }
    }

    report = audit_api_drift(functions, resource_map)
    issues = report["issues"]

    assert any(
        issue["kind"] == "unconfigured_similar_lifecycle_api"
        and issue["function"] == "ext4_journal_stop_handle"
        and issue["role"] == "release"
        for issue in issues
    )
    assert any(
        issue["kind"] == "configured_function_unobserved"
        and issue["function"] == "__ext4_journal_start_sb"
        for issue in issues
    )


def test_api_drift_audit_reports_config_cross_file_mismatches():
    functions = _functions("void work(void) { known_release(ptr); }\n")
    resource_map = {
        "acquire_functions": {
            "known_alloc": {
                "resource_type": "memory",
                "release": ["known_release"],
            }
        }
    }
    protocols = ResourceProtocolDB(
        protocols=[
            ResourceProtocol(
                protocol_id="memory.new_alloc.release",
                resource_kind="memory",
                acquire_functions=("new_alloc",),
                release_functions=("new_release",),
                success_condition="return != NULL",
                resource_expr="lhs",
                required_action="new_release",
                exceptions=(),
                evidence_type="api_lifecycle",
                evidence_level="E2_API_PROTOCOL",
                confidence="medium",
            )
        ]
    )
    wrappers = WrapperSummaryDB(
        summaries=[
            WrapperSummary(
                function="known_wrapper",
                releases=("unknown_release",),
                resource_kinds=("memory",),
            )
        ]
    )

    report = audit_api_drift(
        functions,
        resource_map,
        protocols=protocols,
        wrapper_db=wrappers,
        candidate_rows=[
            {
                "candidate_type": "missing_cleanup",
                "missing_cleanup_candidates": json.dumps(["known_release(ptr)"]),
            },
            {
                "candidate_type": "missing_cleanup",
                "missing_cleanup_candidates": json.dumps(["known_release(ptr)"]),
            },
            {
                "candidate_type": "partial_cleanup",
                "missing_cleanup_candidates": json.dumps(["known_release(ptr)"]),
            },
        ],
    )
    kinds = {issue["kind"] for issue in report["issues"]}

    assert "protocol_acquire_missing_from_resource_map" in kinds
    assert "protocol_release_missing_from_resource_map" in kinds
    assert "wrapper_release_action_unknown" in kinds
    assert "frequent_missing_cleanup_action" in kinds


def test_api_drift_report_writers(tmp_path: Path):
    report = {
        "summary": {"issues": 1},
        "issues": [
            {
                "severity": "medium",
                "kind": "unconfigured_similar_lifecycle_api",
                "function": "foo_stop_new",
                "role": "release",
            }
        ],
    }
    json_out = tmp_path / "drift.json"
    csv_out = tmp_path / "drift.csv"

    write_api_drift_json(report, json_out)
    rows_written = write_api_drift_csv(report, csv_out)

    assert json.loads(json_out.read_text(encoding="utf-8"))["summary"]["issues"] == 1
    assert rows_written == 1
    with csv_out.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["function"] == "foo_stop_new"


def test_cli_writes_api_drift_report(tmp_path: Path):
    linux = tmp_path / "linux"
    ext4 = linux / "fs" / "ext4"
    ext4.mkdir(parents=True)
    (ext4 / "demo.c").write_text(
        """
void work(handle_t *handle)
{
    ext4_journal_stop_handle(handle);
}
""",
        encoding="utf-8",
    )
    out = tmp_path / "error_paths.csv"
    drift_json = tmp_path / "api_drift_report.json"
    drift_csv = tmp_path / "api_drift_report.csv"

    rc = main(
        [
            "--linux",
            str(linux),
            "--out",
            str(out),
            "--audit-api-drift",
            "--api-drift-json-out",
            str(drift_json),
            "--api-drift-csv-out",
            str(drift_csv),
        ]
    )

    assert rc == 0
    report = json.loads(drift_json.read_text(encoding="utf-8"))
    assert drift_csv.exists()
    assert any(
        issue["kind"] == "unconfigured_similar_lifecycle_api"
        and issue["function"] == "ext4_journal_stop_handle"
        for issue in report["issues"]
    )
