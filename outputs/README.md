# Output Layout

`outputs/` contains two different classes of artifacts. They must not be mixed
in evaluation claims.

## Active MOCC-SE evidence

```text
confirmed_bugs.md
mocc-protocol-a-v1/
mocc-protocol-b-v1/
mocc-protocol-c-v1/
mocc-discovery-v2/
mocc-finding-review-v1/
```

- `mocc-protocol-*-v1/` contains versioned Protocol A/B/C development witnesses.
- `mocc-discovery-v2/` contains the M11 fresh review report, source triage and
  current ext4 helper validation/patch proposal.
- `mocc-finding-review-v1/` contains the M8-M10 development review, version
  matrix, repair evidence, bug-hunt report and confirmed-bug linkage.
- `confirmed_bugs.md` records manually/history/dynamically supported findings
  and their distinct submitted/reviewed/accepted states.

The directory name `mocc-discovery-v2` is an experiment-generation label, not
the JSON schema version. Retained reports may use discovery schema v2. Newly
generated reports use schema v3, which adds a separate operation
`control_trace` to candidates and analysis-unknown records; historical reports
are not rewritten in place.

These artifacts are development and review evidence, not a frozen independent
benchmark. `DISCOVERY_REVIEW` is not equivalent to `PROTOCOL_CANDIDATE` or a
confirmed bug.

## Historical development evidence

```text
mocc-discovery-v1/
mocc-discovery-v1-linux-v6.8.json
mocc-discovery-v1-linux-v6.14.json
mocc-discovery-v1-linux-v7.1.json
experiment-v1.3.3/
linux-v6.8/
linux-v7.1/
f2fs_maintainer_feedback.md
```

`mocc-discovery-v1*` records the exact-entry M7 development stage that preceded
fresh discovery. `experiment-v1.3.3` and the versioned `linux-*` directories are
legacy SE-EOD resource/error-path/ranking outputs. Their runtime modules and
experiment scripts have been removed, so they are retained only to interpret
historical bug provenance and development decisions.

Historical ranking scores, LLM verdicts and manually promoted subsets are not
ground truth and cannot be used to report current MOCC-SE precision or recall.

## Removed outputs

The following superseded directories were removed on 2026-07-22:

```text
experiment-v1.3/
experiment-v1.3.1/
experiment-v1.3.2/
experiment-v1.4/
experiment-v1.4-baseline/
experiment-v1.5-cfg/
linux-v6.14-bug-check/
linux-v6.14-xfs-convergence-check/
```

Do not restore these generated files unless a new, explicit research scope
requires the legacy SE-EOD pipeline.
