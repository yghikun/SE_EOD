# RelocationRootAttachmentSettlement v0.3 Draft

状态：`DRAFT`; 未冻结，不能作为 v0.2 held-out 或泛化结论。

## First-principles scope

该协议约束的不是“失败后必须 rollback”这一通用句子，而是一个具体关系：

```text
fs_root.reloc_root + reloc_root reference ownership
```

与 RAS v0.2 的区别是 operation root：当前 runtime relocation merge
只观察和结算一个在更早过程建立的 attachment，不声称当前函数建立它。

```text
prior relocation epoch establishes attachment
-> merge operation imports the preexisting relation
-> merge failure transfers settlement responsibility
-> relation must return to entry prestate before return/termination
```

## Candidate rules

- `RRM-I1`: at relocation settlement, `fs_root.reloc_root` is `DETACHED`.
- `RRM-O1`: a checked merge failure activates one obligation for the imported
  relation; only `relocation_teardown` may complete it.
- `RelocationDetach` discharges the obligation only when it restores the
  imported relation to its recorded prestate.
- `RelocationReturn` and owner termination are independent settlement
  boundaries; an abort or local list cleanup does not discharge `RRM-O1`.

## Evidence boundary

The confirmed `c0041b502e57` revision supplies an exact violation witness:
the failure branch lacks `clear_reloc_root` and the corresponding reference
drop. Commit `83201804efa4` supplies the accepted repair sequence. The fixed
revision remains `INCOMPLETE` under the draft because the frontend closes only
the selected branch, not every relevant call-graph path.

The selected normal runtime chain is now source-closed from
`btrfs_init_reloc_root()` through `merge_reloc_roots()` and
`clean_dirty_subvols()`; see `rras-traceability-v0.3-draft.md`. General alias
and all-path closure remain incomplete.

Independence screening found no second operation family. Related fixes in
`merge_reloc_roots()` count as the same family, so the executable readiness
gate keeps `freeze_eligible=false`. See
`rras-independence-screening-v0.3-draft.md` and
`configs/evaluation/rras-v0.3-readiness.json`.
