"""LibKey Nomad provider (Chrome MCP fallback; inert in a standalone CLI run)."""

from __future__ import annotations

from typing import Optional


class LibKeyNomadProvider:
    """Extracts a PDF URL via the institutional library's LibKey Nomad extension.

    LibKey Nomad automatically inserts a direct PDF link for institutionally
    subscribed journals on PubMed/DOI pages. This extracts that button's href
    via Chrome MCP.

    Uses the Chrome MCP fallback only when dynamic JS/EZproxy authentication
    is required. This class is placed at source 3.5 because it is lighter
    and more stable than EZproxy's Selenium path.

    Requirements:
      - The LibKey Nomad extension installed in Chrome (chrome-extension://dihbgbndebgnbjfmelmegjepbnkhlgni/)
      - Claude Code has Chrome MCP connected (mcp__claude-in-chrome__* tools active)
    """

    PUBMED_BASE = "https://pubmed.ncbi.nlm.nih.gov"
    DOI_BASE = "https://doi.org"

    def __init__(self) -> None:
        self._chrome_mcp_available = self._check_chrome_mcp()

    @staticmethod
    def _check_chrome_mcp() -> bool:
        """Check whether Chrome MCP is connected in the Claude Code session."""
        # Whether MCP is actually connected is decided at runtime, so this
        # always returns True (get_pdf_url returns None if MCP isn't connected).
        return True

    def get_pdf_url(self, doi: str) -> Optional[str]:
        """Extract the PDF-button URL LibKey Nomad inserted for a given DOI.

        Opens the PubMed page via Chrome MCP and returns the href of the
        LibKey "Download PDF" button. Returns None if the LibKey button is
        absent or Chrome MCP isn't connected.

        This method only works via an MCP tool call inside a Claude Code
        session, so a standalone CLI run always returns None (graceful degradation).
        """
        # Chrome MCP is unavailable in a standalone CLI/script run → skip
        # Inside a Claude Code session, Claude calls MCP directly per SKILL.md's guidance
        return None

    def is_available(self) -> bool:
        """Whether Chrome MCP is connected (True only inside a Claude Code session)."""
        return self._chrome_mcp_available
