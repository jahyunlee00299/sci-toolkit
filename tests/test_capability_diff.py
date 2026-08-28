#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regression tests for the shrunken-version detector (capability_diff).

Why this tool exists (a measured case):
  On 2026-06-27, a PII-sanitization pass on the runtime skills turned
  `update_notion.py` from 15.9KB down to 7.4KB. It wasn't replaced with
  placeholders — it was a **shrunken version that lost half its
  functionality** (the briefing-log upsert, overview refresh, and
  dedup-cleanup logic were gone). But the file still existed and the exit
  code was 0. So the weekly-briefing automation produced nothing for 4
  straight weeks and nobody noticed.

  A generic quality comparison (an LLM judge) cannot catch this. A shrunken
  version still reads as "well-written text." The only way to catch it is
  to structurally diff **whether a capability the original had still exists
  in the new version** — that's what this tool does.

Contract:
  1. Catches it when a section (##/###) present in the original disappears
     in the new version.
  2. Catches it when a script/file path the original referenced disappears.
  3. Catches it when a code-fenced command (python x.py ...) present in the
     original disappears.
  4. Warns when size shrinks past a threshold (30% by default).
  5. A rename alone (domain generalization) is not a loss — if the count
     stays the same, it passes. Sanitization's whole point IS renaming, so a
     false positive here would make the tool useless.
"""
from __future__ import annotations

import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "capability_diff", ROOT / "scripts" / "capability_diff.py")
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["capability_diff"] = _mod
_spec.loader.exec_module(_mod)

diff_capabilities = _mod.diff_capabilities

_fail = 0
_pass = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _fail, _pass
    if cond:
        _pass += 1
        print(f"  PASS  {name}")
    else:
        _fail += 1
        print(f"  FAIL  {name}" + (f"  — {detail}" if detail else ""))


ORIGINAL = """---
name: demo
---
# Demo skill

## Setup
Run `python scripts/setup_env.py --check` first.

## Analysis
See `references/analysis_rules.md` for the decision tree.

```bash
python scripts/analyze.py --input data.csv
```

### Edge cases
Handle empty input.

## Reporting
Produces `out/report.html`.
"""


def main() -> int:
    print("Shrunken-version detector verification")
    print("=" * 60)

    # ── 1. Normal sanitization: only names change, capability stays ─────
    print("\n[normal sanitization] domain names only renamed — not a loss")
    sanitized = (ORIGINAL
                 .replace("data.csv", "input.csv")
                 .replace("Handle empty input.", "Handle an empty input file."))
    rep = diff_capabilities(ORIGINAL, sanitized)
    check("judged as 0 losses", not rep.lost_sections and not rep.lost_refs
          and not rep.lost_commands,
          f"false positive: sections={rep.lost_sections} refs={rep.lost_refs} cmds={rep.lost_commands}")
    check("no shrink warning", not rep.shrank, f"shrink_ratio={rep.shrink_ratio:.2f}")

    # ── 2. Section loss ───────────────────────────────────────────────
    print("\n[section loss] ## Reporting deleted wholesale")
    cut = ORIGINAL.split("## Reporting")[0]
    rep = diff_capabilities(ORIGINAL, cut)
    check("catches the missing section", "Reporting" in " ".join(rep.lost_sections),
          f"lost_sections={rep.lost_sections}")

    # ── 3. Reference-path loss ────────────────────────────────────────
    print("\n[reference loss] references/analysis_rules.md reference removed")
    noref = ORIGINAL.replace("See `references/analysis_rules.md` for the decision tree.",
                             "See the decision tree.")
    rep = diff_capabilities(ORIGINAL, noref)
    check("catches the missing file reference",
          any("analysis_rules" in r for r in rep.lost_refs),
          f"lost_refs={rep.lost_refs}")

    # ── 4. Command loss ───────────────────────────────────────────────
    print("\n[command loss] analyze.py execution block removed")
    nocmd = ORIGINAL.replace("python scripts/analyze.py --input data.csv", "(omitted)")
    rep = diff_capabilities(ORIGINAL, nocmd)
    check("catches the missing command",
          any("analyze.py" in c for c in rep.lost_commands),
          f"lost_commands={rep.lost_commands}")

    # ── 5. The 260727 pattern: size cut in half ───────────────────────
    print("\n[shrunken version] half the content lost (the 260727 update_notion.py pattern)")
    half = "\n".join(ORIGINAL.splitlines()[: len(ORIGINAL.splitlines()) // 2])
    rep = diff_capabilities(ORIGINAL, half)
    check("warns about the shrink", rep.shrank, f"shrink_ratio={rep.shrink_ratio:.2f}")
    check("verdict is FAIL", not rep.ok, "it's a shrunken version but ok=True")

    # ── 6. Growth is not a problem ────────────────────────────────────
    print("\n[growth] content grew — should pass")
    more = ORIGINAL + "\n## Troubleshooting\nCheck the log first.\n"
    rep = diff_capabilities(ORIGINAL, more)
    check("growth is not treated as loss", rep.ok,
          f"sections={rep.lost_sections} shrink={rep.shrink_ratio:.2f}")

    print("=" * 60)
    print(f"PASS {_pass} / FAIL {_fail}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
