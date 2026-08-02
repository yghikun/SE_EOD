# OIDS Phase 12 COMMON Claim Disposition and Counterexample Audit

Manifest: `configs/evaluation/oids-phase12-claim-disposition-v0.1.json`

Disposition closed: `True`
Historical results preserved: `True`
COMMON held-out validated: `False`

## Cross-filesystem matrix

| Filesystem | Role | Applicability | Normal profile | Failure path | Held-out disposition |
|---|---|---|---|---|---|
| btrfs | FREEZE_FORMATION_DEVELOPMENT | APPLICABLE | CLOSED | NOT_POST_COMMON_HELDOUT_TESTED | NOT_HELDOUT |
| ext4 | FREEZE_FORMATION_VALIDATION | APPLICABLE_WITH_EXPLICIT_CONFIGURATION_BOUNDARY | CLOSED | ERRORS_CONT_EXCLUDED_WITH_NEGATIVE_WITNESSES | NOT_HELDOUT |
| ubifs | FREEZE_FORMATION_VALIDATION | APPLICABLE_WITH_EXPLICIT_RECOVERY_PROFILE | CLOSED | READ_ONLY_RECOVERY_DEFERRED_OUTSIDE_PROFILE | NOT_POST_COMMON_HELDOUT |
| ocfs2 | POST_COMMON_BLIND_SCREENING | NON_APPLICABLE | LIVE_ONLY_CLOSED | NOT_EVALUABLE_UNDER_COMMON_DEADLINE | CONTROLLED_NON_APPLICABLE_DEADLINE_NOT_ALIGNED |
| reiserfs | POST_COMMON_BLIND_HELD_OUT | APPLICABLE | CLOSED | REFUTED_BY_OIDS_O1_AND_OIDS_O3 | NON_CONFORMANT_HELDOUT |

## Counterexample audit

| Rule | Source flow | Replay | Irreducible | Closed |
|---|---|---|---|---|
| OIDS-O1 | `True` | `VIOLATION_UNDER_LOADED_SPEC` | `True` | `True` |
| OIDS-O3 | `True` | `VIOLATION_UNDER_LOADED_SPEC` | `True` | `True` |

## Claim disposition

- `common_semantic_applicability`: `SUPPORTED_UNDER_FROZEN_NARROW_SCOPE`
- `common_normal_profile_conformance`: `SUPPORTED_FOR_EVALUATED_QUALIFIED_PROFILES`
- `common_failure_path_conformance`: `REFUTED_BY_POST_COMMON_HELDOUT_COUNTEREXAMPLE`
- `common_heldout_validated`: `False`
- `universal_filesystem_conformance`: `NOT_CLAIMED`
- `protocol_v0_1_disposition`: `FROZEN_WITH_RETAINED_COUNTEREXAMPLE`
- `revised_protocol_requirement`: `NEW_VERSION_AND_NEW_EVALUATION_SPLIT`

## Interpretation

The Phase 9 COMMON narrow freeze remains supported as a semantic applicability scope and the evaluated qualified normal profiles remain closed. Universal failure-path conformance is refuted by an applicable post-COMMON blind ReiserFS candidate with independently minimal OIDS-O1 and OIDS-O3 witnesses. OCFS2 remains a controlled non-applicable screening result and does not repair or refute the applicable counterexample. OIDS v0.1 is therefore frozen with its counterexample retained, COMMON_HELDOUT_VALIDATED remains false, and any protocol repair requires a new version and a new evaluation split.

Next phase: Phase 13 will freeze this disposition and preregister an OIDS v0.2 revision track before any semantic edit. ReiserFS OIDS-O1/OIDS-O3 become development counterexamples, not held-out evidence for v0.2; the revision must define its repair objective, create a new development/validation/held-out split, and reserve a genuinely unrevealed filesystem for any later validation claim.
