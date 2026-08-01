# Domain Manual Replay v0.3

| Protocol | Input | Result |
|---|---|---|
| RRAS | confirmed Bug revision | `VIOLATION` (`RRM-I1`) |
| RRAS | accepted fix selected branch | `INCOMPLETE` (repair found; all-path closure not claimed) |
| RRAS | structured normal path | `CONFORMANT` |
| RRAS | unknown helper path | `POSSIBLE_VIOLATION_REVIEW` |
| DSSA | Bug accounting policy | `VIOLATION` (`DSSA-I1/I2`, settlement) |
| DSSA | fixed success path | `CONFORMANT` |
| DSSA | fixed failure rollback | `CONFORMANT` |
| DSSA | unknown policy | `INCOMPLETE` |

These results are relative to the frozen v0.3 protocols and their stated
closure assumptions. They are not cross-filesystem benchmark results.
