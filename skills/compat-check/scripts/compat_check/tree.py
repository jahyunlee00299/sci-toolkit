"""Build a dependency tree for a requirements list via `uv tree`.

uv only exposes a dependency tree for a *project* (a directory with a
pyproject.toml), not for an ad-hoc requirements list — so this module
writes a throwaway pyproject.toml declaring the requirements as
dependencies, in the same disposable-directory spirit as runner.py's
disposable venvs. `uv tree` has no JSON output; its text tree uses
indentation (4 spaces per level, "└── "/"├── "/"│   " box-drawing
prefixes) which this module parses into a nested dict.

Falls back to a flat, single-level tree (no parent/child edges) when uv
isn't installed — pip has no equivalent to `uv tree`, and reproducing one
without a resolver's internal graph is out of scope for this unit.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

_LINE_RE = re.compile(r"^(?P<prefix>(?:[│ ]   )*)(?:├── |└── )?(?P<rest>.+)$")
_PKG_RE = re.compile(r"^(?P<name>[A-Za-z0-9_.\-]+) v(?P<version>[A-Za-z0-9_.\-+]+)(?: \(\*\))?$")


@dataclass
class TreeNode:
    name: str
    version: str
    children: list["TreeNode"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "version": self.version,
                "children": [c.to_dict() for c in self.children]}


def _depth_of(prefix: str) -> int:
    # Each level is exactly 4 characters wide ("│   ", "    ", etc.).
    return len(prefix) // 4


def _parse_uv_tree_output(text: str) -> list[TreeNode]:
    """Parse `uv tree`'s indented box-drawing output into a node list.

    The first line is the project root itself (name + version, no prefix) —
    skipped; its children are what we actually want.
    """
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return []

    roots: list[TreeNode] = []
    stack: list[tuple[int, TreeNode]] = []  # (depth, node)

    for line in lines[1:]:  # skip the project-root line
        m = _LINE_RE.match(line)
        if not m:
            continue
        depth = _depth_of(m.group("prefix"))
        pkg_m = _PKG_RE.match(m.group("rest").strip())
        if not pkg_m:
            continue
        node = TreeNode(name=pkg_m.group("name"), version=pkg_m.group("version"))

        while stack and stack[-1][0] >= depth:
            stack.pop()

        if stack:
            stack[-1][1].children.append(node)
        else:
            roots.append(node)
        stack.append((depth, node))

    return roots


def build_tree(requirements: list[str], python_version: str = "3.11") -> dict:
    """Return {"ok": bool, "roots": [TreeNode.to_dict(), ...], "stderr": str}.

    Requires `uv` — pip has no equivalent tree command. Callers should check
    for uv availability first (see cli.py) and degrade gracefully.
    """
    if not shutil.which("uv"):
        return {"ok": False, "roots": [], "stderr": "uv is required for dependency tree visualization"}

    with tempfile.TemporaryDirectory(prefix="compat_check_tree_") as tmp:
        proj_dir = Path(tmp)
        deps_toml = ", ".join(f'"{r}"' for r in requirements)
        (proj_dir / "pyproject.toml").write_text(
            f'[project]\nname = "compat-check-probe"\nversion = "0.0.0"\n'
            f'requires-python = ">={python_version}"\ndependencies = [{deps_toml}]\n',
            encoding="utf-8",
        )
        proc = subprocess.run(
            ["uv", "tree", "--universal"],
            cwd=str(proj_dir), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        if proc.returncode != 0:
            return {"ok": False, "roots": [], "stderr": proc.stderr}

        roots = _parse_uv_tree_output(proc.stdout)
        return {"ok": True, "roots": [r.to_dict() for r in roots], "stderr": ""}
