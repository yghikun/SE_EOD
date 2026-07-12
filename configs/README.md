# Configuration Layout

Each filesystem has five configuration layers. They serve different stages and
must not be merged merely because some API names overlap.

| Layer | Files | Purpose |
|---|---|---|
| Static resource state | `*_resource_map.json` | Acquisition, release, scope cleanup, callee consumption, and ownership facts used while extracting paths. |
| Ranking protocols | `*_resource_protocols/*.json` | Evidence descriptions used after candidate generation for ranking and explanations. |
| Wrapper summaries | `*_wrapper_summaries.json` | Conservative wrapper/alias evidence. The ext4 canonical file retains the historical name `wrapper_summaries.json`. |
| Reviewed exceptions | `*_review_false_positives.json` | Source-reviewed false-positive contracts and confirmed-bug exceptions. |
| Historical fixes | `*_historical_fixes.json` | Reviewed cross-version source fixes used only for E3 ranking evidence. |

Reviewed exception files contain two rule groups:

- `rules`: stable function-level contracts inherited from earlier review rounds.
- `path_rules`: narrowly scoped contracts that require exact `path_id` matching.

Confirmed bug exceptions take precedence over false-positive rules. New review
rules belong in the filesystem's canonical review file; do not create files
named after experiment versions. Experiment provenance belongs in `rule_id`,
`review_source`, reports, and run manifests.

Historical-fix records do not create or suppress candidates. They require an
exact file, function, candidate type, and affected-line match, then attach the
fixed version and changed source lines to an already generated candidate.

The experiment runner resolves these files in
`scripts/run_experiment_v1_3.py::config_paths`. Protocol directories are loaded
dynamically, so individual protocol JSON files do not need literal filename
references in Python source.
