# P1.5 Domain Traceability Matrix v0.2

`READY` 表示规则同时有设计/对象语义、正常或安全路径、confirmed counterexample 和 repaired/fixed 证据。这里的 fixed fixture 是补丁语义的可执行归一化，不等同于本地 fixed-source differential。

| Protocol | Rule | 设计/规范依据 | 正常或安全路径 | Bug witness | Fixed/repaired path | 状态 |
|---|---|---|---|---|---|---|
| RAS | RAS-I1：settlement 时 attachment state 为 detached | root attachment 持有引用且 recovery owner 退出后不能留下无主关系 | 正常 recovery 完成；`BTRFS_FS_ERROR` guarded teardown 逐 root drop | #7 no-abort QEMU path；v6.8 source repair slice 无 clear/put | accepted fix direction；`ras-fixed` | READY，单 family |
| RAS | RAS-O1：失败后的 `fs_root.reloc_root` 恢复 prestate 或完成合法委托 | attachment delta 与 root-reference ownership 同生共灭 | abort safe sibling 证明 teardown owner 只能在有 guard 的路径承担责任 | #7 attachment 穿过 `out_unset` | `ras-fixed`、`ras-safe-delegated` | READY，source fixed snapshot 缺失 |
| RAS | Deadline：return/owner termination 触发 settlement | recovery owner 消失后 obligation 无法继续由原 owner 履行 | owner termination 前 teardown 完成 | `ras-owner-termination-violation` | `ras-fixed` | READY |
| DTR | DTR-I1/I2：active pointer 在使用/exposure 时必须指向 live valid target | active-device consumer 和 device-name path 要求目标仍为拓扑有效成员 | 正常 sprout 保持 live target；修复系列恢复 pointer | #17 stale/freed pointer；`dtr-exposure` | patch 2/3；`dtr-fixed` | READY，同一 sprout family |
| DTR | DTR-I3：device release 前已脱离 topology 与 post-commit membership | released device 不能继续挂在 device list 或 transaction update list 中 | cleanup 先逐 list deletion 再 release | #16 WARN on non-empty post-commit list；`dtr-release-violation` | patch 1/3；`dtr-release-fixed`；device membership restore witness | READY，同一 sprout family |
| DTR | DTR-O1：failure 后逐 relation restore-or-complete-authority | sprout setup 同时改变 membership、active pointer 和 fsid；abort 不拥有任意内存关系 | full rollback 和逐 relation authority completion | #16/#17/#18；v6.14 source 只找到 membership restore | 3-patch fixed run；`dtr-fixed`、`dtr-delegated-safe` | READY，source fixed snapshot 缺失 |
| DTR | Deadline：release/exposure 优先，未结关系在 settlement 到期 | 危险消费可早于函数返回；其余 topology identity 在失败返回前应复原 | repaired cleanup 按 relation 顺序完成 | #16 release、#17 exposure、#18 partial container | fixed fixture 与 patch-series run | READY |

## Source witness 边界

- RAS：本地 Linux v6.8 提取到 attachment、checked failure 和无 restore 的 repair slice，形成精确 violation witness。
- DTR：本地 Linux v6.14 operation root 提取到 fsid、active-device、device-membership 三类 mutation；cleanup 只找到 device-membership restorer。`post_commit_list` mutation 位于被调 helper，当前 frontend 不宣称其 interprocedural source witness。
- 两个协议目前都缺少同一 frontend 下的本地 fixed-source 快照。补丁接受记录、动态 fixed run 和 fixture 支持 repaired semantics，但 E1 不把它们表述为 source-level Bug/fixed differential。
