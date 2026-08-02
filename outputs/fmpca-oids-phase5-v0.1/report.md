# OIDS Phase 5 ext4 Interprocedural Contracts

Manifest: `configs/evaluation/oids-phase5-ext4-contracts-v0.1.json`

Universal all-path closure: `False`
Failstop-profile closure: `False`

| Stage | Summary | Configuration | Status | Outcome |
|---|---|---|---|---|
| registration | `EXT4-RC-1` | `ALL` | `CLOSED` | no new persistent registration required |
| registration | `EXT4-RC-2` | `ALL` | `CLOSED` | legacy orphan-list registration is selected |
| registration | `EXT4-RC-3` | `ERRORS_RO_OR_FAILSTOP` | `CLOSED` | journal abort or non-RW failstop prevents successful RW commit |
| registration | `EXT4-RC-4` | `ERRORS_CONT` | `UNSAFE` | handle is marked aborted, but jbd2 stop does not abort the journal; commit is not excluded |
| settlement | `EXT4-SC-1` | `ALL` | `CLOSED` | registry removal, inode free, and journal stop share the eviction handle |
| settlement | `EXT4-SC-2` | `ERRORS_RO_OR_FAILSTOP` | `CLOSED` | journal abort or non-RW failstop prevents removal-only commit |
| settlement | `EXT4-SC-3` | `ERRORS_CONT` | `UNSAFE` | partial registry removal may be journaled while inode free is skipped; commit is not excluded |
| recovery | `EXT4-CC-1` | `ALL` | `NOT_APPLICABLE` | no OIDS recovery instance is applicable |
| recovery | `EXT4-CC-2` | `ALL` | `CLOSED` | selected zero-link inode reaches iput-driven eviction before completion marker |
| recovery | `EXT4-CC-3` | `ERRORS_RO_OR_FAILSTOP` | `BLOCKED` | error handling is visible, but journal-flush-to-mount-failure propagation remains unclosed |
| recovery | `EXT4-CC-4` | `ERRORS_CONT` | `UNSAFE` | void cleanup can return and fill_super can reach recovery completion and mount return |

## Blockers

- `EXT4_ERRORS_CONT_REGISTRATION_COMMIT_NOT_EXCLUDED`
- `EXT4_ERRORS_CONT_REMOVAL_ONLY_COMMIT_NOT_EXCLUDED`
- `EXT4_RECOVERY_FAILSTOP_FLUSH_CONTRACT_NOT_LOCKED`
- `EXT4_ERRORS_CONT_RECOVERY_EXPOSURE_NOT_EXCLUDED`

The ext4 OIDS helper audit closes fallback, successful same-handle settlement, and non-continuing error-policy containment. Linux v6.14 JBD2 proves that handle abort is not journal abort. ERRORS_CONT therefore retains registration, removal-only settlement, and recovery-exposure risks; failstop recovery also awaits a locked journal-flush-to-mount-failure contract. Universal ext4 all-path closure and COMMON freeze remain false.
