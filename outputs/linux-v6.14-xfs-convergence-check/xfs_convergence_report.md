# XFS Function-Summary Convergence Diagnosis

> MOCC-SE migration note (2026-07-21): this engineering diagnosis validates the shared interprocedural summary infrastructure. It does not evaluate the MOCC-SE protocol rules.

Date: 2026-07-14

## Root cause

The XFS summary fixed-point loop was not diverging in the call graph. During
conditional-effect propagation, `_map_condition_to_caller()` wrapped every
actual argument in parentheses. Parameter forwarding therefore changed an
equivalent condition such as `arg0->b_flags & XBF_ASYNC` into a new string such
as `(arg0)->b_flags & XBF_ASYNC` at every wrapper level. The effect identity
includes the condition string, so each round incorrectly added another effect.

The pre-fix diagnostic showed 100 new effects per iteration from iteration 6
through iteration 50. The total effect count grew from 458 seeded effects to
at least 5,657, and the loop reached its 50-iteration limit.

## Fix

Parameter-to-parameter forwarding now substitutes the parameter directly and
only parenthesizes non-parameter expressions. This keeps equivalent conditions
in a canonical form while preserving precedence for expressions that need
parentheses.

Changed code:

- `src/function_summary.py::_map_condition_to_caller`
- `tests/test_interprocedural.py::test_conditional_summary_normalizes_parameter_forwarding_at_fixed_point`

## Validation

The same Linux v6.14 XFS source and resource map were rerun after the fix:

| Metric | Before | After |
|---|---:|---:|
| Summary iterations | 50 | 4 |
| Summary converged | false | true |
| Summary effects | continuously growing | 859 |
| Candidates | 69 | 69 |
| LLM tasks | 69 | 69 |
| Runtime (s) | 27.898 | 15.640 |

The old and new ranked candidate JSONL files contain the same 69 candidate IDs
and identical rows. Full regression tests pass: `110 passed`.

## Remaining bounded limitation

The CFG analysis still reports one unresolved indirect call:

- Function: `xfs_getfsmap`
- Source: `fs/xfs/xfs_fsmap.c`
- Approximate line: 1097
- Target expression: `fn`

This is a separate conservative function-pointer resolution limitation. It
does not prevent function-summary convergence and should be reported in the
threats-to-validity/diagnostics section until modeled or explicitly bounded.
