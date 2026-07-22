# ext4 Fast-Commit Replay Helper Fault Validation

This is a source-level control-flow validation, not a full kernel
fault-injection run. The local workspace contains an fs/ source slice,
not a buildable kernel tree.

## Summary

```text
modeled_injection_scenarios              10
original_helper_swallowed_errors         8
original_caller_swallowed_errors         10
original_metadata_write_after_failure    7
fixed_caller_swallowed_errors            0
```

A scenario is counted as swallowed when an injected helper failure
returns 0 from the helper or from the fast-commit replay caller.

## Results

| function | injection site | original helper | original writes metadata | original caller | fixed caller |
|---|---|---:|---|---:|---:|
| `ext4_ext_replay_set_iblocks` | `initial_ext4_find_extent` | -5 | no | 0 | -5 |
| `ext4_ext_replay_set_iblocks` | `data_ext4_map_blocks` | 0 | yes | 0 | -5 |
| `ext4_ext_replay_set_iblocks` | `first_skip_hole` | 0 | yes | 0 | -5 |
| `ext4_ext_replay_set_iblocks` | `first_ext4_find_extent` | 0 | yes | 0 | -5 |
| `ext4_ext_replay_set_iblocks` | `loop_ext4_find_extent` | 0 | yes | 0 | -5 |
| `ext4_ext_replay_set_iblocks` | `loop_skip_hole` | 0 | yes | 0 | -5 |
| `ext4_ext_replay_set_iblocks` | `second_ext4_find_extent` | 0 | yes | 0 | -5 |
| `ext4_ext_clear_bb` | `initial_ext4_find_extent` | -5 | no | 0 | -5 |
| `ext4_ext_clear_bb` | `loop_ext4_map_blocks` | 0 | yes | 0 | -5 |
| `ext4_ext_clear_bb` | `inner_ext4_find_extent` | 0 | no | 0 | -5 |

## Interpretation

- `ext4_ext_replay_set_iblocks()` has six modeled post-initial
  failure sites where the original helper returns 0 and the caller
  also returns 0. These paths still execute the final `i_blocks`
  update in the model.
- `ext4_ext_clear_bb()` has two modeled post-initial failure sites
  where the original helper returns 0 and the caller also returns 0.
- A minimal fixed semantics that preserves the first negative error
  and makes `ext4_fc_replay_inode()` check helper returns changes all
  injected-failure caller outcomes from 0 to `-EIO`.

Initial conclusion: the hypothesis is reproducible at the source
control-flow level. A full confirmed-bug claim still needs a kernel
fault-injection run or an accepted patch/review showing these helper
failures must abort fast-commit replay.
