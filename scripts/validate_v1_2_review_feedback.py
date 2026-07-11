"""Compatibility entry point for SE-EOD v1.2 review-feedback reports."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_v1_2_manual import main


if __name__ == "__main__":
    raise SystemExit(main())
