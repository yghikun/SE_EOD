# Benchmark Evaluation

> This report evaluates one annotation pass. It is not an independent gold-set result until a second reviewer and adjudication are complete.

- Samples: 30
- Overall precision: 0.3667

## Verdicts

| Verdict | Count |
|---|---:|
| `false_positive` | 19 |
| `true_bug` | 11 |

## Precision at K

| K | Precision |
|---:|---:|
| 10 | 0.7 |
| 20 | 0.55 |

## Rank Buckets

| Bucket | Count | Precision | Verdicts |
|---|---:|---:|---|
| top | 10 | 0.7 | false_positive=3, true_bug=7 |
| middle | 10 | 0.4 | false_positive=6, true_bug=4 |
| low | 10 | 0.0 | false_positive=10 |

## Candidate Types

| Type | Count | Precision | Verdicts |
|---|---:|---:|---|
| `error_swallowed` | 21 | 0.4286 | false_positive=12, true_bug=9 |
| `missing_cleanup` | 8 | 0.25 | false_positive=6, true_bug=2 |
| `partial_cleanup` | 1 | 0.0 | false_positive=1 |
