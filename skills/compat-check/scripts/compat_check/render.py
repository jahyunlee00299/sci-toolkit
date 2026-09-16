"""Render a dependency tree (see tree.py) as a colored ASCII tree for the
terminal. No external dependency — plain ANSI escape codes, disabled
automatically when stdout isn't a TTY (e.g. piped to a file) so redirected
output stays clean text.
"""
from __future__ import annotations

import sys

_GREEN = "\033[32m"
_CYAN = "\033[36m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _colors_enabled() -> bool:
    return sys.stdout.isatty()


def _colorize(text: str, code: str) -> str:
    if not _colors_enabled():
        return text
    return f"{code}{text}{_RESET}"


def render_tree(roots: list[dict], label: str | None = None) -> str:
    """roots: list of {"name", "version", "children"} dicts, as returned by
    tree.build_tree()["roots"]. Returns a multi-line string ready to print.

    When `label` is given, roots are nested one level under a synthetic
    label node instead of being printed as separate top-level trees — used
    to show "what this source pulls in" as a single tree rather than a flat
    list of its direct dependencies.
    """
    lines: list[str] = []
    if label is not None:
        lines.append(_colorize(label, _CYAN))
        for i, root in enumerate(roots):
            _render_node(root, prefix="", is_last=(i == len(roots) - 1), lines=lines, is_root=False)
        return "\n".join(lines)

    for i, root in enumerate(roots):
        _render_node(root, prefix="", is_last=(i == len(roots) - 1), lines=lines, is_root=True)
    return "\n".join(lines)


def _render_node(node: dict, prefix: str, is_last: bool, lines: list[str], is_root: bool) -> None:
    name = _colorize(node["name"], _GREEN)
    version = _colorize(f"v{node['version']}", _DIM)

    if is_root:
        lines.append(f"{name} {version}")
        child_prefix = ""
    else:
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{name} {version}")
        child_prefix = prefix + ("    " if is_last else "│   ")

    children = node.get("children", [])
    for i, child in enumerate(children):
        _render_node(child, child_prefix, is_last=(i == len(children) - 1),
                     lines=lines, is_root=False)
