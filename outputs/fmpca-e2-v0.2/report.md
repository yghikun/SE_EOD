# FMPCA Evaluation Report

Manifest: `configs\evaluation\e2-v0.2.json`

Passed: 0 / 0

| Case | Role | Expected | Actual | Pass |
|---|---|---|---|---|

## Baseline Comparison

| Case | B1 API pairing | B2 local restoration | B3 single-object typestate |
|---|---|---|---|

## Guardrails

- Catalog SHA-256: `83ceec611aaffc6cf8fe901c9f76965fd4753e01ecba768240fd2f92aadfb356`
- Bug-specific condition count: `0`
- Held-out checker modifications: `0`
- Results are relative to the loaded protocol, binding, path model, and assumptions; no absolute SAFE claim is made.


## Screening Rejections

| Operation family | Status | Reason |
|---|---|---|
| runtime-relocation-merge | `V0.3_PROTOCOL_CANDIDATE` | The binding introduces relocation_failure and a preexisting attachment lifecycle outside the frozen RAS v0.2 recovery-operation footprint. |