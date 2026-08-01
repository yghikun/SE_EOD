# FMPCA

Failure-aware Metadata Protocol Conformance Analyzer.

FMPCA reconstructs finite metadata protocol instances from typed events and
checks relation, obligation, responsibility, observability, and outcome clauses
at protocol-specific deadlines. Results are always relative to the loaded
protocol, source binding, path model, and recorded assumptions.

## Current Scope

Domain Protocol Catalog v0.2 freezes two filesystem-metadata protocols:

- `fmpca.recovery_attachment_settlement`
- `fmpca.device_topology_rollback`

Domain Protocol Catalog v0.3 freezes two additional protocols in a narrow
scope (one operation family each):

- `fmpca.relocation_root_attachment_settlement`
- `fmpca.device_shrink_space_accounting`

The v0.3 freeze is not a held-out or cross-filesystem generalization claim.
Independent-family evidence is tracked separately by the readiness manifests.

Domain Protocol Catalog v0.4 freezes the device-capacity decomposition:

- `fmpca.device_topology_rollback` remains the unchanged topology component.
- `fmpca.writable_device_capacity_contribution` owns writable-capacity deltas.
- `fmpca.device_topology_capacity_composition` checks their shared identities
  and cross-component relations.

The capacity protocol is validated across independent device-membership and
device-resize operation families. This is cross-operation-family evidence,
not a post-freeze held-out or cross-filesystem generalization claim. Frozen
v0.3 `DeviceShrinkSpaceAccounting` remains immutable and is the shrink
transition predecessor of the v0.4 capacity component.

Domain Protocol Catalog v0.5 freezes one additional narrow protocol:

- `fmpca.chunk_metadata_reservation_completion` owns chunk-tree metadata
  publication/update, transaction-scoped chunk metadata reservation, and
  release-before-commit settlement.

CMRC v0.5 is validated across the confirmed Bug #15 reservation family and an
independent Btrfs device-item update family. This is cross-operation-family
qualification, not post-freeze held-out or cross-filesystem generalization.

Versioned `v0.1`-`v0.3` artifacts are kept on purpose. They are still
referenced by tests, freeze manifests, traceability docs, and the handoff
history, so they are not dead weight. The disposable layer here is generated
runtime cache such as `__pycache__`, not frozen protocol history.

Catalog v0.1 remains a read-only engineering baseline. Its
`MetadataTransitionOutcome` and `FailureRollbackConformance` rules now qualify
the reusable `OutcomeAgreement`, `RestoreOrDelegate`, and `ProofClosure`
mechanisms; they are not the final domain protocols.

The source frontend is intentionally minimal. It maps structural field,
primitive, relation-mutator and repair-slice evidence to domain events. It does
not claim arbitrary C semantics, crash-image analysis, persistence ordering,
complete concurrency, or general heap/shape analysis.

## Requirements

- Python 3.9 or newer
- No third-party runtime dependencies
- Local Linux source snapshots for the real-source evaluation cases
- Git history for provenance-locked revision screening; fetch required commits
  when a snapshot is shallow

## Commands

Validate a protocol:

```powershell
python -m src.fmpca validate-protocol configs/protocols/recovery-attachment-settlement-v0.2.json
```

Validate the frozen v0.3 protocol artifact (the legacy `draft` filename is
retained for compatibility):

```powershell
python -m src.fmpca validate-protocol configs/protocols/relocation-root-attachment-settlement-v0.3-draft.json
```

The frozen device-shrink artifact can be validated with:

```powershell
python -m src.fmpca validate-protocol configs/protocols/device-shrink-space-accounting-v0.3-draft.json
```

Validate the frozen v0.4 capacity protocol:

```powershell
python -m src.fmpca validate-protocol configs/protocols/writable-device-capacity-contribution-v0.4.json
```

Validate the frozen v0.5 chunk-reservation protocol:

```powershell
python -m src.fmpca validate-protocol configs/protocols/chunk-metadata-reservation-completion-v0.5.json
```

Analyze structured events:

```powershell
python -m src.fmpca analyze-events `
  --protocol configs/protocols/device-topology-rollback-v0.2.json `
  --events tests/fixtures/events/dtr-release-violation.json `
  --out outputs/example-dtr.json
```

Analyze one real C operation root:

```powershell
python -m src.fmpca analyze-source `
  --protocol configs/protocols/device-topology-rollback-v0.2.json `
  --binding configs/bindings/device-topology-rollback-v0.2.json `
  --source linux-sources/linux-v6.14-fs/fs/btrfs/volumes.c `
  --source-version linux-v6.14 `
  --function btrfs_init_new_device `
  --out outputs/example-source.json
```

Run the frozen domain E1 evaluation:

```powershell
python -m src.fmpca evaluate `
  --manifest configs/evaluation/e1-v0.2.json `
  --json-out outputs/fmpca-e1-v0.2/results.json `
  --markdown-out outputs/fmpca-e1-v0.2/report.md
```

Run the post-freeze held-out eligibility gate:

```powershell
python -m src.fmpca evaluate `
  --manifest configs/evaluation/e2-v0.2.json `
  --json-out outputs/fmpca-e2-v0.2/results.json `
  --markdown-out outputs/fmpca-e2-v0.2/report.md
```

E2 currently admits zero v0.2 families. The confirmed runtime relocation
merge Bug/fix is retained as a v0.3 protocol candidate because its
preexisting-attachment lifecycle is outside frozen RAS v0.2.

Run the frozen v0.3 replay:

```powershell
python -m src.fmpca evaluate `
  --manifest configs/evaluation/e3-v0.3.json `
  --json-out outputs/fmpca-e3-v0.3/results.json `
  --markdown-out outputs/fmpca-e3-v0.3/report.md
```

The v0.3 replay currently passes 8/8 cases. It is a narrow qualification
evaluation, not held-out or cross-filesystem generalization evidence.

Run the frozen v0.4 capacity and topology-composition evaluation:

```powershell
python -m src.fmpca.composition `
  --manifest configs/evaluation/e4-v0.4.json `
  --json-out outputs/fmpca-e4-v0.4/results.json `
  --markdown-out outputs/fmpca-e4-v0.4/report.md
```

E4 passes 10/10 capacity and composed replay cases, including confirmed Bug,
fixed failure, normal, release-negative, cross-relation-negative and unknown
identity paths.

Run the post-v0.4 held-out applicability screen:

```powershell
python -m src.fmpca.heldout_v4 `
  --manifest configs/evaluation/e5-v0.4-heldout-screening.json `
  --json-out outputs/fmpca-e5-v0.4-heldout-screening/results.json `
  --markdown-out outputs/fmpca-e5-v0.4-heldout-screening/report.md
```

E5 currently screens Btrfs device grow/remove/replace-finish plus the
independent Btrfs chunk-metadata reservation family. None are admitted as
WDC/DTC held-out evidence: grow/remove fail the existing source-witness closure
budget, replace-finish is a topology/identity substitution, and #15 is outside
the device-capacity object model.

Run the frozen ChunkMetadataReservationCompletion readiness gate:

```powershell
python -m src.fmpca.chunk_candidate `
  --manifest configs/evaluation/cmrc-v0.5-readiness.json `
  --json-out outputs/fmpca-cmrc-v0.5-freeze-readiness/results.json `
  --markdown-out outputs/fmpca-cmrc-v0.5-freeze-readiness/report.md
```

CMRC v0.5 currently reports `candidate_ready=True`,
`freeze_eligible=True`, replay `5/5`, and second-family screening `1/1`.
The readiness runner verifies `configs/freeze/domain-semantic-freeze-v0.5.json`
before replay.

Run the post-v0.5 CMRC held-out screen:

```powershell
python -m src.fmpca.heldout_cmrc_v5 `
  --manifest configs/evaluation/e6-v0.5-heldout-screening.json `
  --json-out outputs/fmpca-e6-v0.5-heldout-screening/results.json `
  --markdown-out outputs/fmpca-e6-v0.5-heldout-screening/report.md
```

E6 admits `btrfs-chunk-item-removal` as one post-freeze held-out family for
CMRC and rejects `btrfs-device-item-update` as not independent from the v0.5
freeze. Replay passes 4/4 for normal, fixed/repair, negative and unknown
paths.

Run all tests:

```powershell
python -m unittest discover -s tests -v
```

## Repository Layout

```text
docs/corpus/           recovered and screened confirmed-Bug corpus
docs/cases/            per-Bug evidence dossiers and normalized records
docs/protocol-mining/  versioned domain criteria, evidence, traceability, replay and catalogs
docs/specs/            five executable semantic specifications
docs/gates/            Gate S and Gate R implementation audits
docs/evaluation/       E0 scope, results and interpretation boundary
configs/protocols/     executable frozen protocols and Membership fixture
configs/bindings/      generic and versioned domain source bindings
configs/compositions/  executable cross-protocol composition specifications
configs/freeze/        v0.1-v0.5 semantic hash locks
configs/evaluation/    E0-E5 qualification, readiness and held-out manifests
src/fmpca/             semantic kernel, instance reconstruction and frontend
                       plus versioned domain adapters and composition checker
tests/                 paired semantic, source, summary and evaluation tests
outputs/fmpca-e0-v0.1/ reproducible kernel baseline result and report
outputs/fmpca-e1-v0.2/ reproducible domain qualification result and report
outputs/fmpca-e2-v0.2/ reproducible held-out eligibility result and report
outputs/fmpca-e3-v0.3/ reproducible narrow v0.3 replay result and report
outputs/fmpca-e4-v0.4/ reproducible capacity/composition result and report
outputs/fmpca-e5-v0.4-heldout-screening/
                       reproducible post-v0.4 held-out applicability screen
outputs/fmpca-cmrc-v0.5-freeze-readiness/
                       reproducible CMRC freeze-readiness result and report
outputs/fmpca-e6-v0.5-heldout-screening/
                       reproducible post-v0.5 CMRC held-out screen
```

## Result Classes

```text
VIOLATION_UNDER_LOADED_SPEC
POSSIBLE_VIOLATION_REVIEW
INCOMPLETE_UNDER_LOADED_SPEC
CONFORMANT_UNDER_LOADED_SPEC
NO_APPLICABLE_PROTOCOL
```

FMPCA never emits an absolute `SAFE` result. See the versioned
`docs/protocol-mining/domain-freeze-manifest-*.md` files for frozen evidence
boundaries and `docs/specs/proof-closure.md` for result closure requirements.
