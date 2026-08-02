# OIDS Phase 7 Qualified ext4 Failstop Scope

Manifest: `configs/evaluation/oids-phase7-scope-freeze-v0.1.json`

Qualified scope closed: `True`
Semantic scope: `FS_SPECIFIC`
Freeze boundary: `NARROW_FREEZE`
ERRORS_CONT explicitly excluded: `True`
COMMON freeze generated: `False`
Blind held-out claim allowed: `False`

## Applicability

`filesystem == ext4 AND error_policy != ERRORS_CONT`

The declared scope is `FS_SPECIFIC` and `NARROW_FREEZE`; it covers only the
non-continuing ext4 failstop profile. The Phase 6 ERRORS_CONT witnesses remain
an explicit exclusion and are not hidden assumptions.

## Gate result

| Gate | Result |
|---|---|
| scope declaration | `True` |
| Phase 6 failstop closure | `True` |
| Phase 6 negative witnesses | `True` |
| independent family status | `NOT_A_BLIND_HELD_OUT` |

Phase 7 freezes a narrow ext4 failstop-qualified OIDS scope: filesystem == ext4 AND error_policy != ERRORS_CONT. ERRORS_CONT remains an explicit excluded configuration with closed Phase 6 negative witnesses. COMMON freeze and blind held-out claims remain false.
