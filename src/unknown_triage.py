"""Compatibility entry point for UNKNOWN triage APIs."""

from .evaluation.unknown_triage import *
from .evaluation import unknown_triage as _impl


def __getattr__(name: str):
    return getattr(_impl, name)
