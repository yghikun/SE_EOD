# Configuration Layout

## Active MOCC-SE configuration

`configs/metadata_rules/` contains the versioned, evidence-backed rule
registry. It records source provenance, maturity, supported/unsupported
semantics, and bindings from semantic rules to executable protocol operations.
Coverage targets are kept separate from active rules, so a planned rule family
cannot be reported as current analysis capability.

Validate the registry and its protocol bindings with:

```powershell
python -m src.metadata_rule_registry
python -m src.metadata_evidence_verifier
python -m src.metadata_validation_manifest
python -m src.metadata_validation_labels `
  --labels configs/validation/reviewer_a_labels_v1.json `
  --labels configs/validation/reviewer_b_labels_v1.json `
  --adjudication configs/validation/adjudication_v1.json
python -m src.metadata_batch_scan `
  --source-root linux-sources/linux-v7.1-fs/fs `
  --source-version 7.1 `
  --max-files 1
```

`configs/metadata_protocols/` contains the configuration consumed by the
current EFSM runtime. Protocol A-C are flat runtime files. Protocol D/E are
package manifests composed from:

```text
protocol_families/     reusable roles, actions, obligations, applicability
filesystem_bindings/  filesystem API, object-role, guard, and owner mappings
operations/            entry functions, contracts, effects, and legal exits
```

The composed runtime protocol defines:

```text
filesystem/version applicability
operation and object roles
phases and callee roles
return contracts
effects, compensations and handler ownership
schema-v2 bounded one-call effect summaries and call-site object substitution
accounting constraints
legal exits
discovery-only semantic patterns
```

They are filesystem-specific instances of the shared parameterized EFSM. A
protocol describes legal behavior; it must not encode a known function as a bug.

See [`metadata_rules/README.md`](metadata_rules/README.md) for evidence and
coverage semantics, and
[`metadata_protocols/README.md`](metadata_protocols/README.md) for executable
protocol schema and CLI details.

`configs/validation/` freezes the active protocol/rule configuration, records
the first blind validation batch, and stores empty reviewer/adjudication
templates. It currently contains 14 frozen artifacts and 10 blind, unlabeled
samples. This is not an evaluation result: labels, adjudication, and metrics
must be completed after reviewer access.

## Removed SE-EOD configuration

The root-level resource maps, wrapper summaries, review exceptions,
historical-fix files, and filesystem-specific `*_resource_protocols/`
directories belonged to the removed SE-EOD `src.main` pipeline. They were
deleted after confirming that current source, tests, scripts, and documentation
do not load or reference them.

The active configuration tree is now:

```text
configs/
  protocol_families/    reusable abstract protocol semantics
  filesystem_bindings/ filesystem-specific API and object mappings
  operations/           entry-specific protocol instantiation
  metadata_protocols/   flat protocols, package manifests, and schema fixture
  metadata_rules/       evidence authority, usage, split, maturity, and coverage
  validation/           frozen inputs and blind validation manifest
  README.md
```

Historical outputs remain evidence artifacts, but their deleted resource and
ranking configuration is not a current reproducibility promise.
