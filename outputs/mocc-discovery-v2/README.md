# MOCC-SE Discovery v2

This directory contains M11 fresh discovery reports. These reports are
development review queues, not confirmed bugs and not benchmark labels.

Generation command:

```powershell
python -m src.metadata_protocol_discovery `
  --protocol configs/metadata_protocols/protocol_a_replay_recovery_v1.json `
  --protocol configs/metadata_protocols/protocol_b_device_topology_v1.json `
  --protocol configs/metadata_protocols/protocol_c_activation_accounting_v1.json `
  --source-root linux-sources/linux-v6.8-fs/fs `
  --source-version linux-v6.8 `
  --out outputs/mocc-discovery-v2/linux-v6.8-fresh-review.json
```

The CLI defaults exclude functions listed in `outputs/confirmed_bugs.md` and
all protocol `entry_functions`, so exact regression seeds do not enter the fresh
queue. Use `--include-confirmed-functions` or `--include-regression-seeds` only
for regression/debug runs.

Current `linux-v6.8-fresh-review.json` summary:

```text
schema_version                  2
scanned_files                   278
scanned_functions               8544
applicable_functions            1
protocol_candidate_occurrences  0
discovery_review_occurrences    4
fresh_review_functions          4
fresh_review_root_causes        2
fresh_review_queue_entries      4
excluded_functions              16
analysis_unknown                0
discovery_unknown               0
```

Pattern distribution:

```text
mutation_failure_cleanup  2
failure_return_mismatch    2
```

`fresh_review_queue` is deduplicated by `(function, root_cause_fingerprint)`.
Each item is a source-review lead that still needs manual inspection, version
diffing, and repair/reproduction evidence before it can be promoted to
`outputs/confirmed_bugs.md`.

Review queue generation command:

```powershell
python -m src.metadata_finding_review `
  --discovery-report outputs/mocc-discovery-v2/linux-v6.8-fresh-review.json `
  --source-root linux-sources/linux-v6.8-fs/fs `
  --context-lines 4 `
  --include-discovery-review `
  --out-json outputs/mocc-discovery-v2/linux-v6.8-fresh-review-queue.json `
  --out-md outputs/mocc-discovery-v2/linux-v6.8-fresh-review-queue.md
```

Initial source triage is recorded in
`linux-v6.8-fresh-initial-source-triage.md`. The strongest current lead is an
ext4 fast-commit replay helper error-propagation family in
`ext4_ext_replay_set_iblocks()` / `ext4_ext_clear_bb()`. It is not yet a
confirmed bug record; it still needs patch or fault-injection validation.

The remaining Btrfs entries are currently treated as rule-feedback leads rather
than high-confidence bug candidates: `clean_dirty_subvols()` looks like cleanup
handler noise, and `btrfs_reloc_post_snapshot()` needs an accounting/reservation
model before it can be interpreted safely.

The currently collected high-confidence candidate notes are documented in
`high-confidence-candidates.md`.

The first local validation pass is recorded in
`ext4-fc-helper-fault-validation.md` and
`ext4-fc-helper-fault-validation.json`. It models the observed helper control
flow and shows that the original caller returns success for all 10 injected
helper-failure scenarios, while a minimal fixed model propagates every injected
error.

`ext4-fc-helper-error-propagation-rfc.patch` is a local RFC sketch for the same
finding. It is intended as a starting point for a full-kernel patch/test pass,
not as a submitted or accepted fix.
