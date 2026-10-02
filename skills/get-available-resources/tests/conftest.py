"""Make the skill's scripts importable for the skill-local pytest suite.

`scripts/` is a flat script folder (no installed distribution), so the tests put
it on sys.path, the same way `python scripts/detect_resources.py` does.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS_DIR = HERE.parent / "scripts"
for path in (SCRIPTS_DIR, HERE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
