"""Audit resource-map contracts for migration and precision risks."""

from __future__ import annotations

from typing import Any


def audit_resource_map(resource_map: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    explicit_acquire_contracts = 0
    compatibility_default_acquires = 0
    acquire_functions = resource_map.get("acquire_functions", {})
    if not isinstance(acquire_functions, dict):
        return {
            "warnings": ["acquire_functions must be an object"],
            "explicit_acquire_contracts": 0,
            "compatibility_default_acquires": 0,
            "release_all_without_aggregate_identity": 0,
            "reviewed_all_effects_without_aggregate_identity": 0,
            "membership_relation_without_membership_api": 0,
        }

    release_all_without_aggregate_identity = 0
    membership_relation_without_membership_api = 0
    has_membership_api = bool(resource_map.get("resource_membership_functions"))
    for name, cfg in sorted(acquire_functions.items()):
        if not isinstance(cfg, dict):
            warnings.append(f"acquire {name}: config must be an object")
            continue
        has_explicit_contract = bool(
            str(cfg.get("validity_guard", "")).strip()
            or str(cfg.get("failed_check", "")).strip()
            or str(cfg.get("acquire_success_guard", "")).strip()
            or "direct_resource_arg" in cfg
        )
        if has_explicit_contract:
            explicit_acquire_contracts += 1
        else:
            compatibility_default_acquires += 1
            warnings.append(
                f"acquire {name}: missing explicit validity/failed-check contract"
            )
        if str(cfg.get("release_cardinality", "one")).strip() == "all":
            has_aggregate_identity = bool(
                str(cfg.get("aggregate_id", "")).strip()
                or str(cfg.get("container_owner", "")).strip()
                or str(cfg.get("membership_relation", "")).strip()
            )
            if not has_aggregate_identity:
                release_all_without_aggregate_identity += 1
                warnings.append(
                    f"acquire {name}: release_cardinality=all lacks aggregate identity"
                )
        if str(cfg.get("membership_relation", "")).strip() and not has_membership_api:
            membership_relation_without_membership_api += 1
            warnings.append(
                f"acquire {name}: membership_relation has no membership API contract"
            )

    reviewed_all_effects_without_aggregate_identity = 0
    raw_seeds = resource_map.get("interprocedural_effect_seeds", {})
    if isinstance(raw_seeds, dict):
        for function, raw_effects in sorted(raw_seeds.items()):
            effects = raw_effects if isinstance(raw_effects, list) else [raw_effects]
            for effect in effects:
                if not isinstance(effect, dict):
                    continue
                if str(effect.get("effect_cardinality", "one")).strip() != "all":
                    continue
                has_aggregate_identity = bool(
                    str(effect.get("aggregate_id", "")).strip()
                    or str(effect.get("container_owner", "")).strip()
                    or str(effect.get("membership_relation", "")).strip()
                )
                if not has_aggregate_identity:
                    reviewed_all_effects_without_aggregate_identity += 1
                    warnings.append(
                        f"effect seed {function}: effect_cardinality=all lacks aggregate identity"
                    )

    return {
        "warnings": warnings,
        "explicit_acquire_contracts": explicit_acquire_contracts,
        "compatibility_default_acquires": compatibility_default_acquires,
        "release_all_without_aggregate_identity": release_all_without_aggregate_identity,
        "reviewed_all_effects_without_aggregate_identity": reviewed_all_effects_without_aggregate_identity,
        "membership_relation_without_membership_api": membership_relation_without_membership_api,
    }
