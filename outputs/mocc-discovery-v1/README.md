# MOCC-SE Discovery v1

This directory documents the retained M7 development discovery report:

```text
outputs/mocc-discovery-v1-linux-v6.8.json
```

Reproduction command:

```powershell
python -m src.metadata_protocol_discovery `
  --protocol configs/metadata_protocols/protocol_a_replay_recovery_v1.json `
  --protocol configs/metadata_protocols/protocol_b_device_topology_v1.json `
  --protocol configs/metadata_protocols/protocol_c_activation_accounting_v1.json `
  --source-root linux-sources/linux-v6.8-fs/fs `
  --source-version linux-v6.8 `
  --out outputs/mocc-discovery-v1-linux-v6.8.json
```

Current summary:

```text
scanned_files                  278
scanned_functions              8544
applicable_functions           8
protocol_candidate_occurrences 19
protocol_candidate_families    19
discovery_review_occurrences   0
discovery_review_families      0
analysis_unknown               2
discovery_unknown              0
```

Classification policy:

- `PROTOCOL_CANDIDATE`: exact operation-entry analysis result.
- `DISCOVERY_REVIEW`: non-entry semantic applicability result that needs human
  review before it can be treated as protocol-proven.
- `DISCOVERY_REVIEW_UNKNOWN`: analyzer uncertainty from a non-entry semantic
  match.
- `DISCOVERY_UNKNOWN`: discovery-stage ambiguity, such as multiple operations
  with indistinguishable applicability.

This report is project-development evidence only. It is not an independent
precision/recall benchmark and should not be mixed with frozen evaluation
statistics.
