# Scope-Cleanup Ablation: experiment-v1.3.1

> MOCC-SE migration note (2026-07-21): this report evaluates SE-EOD compiler-managed resource cleanup. It is retained as a baseline ablation and does not evaluate metadata completion protocols.

Generated: 2026-07-12T12:32:02.646959+00:00

## Candidate Counts

| Version | Before | After | Retained | Removed | Added | Reduction |
|---|---:|---:|---:|---:|---:|---:|
| Linux v6.8 | 5 | 5 | 5 | 0 | 0 | 0.0% |
| Linux v7.1 | 543 | 95 | 95 | 448 | 0 | 82.5% |

## v7.1 Candidate Types

- Before: `{'error_swallowed': 11, 'missing_cleanup': 470, 'partial_cleanup': 62}`
- After: `{'error_swallowed': 11, 'missing_cleanup': 71, 'partial_cleanup': 13}`
- Removed: `{'missing_cleanup': 399, 'partial_cleanup': 49}`

## Auto-Cleanup Diagnostic

- `btrfs_free_path` candidates in auto-free functions before: 472
- `btrfs_free_path` candidates in auto-free functions after: 0
- v6.8 retained functions: `{'btrfs_recover_relocation': 4, '__add_reloc_root': 1}`

## Interpretation

Scope-aware cleanup modeling removes the compiler-managed path-cleanup false-positive family without changing the five v6.8 btrfs candidates. The remaining v7.1 candidates require separate review; they must not be reported as confirmed bugs.
