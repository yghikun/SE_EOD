# OIDS Phase 12 COMMON Claim Disposition and Counterexample Audit

## Purpose

Phase 12 does not select another filesystem and does not revise the frozen OIDS v0.1 candidate. It disposes the claims supported by Phases 9–11 and independently audits the ReiserFS held-out counterexamples. The central distinction is between protocol applicability and implementation conformance.

```text
COMMON semantic applicability != universal filesystem conformance
qualified normal-path evidence != failure-path conformance
freeze formation evidence != post-freeze held-out evidence
```

## Cross-filesystem disposition

| Filesystem | Evaluation role | Applicability | Normal-profile result | Failure-path/held-out disposition |
|---|---|---|---|---|
| Btrfs | freeze formation / development | applicable to the frozen successful profile | closed | not post-COMMON held-out tested |
| ext4 | freeze formation / validation | applicable under `ERRORS_RO_OR_FAILSTOP` | closed | `ERRORS_CONT` remains explicitly excluded with negative witnesses |
| UBIFS | freeze formation / validation | applicable to live and successful-RW profiles | closed | read-only recovery remains deferred outside the qualified profile |
| OCFS2 | post-COMMON blind screening | non-applicable / deadline not aligned | live path closed only | orphan recovery is not joined before mount exposure |
| ReiserFS | post-COMMON blind held-out | applicable | successful live and RW recovery closed | non-conformant held-out via OIDS-O1 and OIDS-O3 |

The Phase 9 COMMON narrow freeze remains valid as a semantic-scope artifact. It establishes a reusable protocol footprint and qualified applicability predicates across independent operation families. It does not establish that every applicable implementation conforms on every failure path.

## OIDS-O1 minimal audit

The independent source slice is:

```text
void add_save_link(...)                       super.c:429
reiserfs_insert_item(...)                     super.c:494
if (retval) without propagation               super.c:496
reiserfs_unlink() calls add_save_link          namei.c:1076
reiserfs_unlink() reaches journal_end          namei.c:1078
```

The rule-specific minimal replay is:

```text
InitializeOrphanDeletion
LastLinkRemoved
RegistrationTransactionCommit
=> VIOLATION_UNDER_LOADED_SPEC / OIDS-O1
```

Deleting any one of these three events removes OIDS-O1. The source control-flow path and replay minimality are therefore independently closed.

## OIDS-O3 minimal audit

The independent source slice is:

```text
finish_unfinished() returns retval            super.c:420
reiserfs_fill_super() ignores that result     super.c:2185
successful mount return remains reachable     super.c:2214
```

The rule-specific minimal replay is:

```text
InitializeOrphanDeletion
LastLinkRemoved
OrphanRegistryAccepted
RecoveryAuthorityAccepted
RecoveryExposure
=> VIOLATION_UNDER_LOADED_SPEC / OIDS-O3
```

Deleting any one of these five events removes OIDS-O3. This replay isolates recovery exposure without introducing OIDS-O1.

## Narrowing audit

The Phase 9 frozen predicates use only filesystem identity, zero-link deletion, error policy, live cleanup profile, and successful-RW recovery exposure profile. None depends on whether an internal operation happened to succeed.

The following post-reveal predicates are rejected:

```text
add_save_link_succeeded
remove_save_link_succeeded
finish_unfinished_succeeded
```

Adding any of them would condition applicability on the outcome being evaluated and would erase the held-out counterexample post hoc.

## Final claim disposition

```text
common_semantic_applicability = SUPPORTED_UNDER_FROZEN_NARROW_SCOPE
common_normal_profile_conformance = SUPPORTED_FOR_EVALUATED_QUALIFIED_PROFILES
common_failure_path_conformance = REFUTED_BY_POST_COMMON_HELDOUT_COUNTEREXAMPLE
common_heldout_validated = false
universal_filesystem_conformance = NOT_CLAIMED
protocol_v0_1_disposition = FROZEN_WITH_RETAINED_COUNTEREXAMPLE
```

Any attempt to repair the protocol, alter its applicability boundary, or evaluate a revised claim requires a new protocol version and a new development/validation/held-out split. Phase 11 provenance cannot be reused after such a revision.

