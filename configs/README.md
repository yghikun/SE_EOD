# Configuration Layout

## Active MOCC-SE configuration

`configs/metadata_protocols/` contains the only configuration consumed by the
current runtime. Protocol files define:

```text
filesystem/version applicability
operation and object roles
phases and callee roles
return contracts
effects, compensations and handler ownership
accounting constraints
legal exits
discovery-only semantic patterns
```

They are filesystem-specific instances of the shared parameterized EFSM. A
protocol describes legal behavior; it must not encode a known function as a bug.

See [`metadata_protocols/README.md`](metadata_protocols/README.md) for schema and
CLI details.

## Archived SE-EOD configuration

The remaining root-level resource maps, ranking protocols, wrapper summaries,
review exceptions and historical-fix files belong to the removed SE-EOD
`src.main` pipeline. They are retained only to interpret historical outputs and
confirmed-bug provenance.

Current `src/` modules do not load these files. Do not cite them as active
MOCC-SE semantics, and do not add new resource/ranking entries unless the legacy
pipeline is explicitly restored by a new scope decision.
