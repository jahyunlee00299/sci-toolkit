#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cross-platform preflight: can this machine actually run the toolkit's hooks?

Why this exists
----------------
`hooks/hooks.json` runs `sh "${CLAUDE_PLUGIN_ROOT}/hooks/_run_hooks_chained.sh"`.
On a Windows machine with no Git Bash and no WSL, `sh` isn't on PATH at all, and
Claude Code's documented behavior is to fall back to `cmd.exe` for hook execution
-- which cannot parse `.sh` files or `$HOME`-style syntax. The hook then fails
with something like `'$HOME' is not recognized...`, and every guard that hook
enforces (secret scan, dangerous-git, docx corruption, etc.) is silently gone.
This is the sci-toolkit-distribution version of the "hardcoded to one machine's
shape" bug class documented in this user's dual-PC config (a hook that only
works where it was authored) -- except here the audience is unknown installers,
not two known machines.

`detect()` reports whether a bash-capable shell is reachable, and if not, gives
the exact fix (Anthropic's own `CLAUDE_CODE_GIT_BASH_PATH` env var) rather than
letting hooks fail silently. See:
https://github.com/anthropics/claude-code/issues/16602
"""
from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path

GIT_BASH_ENV_VAR = "CLAUDE_CODE_GIT_BASH_PATH"

# Common Git-for-Windows install locations, checked when nothing is on PATH.
_WINDOWS_GIT_BASH_CANDIDATES = [
    r"C:\Program Files\Git\bin\bash.exe",
    r"C:\Program Files (x86)\Git\bin\bash.exe",
    str(Path.home() / "AppData" / "Local" / "Programs" / "Git" / "bin" / "bash.exe"),
    str(Path.home() / "scoop" / "apps" / "git" / "current" / "bin" / "bash.exe"),
]


def _is_wsl_stub(path: str) -> bool:
    """`C:\\Windows\\System32\\bash.exe` is the WSL launcher, not a real POSIX
    shell on the Windows side -- it only works if a WSL distro is fully set up,
    and path translation inside it differs from Git Bash. Treat it as unproven."""
    return "system32" in path.lower()


def detect() -> dict:
    """Returns a dict: os, shell_ok (bool), shell_path, shell_source, advice (list[str])."""
    system = platform.system()  # "Windows" | "Darwin" | "Linux"
    result = {
        "os": system,
        "shell_ok": False,
        "shell_path": None,
        "shell_source": None,
        "advice": [],
    }

    if system != "Windows":
        # macOS/Linux ship a POSIX shell by definition; this is a sanity check,
        # not a real gap -- but check anyway rather than assume.
        sh = shutil.which("sh") or shutil.which("bash")
        if sh:
            result.update(shell_ok=True, shell_path=sh, shell_source="PATH")
        else:
            result["advice"].append(
                f"[Notice] This is {system} but sh/bash wasn't found on PATH — an unusual setup. "
                "Check directly with `bash --version` whether hooks can run."
            )
        return result

    # Windows: prefer the CLAUDE_CODE_GIT_BASH_PATH env var if it's already
    # set and points at a real file -- that's what Claude Code itself reads.
    env_path = os.environ.get(GIT_BASH_ENV_VAR)
    if env_path and Path(env_path).is_file():
        result.update(shell_ok=True, shell_path=env_path, shell_source=f"env:{GIT_BASH_ENV_VAR}")
        return result

    which_bash = shutil.which("bash")
    if which_bash and not _is_wsl_stub(which_bash):
        result.update(shell_ok=True, shell_path=which_bash, shell_source="PATH")
        return result

    for cand in _WINDOWS_GIT_BASH_CANDIDATES:
        if Path(cand).is_file():
            result["shell_path"] = cand
            result["shell_source"] = "known_location"
            result["advice"].append(
                f"[Action needed] Git Bash is at {cand} but it isn't on PATH, and "
                f"the {GIT_BASH_ENV_VAR} environment variable isn't set either. In this case Claude "
                "Code falls back to cmd.exe for hook execution, and cmd.exe can't run .sh files, "
                "so hooks fail silently.\n"
                f"  Fix: add the following to \"env\" in ~/.claude/settings.json.\n"
                f'    "{GIT_BASH_ENV_VAR}": "{cand}"'
            )
            return result

    if which_bash and _is_wsl_stub(which_bash):
        result["shell_path"] = which_bash
        result["shell_source"] = "wsl_stub"
        result["advice"].append(
            f"[Action needed] The bash on PATH is the WSL launcher ({which_bash}) — if the WSL "
            "distro isn't fully set up, hooks may fail. Installing Git Bash is recommended: "
            "https://git-scm.com/download/win"
        )
        return result

    result["advice"].append(
        "[Action needed] Could not find sh/bash on this Windows setup. Claude Code hooks fall "
        "back to cmd.exe by default, and cmd.exe can't run .sh files, so hooks (secret scanning, "
        "dangerous-git guard, docx-corruption prevention, etc.) all run silently disabled.\n"
        "  Fix: install Git for Windows (https://git-scm.com/download/win), then add "
        f"\"{GIT_BASH_ENV_VAR}\": \"C:\\\\Program Files\\\\Git\\\\bin\\\\bash.exe\" to \"env\" in ~/.claude/settings.json."
    )
    return result


if __name__ == "__main__":
    import json
    import sys

    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            try:
                _s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    r = detect()
    status = "OK" if r["shell_ok"] else "FAIL"
    if "--json" in sys.argv:
        print(json.dumps(r, ensure_ascii=False))
    else:
        print(f"[{status}] shell: os={r['os']} path={r['shell_path']} source={r['shell_source']}")
        for line in r["advice"]:
            print(line)
    sys.exit(0 if r["shell_ok"] else 1)
