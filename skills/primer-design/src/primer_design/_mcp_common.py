"""Shared state for the MCP tool modules: stderr logging and the designer singletons.

The server speaks JSON-RPC on stdout, so logging must go to stderr only and no
module may print(). Importing this module configures logging once (the same
configuration the single-file server had at import time).
"""

from __future__ import annotations

import logging
import sys

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [primer-design] %(levelname)s: %(message)s",
)
logger = logging.getLogger("primer-design")

from .colony_pcr_mode import ColonyPCRDesigner  # noqa: E402
from .expression_analyzer import ExpressionAnalyzer  # noqa: E402
from .restriction_cloning_mode import RestrictionCloningDesigner  # noqa: E402

# Singleton instances shared by every tool module.
_re_designer = RestrictionCloningDesigner()
_colony_designer = ColonyPCRDesigner()
_expression_analyzer = ExpressionAnalyzer()
