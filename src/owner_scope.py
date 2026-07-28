"""Compatibility entry point for owner-scope semantics."""

from .semantics.owner_scope import *
from .semantics import owner_scope as _impl


def __getattr__(name: str):
    return getattr(_impl, name)
