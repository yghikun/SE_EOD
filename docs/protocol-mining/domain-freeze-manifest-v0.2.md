# Domain Semantic Freeze v0.2

冻结日期：2026-07-31。机器可校验清单位于 `configs/freeze/domain-semantic-freeze-v0.2.json`。

冻结范围包括领域资格标准、候选决策、traceability、manual replay、operation-family split、Domain Catalog、两个可执行协议、两个通用结构 binding 和 E1 manifest。v0.1 Catalog、协议、E0 manifest、E0 输出及其 hash 不在本次变更范围内。

已知未建模语义：完整 C alias/shape、宏展开、跨线程 interleaving、crash persistence ordering、任意 helper summary、自动识别所有 release/exposure consumer。source frontend 的 conformance 结论因此仍需 all-path closure；当前真实源码案例只用于精确 violation witness。

冻结后的规则变更必须创建新 Catalog 版本。新增 source binding 或 summary 若不改变 protocol/AcceptP，可作为实现修订；任何基于 held-out 结果改变领域规则的版本都不能继续把该案例称为 held-out。

