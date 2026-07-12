# experiment-v1.3.3 Model-Refinement Comparison

Generated: 2026-07-12T13:18:55.587221+00:00

## Candidate Counts

| Version | Filesystem | v1.3 | v1.3.3 | Retained | Removed | Added | Reduction |
|---|---|---:|---:|---:|---:|---:|---:|
| linux-v6.8 | ext4 | 16 | 16 | 16 | 0 | 0 | 0.0% |
| linux-v6.8 | btrfs | 5 | 5 | 5 | 0 | 0 | 0.0% |
| linux-v6.8 | xfs | 6 | 6 | 6 | 0 | 0 | 0.0% |
| linux-v6.8 | f2fs | 0 | 0 | 0 | 0 | 0 | n/a |
| linux-v7.1 | ext4 | 13 | 13 | 13 | 0 | 0 | 0.0% |
| linux-v7.1 | btrfs | 543 | 4 | 4 | 539 | 0 | 99.3% |
| linux-v7.1 | xfs | 8 | 8 | 8 | 0 | 0 | 0.0% |
| linux-v7.1 | f2fs | 4 | 4 | 4 | 0 | 0 | 0.0% |

## Known btrfs Positive Retention

| Version | Baseline known positives | Retained | Retention |
|---|---:|---:|---:|
| linux-v6.8 | 5 | 5 | 100.0% |
| linux-v7.1 | 4 | 4 | 100.0% |

## Interpretation

The refinement models compiler-managed cleanup, direct acquisition failure, cleanup aliases, error-return consumers, and narrowly reviewed sentinel contracts. Linux v7.1 btrfs falls from 543 candidates to 4 while retaining the four records for the dynamically supported `btrfs_recover_relocation()` defect. Linux v6.8 retains all five btrfs known-positive records, including `__add_reloc_root()`.

Candidate reduction is not itself a precision measurement. Precision and recall must be reported on the independent frozen benchmark.
