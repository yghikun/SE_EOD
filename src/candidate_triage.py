"""Compatibility entry point for candidate triage APIs."""

from .evaluation.candidate_triage import *
from .evaluation import candidate_triage as _impl


def __getattr__(name: str):
    return getattr(_impl, name)
