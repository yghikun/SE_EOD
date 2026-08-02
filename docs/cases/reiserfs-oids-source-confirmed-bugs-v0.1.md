# ReiserFS OIDS Source-confirmed Correctness Bugs

## Evidence boundary

These cases are confirmed from Linux v6.8 source control flow and independently minimal OIDS replay. Calling them correctness bugs is justified because the implementation can reach an externally successful protocol checkpoint after suppressing an error required for persistent cleanup correctness.

The current evidence does not establish an upstream report, runtime reproduction, security exploitability, or CVE. Those claims remain explicitly false until separate evidence exists.

## Case 1: save-link ENOSPC is not propagated

```text
case_id = REISERFS_SAVE_LINK_ENOSPC_UNPROPAGATED
classification = SOURCE_CONFIRMED_CORRECTNESS_BUG
protocol rule = OIDS-O1
```

`add_save_link()` is declared `void`. Its `reiserfs_insert_item()` call can fail, including with `-ENOSPC`, but the error branch only logs selected errors. `reiserfs_unlink()` cannot inspect the result and still reaches `journal_end()` after the final-link and namespace transitions.

```text
add_save_link                         super.c:429
reiserfs_insert_item                  super.c:494
unpropagated retval branch            super.c:496
caller add_save_link                  namei.c:1076
caller journal_end                    namei.c:1078
```

The correctness impact mechanism is a crash window in which the namespace removal is committed but no persistent save link makes the zero-link inode discoverable by mount recovery. The source evidence proves the missing responsibility record and reachable commit; runtime fault injection remains future work.

Required repair contract: propagate failure and prevent commit, prove rollback/abort, or enter failstop before unsafe success exposure.

## Case 2: recovery cleanup error is ignored

```text
case_id = REISERFS_RECOVERY_ERROR_EXPOSURE_REACHABLE
classification = SOURCE_CONFIRMED_CORRECTNESS_BUG
protocol rule = OIDS-O3
```

`finish_unfinished()` returns its cleanup status. `reiserfs_fill_super()` calls it as a bare statement, discards the result, and can continue to successful mount return.

```text
finish_unfinished return retval       super.c:420
ignored finish_unfinished call        super.c:2185
successful fill_super return          super.c:2214
```

The correctness impact mechanism is normal mount exposure while required save-link cleanup remains incomplete. The source evidence proves error suppression and reachable exposure; it does not establish a specific corruption image or security consequence.

Required repair contract: propagate mount failure, enter explicit failstop/read-only containment with retained cleanup responsibility, or prove deadline-safe delegation before exposure.

## Versioning role

Both cases retain their v0.1 held-out provenance in the historical record. Because they are now revealed, they become development counterexamples for the planned OIDS v0.2 diagnostic extension and are permanently ineligible as v0.2 held-out evidence.
