# Archived SE-EOD Benchmark Pilot

This directory contains the old ext4 v6.8 resource/error-path pilot and its
review artifacts. It is retained as development provenance only.

The scripts that created, evaluated and compared this pilot were removed when
the repository was reduced to the MOCC-SE protocol/EFSM core. Therefore:

- these files are not a reproducible current benchmark;
- ranking scores and LLM outputs are not ground truth;
- the labels participated in earlier development and cannot be reused as an
  independent MOCC-SE test set;
- no precision/recall claim for the current analyzer may be derived from these
  files.

A future MOCC-SE evaluation must freeze protocol definitions first, collect a
separate validation/test set, use independent reviewers, report the three
violation classes separately, and provide new versioned evaluation tooling.
