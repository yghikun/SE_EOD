# Benchmark Taxonomy

> MOCC-SE migration note (2026-07-21): this taxonomy describes the SE-EOD resource/error-path pilot. MOCC-SE adds protocol labels, effect scopes, legal completion modes, and the three metadata violation classes; those labels require a separately frozen dataset.

> Based on the first source-review pass; use for development prioritization, not final paper claims.

- Samples: 30
- True bugs: 11
- False positives: 19

## False-Positive Causes

| Priority | Category | Count | Share |
|---:|---|---:|---:|
| 1 | `intentional_api_sentinel` | 11 | 57.9% |
| 2 | `acquire_failure_no_resource` | 5 | 26.3% |
| 3 | `cleanup_already_present` | 2 | 10.5% |
| 4 | `conditional_container_cleanup` | 1 | 5.3% |

## Recommended Actions

### intentional_api_sentinel

- model inline-write one as handled success (2)
- model lookup ENOENT as NULL not-found result (2)
- model ext4_map_blocks zero as unmapped success (1)
- model fiemap_fill_next_extent one as buffer-full completion (1)
- distinguish local control flags from errno values (1)
- model query-helper zero fallback contract (1)
- model positive map result as success (1)
- model seq_file show return contract (1)
- model pointer-return NULL failure contract (1)

### acquire_failure_no_resource

- model ERR_PTR acquisition failure (2)
- model NULL acquisition failure (1)
- model ERR_PTR and NULL acquisition failure (1)
- model out-parameter acquisition failure (1)

### cleanup_already_present

- improve path-local release matching (2)

### conditional_container_cleanup

- model conditionally allocated container ownership (1)

## True-Bug Families

| Category | Count |
|---|---:|
| `confirmed_error_swallowed` | 9 |
| `confirmed_missing_cleanup` | 2 |
