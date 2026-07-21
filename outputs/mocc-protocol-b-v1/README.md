# MOCC-SE Protocol B MVP Results

This directory records the device/topology rollback end-to-end runs. The Btrfs
functions and versions are protocol development and version-consistency inputs,
not an unbiased evaluation set.

## Versions

- Metadata protocol schema: `1`
- Protocol: `mocc.protocol_b.device_topology_rollback`
- Protocol version: `1.0.0`
- Analyzer: `src.metadata_protocol_analyzer`
- Protocol SHA-256: `F0208CE5D8C928623515E2966B63D7DA9B210F22E210055300BC8C9D0643E903`

## Commands

```powershell
python -m src.metadata_protocol_analyzer --protocol configs/metadata_protocols/protocol_b_device_topology_v1.json --source linux-sources/linux-v6.8-fs/fs/btrfs/relocation.c --source-version linux-v6.8 --function btrfs_recover_relocation --out outputs/mocc-protocol-b-v1/relocation-linux-v6.8.json
python -m src.metadata_protocol_analyzer --protocol configs/metadata_protocols/protocol_b_device_topology_v1.json --source linux-sources/linux-v6.8-fs/fs/btrfs/volumes.c --source-version linux-v6.8 --function btrfs_init_new_device --out outputs/mocc-protocol-b-v1/sprout-linux-v6.8.json
python -m src.metadata_protocol_analyzer --protocol configs/metadata_protocols/protocol_b_device_topology_v1.json --source linux-sources/linux-v6.14-fs/fs/btrfs/relocation.c --source-version linux-v6.14 --function btrfs_recover_relocation --out outputs/mocc-protocol-b-v1/relocation-linux-v6.14.json
python -m src.metadata_protocol_analyzer --protocol configs/metadata_protocols/protocol_b_device_topology_v1.json --source linux-sources/linux-v6.14-fs/fs/btrfs/volumes.c --source-version linux-v6.14 --function btrfs_init_new_device --out outputs/mocc-protocol-b-v1/sprout-linux-v6.14.json
```

## Results

| Source | Function | Events | Effect events | Compensation events | Candidates | Unknown |
|---|---|---:|---:|---:|---:|---:|
| Linux v6.8 | `btrfs_recover_relocation` | 46 | 1 | 0 | 1 | 0 |
| Linux v6.8 | `btrfs_init_new_device` | 61 | 6 | 2 | 1 | 1 |
| Linux v6.14 | `btrfs_recover_relocation` | 44 | 1 | 0 | 1 | 0 |
| Linux v6.14 | `btrfs_init_new_device` | 61 | 6 | 2 | 1 | 1 |

Each relocation candidate is an `incomplete_failure_completion` witness with
an open `reloc.root_pointer` effect before failed transaction commit. Each
sprout candidate retains the open `sprout.fs_devices_topology`,
`sprout.active_s_bdev`, and `sprout.active_latest_dev` effects. The device and
allocation-list membership effects are matched to their failure-path removals
and do not remain open.

The `post_commit_list` effect is a reviewed callee summary with `may` strength.
It is emitted as `ANALYSIS_UNKNOWN` with `may_effect_summary`, separate from the
high-certainty candidates. Fault-injection and patch evidence remain external
validation/ranking evidence and do not change protocol state.
