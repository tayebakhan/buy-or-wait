"""Submission entry point.

Run from the repository root:
    python code/main.py --dataset dataset --output output.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buy_or_wait.batch import main


if __name__ == "__main__":
    raise SystemExit(main())
