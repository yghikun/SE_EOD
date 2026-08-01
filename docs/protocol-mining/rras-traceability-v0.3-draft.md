# RRAS Traceability v0.3 Draft

状态：`DRAFT_EVIDENCE_COMPLETE_FOR_SELECTED_PATHS`; 不代表全路径闭包或协议冻结。

| Rule or boundary | Design/source evidence | Bug path | Fixed/normal path | Current closure |
|---|---|---|---|---|
| Attachment origin | `btrfs_init_reloc_root()` states that the relocation root has one reference for `root->reloc_root`, then assigns it with `btrfs_grab_root()` | The later merge path inherits this relation | Same origin in fixed revision | Exact selected source witness |
| Imported identity | `merge_reloc_roots()` checks `root->reloc_root` against the relocation root selected from `rc->reloc_roots` | The confirmed error branch retains the imported relation while freeing its target | Fixed branch clears the same typed access path | Exact selected source witness; general alias closure open |
| Normal handoff | `merge_reloc_root()` calls `insert_dirty_subvol()`, which adds the root to `rc->dirty_subvol_roots` after the update succeeds | Failure before list insertion bypasses normal cleanup ownership | Success transfers cleanup responsibility to the dirty-root list | Exact selected call/list witness |
| Normal settlement | `relocate_block_group()` invokes `merge_reloc_roots()` before `clean_dirty_subvols()` | Bug root is absent from the dirty list and escapes cleanup | `clean_dirty_subvols()` clears the relation and consumes the owned relocation-root reference | Exact selected caller-order witness |
| `RRM-I1` | A relation whose target can be freed cannot remain observable after settlement | Bug leaves stale attachment; later unmount dereferences it | Fixed error branch and normal cleanup both detach | Bug/fixed/normal evidence present |
| `RRM-O1` | Failure before normal handoff leaves settlement responsibility with merge owner | Missing clear and reference settlement | Fixed branch performs direct settlement | Bug/fixed evidence present |

## Evidence chain

```text
btrfs_init_reloc_root
  root->reloc_root = btrfs_grab_root(reloc_root)
-> merge_reloc_roots
  typed identity check imports the relation
-> merge_reloc_root -> insert_dirty_subvol
  successful merge hands root to dirty_subvol_roots
-> relocate_block_group
  merge_reloc_roots precedes clean_dirty_subvols
-> clean_dirty_subvols
  clear_reloc_root + btrfs_drop_snapshot/btrfs_put_root
```

This closes one selected normal runtime chain. It does not prove every caller,
alias, retry, concurrent mutation or teardown path. Those dimensions remain
`INCOMPLETE` for universal conformance.
