# Metadata Scope

`metadata_scope_v1.json` is the current metadata boundary for MetaWindow.

It records:

```text
target file systems
metadata domains
inclusion requirements
supporting-resource policy
confirmed-bug scope decisions
```

The scope gate exists to keep MetaWindow from becoming a general cleanup
checker.  Ordinary memory, buffer, folio, path/name, lock, and helper-temporary
bugs are out of scope unless the object carries file-system metadata completion
semantics.
