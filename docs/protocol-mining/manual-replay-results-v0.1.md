# P0.5 Manual Replay Results v0.1

State notation lists only changed fields. Each replay assumes an exact anchor
identity unless explicitly marked unknown.

## MetadataTransitionOutcome

| Path | ProtocolInstanceKey | Event sequence and state progression | Deadline clauses | Result |
|---|---|---|---|---|
| #5 Bug | `<MTO,replay+inode,epoch>` | `Begin` -> `IN_PROGRESS`; `MetadataStep` -> `completion=PARTIAL`; `FailureObserved` -> `active_failure=true`, MTO-O1 active; `ReportSuccess`; `OperationReturn` | MTO-R1 false; MTO-O1 due/open | VIOLATION |
| #5 fixed | same versioned key | failure activates MTO-O1; `ReportError`; `OperationReturn` | MTO-O1 discharged by error propagation; MTO-R1/R2 hold | CONFORMANT |
| Normal success | `<MTO,op+subject,epoch>` | `Begin`; zero or more steps; `TransitionComplete`; `ReportSuccess`; `OperationReturn` | completion exact, no active failure | CONFORMANT |
| Safe error before completion | same | `Begin`; `FailureObserved`; `ReportError`; `OperationReturn` | failure propagated | CONFORMANT |
| Successful retry (#4 fixed shape) | same | failure; `RetryBegin`; steps; `FailureSuperseded`; `TransitionComplete`; `ReportSuccess`; return | MTO-O1 discharged by proven recovery; R2 holds | CONFORMANT |
| Stale retry outcome (#4) | same | failure; retry; supersede; complete; `ReportError`; return | MTO-R2 false | VIOLATION |
| Unknown helper | same | step precision becomes `UNKNOWN`; `ReportSuccess`; return | MTO-R1 cannot be proven and no exact violation witness | INCOMPLETE |
| #1/#2 validation | replay keys | internal failure; common cleanup; literal success; return | same generic R1/O1 failure; no new rule | VIOLATION |
| #8 held-out Bug | `<MTO,growfs+summary,epoch>` | summary mutation; failure; cleanup; literal success; return | MTO-R1/O1 fail | VIOLATION |
| #8 fixed | same versioned key | failure; cleanup; return current error | MTO-O1 discharged | CONFORMANT |
| #13 held-out Bug | `<MTO,growfs+rtginode,epoch>` | load failure other than absence; transaction cancel; literal success | cancel does not supersede failure; R1/O1 fail | VIOLATION |

MTO has no legal authority-transfer path because the direct outcome owner must
report the result. A purported transfer is therefore an invalid event rather
than a conformant replay.

## FailureRollbackConformance

| Path | ProtocolInstanceKey | Event sequence and state progression | Deadline clauses | Result |
|---|---|---|---|---|
| #7 non-abort Bug | `<FRC,recovery+fs_root,epoch>` | snapshot detached; attach reloc root; failure; FRC-O1 active; owner teardown without matching detach | FRC-O1 due at owner termination | VIOLATION |
| #7 abort safe sibling | same | attach; failure; abort establishes guarded teardown authority; detach/drop each root; owner termination | every delegated/restoration obligation completed | CONFORMANT |
| #7 repaired path | same | attach; failure; explicit tracked-root detach/drop before exit | symbolic prestate restored | CONFORMANT |
| Normal relocation recovery | same | attach; transaction completes; protocol-owned cleanup reaches stable relation; complete | no failed-transition rollback remains due | CONFORMANT |
| #16 Bug | `<FRC,device-add+sprout,epoch>` | attach device to update list; failure; abort; release device while still attached | FRC-I1 and O1 fail at owner termination | VIOLATION |
| #17 validation Bug | same operation/container, active-pointer role | rebind active pointer; failure; release new device; live exposure | irreversible stale-target witness at exposure | VIOLATION |
| #18 Bug | same operation/container | move seed members/change fsid; failure; partial cleanup; return error | container relation differs from symbolic prestate | VIOLATION |
| Full sprout rollback | same | all deltas recorded; failure; detach list, restore pointers, members, fsid; return error | all relation obligations discharged independently | CONFORMANT |
| Legal responsibility transfer | generic key | mutation; failure; delegate one relation to allowed teardown owner with closed isolation; authority completes before original deadline | delegation alone does not discharge; completion does | CONFORMANT |
| Delegation without completion | same | delegate; reach original deadline | FRC-O2 due/open | VIOLATION |
| Unknown helper | same | helper may restore or mutate relation; precision `UNKNOWN`; settlement | neither conformance nor exact violation closure | INCOMPLETE |
| Failure before relation delta | same | snapshot; failure; error return | no FRC-O1 activated | NO_APPLICABLE_PROTOCOL |

## Closure Check

Every VIOLATION row has an exact witness ending at or before the rule deadline.
Every CONFORMANT row closes all relevant paths represented by that replay.
Unknown helper rows never prove safety, and cleanup after a recorded exposure
does not erase the irreversible witness.
