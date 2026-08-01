# Domain Traceability Matrix v0.4

| Rule | Design/source semantics | Negative witness | Repaired/safe | Boundary |
|---|---|---|---|---|
| WDC-I1 | membership plus writable/allocation eligibility determines contribution | composed eligibility mismatch | add success and full rollback | cross-protocol fact must be exact |
| WDC-I2 | add/remove symmetric aggregate deltas; shrink used-aware `free_diff` | confirmed shrink Bug | accepted shrink fix and add rollback | actual allocatable capacity, not raw size |
| WDC-I3 | membership removal and aggregate removal precede release | release-before-detach replay and DTR release family | detached release replay/component rule | `BEFORE_RELEASE` |
| WDC-O1 | every changed contribution relation has independent prestate | partial aggregate rollback replay; confirmed shrink rollback Bug | full add/shrink rollback | delegation is not completion |
| DTC-ID | components share operation/device identity | identity mismatch replay | exact shared identity | mismatch yields `INCOMPLETE` |
| DTC-C1/C2 | topology membership controls capacity eligibility/contribution | cross-relation mismatch replay | add success/full rollback | component conformance alone is insufficient |
| DTC-C3 | release requires topology and contribution absence | release negative replay | detached component paths | earliest release boundary |

No rule or binding contains a Bug ID, patch ID, target function or source line.
