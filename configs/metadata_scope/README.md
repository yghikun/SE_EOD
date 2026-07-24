# Filesystem Metadata Scope

`metadata_scope_v1.json` is the current boundary for filesystem metadata
residual analysis.

It records:

```text
target file systems
metadata domains
inclusion requirements
supporting-resource policy
confirmed-bug scope decisions
```

The scope gate keeps the analyzer from becoming a general cleanup checker.
Ordinary memory, buffer, folio, path/name, lock, and helper-temporary bugs are
out of scope unless independent evidence connects the object to filesystem
metadata completion, topology, namespace, quota, recovery, or accounting state.
