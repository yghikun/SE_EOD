# MOCC-SE Finding Review v1

This directory contains the first M8 development review queue derived from the
M7 discovery report.

Inputs:

```text
outputs/mocc-discovery-v1-linux-v6.8.json
linux-sources/linux-v6.8-fs/fs
```

Reproduction command:

```powershell
python -m src.metadata_finding_review `
  --discovery-report outputs/mocc-discovery-v1-linux-v6.8.json `
  --source-root linux-sources/linux-v6.8-fs/fs `
  --context-lines 4 `
  --out-json outputs/mocc-finding-review-v1/linux-v6.8-review-queue.json `
  --out-md outputs/mocc-finding-review-v1/linux-v6.8-review-queue.md
```

Current queue:

```text
review_items        19
protocol_candidates 19
discovery_reviews   0
```

Protocol split:

```text
mocc.protocol_a.replay_recovery           15
mocc.protocol_b.device_topology_rollback   2
mocc.protocol_c.activation_accounting      2
```

Violation split:

```text
failure_reported_as_success       15
incomplete_failure_completion      2
metadata_state_divergence          2
```

The JSON queue keeps structured witness, unresolved failures, open effects,
accounting state, review focus, likely summary gaps, and source snippets. The
Markdown queue is for fast source-level reading.

Source-review annotation pass:

```powershell
python -m src.metadata_finding_review `
  --discovery-report outputs/mocc-discovery-v1-linux-v6.8.json `
  --source-root linux-sources/linux-v6.8-fs/fs `
  --context-lines 4 `
  --annotations outputs/mocc-finding-review-v1/linux-v6.8-source-review-notes.json `
  --out-json outputs/mocc-finding-review-v1/linux-v6.8-reviewed-queue.json `
  --out-md outputs/mocc-finding-review-v1/linux-v6.8-reviewed-queue.md
```

Annotated source-review summary:

```text
reviewed_items      19
unreviewed_items     0
likely_true_candidate 19
high confidence      17
medium confidence     2
unmatched annotations 0
conflicting annotations 0
```

The annotations intentionally group repeated Protocol A occurrences by source
function.  They are development triage notes: useful for deciding where to
inspect fixed versions and where to improve summaries, but not final confirmed
bug labels.

Initial source triage:

```powershell
python -m src.metadata_finding_triage `
  --review-queue outputs/mocc-finding-review-v1/linux-v6.8-reviewed-queue.json `
  --out-json outputs/mocc-finding-review-v1/linux-v6.8-initial-source-triage.json `
  --out-md outputs/mocc-finding-review-v1/linux-v6.8-initial-source-triage.md
```

Triage summary:

```text
triage_items                       19
reviewed_items                     19
unreviewed_items                    0
candidate_survives_initial_review  19

mocc.protocol_a.replay_recovery     15
mocc.protocol_b.device_topology_rollback 2
mocc.protocol_c.activation_accounting    2
```

Cross-version discovery matrix:

```powershell
python -m src.metadata_finding_matrix `
  --report v6.8=outputs/mocc-discovery-v1-linux-v6.8.json `
  --report v6.14=outputs/mocc-discovery-v1-linux-v6.14.json `
  --report v7.1=outputs/mocc-discovery-v1-linux-v7.1.json `
  --out-json outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-discovery-matrix.json `
  --out-md outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-discovery-matrix.md
```

Matrix summary:

```text
v6.8  candidates 19, unknown 2
v6.14 candidates 20, unknown 2
v7.1  candidates 14, unknown 3

persistent candidate functions:
  ext4_fc_replay_add_range
  ext4_fc_replay_del_range
  btrfs_recover_relocation
  btrfs_init_new_device
  reserve_chunk_space
  ext4_expand_extra_isize_ea

candidate removed/cleared by v7.1:
  ext4_fc_replay_inode
  xfs_rtcopy_summary

candidate added after v6.8:
  xfs_rtginode_ensure
```

Function-level repair diffs:

```powershell
python -m src.metadata_function_diff `
  --function xfs_rtcopy_summary `
  --source v6.8=linux-sources/linux-v6.8-fs/fs/xfs/xfs_rtalloc.c `
  --source v6.14=linux-sources/linux-v6.14-fs/fs/xfs/xfs_rtalloc.c `
  --source v7.1=linux-sources/linux-v7.1-fs/fs/xfs/xfs_rtalloc.c `
  --out-json outputs/mocc-finding-review-v1/xfs_rtcopy_summary-v6.8-v6.14-v7.1-function-diff.json `
  --out-md outputs/mocc-finding-review-v1/xfs_rtcopy_summary-v6.8-v6.14-v7.1-function-diff.md
```

```powershell
python -m src.metadata_function_diff `
  --function ext4_fc_replay_inode `
  --source v6.8=linux-sources/linux-v6.8-fs/fs/ext4/fast_commit.c `
  --source v6.14=linux-sources/linux-v6.14-fs/fs/ext4/fast_commit.c `
  --source v7.1=linux-sources/linux-v7.1-fs/fs/ext4/fast_commit.c `
  --out-json outputs/mocc-finding-review-v1/ext4_fc_replay_inode-v6.8-v6.14-v7.1-function-diff.json `
  --out-md outputs/mocc-finding-review-v1/ext4_fc_replay_inode-v6.8-v6.14-v7.1-function-diff.md
```

Both disappearing Protocol A functions have a reusable repair signal in v7.1:

```text
xfs_rtcopy_summary:      return 0 -> return error
ext4_fc_replay_inode:    return 0 -> return ret
semantic hint:           local_return_propagation_repair
```

Repair evidence ledger:

```powershell
python -m src.metadata_repair_evidence `
  --triage outputs/mocc-finding-review-v1/linux-v6.8-initial-source-triage.json `
  --function-diff outputs/mocc-finding-review-v1/xfs_rtcopy_summary-v6.8-v6.14-v7.1-function-diff.json `
  --function-diff outputs/mocc-finding-review-v1/ext4_fc_replay_inode-v6.8-v6.14-v7.1-function-diff.json `
  --out-json outputs/mocc-finding-review-v1/linux-v6.8-repair-evidence-ledger.json `
  --out-md outputs/mocc-finding-review-v1/linux-v6.8-repair-evidence-ledger.md
```

Current repair evidence summary:

```text
triage_items                19
items_with_repair_evidence   7
items_without_repair_evidence 12
repair evidence functions:
  ext4_fc_replay_inode
  xfs_rtcopy_summary
```

Development bug-hunt report:

```powershell
python -m src.metadata_bug_hunt_report `
  --reviewed-queue outputs/mocc-finding-review-v1/linux-v6.8-reviewed-queue.json `
  --triage outputs/mocc-finding-review-v1/linux-v6.8-initial-source-triage.json `
  --matrix outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-discovery-matrix.json `
  --repair-evidence outputs/mocc-finding-review-v1/linux-v6.8-repair-evidence-ledger.json `
  --out-json outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-development-bug-hunt-report.json `
  --out-md outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-development-bug-hunt-report.md
```

Bug-hunt report summary:

```text
review_items                       19
candidates surviving source review 19
items_with_repair_evidence          7
persistent candidates              12
removed/cleared functions           2
added functions to inspect          1
```

This is project-development material. It is not a frozen benchmark, and these
19 items must not be reported as independent precision/recall evidence.

Confirmed bug linkage:

```powershell
python -m src.metadata_confirmed_bug_linkage `
  --bug-hunt-report outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-development-bug-hunt-report.json `
  --confirmed-bugs outputs/confirmed_bugs.md `
  --out-json outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-confirmed-bug-linkage.json `
  --out-md outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-confirmed-bug-linkage.md
```

Linkage summary:

```text
candidate queue entries                 22
entries linked to confirmed records     22
unique confirmed records                18
unique confirmed records linked         11
confirmed records outside this queue     7
```

The 22 entries are occurrence/priority-queue views, not 22 independent bugs.
The linkage covers confirmed records #1, #2, #4, #5, #7, #8, #13, #15, and
#16-#18. Records outside the current M9 queue remain confirmed; they are not
reclassified as pending candidates. This report is development bookkeeping,
not a precision/recall dataset.
