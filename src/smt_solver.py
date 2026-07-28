"""Compatibility entry point for residual constraint solving."""

from .semantics.smt_solver import *
from .semantics import smt_solver as _impl


def __getattr__(name: str):
    return getattr(_impl, name)
