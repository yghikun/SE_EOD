"""Compatibility entry point for semantic blocker impact APIs."""

from .evaluation.semantic_blocker_impact import *
from .evaluation import semantic_blocker_impact as _impl


def __getattr__(name: str):
    return getattr(_impl, name)
