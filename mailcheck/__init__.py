"""mailcheck: a deterministic style checker for Korean academic mail drafts (no LLM, no network)."""
from .config import Config, load_config
from .style import StyleContext, StyleReport, Violation, amounts, check

__all__ = ["Config", "load_config", "StyleContext", "StyleReport", "Violation", "amounts", "check"]
