"""Compatibility entry point for failure-domain primitive semantics."""

from .semantics.failure_domain_primitives import *
from .semantics import failure_domain_primitives as _impl


def __getattr__(name: str):
    return getattr(_impl, name)
