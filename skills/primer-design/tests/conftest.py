"""Make `primer_design` importable for the skill-local pytest suite.

The package lives under ../src and has no installed distribution, so the
tests put that folder on sys.path (same pattern as web-scraping/tests).
"""
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
