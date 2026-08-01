# E2 Held-out Freeze Manifest v0.2

Freeze date: 2026-07-31.

E2 is an executable eligibility gate over a post-freeze candidate. It reuses
Domain Protocol Catalog v0.2 without changing protocol phases, invariants,
obligations, deadlines or AcceptP. The candidate's binding is intentionally
rejected because it introduces a preexisting-attachment runtime lifecycle that
is outside the frozen RAS v0.2 semantic footprint.

The machine-readable freeze is `configs/freeze/heldout-semantic-freeze-e2-v0.2.json`. It locks the protocol/catalog, held-out screening and dossier, binding, fixtures, evaluation manifest, extension and semantic kernel. Git artifacts additionally lock both full commit IDs and `fs/btrfs/relocation.c` blob object IDs.

Interpretation boundary:

- The real Bug/fixed revisions supply a confirmed, provenance-locked v0.3
  candidate and preserve the exact missing/present repair evidence.
- Zero operation families are admitted to the v0.2 held-out set.
- Multiple related relocation commits are not counted as additional independent
  families.
- No E2 observation may be used to edit v0.2 AcceptP while retaining held-out
  status.
