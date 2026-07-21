# MOCC-SE Protocol C v1 Outputs

Protocol: `mocc.protocol_c.activation_accounting`

Schema version: `1`

Protocol version: `1.0.0`

Config: `configs/metadata_protocols/protocol_c_activation_accounting_v1.json`

This is a development and version-consistency artifact, not an unbiased
precision/recall evaluation. The inputs are development findings from
`outputs/confirmed_bugs.md`: ext4 #4 and Btrfs #15.

## Reproduction

Run from the repository root.

```powershell
python -m src.metadata_protocol_analyzer `
  --protocol configs/metadata_protocols/protocol_c_activation_accounting_v1.json `
  --source linux-sources/linux-v6.8-fs/fs/ext4/xattr.c `
  --source-version linux-v6.8 `
  --function ext4_expand_extra_isize_ea `
  --out outputs/mocc-protocol-c-v1/ext4-linux-v6.8.json

python -m src.metadata_protocol_analyzer `
  --protocol configs/metadata_protocols/protocol_c_activation_accounting_v1.json `
  --source linux-sources/linux-v6.8-fs/fs/btrfs/block-group.c `
  --source-version linux-v6.8 `
  --function reserve_chunk_space `
  --out outputs/mocc-protocol-c-v1/btrfs-linux-v6.8.json

python -m src.metadata_protocol_analyzer `
  --protocol configs/metadata_protocols/protocol_c_activation_accounting_v1.json `
  --source linux-sources/linux-v6.14-fs/fs/ext4/xattr.c `
  --source-version linux-v6.14 `
  --function ext4_expand_extra_isize_ea `
  --out outputs/mocc-protocol-c-v1/ext4-linux-v6.14.json

python -m src.metadata_protocol_analyzer `
  --protocol configs/metadata_protocols/protocol_c_activation_accounting_v1.json `
  --source linux-sources/linux-v6.14-fs/fs/btrfs/block-group.c `
  --source-version linux-v6.14 `
  --function reserve_chunk_space `
  --out outputs/mocc-protocol-c-v1/btrfs-linux-v6.14.json

python -m src.metadata_protocol_analyzer `
  --protocol configs/metadata_protocols/protocol_c_activation_accounting_v1.json `
  --source linux-sources/linux-v7.1-fs/fs/ext4/xattr.c `
  --source-version linux-v7.1 `
  --function ext4_expand_extra_isize_ea `
  --out outputs/mocc-protocol-c-v1/ext4-linux-v7.1.json

python -m src.metadata_protocol_analyzer `
  --protocol configs/metadata_protocols/protocol_c_activation_accounting_v1.json `
  --source linux-sources/linux-v7.1-fs/fs/btrfs/block-group.c `
  --source-version linux-v7.1 `
  --function reserve_chunk_space `
  --out outputs/mocc-protocol-c-v1/btrfs-linux-v7.1.json
```

## Result Summary

| Output | Candidates | Unknown | Candidate summary |
|---|---:|---:|---|
| `ext4-linux-v6.8.json` | 1 | 0 | `metadata_state_divergence`, `stale_result_provenance` |
| `ext4-linux-v6.14.json` | 1 | 0 | `metadata_state_divergence`, `stale_result_provenance` |
| `ext4-linux-v7.1.json` | 1 | 0 | `metadata_state_divergence`, `stale_result_provenance` |
| `btrfs-linux-v6.8.json` | 1 | 1 | `metadata_state_divergence`, `pending_without_reservation` |
| `btrfs-linux-v6.14.json` | 1 | 1 | `metadata_state_divergence`, `pending_without_reservation` |
| `btrfs-linux-v7.1.json` | 1 | 1 | `metadata_state_divergence`, `pending_without_reservation` |

Btrfs unknown entries are the conservative `return_outcome_unknown` records for
the negative `void return;` path. They are kept separate from definite
candidates.

## Witness Shape

Ext4 representative witness:

```text
necessary_step -> branch -> failure -> effect_created
  -> stale_result -> exit -> handler
```

Btrfs representative witness:

```text
necessary_step -> branch -> effect_created
  -> accounting_check -> exit
```

## SHA-256

```text
btrfs-linux-v6.14.json 95673BDFDB7CA98245725A785EF7330E88A1000E747887FDFE894C05601B322C
btrfs-linux-v6.8.json 94BFE434DE19E2B4DE129BD3B3E33B3748064AA7ED64F4490AEDFE0D591AF620
btrfs-linux-v7.1.json 2CA42B8A93104D479E350AF70BDD5CFB389EAE5DA17884CE3389D8A6D6F75587
ext4-linux-v6.14.json 16B132B87D5E62905AA029E14CE8CC57B9B2AF9B79AEBC94CFE838A508B1B1B4
ext4-linux-v6.8.json F2064DC6FD26F70220671E75BF8798237C431DC26A1DB5067A3C28736205BFAC
ext4-linux-v7.1.json F8F25ACCEB3CD0D7D5412B02E10ADE5255D2E5AEE1CE536076225410DEE1418E
```
