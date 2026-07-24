# Outputs

Only curated evidence needed by filesystem metadata residual analysis is part
of the active project story.

```text
confirmed_bugs.md
  Source-level confirmed or reviewed Linux filesystem findings used to define
  the filesystem metadata residual evidence boundary.

linux-v6.8/btrfs/recover_relocation_qemu_report.md
  Targeted fault-injection evidence for the relocation-root recovery residual.
  This file is retained because confirmed_bugs.md cites it as provenance.
```

Generated evaluation directories under `outputs/residual-evaluation*` are
ignored run artifacts. Historical handoff entries may mention prior run
locations, but those directories are not part of the active evidence chain and
can be regenerated when a milestone comparison needs them.
