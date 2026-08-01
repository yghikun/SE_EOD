# FMPCA Protocol Catalog v0.1 Freeze Manifest

Freeze date: 2026-07-31

Catalog version: `0.1.0`

Freeze status: `GATE_P_PASSED_WITH_RECORDED_EVIDENCE_GAPS`

The recorded gaps affect historical baseline identity for several corpus cases
but do not define any frozen rule. Both frozen protocols have independent
design/normal-source evidence, confirmed counterexamples, safe or repaired
paths, and validation cases. No frozen rule is `BUG_DERIVED_ONLY`.

## Frozen Content Hashes

| Artifact | SHA-256 |
|---|---|
| `docs/corpus/confirmed-bugs-source.md` | `d90cddfed582bcc4bcd32b40a17932baa7433ae16144350332be439af01d0e96` |
| `docs/corpus/confirmed-metadata-bugs.md` | `e59698d747a592af3ea86ae04c24ad623da3614ae29c031d2986367bde2e026f` |
| `docs/protocol-mining/candidate-clusters.md` | `663a53f39d0e434943ddb5d3367fae2da5444376b11dbba896ac10dbef38a964` |
| `docs/protocol-mining/evaluation-split.md` | `034e88274630e44b0568cdf6f66cf15e34a60fa6dcc79000e2fd429169e84cbe` |
| `docs/protocol-mining/traceability-matrix.md` | `5f54d9a5f1f6ec1ab66deb0b34db2c4080339fea16a20964069b6ddde769bfce` |
| `docs/protocol-mining/protocol-catalog-v0.1.md` | `2e8695927e86c7cf2e68df9c31b735f2fcf5a6871bb087fab0f76336e1ac087d` |
| `docs/protocol-mining/manual-replay-results-v0.1.md` | `4711c7286a0c075525e2948c41cdeb8df44563731bf968878e0055e0e7404024` |
| `docs/protocol-mining/dossier-hashes-v0.1.txt` | `2efcd373adacfd5670792833595990f3bf8e2f3eadfe7d86b27b52e9e9b264f2` |

The 11 dossier hashes are recorded in `dossier-hashes-v0.1.txt`. Any dossier
change after freeze requires a new catalog version if it changes a general
rule. Pure provenance completion may update a dossier without changing Catalog
v0.1, but must be logged.

## Corpus Decision

- Included: `#1,#2,#4,#5,#7,#8,#13,#15,#16,#17,#18`
- Excluded: `#3,#6,#9,#10,#11,#12,#14`
- Frozen-protocol evidence: `#1,#2,#4,#5,#7,#8,#13,#16,#17,#18`
- Deferred candidate only: `#15`

## Evaluation Split

- Development: `#4,#5,#7,#16,#18`
- Deferred-candidate development: `#15`
- Validation: `#1,#2,#17` plus excluded scope negatives
- Held-out: `#8,#13`

## Source Versions

| Version | Git tag/commit | Archive SHA-256 |
|---|---|---|
| Linux v6.8 | `e8f897f4afef0031fe618a8e94127a0934896aba` | `87eebb4c5d35b5c71e2b1dbdd106be6e6ccc0ee3c3ba0602a3fc4d9d169a6b93` |
| Linux v6.14 | `38fec10eb60d687e30c8c6b5420d86e8149f7557` | `a294b683e7b161bb0517bb32ec7ed1d2ea7603dfbabad135170ed12d00c47670` |
| Linux v7.1 | `8cd9520d35a6c38db6567e97dd93b1f11f185dc6` | `691f44797fbe790dc8a321604c927087526ad27b6d649925d60f8eed0a2564a0` |

## Binding And Kernel Policy

- Semantic kernel version to implement: `fmpca-kernel-0.1.0`.
- Source binding version to implement: `source-bindings-0.1.0`.
- Bindings may use types, field/access paths, primitive calls, parameter/return
  partitions, and structural control-flow evidence.
- Bindings may select an operation root as analysis input, but may not put its
  function name into a protocol guard or acceptance clause.
- Held-out binding additions must remain generic and cannot change the catalog
  hash or `AcceptP`.

## Known Unmodeled Semantics

- arbitrary crash points, persistence ordering, and crash images;
- general durability and persistent recovery authority;
- complete thread interleavings;
- arbitrary atomic points;
- complete heap/shape analysis;
- unbounded alias candidate sets;
- catalog coverage for the singleton companion-reservation case #15.

## Gate P Audit

- Metadata Bug screening complete: PASS.
- Normative/design, normal-source, and confirmed-Bug evidence per frozen
  protocol: PASS.
- Bug, fixed/safe, and unknown manual replay: PASS.
- Frozen `BUG_DERIVED_ONLY` rules: NONE.
- Development/validation/held-out split recorded: PASS.
- Catalog and freeze manifest generated: PASS.
