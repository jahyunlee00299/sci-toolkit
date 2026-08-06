#!/usr/bin/env python3
"""
Example usage of the Research Lookup skill with free APIs (OpenAlex + PubMed).

This script demonstrates:
1. Automatic backend selection based on query content
2. Manual backend override
3. Batch query processing
"""

from research_lookup import ResearchLookup


def example_automatic_selection():
    """Demonstrate automatic backend selection."""
    print("=" * 80)
    print("EXAMPLE 1: Automatic Backend Selection")
    print("=" * 80)
    print()

    research = ResearchLookup()

    # General scholarly query -> OpenAlex
    query1 = "Recent advances in transformer attention mechanisms"
    print(f"Query: {query1}")
    print(f"Expected backend: OpenAlex (general scholarly)")
    result1 = research.lookup(query1)
    print(f"Actual backend: {result1.get('backend')}")
    print(f"Results found: {result1.get('total_count', 0)}")
    print()

    # Biomedical query -> PubMed
    query2 = "CRISPR clinical trials gene therapy patients"
    print(f"Query: {query2}")
    print(f"Expected backend: PubMed (biomedical)")
    result2 = research.lookup(query2)
    print(f"Actual backend: {result2.get('backend')}")
    print(f"Results found: {result2.get('total_count', 0)}")
    print()


def example_manual_override():
    """Demonstrate manual backend override."""
    print("=" * 80)
    print("EXAMPLE 2: Manual Backend Override")
    print("=" * 80)
    print()

    query = "machine learning drug discovery"

    # Force OpenAlex
    research_oa = ResearchLookup(force_backend="openalex")
    result = research_oa.lookup(query)
    print(f"Query: {query}")
    print(f"Forced backend: openalex -> {result.get('backend')}")
    print(f"Results: {result.get('total_count', 0)}")
    print()

    # Force PubMed
    research_pm = ResearchLookup(force_backend="pubmed")
    result = research_pm.lookup(query)
    print(f"Query: {query}")
    print(f"Forced backend: pubmed -> {result.get('backend')}")
    print(f"Results: {result.get('total_count', 0)}")
    print()


def example_batch_queries():
    """Demonstrate batch query processing."""
    print("=" * 80)
    print("EXAMPLE 3: Batch Query Processing")
    print("=" * 80)
    print()

    research = ResearchLookup()

    queries = [
        "quantum computing error correction",       # -> OpenAlex
        "immunotherapy cancer clinical trial",       # -> PubMed
        "large language models reasoning",           # -> OpenAlex
    ]

    print("Processing batch queries...")
    results = research.batch_lookup(queries, delay=0.5)

    for i, result in enumerate(results):
        print(f"Query {i+1}: {result['query'][:50]}...")
        print(f"  Backend: {result.get('backend')}")
        print(f"  Results: {result.get('total_count', 0)}")
        print(f"  Success: {result.get('success')}")
        print()


def example_routing_demo():
    """Show routing logic without making API calls."""
    print("=" * 80)
    print("ROUTING DEMO (No API calls)")
    print("=" * 80)
    print()

    research = ResearchLookup()

    test_queries = [
        ("Recent CRISPR studies", "openalex"),
        ("Clinical trial diabetes treatment", "pubmed"),
        ("Transformer architecture NeurIPS", "openalex"),
        ("Gene therapy patients drug", "pubmed"),
        ("Renewable energy policy", "openalex"),
        ("Protein enzyme receptor binding", "pubmed"),
    ]

    for query, expected in test_queries:
        actual = research._select_backend(query)
        status = "OK" if actual == expected else "MISMATCH"
        print(f"[{status}] '{query}'")
        print(f"  -> Expected: {expected}, Actual: {actual}")
        print()


if __name__ == "__main__":
    # Routing demo always works (no API calls)
    example_routing_demo()

    # Uncomment to run live API examples:
    # example_automatic_selection()
    # example_manual_override()
    # example_batch_queries()
