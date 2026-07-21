# MOCC-SE Protocol A MVP Results

This directory records the first replay/recovery end-to-end run. These inputs
are the protocol development set and version-difference checks, not an unbiased
evaluation set.

## Versions

- Metadata protocol schema: `1`
- Protocol: `mocc.protocol_a.replay_recovery`
- Protocol version: `1.0.0`
- Analyzer: `src.metadata_protocol_analyzer`
- Test baseline at generation: `239 passed`
- Frozen Protocol A SHA-256: `C329F3D4E2EBA2527EAA6962D81FC9EB38F81E45DA9F873F56ABB6492F50E2E3`

## Commands

Each command used the same protocol file:

```powershell
python -m src.metadata_protocol_analyzer --protocol configs/metadata_protocols/protocol_a_replay_recovery_v1.json --source linux-sources/linux-v6.8-fs/fs/ext4/fast_commit.c --source-version linux-v6.8 --function ext4_fc_replay_add_range --function ext4_fc_replay_del_range --function ext4_fc_replay_inode --out outputs/mocc-protocol-a-v1/ext4-linux-v6.8.json
python -m src.metadata_protocol_analyzer --protocol configs/metadata_protocols/protocol_a_replay_recovery_v1.json --source linux-sources/linux-v6.8-fs/fs/xfs/xfs_rtalloc.c --source-version linux-v6.8 --function xfs_rtcopy_summary --out outputs/mocc-protocol-a-v1/xfs-linux-v6.8.json
python -m src.metadata_protocol_analyzer --protocol configs/metadata_protocols/protocol_a_replay_recovery_v1.json --source linux-sources/linux-v6.14-fs/fs/xfs/xfs_rtalloc.c --source-version linux-v6.14 --function xfs_rtginode_ensure --out outputs/mocc-protocol-a-v1/xfs-linux-v6.14.json
python -m src.metadata_protocol_analyzer --protocol configs/metadata_protocols/protocol_a_replay_recovery_v1.json --source linux-sources/linux-v7.1-fs/fs/ext4/fast_commit.c --source-version linux-v7.1 --function ext4_fc_replay_inode --out outputs/mocc-protocol-a-v1/ext4-linux-v7.1-fixed.json
python -m src.metadata_protocol_analyzer --protocol configs/metadata_protocols/protocol_a_replay_recovery_v1.json --source linux-sources/linux-v7.1-fs/fs/xfs/xfs_rtalloc.c --source-version linux-v7.1 --function xfs_rtcopy_summary --out outputs/mocc-protocol-a-v1/xfs-linux-v7.1-fixed.json
python -m src.metadata_protocol_analyzer --protocol configs/metadata_protocols/protocol_a_replay_recovery_v1.json --source linux-sources/linux-v6.14-fs/fs/xfs/xfs_rtalloc.c --source-version linux-v6.14-held-out --function xfs_rtcopy_summary --out outputs/mocc-protocol-a-v1/frozen-xfs-linux-v6.14.json
```

## Development Results

| Source | Function | Events | Candidates | Unknown |
|---|---|---:|---:|---:|
| Linux v6.8 ext4 | `ext4_fc_replay_inode` | 24 | 7 | 0 |
| Linux v6.8 ext4 | `ext4_fc_replay_add_range` | 26 | 6 | 0 |
| Linux v6.8 ext4 | `ext4_fc_replay_del_range` | 15 | 3 | 0 |
| Linux v6.8 XFS | `xfs_rtcopy_summary` | 11 | 3 | 0 |
| Linux v6.14 XFS | `xfs_rtginode_ensure` | 5 | 1 | 0 |

Candidate counts are failure occurrences, not bug counts. Every candidate has
a representative witness containing a necessary step, return-contract branch,
failure token, and observed success exit.

## Version Difference

| Source | Function | Candidates | Unknown | Interpretation |
|---|---|---:|---:|---|
| Linux v7.1 ext4 | `ext4_fc_replay_inode` | 0 | 1 | The old swallowed-success violation is absent; one return expression is outside the MVP contract and remains unknown. |
| Linux v7.1 XFS | `xfs_rtcopy_summary` | 0 | 0 | The shared cleanup returns `error`, so the v6.8 violation is absent. |

The remaining ext4 add/del functions and the observed XFS ensure source are not
called fixed here. Historical evidence and submitted patches remain separate
from static protocol output.

## Frozen Version Check

After recording the protocol hash above, the unchanged protocol was run on the
previously unused Linux v6.14 `xfs_rtcopy_summary` source. It produced 11 events,
3 failure-occurrence candidates, 0 unknown records, and a complete CFG snapshot.
This is a held-out version check for the already defined operation semantics;
it is not a claim of unbiased corpus-wide precision or recall.
