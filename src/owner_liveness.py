"""Compatibility entry point for owner-liveness semantics."""

from .semantics.owner_liveness import *
from .semantics import owner_liveness as _impl


def __getattr__(name: str):
    return getattr(_impl, name)
