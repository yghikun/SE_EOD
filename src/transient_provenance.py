"""Compatibility entry point for transient provenance semantics."""

from .semantics.transient_provenance import *
from .semantics import transient_provenance as _impl


def __getattr__(name: str):
    return getattr(_impl, name)
