"""Compatibility entry point for evaluation harness APIs."""

from .evaluation.harness import *
from .evaluation import harness as _impl


def __getattr__(name: str):
    return getattr(_impl, name)
