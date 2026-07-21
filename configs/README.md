# Configuration Layout: SE-EOD Baseline and MOCC-SE Protocols

Each filesystem has five baseline configuration layers plus the planned MOCC-SE
metadata protocol layer. They serve different stages and
must not be merged merely because some API names overlap.

| Layer | Files | Purpose |
|---|---|---|
| Static resource state | `*_resource_map.json` | Acquisition, release, scope cleanup, callee consumption, and ownership facts used while extracting paths. |
| Ranking protocols | `*_resource_protocols/*.json` | Evidence descriptions used after candidate generation for ranking and explanations. |
| Wrapper summaries | `*_wrapper_summaries.json` | Conservative wrapper/alias evidence. The ext4 canonical file retains the historical name `wrapper_summaries.json`. |
| Reviewed exceptions | `*_review_false_positives.json` | Source-reviewed false-positive contracts and confirmed-bug exceptions. |
| Historical fixes | `*_historical_fixes.json` | Reviewed cross-version source fixes used only for E3 ranking evidence. |
| Metadata protocols (M0) | `metadata_protocols/*.json` | Strict schema v1 for operation phases, return contracts, effect ownership, compensations, handlers, accounting constraints, and legal exits. |

Metadata protocol files are semantic specifications, not ranking hints. They
must not be used to silently suppress a candidate. Each effect declares its
scope (`LOCAL`, `IN_MEMORY_GLOBAL`, `TRANSACTION_SCOPED`, `PERSISTENT`,
`RECOVERY_OWNED`, or `DEFERRED_OWNED`) so that an abort or recovery handler only
closes obligations it actually owns.

M0 is implemented by `src/metadata_protocol.py`. Its JSON loader rejects
unknown fields/enums, unstable or duplicate IDs, dangling references, invalid
phase/object ownership, ambiguous return contracts, and illegal handler scope.
These protocols are not yet loaded by `src/main.py`; event extraction and
candidate generation remain later milestones.

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

Reviewed static effects belong under `interprocedural_effect_seeds` in a
resource map. Summary schema v4 supports `resource`, `action`, `strength`,
`condition`, `exit_class`, `return_guard`, and `effect_cardinality`. Serialized
automatic effects also include `must_reason` so a `must` conclusion can be
audited. `exit_class` defaults to `any`, and `effect_cardinality` defaults to
`one`; use `all` only for a reviewed operation that discharges every abstract
instance.
An effect that consumes a resource only after a successful or failed call must
use `exit_class: success|error` plus an explicit guard such as
`return == 0` or `return < 0`; it must not be encoded as an unconditional
`must` effect.

Acquire entries should use `validity_guard` with `{var}` and `{return}`
placeholders, `failed_check`, or an explicit out-parameter
`acquire_success_guard`. Guards are bound to the created resource instance and
evaluated against CFG edge facts. For historical compatibility, an unconfigured
pointer acquire still receives `var != NULL` and an out-parameter acquire still
receives `return == 0`, but these are tagged `compatibility_default`: they can
recognize a definite failure edge and cannot prove definite success. Apparent
success remains `MAY_ACQUIRED` with `unresolved_acquire_validity`, and the run
diagnostics count inferred guards. Migrate resource maps to explicit contracts.

An acquire entry may set `release_cardinality` to `one`, `all`, or `unknown`.
The default is `one`. This is relevant when loop analysis has promoted the
resource to `multiplicity=many`; only a reviewed `all` release can definitely
discharge that obligation.

Legacy `resource_ownership_transfers` entries are hints only. They no longer
remove a held resource. A match produces `MAY_ACQUIRED` with
`unreviewed_ownership_transfer_hint`. A real ownership transfer must be encoded
as an exact interprocedural semantic effect with resource argument, action,
strength, condition, and any required return guard.

The experiment runner resolves these files in
`scripts/run_experiment_v1_3.py::config_paths`. Protocol directories are loaded
dynamically, so individual protocol JSON files do not need literal filename
references in Python source.
