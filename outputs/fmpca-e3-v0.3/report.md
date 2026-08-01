# FMPCA Evaluation Report

Manifest: `configs\evaluation\e3-v0.3.json`

Passed: 8 / 8

| Case | Role | Expected | Actual | Pass |
|---|---|---|---|---|
| rras-bug | DEVELOPMENT_BUG | `VIOLATION_UNDER_LOADED_SPEC` | `VIOLATION_UNDER_LOADED_SPEC` | PASS |
| rras-fixed | FIXED_STRUCTURED_PATH | `CONFORMANT_UNDER_LOADED_SPEC` | `CONFORMANT_UNDER_LOADED_SPEC` | PASS |
| rras-normal | NORMAL | `CONFORMANT_UNDER_LOADED_SPEC` | `CONFORMANT_UNDER_LOADED_SPEC` | PASS |
| rras-unknown | UNKNOWN | `POSSIBLE_VIOLATION_REVIEW` | `POSSIBLE_VIOLATION_REVIEW` | PASS |
| dssa-bug | DEVELOPMENT_BUG | `VIOLATION_UNDER_LOADED_SPEC` | `VIOLATION_UNDER_LOADED_SPEC` | PASS |
| dssa-fixed-success | FIXED_SUCCESS | `CONFORMANT_UNDER_LOADED_SPEC` | `CONFORMANT_UNDER_LOADED_SPEC` | PASS |
| dssa-fixed-failure | FIXED_FAILURE | `CONFORMANT_UNDER_LOADED_SPEC` | `CONFORMANT_UNDER_LOADED_SPEC` | PASS |
| dssa-unknown | UNKNOWN | `INCOMPLETE_UNDER_LOADED_SPEC` | `INCOMPLETE_UNDER_LOADED_SPEC` | PASS |

## Baseline Comparison

| Case | B1 API pairing | B2 local restoration | B3 single-object typestate |
|---|---|---|---|
| rras-bug | `NO_APPLICABLE_CHECK` | `NO_APPLICABLE_CHECK` | `NO_APPLICABLE_CHECK` |
| rras-fixed | `NO_APPLICABLE_CHECK` | `NO_APPLICABLE_CHECK` | `NO_APPLICABLE_CHECK` |
| rras-normal | `NO_APPLICABLE_CHECK` | `NO_APPLICABLE_CHECK` | `NO_APPLICABLE_CHECK` |
| rras-unknown | `NO_APPLICABLE_CHECK` | `NO_APPLICABLE_CHECK` | `NO_APPLICABLE_CHECK` |
| dssa-bug | `NO_APPLICABLE_CHECK` | `NO_APPLICABLE_CHECK` | `NO_APPLICABLE_CHECK` |
| dssa-fixed-success | `NO_APPLICABLE_CHECK` | `NO_APPLICABLE_CHECK` | `NO_APPLICABLE_CHECK` |
| dssa-fixed-failure | `NO_APPLICABLE_CHECK` | `NO_APPLICABLE_CHECK` | `NO_APPLICABLE_CHECK` |
| dssa-unknown | `NO_APPLICABLE_CHECK` | `NO_APPLICABLE_CHECK` | `NO_APPLICABLE_CHECK` |

## Guardrails

- Catalog SHA-256: `46bb4fcbf3d4327cfe7850a756f0a7822be0476b025d500a86e1ba461d144304`
- Bug-specific condition count: `0`
- Held-out checker modifications: `0`
- Results are relative to the loaded protocol, binding, path model, and assumptions; no absolute SAFE claim is made.
