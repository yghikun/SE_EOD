# Paper Roadmap: Failure-Path Filesystem Metadata Residual Analysis

Updated: 2026-07-24

## Thesis

Linux filesystem error paths can leave residual filesystem metadata effects
when a failure occurs after partial metadata mutation. The method computes the
metadata effects reaching a failure point, the effects cancelled or protected
on the error path, and the residual effects that still reach an error exit.

## Main Contribution

The core contribution is not a four-state window model. It is:

```text
Failure-Path Filesystem Metadata Residual Analysis
```

with four technical pieces:

```text
1. automatic filesystem metadata effect extraction
2. identity-aware metadata effect cancellation
3. failure-anchored bidirectional slicing
4. explicit protection and transfer recognition
```

The lightweight state labels are implementation support:

```text
EXPOSED | PROTECTED | CLOSED | UNKNOWN
```

They are not presented as a complete typestate or protocol EFSM.

## Formal Core

For each failure point `f`:

```text
E_f = filesystem metadata effects reaching f
C_f = cancellation or compensation effects on the error path
T_f = transaction, journal, orphan, recovery, or deferred protection effects

R_f = Normalize(E_f (+) C_f) - T_f
```

Report a candidate only when:

```text
R_f != empty
and R_f affects STRUCTURAL, ACCOUNTING, or RECOVERY metadata
and the path reaches an error exit
and the residual is not UNKNOWN
```

## Research Questions

```text
RQ1: How many curated filesystem metadata findings are expressible as residuals?
RQ2: How much ordinary cleanup noise does the metadata scope gate remove?
RQ3: How accurately can identity-aware cancellation compute C_f?
RQ4: How often are residuals resolved as protected rather than exposed?
RQ5: How much configuration is avoided compared with MOCC-SE?
```

## Method Pipeline

```text
source
  -> FunctionIR and CFG
  -> filesystem metadata scope gate
  -> failure point discovery
  -> backward slice for E_f
  -> forward error-path slice for C_f and T_f
  -> identity-aware cancellation
  -> residual normalization
  -> error-exit verification
```

## Relationship to Prior Internal Designs

```text
MOCC-SE:
  Too heavy. It modeled protocol EFSMs, owner/handler transfer, accounting
  obligations, and rule registries.

MetaWindow:
  Good intuition, but the four-state model alone looks like domain-specific
  typestate.

Residual analysis:
  Keeps the filesystem metadata scope, removes full protocols, and centers the
  algorithm on failure-path residual computation.
```

## Expected Evaluation

Development examples:

```text
#7, #16, #17, #18, maybe #12
```

Outcome-residual extension:

```text
#1, #2, #5, #8, #13, maybe #4 and #15
```

Out of scope:

```text
#3, #6, #9, #10, #11, #14
```

Report:

```text
residual-expressible curated findings
out-of-scope filtering decisions
EXPOSED / PROTECTED / CLOSED / UNKNOWN distribution
candidate precision after manual review
configuration size compared with MOCC-SE
```

## Paper Non-Claims

Do not claim:

```text
complete Linux C soundness
complete crash consistency
automatic bug confirmation
coverage of ordinary resource leaks
first-ever error-path checker
full replacement for filesystem semantic validation
```
