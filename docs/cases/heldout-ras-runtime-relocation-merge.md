# Held-out RAS: runtime relocation merge failure

Status: `CONFIRMED_V0.3_PROTOCOL_CANDIDATE`; not eligible for frozen RAS v0.2 held-out evaluation.

## Provenance

- Fixed commit: `83201804efa4a5168be754e1dfc9b2faee760cac`, `btrfs: fix use-after-free on reloc root after error in insert_dirty_subvol()`.
- Bug revision: fixed commit parent `c0041b502e579a5c52e5cae918b90678f03faddd`.
- Bug blob: `fs/btrfs/relocation.c` Git object `0d63d117db596a0bc5d222e64ffb108617e413be`.
- Fixed blob: `fs/btrfs/relocation.c` Git object `a8d0acb0ad35fb40f0ae30d90d7ae20b184979b1`.
- Confirmation: syzbot/KASAN use-after-free report in the commit message; Reviewed-by Qu Wenruo; merged by the Btrfs maintainer path.

The revisions were revealed only after Domain Catalog v0.2 and its AcceptP were frozen. The case did not participate in protocol construction.

## Independence

The development RAS family is mount-time `btrfs_recover_relocation()`. This
candidate is runtime block-group relocation, with settlement in
`merge_reloc_roots()` after `insert_dirty_subvol()`/`merge_reloc_root()` failure.
It is a different operation root and failure trigger while managing the same
`fs_root <-> reloc_root` attachment and reference ownership. The shared
relation is not sufficient for v0.2 eligibility because the attachment is
preexisting at the selected operation root.

## Causal chain

```text
relocation epoch establishes root->reloc_root
-> merge_reloc_root() fails
-> the reloc root is added to the local free list
-> free_reloc_roots() frees that reloc root
-> Bug path leaves root->reloc_root attached
-> later unmount dereferences the stale attachment
-> KASAN use-after-free / possible double free
```

The fix clears `root->reloc_root`, drops the root-owned reference, and only then permits the local cleanup list to own/free the relocation root. This is a domain relation settlement, not merely a missing free.

## Unified semantic record

- OperationRoot: runtime relocation merge epoch.
- Anchors: relocation operation plus `fs_root` identity.
- Entry relation: attachment was established earlier in the same relocation epoch.
- Failure event: checked `merge_reloc_root()` error.
- Bug repair slice: list transfer and exit without clearing the attachment.
- Fixed repair slice: `clear_reloc_root(root)` plus `btrfs_put_root(reloc_root)`.
- Deadline: operation settlement; later unmount is an exposure witness, not the repair deadline.
- Candidate protocol direction: `RelocationRootAttachmentSettlement` v0.3;
  no v0.2 protocol conclusion is emitted.

The revision frontend preserves the selected failure branch and repair evidence
for future v0.3 mining. It is not loaded into the frozen v0.2 protocol, so no
v0.2 violation or conformance result is claimed.
