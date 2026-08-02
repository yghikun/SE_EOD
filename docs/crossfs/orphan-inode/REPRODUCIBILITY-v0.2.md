# OIDS v0.2 Reproducibility

Run commands from the repository root with Python 3.9 or newer.

## Historical freeze

Phase 15 records a historical pre-source-reveal state. Because the JFS sources
are now present, do not rerun the Phase 15 runner and interpret its current-source
check as the historical result. Verify the frozen files instead:

```powershell
Get-FileHash -Algorithm SHA256 configs/evaluation/oids-phase15-jfs-heldout-preregistration-v0.1.json
Get-FileHash -Algorithm SHA256 outputs/fmpca-oids-phase15-v0.1/summary.json
```

Expected hashes are `938f31a9381c8998d3f0aabdc314c38ca775626df559580aff61b1fce4076595`
and `f59395580b5c1dc520458b7e8d67455bf1d448e15f6fd534b79c0923888f5334`.

## Re-executable evaluation

```powershell
python -m src.fmpca.orphan_phase16 --manifest configs/evaluation/oids-phase16-jfs-heldout-v0.1.json --json-out outputs/fmpca-oids-phase16-v0.1/summary.json --markdown-out outputs/fmpca-oids-phase16-v0.1/report.md
python -m src.fmpca.orphan_phase17 --manifest configs/evaluation/oids-phase17-jfs-result-freeze-v0.1.json --json-out outputs/fmpca-oids-phase17-v0.1/summary.json --markdown-out outputs/fmpca-oids-phase17-v0.1/report.md
python -m src.fmpca.orphan_phase18 --manifest configs/evaluation/oids-final-release-v0.2.json --json-out outputs/fmpca-oids-final-v0.2/summary.json --markdown-out outputs/fmpca-oids-final-v0.2/report.md
python -m pytest -q
python -m compileall -q src tests
git diff --check
```

All JSON files under `configs`, `outputs`, and `tests/fixtures` must parse. The
Phase 16 runner independently verifies every acquired JFS source hash and every
registered line-level evidence anchor.
