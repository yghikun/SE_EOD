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

An unfrozen `RelocationRootAttachmentSettlement` v0.3 draft now models
runtime merge settlement for a preexisting `fs_root.reloc_root` attachment.
It is candidate evidence only and is not included in v0.2 evaluation claims.

An unfrozen `DeviceShrinkSpaceAccounting` v0.3 draft models the coupled
`device.total_bytes` / `total_rw_bytes` / `free_chunk_space` accounting
transition. It is a singleton candidate and is not frozen.

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

Validate the unfrozen v0.3 draft:

```powershell
python -m src.fmpca validate-protocol configs/protocols/relocation-root-attachment-settlement-v0.3-draft.json
```

The device-shrink draft can be validated with:

```powershell
python -m src.fmpca validate-protocol configs/protocols/device-shrink-space-accounting-v0.3-draft.json
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

Run all tests:

```powershell
python -m unittest discover -s tests -v
```

## Repository Layout

```text
docs/corpus/           recovered and screened confirmed-Bug corpus
docs/cases/            per-Bug evidence dossiers and normalized records
docs/protocol-mining/  v0.1 baseline plus v0.2 domain criteria, traceability, replay and catalog
docs/specs/            five executable semantic specifications
docs/gates/            Gate S and Gate R implementation audits
docs/evaluation/       E0 scope, results and interpretation boundary
configs/protocols/     executable frozen protocols and Membership fixture
configs/bindings/      generic source bindings and v0.3 draft binding
configs/freeze/        v0.1 baseline and v0.2 domain semantic hash locks
configs/evaluation/    E0 kernel-regression, E1 domain-qualification and E2
                       held-out eligibility manifests
src/fmpca/             semantic kernel, instance reconstruction and frontend
                         plus isolated v0.3 candidate adapter
tests/                 paired semantic, source, summary and evaluation tests
outputs/fmpca-e0-v0.1/ reproducible kernel baseline result and report
outputs/fmpca-e1-v0.2/ reproducible domain qualification result and report
outputs/fmpca-e2-v0.2/ reproducible held-out eligibility result and report
```

## Result Classes

```text
VIOLATION_UNDER_LOADED_SPEC
POSSIBLE_VIOLATION_REVIEW
INCOMPLETE_UNDER_LOADED_SPEC
CONFORMANT_UNDER_LOADED_SPEC
NO_APPLICABLE_PROTOCOL
```

FMPCA never emits an absolute `SAFE` result. See
`docs/protocol-mining/domain-freeze-manifest-v0.2.md` for the frozen domain
evidence boundary and `docs/specs/proof-closure.md` for result closure
requirements.
