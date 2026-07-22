# Filesystem Bindings

A filesystem binding maps one abstract protocol family to concrete source
facts:

```text
filesystem and Linux versions
abstract-role to runtime-role mapping
action to callee/API mapping
call-site object extraction and normalization
guards, strength, and bounded call depth
```

A binding must not name a target operation entry or add a new correctness
obligation. It explains how family actions are recognized in one filesystem;
it does not decide that a particular function is buggy.
