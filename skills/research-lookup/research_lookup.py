#!/usr/bin/env python3
"""
Research Information Lookup Tool (Free APIs)

Routes research queries to free academic databases:
  - OpenAlex API: Default for all scholarly queries (240M+ works, no key required)
  - PubMed E-utilities: Biomedical/life science queries (no key required)

No API keys required.
"""

import os
import sys
import json
import re
import time
import requests
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote


class ResearchLookup:
    """Research information lookup using free academic APIs.

    Routes queries to OpenAlex (default) or PubMed (biomedical).
    No API keys required.
    """

    BIOMEDICAL_KEYWORDS = [
        "pubmed", "pmid", "medline",
        "clinical trial", "clinical trials",
        "randomized controlled", "rct",
        "patient", "patients", "disease", "therapy",
        "drug", "treatment", "diagnosis", "prognosis",
        "cancer", "tumor", "tumour",
        "protein", "gene", "enzyme", "receptor",
        "antibody", "antigen", "immune",
        "cell line", "in vivo", "in vitro",
        "pharmaceutical", "pharmacology",
        "pathology", "etiology", "epidemiology",
        "surgery", "surgical",
        "biomarker", "assay",
        "nejm", "lancet", "jama", "bmj",
    ]

    OPENALEX_BASE = "https://api.openalex.org"
    PUBMED_SEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    PUBMED_FETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    PUBMED_SUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

    def __init__(self, force_backend: Optional[str] = None, email: Optional[str] = None):
        """Initialize the research lookup tool.

        Args:
            force_backend: Force a specific backend ('openalex' or 'pubmed').
            email: Email for PubMed E-utilities (polite usage, not required).
        """
        self.force_backend = force_backend
        self.email = email or os.getenv("NCBI_EMAIL", "")

    def _select_backend(self, query: str) -> str:
        """Select the best backend for a query."""
        if self.force_backend:
            return self.force_backend

        query_lower = query.lower()
        is_biomedical = any(kw in query_lower for kw in self.BIOMEDICAL_KEYWORDS)

        if is_biomedical:
            return "pubmed"
        return "openalex"

    # ------------------------------------------------------------------
    # OpenAlex backend (free, no key)
    # ------------------------------------------------------------------

    def _openalex_lookup(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """Search OpenAlex for scholarly works."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            params = {
                "search": query,
                "per_page": max_results,
                "sort": "relevance_score:desc",
                "select": (
                    "id,doi,title,authorships,publication_year,"
                    "cited_by_count,primary_location,type,abstract_inverted_index,"
                    "open_access,biblio"
                ),
            }
            if self.email:
                params["mailto"] = self.email

            print(f"[Research] OpenAlex search...", file=sys.stderr)
            resp = requests.get(
                f"{self.OPENALEX_BASE}/works",
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            works = data.get("results", [])
            citations = []
            summaries = []

            for work in works:
                title = work.get("title", "Untitled")
                doi = work.get("doi", "")
                year = work.get("publication_year", "")
                cited_by = work.get("cited_by_count", 0)

                # Extract authors
                authors = []
                for authorship in work.get("authorships", [])[:5]:
                    author = authorship.get("author", {})
                    name = author.get("display_name", "")
                    if name:
                        authors.append(name)
                author_str = ", ".join(authors)
                if len(work.get("authorships", [])) > 5:
                    author_str += " et al."

                # Extract journal/source
                source_name = ""
                primary_loc = work.get("primary_location", {}) or {}
                source = primary_loc.get("source", {}) or {}
                source_name = source.get("display_name", "")

                # Reconstruct abstract from inverted index
                abstract = self._reconstruct_abstract(
                    work.get("abstract_inverted_index")
                )

                citation = {
                    "type": "openalex",
                    "title": title,
                    "authors": author_str,
                    "year": year,
                    "source": source_name,
                    "cited_by_count": cited_by,
                    "doi": doi.replace("https://doi.org/", "") if doi else "",
                    "url": doi or work.get("id", ""),
                    "open_access": work.get("open_access", {}).get("is_oa", False),
                }
                citations.append(citation)

                # Build summary line
                oa_tag = " [OA]" if citation["open_access"] else ""
                summary = (
                    f"**{title}**\n"
                    f"  {author_str} ({year}) — *{source_name}*\n"
                    f"  Cited by: {cited_by}{oa_tag}"
                )
                if doi:
                    summary += f"\n  DOI: {doi}"
                if abstract:
                    summary += f"\n  > {abstract[:200]}{'...' if len(abstract) > 200 else ''}"
                summaries.append(summary)

            response_text = f"# OpenAlex Results for: {query}\n\n"
            response_text += f"Found {data.get('meta', {}).get('count', len(works))} total works. "
            response_text += f"Showing top {len(works)} by relevance.\n\n"
            for i, s in enumerate(summaries, 1):
                response_text += f"## {i}. {s}\n\n"

            return {
                "success": True,
                "query": query,
                "response": response_text,
                "citations": citations,
                "sources": citations,
                "total_count": data.get("meta", {}).get("count", 0),
                "timestamp": timestamp,
                "backend": "openalex",
                "model": "openalex-api",
            }

        except Exception as e:
            return {
                "success": False,
                "query": query,
                "error": str(e),
                "timestamp": timestamp,
                "backend": "openalex",
                "model": "openalex-api",
            }

    def _reconstruct_abstract(self, inverted_index: Optional[Dict]) -> str:
        """Reconstruct abstract text from OpenAlex inverted index."""
        if not inverted_index:
            return ""
        word_positions = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))
        word_positions.sort()
        return " ".join(w for _, w in word_positions)

    # ------------------------------------------------------------------
    # PubMed E-utilities backend (free, no key)
    # ------------------------------------------------------------------

    def _pubmed_lookup(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """Search PubMed for biomedical literature."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            # Step 1: Search for IDs
            search_params = {
                "db": "pubmed",
                "term": query,
                "retmax": max_results,
                "sort": "relevance",
                "retmode": "json",
            }
            if self.email:
                search_params["email"] = self.email

            print(f"[Research] PubMed search...", file=sys.stderr)
            search_resp = requests.get(
                self.PUBMED_SEARCH, params=search_params, timeout=30
            )
            search_resp.raise_for_status()
            search_data = search_resp.json()

            id_list = search_data.get("esearchresult", {}).get("idlist", [])
            total_count = int(
                search_data.get("esearchresult", {}).get("count", "0")
            )

            if not id_list:
                return {
                    "success": True,
                    "query": query,
                    "response": f"No PubMed results found for: {query}",
                    "citations": [],
                    "sources": [],
                    "total_count": 0,
                    "timestamp": timestamp,
                    "backend": "pubmed",
                    "model": "pubmed-eutils",
                }

            # Step 2: Fetch summaries
            ids_str = ",".join(id_list)
            summary_params = {
                "db": "pubmed",
                "id": ids_str,
                "retmode": "json",
            }
            if self.email:
                summary_params["email"] = self.email

            summary_resp = requests.get(
                self.PUBMED_SUMMARY, params=summary_params, timeout=30
            )
            summary_resp.raise_for_status()
            summary_data = summary_resp.json()

            result_entries = summary_data.get("result", {})
            citations = []
            summaries = []

            for pmid in id_list:
                entry = result_entries.get(pmid, {})
                if not entry or isinstance(entry, str):
                    continue

                title = entry.get("title", "Untitled")
                # Extract authors
                authors_list = entry.get("authors", [])
                author_names = [a.get("name", "") for a in authors_list[:5]]
                author_str = ", ".join(author_names)
                if len(authors_list) > 5:
                    author_str += " et al."

                source = entry.get("fulljournalname", entry.get("source", ""))
                pub_date = entry.get("pubdate", "")
                year = pub_date[:4] if pub_date else ""

                # Extract DOI from articleids
                doi = ""
                for aid in entry.get("articleids", []):
                    if aid.get("idtype") == "doi":
                        doi = aid.get("value", "")
                        break

                citation = {
                    "type": "pubmed",
                    "title": title,
                    "authors": author_str,
                    "year": year,
                    "source": source,
                    "pmid": pmid,
                    "doi": doi,
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                }
                citations.append(citation)

                doi_line = f"\n  DOI: https://doi.org/{doi}" if doi else ""
                summary = (
                    f"**{title}**\n"
                    f"  {author_str} ({year}) — *{source}*\n"
                    f"  PMID: {pmid}{doi_line}"
                )
                summaries.append(summary)

            response_text = f"# PubMed Results for: {query}\n\n"
            response_text += f"Found {total_count} total articles. "
            response_text += f"Showing top {len(summaries)} by relevance.\n\n"
            for i, s in enumerate(summaries, 1):
                response_text += f"## {i}. {s}\n\n"

            return {
                "success": True,
                "query": query,
                "response": response_text,
                "citations": citations,
                "sources": citations,
                "total_count": total_count,
                "timestamp": timestamp,
                "backend": "pubmed",
                "model": "pubmed-eutils",
            }

        except Exception as e:
            return {
                "success": False,
                "query": query,
                "error": str(e),
                "timestamp": timestamp,
                "backend": "pubmed",
                "model": "pubmed-eutils",
            }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def lookup(self, query: str) -> Dict[str, Any]:
        """Perform a research lookup, routing to the best backend.

        OpenAlex is used by default. PubMed is used for biomedical queries.
        """
        backend = self._select_backend(query)
        print(f"[Research] Backend: {backend} | Query: {query[:80]}...", file=sys.stderr)

        if backend == "pubmed":
            return self._pubmed_lookup(query)
        else:
            return self._openalex_lookup(query)

    def batch_lookup(self, queries: List[str], delay: float = 0.5) -> List[Dict[str, Any]]:
        """Perform multiple research lookups with delay between requests."""
        results = []
        for i, query in enumerate(queries):
            if i > 0 and delay > 0:
                time.sleep(delay)
            result = self.lookup(query)
            results.append(result)
            print(f"[Research] Completed query {i+1}/{len(queries)}: {query[:50]}...", file=sys.stderr)
        return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """Command-line interface for the research lookup tool."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Research Information Lookup Tool (OpenAlex + PubMed, free)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # General scholarly search (uses OpenAlex)
  python research_lookup.py "latest advances in quantum computing 2025"

  # Biomedical search (auto-routes to PubMed)
  python research_lookup.py "CRISPR clinical trials gene therapy"

  # Force a specific backend
  python research_lookup.py "topic" --force-backend openalex
  python research_lookup.py "topic" --force-backend pubmed

  # Save output to file
  python research_lookup.py "topic" -o results.md

  # JSON output
  python research_lookup.py "topic" --json -o results.json
        """,
    )
    parser.add_argument("query", nargs="?", help="Research query to look up")
    parser.add_argument("--batch", nargs="+", help="Run multiple queries")
    parser.add_argument(
        "--force-backend",
        choices=["openalex", "pubmed"],
        help="Force a specific backend (default: auto-select)",
    )
    parser.add_argument("-o", "--output", help="Write output to file")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("-n", "--max-results", type=int, default=10,
                        help="Max results per query (default: 10)")

    args = parser.parse_args()

    output_file = None
    if args.output:
        output_file = open(args.output, "w", encoding="utf-8")

    def write_output(text):
        if output_file:
            output_file.write(text + "\n")
        else:
            try:
                print(text)
            except UnicodeEncodeError:
                print(text.encode("utf-8", errors="replace").decode("utf-8"))

    if not args.query and not args.batch:
        parser.print_help()
        if output_file:
            output_file.close()
        return 1

    try:
        research = ResearchLookup(force_backend=args.force_backend)

        if args.batch:
            print(f"Running batch research for {len(args.batch)} queries...", file=sys.stderr)
            results = research.batch_lookup(args.batch)
        else:
            print(f"Researching: {args.query}", file=sys.stderr)
            results = [research.lookup(args.query)]

        if args.json:
            write_output(json.dumps(results, indent=2, ensure_ascii=False, default=str))
            if output_file:
                output_file.close()
            return 0

        for i, result in enumerate(results):
            if result["success"]:
                write_output(f"\n{'='*80}")
                write_output(f"Query {i+1}: {result['query']}")
                write_output(f"Timestamp: {result['timestamp']}")
                write_output(f"Backend: {result.get('backend', 'unknown')}")
                write_output(f"Total found: {result.get('total_count', 'N/A')}")
                write_output(f"{'='*80}")
                write_output(result["response"])

                citations = result.get("citations", [])
                if citations:
                    write_output(f"\nCitations ({len(citations)}):")
                    for j, cit in enumerate(citations):
                        title = cit.get("title", "Untitled")
                        authors = cit.get("authors", "")
                        year = cit.get("year", "")
                        source = cit.get("source", "")
                        doi = cit.get("doi", "")
                        url = cit.get("url", "")
                        write_output(f"  [{j+1}] {title}")
                        write_output(f"      {authors} ({year}) — {source}")
                        if doi:
                            write_output(f"      DOI: {doi}")
                        if url:
                            write_output(f"      {url}")
            else:
                write_output(f"\nError in query {i+1}: {result['error']}")

        if output_file:
            output_file.close()
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if output_file:
            output_file.close()
        return 1


if __name__ == "__main__":
    sys.exit(main())
