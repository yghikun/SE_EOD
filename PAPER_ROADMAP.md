# Paper Roadmap: Failure-Local Metadata Residual Analysis

Updated: 2026-07-23

## Thesis

Linux file-system error paths can leave residual metadata effects when a
software failure occurs after partial metadata mutation.  We propose a
failure-local residual analysis that computes the metadata effects reaching a
failure point, the effects cancelled or protected on the error path, and the
residual effects that still reach an error exit.

## Main Contribution

The core contribution is not a four-state window model.  It is:

```text
Failure-Local Metadata Residual Analysis
```

with three technical pieces:

```text
1. automatic metadata effect extraction
2. identity-aware metadata effect cancellation
3. failure-anchored bidirectional slicing
```

The lightweight state labels are implementation support:

```text
EXPOSED | PROTECTED | CLOSED | UNKNOWN
```

They are not presented as a complete typestate or protocol EFSM.

## Formal Core

For each failure point `f`:

```text
E_f = metadata effects reaching f
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
RQ1: How many curated metadata findings are expressible as residuals?
RQ2: How much ordinary cleanup noise does the metadata scope gate remove?
RQ3: How accurately can identity-aware cancellation compute C_f?
RQ4: How often are residuals resolved as protected rather than exposed?
RQ5: Does optional MDR evidence improve review quality or patch hints?
RQ6: How much configuration is avoided compared with MOCC-SE?
```

## Method Pipeline

```text
source
  -> FunctionIR and CFG
  -> metadata scope gate
  -> failure point discovery
  -> backward slice for E_f
  -> forward error-path slice for C_f and T_f
  -> identity-aware cancellation
  -> residual normalization
  -> error-exit verification
  -> optional MDR evidence
```

## Relationship to Prior Internal Designs

```text
MOCC-SE:
  Too heavy.  It modeled protocol EFSMs, owner/handler transfer, accounting
  obligations, and rule registries.

MDR:
  Useful as evidence, but too dependent on comparable sibling paths.

MetaWindow:
  Good intuition, but the four-state model alone looks like domain-specific
  typestate.

Residual analysis:
  Keeps the metadata scope, removes full protocols, and centers the algorithm
  on failure-local residual computation.
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
manual review time with and without MDR evidence
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
