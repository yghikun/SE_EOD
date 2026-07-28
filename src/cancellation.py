"""Compatibility entry point for cancellation semantics."""

from .semantics.cancellation import *
from .semantics import cancellation as _impl


def __getattr__(name: str):
    return getattr(_impl, name)
