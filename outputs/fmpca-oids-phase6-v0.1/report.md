# OIDS Phase 6 ext4 Configuration Boundary

Manifest: `configs/evaluation/oids-phase6-configuration-boundary-v0.1.json`

Failstop profile closed: `True`
ERRORS_CONT negative witnesses closed: `True`
Configuration decision: `VALID_CONFIGURATION_BOUNDARY`
Universal all-path closure: `False`

## Failstop recovery

journal abort forces flush -EIO through recovery completion into mount failure

## ERRORS_CONT witnesses

| Stage | Source | Verdict | Required rule | Closed |
|---|---|---|---|---|
| registration | True | `VIOLATION_UNDER_LOADED_SPEC` | `OIDS-O1` | `True` |
| settlement | True | `VIOLATION_UNDER_LOADED_SPEC` | `OIDS-O2` | `True` |
| recovery | True | `VIOLATION_UNDER_LOADED_SPEC` | `OIDS-O3` | `True` |

## Decision

Linux v6.14 closes ext4 OIDS registration, settlement, and recovery for the explicitly qualified non-continuing failstop profile. ERRORS_CONT remains a valid ext4 configuration and now has closed source-plus-semantic negative witnesses for OIDS-O1, OIDS-O2, and OIDS-O3. It is therefore a configuration boundary that rejects unqualified universal ext4 validation; no COMMON freeze manifest is generated.
