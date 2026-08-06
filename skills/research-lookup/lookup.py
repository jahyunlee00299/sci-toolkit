#!/usr/bin/env python3
"""
Research Lookup Tool for Claude Code
Performs research queries using OpenAlex and PubMed (free, no API key required).
"""

import sys
from typing import Optional
from research_lookup import ResearchLookup


def format_response(result: dict) -> str:
    """Format the research result for display."""
    if not result["success"]:
        return f"Research lookup failed: {result['error']}"

    response = result["response"]
    citations = result.get("citations", [])

    output = f"""**Research Results**

**Query:** {result['query']}
**Backend:** {result['backend']}
**Timestamp:** {result['timestamp']}
**Total found:** {result.get('total_count', 'N/A')}

---

{response}

"""

    if citations:
        output += f"\n**Structured Citations ({len(citations)}):**\n\n"
        for i, cit in enumerate(citations, 1):
            title = cit.get("title", "Untitled")
            authors = cit.get("authors", "")
            year = cit.get("year", "")
            source = cit.get("source", "")
            doi = cit.get("doi", "")
            url = cit.get("url", "")
            cited_by = cit.get("cited_by_count", "")

            venue_tier = _detect_venue_tier(source)
            tier_str = f" [{venue_tier}]" if venue_tier else ""

            output += f"{i}. **{title}**{tier_str}\n"
            output += f"   {authors} ({year}) — *{source}*\n"

            if cited_by:
                output += f"   Cited by: {cited_by}\n"
            if doi:
                output += f"   DOI: https://doi.org/{doi}\n"
            elif url:
                output += f"   {url}\n"
            output += "\n"

    return output


def _detect_venue_tier(source_name: str) -> Optional[str]:
    """Detect venue tier from journal/source name."""
    if not source_name:
        return None

    name_lower = source_name.lower()

    tier1 = {
        "nature": "Tier 1", "science": "Tier 1", "cell": "Tier 1",
        "new england journal of medicine": "Tier 1", "nejm": "Tier 1",
        "the lancet": "Tier 1", "lancet": "Tier 1",
        "jama": "Tier 1", "pnas": "Tier 1",
        "proceedings of the national academy": "Tier 1",
    }

    tier2 = {
        "neurips": "Tier 2", "icml": "Tier 2", "iclr": "Tier 2",
        "blood": "Tier 2", "circulation": "Tier 2",
        "journal of clinical investigation": "Tier 2",
        "nature medicine": "Tier 1", "nature biotechnology": "Tier 1",
        "nature methods": "Tier 1", "nature genetics": "Tier 1",
    }

    for key, tier in tier1.items():
        if key in name_lower:
            return tier

    for key, tier in tier2.items():
        if key in name_lower:
            return tier

    return None


def main():
    """Main entry point for Claude Code tool."""
    if len(sys.argv) < 2:
        print("Error: No query provided")
        print("Usage: python lookup.py 'your research query here'")
        return 1

    query = " ".join(sys.argv[1:])

    try:
        research = ResearchLookup()
        print(f"Researching: {query}")
        result = research.lookup(query)
        formatted_output = format_response(result)
        print(formatted_output)
        return 0 if result["success"] else 1

    except Exception as e:
        print(f"Error: {str(e)}")
        return 1


if __name__ == "__main__":
    exit(main())
