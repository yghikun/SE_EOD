# OIDS Phase 1 Cross-filesystem Correspondence Matrix

Status: Phase 1 source correspondence complete.
Decision: proceed to Phase 2 with Btrfs as development and ext4 as independent
validation. XFS is applicable pre-freeze screening, not blind held-out data.

## Evidence base

All three dossiers use the checksum-verified official Linux `v6.14` snapshot
at commit `38fec10eb60d687e30c8c6b5420d86e8149f7557`. File hashes and exact source
spans are recorded in:

- `docs/crossfs/orphan-inode/btrfs.md`
- `docs/crossfs/orphan-inode/ext4.md`
- `docs/crossfs/orphan-inode/xfs.md`
- `configs/evaluation/oids-phase1-evidence-v0.1.json`

## Canonical object correspondence

| Canonical role | Btrfs | ext4 | XFS |
|---|---|---|---|
| `operation` | unlink transaction, eviction, mount cleanup | journaled unlink, eviction, mount cleanup | remove transaction, inactive free, log recovery |
| `inode` | root-scoped `struct btrfs_inode` | `struct ext4_inode_info` / VFS inode | AG-scoped `struct xfs_inode` |
| `namespace_entry` | B-tree dir item/index/inode ref | ext4 directory entry | XFS directory name record |
| `orphan_registry` | per-root orphan item | orphan-file slot or legacy list | AGI unlinked bucket and inode forward link |
| `transaction_or_journal` | `btrfs_trans_handle` | JBD2 `handle_t` | `xfs_trans` / log recovery |
| `deletion_authority` | final eviction or mount orphan cleanup | final eviction or mount orphan cleanup | inactive/inodegc or log recovery |

The registry role is deliberately semantic. It does not imply that a B-tree
item, ext4 orphan-file slot and XFS AGI bucket are the same data structure.

## Relation correspondence

| Canonical relation | Btrfs | ext4 | XFS | Decision |
|---|---|---|---|---|
| `inode.namespace_attached` | directory item/ref exists | directory entry exists | directory name record exists | `CLOSED` |
| `inode.last_link_removed` | `drop_nlink()` in unlink | `drop_nlink()` in unlink | `xfs_droplink()` | `CLOSED` |
| `inode.cleanup_required` | zero link plus persistent inode items | zero link plus allocated inode/data | zero link plus allocated inode/resources | `CLOSED` |
| `orphan_registry.records_inode` | orphan key offset is inode number | slot/list stores inode number | AGI bucket chain stores AG inode number | `CLOSED` |
| `deletion_authority.accepted` | orphan insertion succeeds in transaction | orphan-file/list update succeeds in journal handle | AGI insertion succeeds in remove transaction | `CLOSED` |
| `inode.terminally_deleted` | persistent inode items truncated; inode cleared | inode truncated, dtime dirtied and inode freed | inode truncated and freed in on-disk index | `CLOSED_WITH_FS_ADAPTER` |

The canonical relation `orphan_registry.records_inode` must be guarded by
`last_link_removed`. Btrfs and ext4 reuse orphan machinery for linked truncate
or other cleanup records; those records are outside OIDS.

## Lifecycle correspondence

| Stage | Btrfs | ext4 | XFS |
|---|---|---|---|
| Namespace transition | delete dir metadata, then drop link | delete dir entry, then drop link | drop link/register, then remove name |
| Responsibility registration | orphan item in same transaction | orphan-file/list record in same journal handle | AGI unlinked insertion in same transaction |
| Live-open interval | persistent orphan item remains | persistent orphan record remains | AGI unlinked record remains |
| Normal terminal authority | `btrfs_evict_inode()` | `ext4_evict_inode()` | `xfs_inactive()` / inodegc |
| Recovery authority | `btrfs_orphan_cleanup()` | `ext4_orphan_cleanup()` | `xlog_recover_process_iunlinks()` |
| Registry settlement | after persistent item truncation | before inode free in statement order, same journal transaction | atomic with inode free |

Different source order inside one transaction does not break lifecycle
correspondence. The common semantic point is the transaction outcome: namespace
detachment cannot commit without accepted cleanup responsibility, and registry
removal cannot commit without terminal deletion settlement.

## Authority correspondence

| Question | Btrfs | ext4 | XFS | Decision |
|---|---|---|---|---|
| Who owns cleanup while inode is open? | persistent orphan item plus future final `iput` | persistent orphan record plus future final `iput` | AGI unlinked record plus future inactive processing | `CLOSED` |
| Who executes normal deletion? | eviction | eviction | inactive/inodegc | `CLOSED` |
| Who executes crash recovery? | mount orphan cleanup | mount orphan cleanup | log recovery iunlink processor | `CLOSED` |
| Does registration failure count as delegation? | no; transaction abort/error | no; journal operation error | no; transaction error | `CLOSED` |

`deletion_authority.accepted` means persistent registry acceptance in a
transaction that can settle. It is not inferred from an in-memory list link or
from merely entering an unlink helper.

## Deadline correspondence

| Deadline | Btrfs | ext4 | XFS | Cross-FS rule |
|---|---|---|---|---|
| `BEFORE_COMMIT` | orphan insert before unlink transaction end | orphan add before journal stop | iunlink insertion and name removal before transaction commit | A zero-link namespace transition cannot commit without registry acceptance. |
| `BEFORE_RECOVERY_EXPOSURE` | mount orphan cleanup | cleanup before recovery-complete marker | iunlink processing during recovery finish | Recovery must settle registered deletion before normal exposure. |
| `BEFORE_ORPHAN_REGISTRY_REMOVAL` | deletion transaction settles before orphan delete | orphan delete then inode free in one handle | inode free and list removal atomic | Registry removal cannot commit unless terminal deletion is already durably settled or atomically co-settled in the same transaction. |

The last rule is intentionally settlement-scoped. A literal source-order rule
would incorrectly reject ext4, while mandatory same-transaction settlement
would incorrectly reject Btrfs, whose inode-item deletion transaction ends
before the orphan-removal transaction begins. The narrow common invariant is
therefore prior durable deletion or atomic co-settlement, never arbitrary later
cleanup.

## Identity and epoch correspondence

| Dimension | Btrfs | ext4 | XFS | Phase 2 requirement |
|---|---|---|---|---|
| Filesystem container | filesystem + root | superblock | mount + allocation group | required |
| Persistent registry identity | root + inode number | inode number/slot or chain | AG inode number/bucket | source-supported |
| Allocation generation | not stored in orphan key | not stored in orphan record | not stored in AGI chain identity | adapter must add allocation/mount epoch |
| Operation epoch | unlink transaction then cleanup transaction | unlink handle then cleanup handle | remove transaction then ifree transaction | must remain two-stage, never merged blindly |

Identity correspondence is sufficient for Phase 2 design but not yet for proof
closure. Each adapter must prevent inode-number reuse from merging distinct
protocol instances.

## Applicability and evidence roles

| Filesystem | Applicability | Phase 2 role | Used to claim common freeze now? |
|---|---|---|---|
| Btrfs | `APPLICABLE` | `DEVELOPMENT` | no; DSL/binding/replay do not exist yet |
| ext4 | `APPLICABLE` | `VALIDATION` | no; DSL/binding/replay do not exist yet |
| XFS | `APPLICABLE` | `PRE_FREEZE_SCREENING` | no; excluded from the two-FS basis |

No filesystem is `NON_APPLICABLE` or `UNRESOLVED` at the Phase 1 semantic
correspondence level. This does not mean the future adapters or replay closure
will automatically succeed.

## Phase 1 gate result

```text
source snapshot integrity = CLOSED
object correspondence = CLOSED
relation correspondence = CLOSED
lifecycle correspondence = CLOSED_WITH_TRANSACTIONAL_EQUIVALENCE
authority correspondence = CLOSED
deadline correspondence = CLOSED_WITH_TRANSACTIONAL_EQUIVALENCE
Btrfs/ext4 Phase 2 basis = ELIGIBLE
canonical DSL = NOT_STARTED
per-FS binding = NOT_STARTED
replay/proof closure = NOT_STARTED
COMMON claim = NOT_ALLOWED
```

Phase 1 therefore authorizes Phase 2 implementation, not a common freeze.

## XFS held-out correction

The earlier plan called XFS a future held-out filesystem while also requiring a
full XFS dossier before protocol design. Those two claims are incompatible.
Because the XFS lifecycle has now been inspected, a later unchanged-protocol
XFS run is valuable post-freeze validation but not blind held-out evidence.

The project must use one of these labels:

- `POST_FREEZE_XFS_VALIDATED` if the frozen Btrfs/ext4 protocol works on XFS
  without semantic modifications;
- `NON_APPLICABLE` if an adapter-level object, authority or deadline gap is
  established;
- `COMMON_HELDOUT_VALIDATED` only for a genuinely unrevealed filesystem, such
  as a separately reserved F2FS evaluation if it passes eligibility screening.

## Phase 2 constraints

The canonical DSL and adapters must preserve all of the following:

1. Registry acceptance is transaction-scoped, not inferred from call entry.
2. Only zero-link deletion records activate OIDS.
3. Registry removal requires terminal deletion to be already durably settled
   or atomically co-settled with removal; strict C-call order is not canonical.
4. Normal and recovery authority are distinct execution paths for the same
   obligation.
5. Unlink and final cleanup are separate operation epochs tied by persistent
   inode identity.
6. A leftover registry record is a retry state, not automatically a violation.
7. Persistent registry absence alone cannot prove deletion without transaction
   and terminal-state evidence.
