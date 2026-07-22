import json
from pathlib import Path

import pytest

from src.metadata_batch_scan import (
    BatchScanCoverageError,
    _active_protocols,
    main,
    scan_source_tree,
)
from src.metadata_validation_manifest import ProtocolFreeze


ROOT = Path(__file__).parents[1]
FREEZE_PATH = ROOT / "configs" / "validation" / "protocol_freeze_v1.json"


def _write_source(root: Path, relative: str, source: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_batch_scan_produces_candidate_queue_not_bug_claims(tmp_path):
    _write_source(
        tmp_path,
        "fs/ext4/fresh.c",
        """
int fresh_case(void)
{
    int ret = ext4_ext_remove_space();
    if (ret)
        goto out;
out:
    return 0;
}
""",
    )

    payload = scan_source_tree(
        tmp_path,
        workspace=ROOT,
        source_version="7.1",
        include=("*.c",),
        include_confirmed_functions=True,
        include_regression_seeds=True,
    ).to_dict()

    assert payload["result_semantics"] == "candidate_queue_not_bug_claims"
    assert payload["validation_gate"]["bug_claims_allowed"] is False
    assert payload["summary"]["scanned_files"] == 1
    assert payload["summary"]["discovery_review_queue_entries"] >= 1
    assert payload["protocol_candidates"] == []
    assert payload["coverage_health"]["status"] == "no_protocol_analysis_exercised"
    assert payload["coverage_health"]["protocol_analysis_exercised"] is False


def test_batch_scan_can_require_real_protocol_analysis(tmp_path):
    _write_source(
        tmp_path,
        "fs/ext4/fresh.c",
        """
int fresh_case(void)
{
    int ret = ext4_ext_remove_space();
    if (ret)
        goto out;
out:
    return 0;
}
""",
    )

    with pytest.raises(BatchScanCoverageError, match="no exact or semantic"):
        scan_source_tree(
            tmp_path,
            workspace=ROOT,
            source_version="7.1",
            include_confirmed_functions=True,
            include_regression_seeds=True,
            require_protocol_analysis=True,
        )


def test_active_protocols_are_filtered_by_rule_applicability():
    freeze = ProtocolFreeze.read_json(FREEZE_PATH)

    protocol_ids = {
        protocol.protocol_id for protocol in _active_protocols(ROOT, freeze, "7.1")
    }

    assert "mocc.protocol_b.device_topology_rollback" not in protocol_ids
    assert "mocc.protocol_a.replay_recovery" in protocol_ids
    assert "mocc.protocol_c.activation_accounting" in protocol_ids
    assert "mocc.protocol_d.transaction_lifecycle" in protocol_ids
    assert "mocc.protocol_e.allocation_lifecycle" in protocol_ids


def test_batch_scan_cli_writes_report(tmp_path):
    _write_source(
        tmp_path,
        "fs/ext4/fresh.c",
        """
int fresh_case(void)
{
    int ret = ext4_ext_remove_space();
    if (ret)
        goto out;
out:
    return 0;
}
""",
    )
    output = tmp_path / "scan.json"

    assert (
        main(
            [
                "--workspace",
                str(ROOT),
                "--source-root",
                str(tmp_path),
                "--source-version",
                "7.1",
                "--include-confirmed-functions",
                "--include-regression-seeds",
                "--out",
                str(output),
            ]
        )
        == 0
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["summary"]["scanned_files"] == 1
    assert payload["result_semantics"] == "candidate_queue_not_bug_claims"
