# Domain Manual Replay v0.4

| Case | Result |
|---|---|
| shrink normal success | `CONFORMANT` |
| shrink fixed failure | `CONFORMANT` |
| shrink confirmed wrong delta | `VIOLATION` |
| capacity unknown helper | `INCOMPLETE` |
| release before capacity detach | `VIOLATION` |
| topology add plus capacity contribution | `CONFORMANT` |
| topology and capacity full rollback | `CONFORMANT` |
| topology restored, capacity partially restored | `VIOLATION` |
| membership/eligibility mismatch | `VIOLATION` |
| component identity mismatch | `INCOMPLETE` |

The replay separates component results from cross-protocol closure. A safe
DTR result cannot hide a WDC or DTC violation.
