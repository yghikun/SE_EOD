# Output Layout: SE-EOD Baselines and MOCC-SE Evidence

`outputs/` keeps final or currently useful SE-EOD artifacts that serve as
historical baselines, motivating examples, and regression evidence for MOCC-SE.
They are not an independent MOCC-SE test set. Results are grouped
first by Linux version and then by filesystem, so scans from different source
snapshots cannot overwrite or mix with each other.

## Root

- `confirmed_bugs.md`: all confirmed bugs across filesystems.
- `f2fs_maintainer_feedback.md`: upstream review outcomes for the July 2026
  F2FS folio-lifetime submissions, including withdrawn and pending findings.
- `linux-v6.8/`: results produced from `linux-sources/linux-v6.8-fs`.
- `linux-v7.1/`: results produced from `linux-sources/linux-v7.1-fs`.
- `mocc-protocol-a-v1/`: versioned Protocol A replay/recovery JSON and witness.
- `mocc-protocol-b-v1/`: versioned Protocol B device/topology rollback JSON and witness.
- `mocc-protocol-c-v1/`: versioned Protocol C activation/accounting JSON and witness.
- `mocc-discovery-v1-linux-v6.8.json`: M7 development discovery scan across
  Linux v6.8 `fs/` for Protocol A/B/C. It is not a frozen benchmark.
- `mocc-discovery-v1/`: notes for interpreting the M7 discovery output.
- `mocc-finding-review-v1/`: M8-M10 source review, triage, cross-version
  matrix, repair evidence, development bug-hunt report, and confirmed-bug
  linkage. These artifacts are development evidence, not a frozen benchmark.

## Linux v6.8

### ext4

- `error_paths.csv`: extracted ext4 error paths.
- `suspicious_candidates.csv`: ext4 static candidates.
- `ranked_candidates.jsonl`: ext4 ranked candidates with evidence.
- `deepseek_true_candidates.jsonl`: ext4 LLM true-candidate subset.
- `manual_review_labels.jsonl`: ext4 review-feedback labels.
- `manual_bug_candidates_to_verify.md`: ext4 promoted candidates and review notes.

### btrfs

- `error_paths.csv`: extracted btrfs error paths.
- `suspicious_candidates.csv`: btrfs static candidates.
- `ranked_candidates.jsonl`: btrfs ranked candidates with evidence.
- `candidates_with_evidence.csv`: btrfs CSV evidence summary.
- `deepseek_true_candidates.jsonl`: btrfs LLM true-candidate subset.
- `deepseek_true_candidate_audit.md`: btrfs source-level audit notes.
- `recover_relocation_qemu_report.md`: btrfs relocation recovery fault-injection report.

### XFS

- `error_paths.csv`: extracted XFS error paths.
- `suspicious_candidates.csv`: XFS static candidates.
- `ranked_candidates.jsonl`: XFS ranked candidates with evidence.
- `candidates_with_evidence.csv`: XFS CSV evidence summary.
- `llm_review_tasks.jsonl`: XFS LLM review tasks.
- `deepseek_reviews.jsonl`: XFS DeepSeek review responses.
- `deepseek_true_candidates.jsonl`: XFS LLM true-candidate subset.

### F2FS

- `error_paths.csv`: extracted F2FS error paths.
- `suspicious_candidates.csv`: F2FS static candidates.
- `ranked_candidates.jsonl`: F2FS ranked candidates with evidence.
- `candidates_with_evidence.csv`: F2FS CSV evidence summary.
- `llm_review_tasks.jsonl`: F2FS LLM review tasks.
- `deepseek_reviews.jsonl`: F2FS DeepSeek review responses.
- `deepseek_true_candidates.jsonl`: F2FS LLM true-candidate subset.

## Linux v7.1

Use the same per-filesystem filenames under `outputs/linux-v7.1/<filesystem>/`.
Always pass explicit output paths when scanning this source version.
