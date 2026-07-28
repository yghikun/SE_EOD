"""Compatibility entry point for candidate review oracle APIs."""

from .evaluation.candidate_review_oracle import *
from .evaluation import candidate_review_oracle as _impl


def __getattr__(name: str):
    return getattr(_impl, name)
