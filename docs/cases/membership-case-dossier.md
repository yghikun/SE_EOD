# MembershipConsistency First Case Dossier

Updated: 2026-07-31

## 1. Status

```text
Real Btrfs case qualification: NO CASE ACCEPTED YET
Synthetic semantic fallback: READY
Paper-validity evidence: NO
Analyzer implementation gate: NOT SATISFIED
```

This dossier records the first qualification pass for a real Btrfs
`MembershipConsistency` failure path. The pass did not identify a case that
simultaneously has confirmed real-bug evidence and violates the first-version
membership/counter formula. The dossier therefore freezes a synthetic semantic
fallback but does not count that fallback as empirical evidence.

## 2. Audited source snapshots

| Version | Commit | Source | Archive SHA-256 |
|---|---|---|---|
| v6.8 | `e8f897f4afef0031fe618a8e94127a0934896aba` | official tag tarball | `87eebb4c5d35b5c71e2b1dbdd106be6e6ccc0ee3c3ba0602a3fc4d9d169a6b93` |
| v6.14 | `38fec10eb60d687e30c8c6b5420d86e8149f7557` | kernel.org `linux-6.14.tar.xz` | `a294b683e7b161bb0517bb32ec7ed1d2ea7603dfbabad135170ed12d00c47670` |
| v7.1 | `8cd9520d35a6c38db6567e97dd93b1f11f185dc6` | kernel.org `linux-7.1.tar.xz` | `691f44797fbe790dc8a321604c927087526ad27b6d649925d60f8eed0a2564a0` |

The audit used the re-downloaded `fs/btrfs` trees, the local confirmed-bug and
pending-review records, version diffs, and upstream commit metadata. It is a
targeted qualification pass, not a claim that every historical Btrfs bug has
been exhaustively enumerated.

## 3. Acceptance predicate

A real case is accepted for the first `MembershipConsistency` vertical only if
all of the following hold:

1. A real bug, accepted/submitted fix, maintainer confirmation, or reproducible
   failure establishes the path.
2. The path binds a concrete `container`, `member`, and membership `counter`.
3. Before `ReleaseIsolation`, `LiveExposure`, or `OperationReturn`, the exact
   path establishes:

   ```text
   DeltaCount(container)
   != sum(DeltaMembership(container, member))
   ```

4. The mismatch is not merely a reference leak, active-pointer violation,
   duplicate use of one list node, or an outcome/rollback-policy violation.
5. A fixed version or a safe sibling path provides a negative control.

The fourth condition prevents expanding `MembershipConsistency` until it
silently absorbs the later `ReferenceDelta`, `ActiveMemberSafety`, or
`OutcomeContract` protocols.

## 4. Candidate qualification matrix

| Candidate | Evidence strength | Exact relation at deadline | Decision |
|---|---|---|---|
| `btrfs_init_new_device()` ordinary device add cleanup | exact v6.14 source | `dev_list +1`, `num_devices +1`; error cleanup performs both `-1` | Reject as violation; this is the conformant rollback control |
| confirmed sprout bug #16, `post_commit_list` remains linked | fault injection plus submitted patch | transaction-list membership remains, but no corresponding membership counter is identified | Route to responsibility/list-membership work; not the first formula |
| confirmed sprout bug #17, stale `latest_dev`/`s_bdev` | fault injection plus submitted patch | active pointer can name a removed/freed device | Route to `ActiveMemberSafety` |
| confirmed sprout bug #18, sprout setup not restored | fault injection plus submitted patch | seed members are spliced out and `num_devices` is reset consistently; later new-device cleanup is also paired | The pre-operation container state is not restored, but the first delta-equality formula still holds; needs outcome/rollback obligation |
| pending `btrfs_dev_replace_start()` target cleanup | source-confirmed candidate; no accepted fix or completed reproduction in the local record | target list membership, `num_devices`, and `open_devices` all remain `+1` | The relation is internally consistent; candidate is an incomplete operation/outcome case, not a count mismatch |
| upstream `2d8e5168d48a`, pending block-group race | reproduced upstream fix | list state races with block-group lifetime/refcount | Requires concurrency and `ReferenceDelta`; outside first-version scope |
| upstream `3a1f4264daed`, `dirty_list` corruption | reproduced upstream fix | the same list node is added to two lists | No membership counter role; not the target formula |
| upstream `f260c6aff0b8`, qgroup-list leak | upstream fix | preallocated object is leaked before relation insertion | Resource ownership leak, not membership/counter divergence |

## 5. Key source evidence

### 5.1 Conformant device rollback

In v6.14 `fs/btrfs/volumes.c`, `btrfs_init_new_device()` performs:

```text
line 2883  list_add_rcu(&device->dev_list, &fs_devices->devices)
line 2885  fs_devices->num_devices++
```

The `error_sysfs` path performs:

```text
line 2991  list_del_rcu(&device->dev_list)
line 2993  fs_info->fs_devices->num_devices--
```

For the `device` member and `num_devices` counter, this is the required safe
pair. The path must be retained as a negative control.

### 5.2 Sprout state is not a first-formula mismatch

`btrfs_setup_sprout()` moves all seed devices to `seed_devices->devices` and
then sets the old container's `num_devices` to zero:

```text
line 2681  list_splice_init_rcu(...)
line 2687  fs_devices->num_devices = 0
```

The confirmed bug is that a later failure does not restore the complete
pre-operation sprout state. That is a real protocol problem, but a detector
based only on membership/count equality would see a matched membership and
counter change. Treating it as a count mismatch would be a false semantic
classification.

### 5.3 Device-replace P3 is internally count-consistent

In v6.14 `fs/btrfs/dev-replace.c`, target initialization adds the target and
increments both counters at lines 327-329. If `mark_block_group_to_copy()`
fails, `btrfs_dev_replace_start()` returns directly at lines 636-638 and skips
the cleanup at line 720.

This is a strong incomplete-operation candidate, but at that return:

```text
DeltaMembership(target) = +1
DeltaCount(num_devices) = +1
DeltaCount(open_devices) = +1
```

The target should not remain after a failed start, but the first
membership/count equality is not what proves that requirement. It needs an
operation outcome or rollback obligation, and the local record still marks the
case pending review.

## 6. Qualification result

No audited real case currently proves a one-sided membership/counter mutation
before the first-version deadline. Therefore:

```text
Do not report a real MembershipConsistency violation.
Do not use the sprout series or device-replace P3 as a substitute.
Do not count this dossier as paper-validity evidence.
```

The real-case search remains open. A future candidate must show, on one exact
path, a member insertion/removal without the corresponding membership counter
change, or the converse, with a real fix or reproduction.

## 7. Synthetic fallback

Fixture: `docs/cases/fixtures/membership_minimal.c`

### Roles and identity

```text
container = struct membership_container *container
member    = const struct membership_member *member
counter   = container->count

SemanticInstanceKey = <
    MembershipConsistency,
    identity(container),
    identity(member),
    operation invocation epoch
>
```

### Typed event binding

| Source operation | Typed event |
|---|---|
| `acquire_isolation()` | `AcquireIsolation(container)` |
| `add_member()` | `AddMember(container, member, +1)` |
| `remove_member()` | `RemoveMember(container, member, -1)` |
| `adjust_count()` | `AdjustCount(container, delta)` |
| `release_isolation()` | `ReleaseIsolation(container)` |
| function return | `OperationReturn(outcome)` |
| indirect `repair(container, member)` | `UnknownRepair(instance)` |

### Preconditions

```text
container->member == NULL
container->count == 0
container->isolated == false
member != NULL
```

### Four manual executions

| Path | Event sequence | State at deadline | Expected result |
|---|---|---|---|
| normal | Acquire, AddMember, AdjustCount(+1), Release, ReturnSuccess | membership `+1`, count `+1` | `CONFORMANT_UNDER_LOADED_SPEC` |
| rollback | Acquire, AddMember, RemoveMember, Release, ReturnError | membership `0`, count `0` | `CONFORMANT_UNDER_LOADED_SPEC` |
| violation | Acquire, AddMember, Release, ReturnError | membership `+1`, count `0` | `VIOLATION_UNDER_LOADED_SPEC` |
| unknown | Acquire, AddMember, UnknownRepair, Release, ReturnError | repair may remove member or adjust count | `INCOMPLETE_UNDER_LOADED_SPEC` |

The first deadline is `ReleaseIsolation`; `OperationReturn` is a terminal
settlement immediately afterward. `UnknownRepair` cannot discharge the
obligation without a summary that proves its effect and identity.

## 8. Minimal proof obligations

For the synthetic violation path:

```text
required_formula:
    DeltaCount(container)
    == sum(DeltaMembership(container, member))

activation_horizon:
    after AddMember

deadline_policy:
    MUST_DISCHARGE

completion_deadline:
    ReleaseIsolation | OperationReturn
```

`ViolationProofClosure` requires exact identity for `container` and `member`,
an exact `AddMember`, an exact zero `CounterDelta`, and a closed repair slice
up to `ReleaseIsolation`. The unknown path deliberately fails that closure and
must remain `INCOMPLETE`.

## 9. Next evidence action

Continue the real-case search without changing the frozen formula. Prefer
historical fixes whose patch adds exactly one missing list operation or one
missing membership-counter adjustment on an error path. If a candidate instead
requires rollback-to-prestate, active-pointer validity, reference lifetime, or
full concurrency, route it to the corresponding later protocol rather than
expanding `MembershipConsistency`.
