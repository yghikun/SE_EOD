# Output Layout

`outputs/` keeps final or currently useful SE-EOD artifacts.  Files are grouped
by filesystem so new filesystem targets can be added without mixing results.

## Root

- `confirmed_bugs.md`: all confirmed bugs across filesystems.

## ext4

- `error_paths.csv`: extracted ext4 error paths.
- `suspicious_candidates.csv`: ext4 static candidates.
- `ranked_candidates.jsonl`: ext4 ranked candidates with evidence.
- `deepseek_true_candidates.jsonl`: ext4 LLM true-candidate subset.
- `manual_review_labels.jsonl`: ext4 review-feedback labels.
- `manual_bug_candidates_to_verify.md`: ext4 promoted candidates and review notes.

## btrfs

- `error_paths.csv`: extracted btrfs error paths.
- `suspicious_candidates.csv`: btrfs static candidates.
- `ranked_candidates.jsonl`: btrfs ranked candidates with evidence.
- `candidates_with_evidence.csv`: btrfs CSV evidence summary.
- `deepseek_true_candidates.jsonl`: btrfs LLM true-candidate subset.
- `deepseek_true_candidate_audit.md`: btrfs source-level audit notes.
- `recover_relocation_qemu_report.md`: btrfs relocation recovery fault-injection report.
