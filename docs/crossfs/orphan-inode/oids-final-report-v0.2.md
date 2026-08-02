# OIDS Final Report v0.2

OIDS models persistent orphan-inode deletion settlement across registration,
terminal settlement, and recovery exposure. The project closes at Phase 18 with
the v0.1 executable protocol unchanged and a separate v0.2 diagnostic extension.

## Final claims

| Claim | Final disposition |
|---|---|
| Btrfs qualified profile | Closed |
| ext4 fail-stop profile | Closed; `ERRORS_CONT` remains a negative boundary |
| UBIFS live/RW profile | Closed; read-only recovery remains deferred |
| ReiserFS error cases | Two source-confirmed correctness bugs under the frozen OIDS contract |
| JFS blind held-out | `NON_APPLICABLE / PERSISTENT_CLEANUP_OBJECT_NOT_FOUND` |
| COMMON v0.2 held-out validation | Not validated |

The JFS result is the first and final preregistered attempt. It was not replaced.
It neither supports nor refutes protocol conformance because JFS has no persistent
pending-cleanup object corresponding to the OIDS domain in the pinned kernel
implementation.

## Endpoint

The research implementation and evidence package are complete. Phase 18 is the
hard endpoint; future work is limited to bug fixes, dependency maintenance, and
reproducibility maintenance. New empirical claims require a separately versioned
project rather than Phase 19.
