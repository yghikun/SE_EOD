"""Shared cleanup-call matching for resource lifetimes."""

from __future__ import annotations

from typing import Any

from .parser import call_name_and_args
from .resource_expr import same_resource_expr


def resource_var(resource: Any) -> str:
    if isinstance(resource, dict):
        return str(resource.get("var", "") or "")
    return str(getattr(resource, "var", "") or "")


def resource_kind(resource: Any) -> str:
    if isinstance(resource, dict):
        return str(
            resource.get("resource_kind") or resource.get("resource_type") or ""
        )
    return str(getattr(resource, "resource_kind", "") or getattr(resource, "resource_type", "") or "")


def release_functions(resource: Any) -> list[str]:
    if isinstance(resource, dict):
        releases = resource.get("release_functions", [])
    else:
        releases = getattr(resource, "release_functions", [])
    if isinstance(releases, str):
        releases = [releases]
    return [str(item) for item in releases]


def release_arg_index(resource: Any) -> int:
    if isinstance(resource, dict):
        value = resource.get("release_arg_index", 0)
    else:
        value = getattr(resource, "release_arg_index", 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def release_arg_requires_address(resource: Any) -> bool:
    if isinstance(resource, dict):
        return bool(resource.get("release_arg_requires_address", False))
    return bool(getattr(resource, "release_arg_requires_address", False))


def resource_aggregate_id(resource: Any) -> str:
    if isinstance(resource, dict):
        return str(resource.get("aggregate_id", "") or "")
    return str(getattr(resource, "aggregate_id", "") or "")


def resource_multiplicity(resource: Any) -> str:
    if isinstance(resource, dict):
        return str(resource.get("multiplicity", "one") or "one")
    return str(getattr(resource, "multiplicity", "one") or "one")


def resource_release_cardinality(resource: Any) -> str:
    if isinstance(resource, dict):
        return str(resource.get("release_cardinality", "one") or "one")
    return str(getattr(resource, "release_cardinality", "one") or "one")


def cleanup_call_releases_resource(call_expr: str, resource: Any) -> bool:
    name, args = call_name_and_args(call_expr)
    return call_releases_resource(name, args, resource)


def missing_cleanup_matches_resource(
    missing_action: str, missing_arg: str, resource: Any
) -> bool:
    return _action_releases_resource(missing_action, [missing_arg], resource)


def call_releases_resource(name: str, args: list[str], resource: Any) -> bool:
    return _action_releases_resource(name, args, resource)


def _action_releases_resource(name: str, args: list[str], resource: Any) -> bool:
    releases = release_functions(resource)
    var = resource_var(resource)
    kind = resource_kind(resource)
    first_arg = args[0] if args else ""
    arg_index = release_arg_index(resource)

    def matches(target: str) -> bool:
        if release_arg_requires_address(resource):
            target = target.strip()
            while target.startswith("&"):
                target = target[1:].strip()
        aggregate = resource_aggregate_id(resource)
        if (
            resource_multiplicity(resource) == "many"
            and resource_release_cardinality(resource) == "all"
            and aggregate
        ):
            return same_resource_expr(target, aggregate)
        return same_resource_expr(target, var) or bool(
            aggregate and same_resource_expr(target, aggregate)
        )

    if name == "kmem_cache_free" and "kmem_cache_free" in releases:
        target = args[1] if len(args) >= 2 else first_arg
        return matches(target)

    if name in releases:
        target = args[arg_index] if len(args) > arg_index else first_arg
        if matches(target):
            return True

    if name in releases and matches(first_arg):
        return True

    if name == "put_bh" and "brelse" in releases:
        return same_resource_expr(first_arg, var)

    if name == "kobject_put" and "kfree" in releases and kind == "memory":
        return same_resource_expr(first_arg, var)

    if name == "ext4_fc_free" and "kfree" in releases and kind == "memory":
        return _ext4_fc_free_releases(var)

    return False


def _ext4_fc_free_releases(var: str) -> bool:
    return (
        same_resource_expr(var, "fc->fs_private")
        or var in {"s_ctx", "ctx"}
        or var.endswith("->fs_private")
        or var.endswith(".fs_private")
    )
