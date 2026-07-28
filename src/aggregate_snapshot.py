"""Compatibility entry point for aggregate snapshot semantics."""

from .semantics.aggregate_snapshot import *
from .semantics import aggregate_snapshot as _impl


def __getattr__(name: str):
    return getattr(_impl, name)
