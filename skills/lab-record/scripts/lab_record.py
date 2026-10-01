#!/usr/bin/env python3
"""lab-record entry point; implementation lives in lab_record_lib/ (next to this file)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lab_record_lib.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
