# Domain Manual Replay v0.5

| Case | Role | Result |
|---|---|---|
| `cmrc-bug-v0.5.json` | confirmed Bug #15 positive-success reservation skip | `VIOLATION` |
| `cmrc-fixed-v0.5.json` | fixed/repair path with reservation completed | `CONFORMANT` |
| `cmrc-normal-v0.5.json` | normal chunk allocation reservation path | `CONFORMANT` |
| `cmrc-device-update-normal-v0.5.json` | sibling device-item update family | `CONFORMANT` |
| `cmrc-unknown-v0.5.json` | missing commit/path closure | `INCOMPLETE` |

The replay proves conformance only relative to the loaded CMRC v0.5 spec,
binding and closure assumptions. It does not claim arbitrary chunk-tree
operations or cross-filesystem reservation protocols are covered.

