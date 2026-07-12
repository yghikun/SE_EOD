# Benchmark Pilot

This directory contains independently reviewed benchmark data. LLM outputs and
ranking scores are not ground truth. A reviewer must inspect the source path,
resource lifetime, cleanup path, and current upstream history before assigning a
label.

## Create the ext4 v6.8 pilot

From the repository root:

```bash
python scripts/create_benchmark_pilot.py \
  --input outputs/linux-v6.8/ext4/ranked_candidates.jsonl \
  --output benchmark/ext4-v6.8-pilot.jsonl \
  --manifest-out benchmark/ext4-v6.8-pilot-manifest.jsonl \
  --version v6.8 \
  --filesystem ext4 \
  --per-bucket 10
```

The script divides the ranked input into top/middle/low thirds and selects 10
rows from each third, cycling through candidate types where possible. The pilot
file is blinded to ranking score and LLM verdict. The manifest is intentionally
non-blinded and must not be used as the annotation answer key.

## Annotation labels

Each JSONL row contains an `annotation` object. Fill these fields without
deleting the source fields:

- `verdict`: `true_bug`, `false_positive`, or `uncertain`.
- `confidence`: `high`, `medium`, or `low`.
- `reason`: concise explanation tied to source lines and control flow.
- `evidence`: list of patch, upstream, reproduction, or source references.
- `upstream_status`: `unknown`, `not_found`, `historical_fixed`,
  `patch_submitted`, `upstream_accepted`, or `duplicate`.
- `reviewer`: stable reviewer identifier.
- `reviewed_at`: ISO-8601 timestamp.

Do not use DeepSeek/Codex verdicts as labels. Keep uncertain cases uncertain
until an independent reviewer or adjudicator resolves them.

## Review protocol

1. Inspect the complete function and every relevant error exit.
2. Confirm whether the resource was successfully acquired on this path.
3. Check wrappers, ownership transfer, aliases, and caller expectations.
4. Search the latest upstream source and patch history.
5. Record the exact evidence and leave the verdict as `uncertain` when evidence
   is insufficient.

The first pilot is a calibration set. After annotation, calculate Precision@10,
Precision@20, overall precision, and the distribution of true/false/uncertain
labels before changing analysis rules.

## First-pass labels

The initial source review is stored separately in
`benchmark/ext4-v6.8-pilot-labels.jsonl`. It is not an independent gold label
set: it is a first reviewer pass that must be adjudicated or compared with a
second reviewer before it is used as the final test split.

Evaluate the pass with:

```bash
python scripts/evaluate_benchmark.py \
  --pilot benchmark/ext4-v6.8-pilot.jsonl \
  --labels benchmark/ext4-v6.8-pilot-labels.jsonl \
  --json-out benchmark/ext4-v6.8-pilot-evaluation.json \
  --report-out benchmark/ext4-v6.8-pilot-evaluation.md
```

Prepare a blinded second-review file:

```bash
python scripts/prepare_benchmark_review.py \
  --pilot benchmark/ext4-v6.8-pilot.jsonl \
  --output benchmark/ext4-v6.8-pilot-reviewer2-todo.jsonl \
  --reviewer reviewer_2
```

After all second-review verdicts are filled, compare both passes:

```bash
python scripts/compare_benchmark_reviews.py \
  --first benchmark/ext4-v6.8-pilot-labels.jsonl \
  --second benchmark/ext4-v6.8-pilot-reviewer2-todo.jsonl \
  --output benchmark/ext4-v6.8-pilot-review-comparison.json
```

Analyze first-pass error causes for development planning:

```bash
python scripts/analyze_benchmark_taxonomy.py \
  --labels benchmark/ext4-v6.8-pilot-labels.jsonl \
  --taxonomy benchmark/ext4-v6.8-pilot-taxonomy.jsonl \
  --json-out benchmark/ext4-v6.8-pilot-taxonomy.json \
  --report-out benchmark/ext4-v6.8-pilot-taxonomy.md
```
