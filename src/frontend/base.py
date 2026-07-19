"""Frontend interface used by the analysis pipeline."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from .model import TranslationUnitIR


class Frontend(ABC):
    """Convert one source translation unit into the shared frontend IR."""

    name: str

    @abstractmethod
    def parse(self, path: str | Path) -> TranslationUnitIR:
        raise NotImplementedError
