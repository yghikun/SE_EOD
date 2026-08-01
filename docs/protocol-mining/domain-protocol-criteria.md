# P1.0 领域协议资格标准

版本：`p1.0-v0.2`；日期：2026-07-31。

## 问题本质

元数据协议不是“失败要返回错误”或“失败要回滚”的同义词。它描述一个具体元数据对象集合在一个 operation epoch 内允许怎样改变关系、由谁承担未完成责任，以及最晚在哪个可观察边界完成结算。

因此，`OutcomeAgreement`、`RestoreOrDelegate` 和 `ProofClosure` 是可复用语义内核，不是领域协议。一个候选只有同时回答以下问题才有资格进入 Domain Catalog：

1. 具体管理哪些元数据对象和跨对象关系？
2. operation root、anchor role 和 epoch 如何确定实例身份？
3. 合法 prestate、intermediate、failure-pending 和 settled state 分别是什么？
4. 哪些 typed event 可以改变关系或转移责任？
5. 每个 relation obligation 的 owner/authority 是谁？
6. exposure、release、operation return、owner termination 中哪个是最早有效 deadline？
7. 正常、Bug、fixed、安全错误、合法委托和 unknown 路径如何区分？

## 纳入标准

| 维度 | 必须满足 | 拒绝条件 |
|---|---|---|
| 领域对象 | 名称和 footprint 指向具体元数据对象/关系 | 只描述 error、rollback、cleanup 或 return |
| 状态机 | 有合法阶段、typed event、relation delta 和 terminal settlement | 仅靠 API pairing 或字段是否为 NULL |
| 责任 | delegation 指定允许 authority，completion 单独取证 | 把 abort、goto cleanup 或 delegation 当作 discharge |
| deadline | relation-specific，且不晚于首次危险 exposure/release/owner termination | 把所有函数出口无条件当成同一个边界 |
| 证据 | 设计语义、正常/安全路径、Bug 反例、fixed/repaired 路径可追踪 | 规则只有 Bug 路径支持，即 `BUG_DERIVED_ONLY` |
| 证明闭包 | violation 有精确 witness 和 repair slice；conformance 有全路径闭包 | 用 `UNKNOWN/WIDENED` 证明安全 |
| 独立性 | 按 operation family 计数 | 同一函数/补丁系列的多个 relation 投影重复计数 |

Bug ID、目标函数、源码行号和补丁 ID 只能出现在 evidence reference，不能进入 guard、AcceptP 或 binding 选择条件。binding 只把结构化源码事实映射为领域事件，不能补写协议语义。

## TOC 约束与 Gate P1

当前系统的主约束不是 DSL 表达力，而是领域证据独立性：#7 是单一 recovery operation family，#16-#18 是单一 sprout operation family。先冻结诚实、可执行的窄协议，比把同一案例投影包装成泛化更重要。

Gate P1 通过条件：

- 协议名、roles、relations、phases、authorities 和 deadlines 均为领域实体；
- 每条冻结规则在 traceability matrix 中不是 `BUG_DERIVED_ONLY`；
- Bug/fixed/safe/delegated/unknown 路径完成手工 replay；
- source binding 不含 Bug/函数/行号特判；
- operation-family split 明确，未制造 held-out；
- v0.2 有独立 Catalog、evaluation manifest 和 hash freeze，不回写 v0.1。

