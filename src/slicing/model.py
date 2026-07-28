"""Data models shared by residual slicing stages."""

from __future__ import annotations

from dataclasses import dataclass

from ..function_summary import ErrorExitPartition, LifecycleFact
from ..metadata_residual import MetadataEffect, OwnerTeardown, ResidualSlice, SourceSite


@dataclass(frozen=True)
class ResidualSlicingResult:
    function: str
    slices: tuple[ResidualSlice, ...]
    unknown_causes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "function": self.function,
            "slices": [item.to_dict() for item in self.slices],
            "unknown_causes": list(self.unknown_causes),
        }


@dataclass(frozen=True)
class _LocatedEffect:
    effect: MetadataEffect
    block_id: int | None


@dataclass(frozen=True)
class _ErrorPathReachability:
    reachable: set[int]
    must_execute: set[int]


@dataclass(frozen=True)
class _UnknownInfluence:
    cause: str
    site: SourceSite
    phase: str
    conditional_effects: tuple[MetadataEffect, ...] = ()


@dataclass(frozen=True)
class _SummaryApp:
    function_name: str
    block_id: int | None
    site: SourceSite
    opens: tuple[MetadataEffect, ...]
    cancels: tuple[MetadataEffect, ...]
    protects: tuple[MetadataEffect, ...]
    error_opens: tuple[MetadataEffect, ...]
    error_cancels: tuple[MetadataEffect, ...]
    error_protects: tuple[MetadataEffect, ...]
    unknown: bool
    unknown_causes: tuple[str, ...]
    failure_unknown: bool
    failure_unknown_causes: tuple[str, ...]
    failure_effects_complete: bool
    may_fail: bool
    has_ownership_transfer: bool
    lifecycle_facts: tuple[LifecycleFact, ...]
    owner_teardowns: tuple[OwnerTeardown, ...]
    error_exit_partitions: tuple[ErrorExitPartition, ...]
    error_partitions_exhaustive: bool

    @property
    def cancels_before_failure(self) -> tuple[MetadataEffect, ...]:
        return self.cancels

    @property
    def protects_before_failure(self) -> tuple[MetadataEffect, ...]:
        return self.protects
