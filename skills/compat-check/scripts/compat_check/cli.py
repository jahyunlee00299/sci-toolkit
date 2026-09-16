"""compat-check CLI entry point — wires fetcher -> cache -> runner into a
human-readable report.

    compat-check <github-url-or-pypi-name> [--python 3.11] [--no-cache]
"""
from __future__ import annotations

import argparse
import sys

from compat_check.cache import cached_probe_all
from compat_check.fetcher import FetchError, fetch_requirements
from compat_check.render import render_tree
from compat_check.runner import probe_all
from compat_check.tree import build_tree


def _print_report(source: str, requirements: list[str], result: dict) -> None:
    cache_note = " (cached)" if result.get("cache_hit") else ""
    print(f"compat-check: {source}{cache_note}")
    print(f"backend: {result['backend']}")
    print(f"requirements checked: {', '.join(requirements)}")
    print()

    if result["ok"]:
        print(f"OK — {len(result['resolved'])} package(s) would install cleanly:")
        for pkg in result["resolved"]:
            print(f"  + {pkg}")
        return

    print(f"PROBLEMS FOUND — {len(result['failures'])} package(s) cannot be resolved:")
    for f in result["failures"]:
        print(f"\n  [{f['package']}]")
        # Indent the raw resolver output so it reads as evidence, not noise.
        for line in f["stderr"].strip().splitlines():
            print(f"    {line}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="compat-check",
        description="Check whether a GitHub repo or PyPI package would install "
                    "cleanly in this environment, without actually installing it.",
    )
    parser.add_argument("source", help="GitHub repo URL or PyPI package name")
    parser.add_argument("--python", default="3.11", dest="python_version",
                         help="target Python version (default: 3.11; ignored by the pip fallback)")
    parser.add_argument("--no-cache", action="store_true",
                         help="skip the local failure-history cache, always probe fresh")
    parser.add_argument("--tree", action="store_true",
                         help="show the full dependency tree (requires uv; no pip fallback)")
    args = parser.parse_args(argv)

    try:
        requirements = fetch_requirements(args.source)
    except FetchError as e:
        print(f"compat-check: could not resolve requirements for '{args.source}': {e}", file=sys.stderr)
        return 2

    if args.no_cache:
        result = probe_all(requirements, python_version=args.python_version)
        result = {**result, "cache_hit": False}
    else:
        result = cached_probe_all(requirements, python_version=args.python_version)

    _print_report(args.source, requirements, result)

    if args.tree:
        print()
        tree_result = build_tree(requirements, python_version=args.python_version)
        if tree_result["ok"]:
            print(render_tree(tree_result["roots"], label=args.source))
        else:
            print(f"(tree unavailable: {tree_result['stderr'].strip()})", file=sys.stderr)

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
