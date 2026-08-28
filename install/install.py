#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sci-toolkit à la carte installer

Pick only the features (skills) you want and install them to a destination
folder.
- Choose a whole preset at once ("paper writing," "literature review," etc.)
- Or hand-pick individual skills
- Hard dependencies between skills (e.g. manuscript-pipeline -> docx,
  academic-term-rules) are auto-installed alongside, based on
  config/catalog.json.

The default is preview (dry-run). Actual copying only happens with --apply.

Examples:
  python install/install.py                      # interactive, preview
  python install/install.py --apply              # interactive, actual install
  python install/install.py --preset paper-writing --dest ~/.claude/skills --apply
  python install/install.py --skills docx,xlsx --dest ./out --apply
  python install/install.py --list               # print the catalog only
"""
from __future__ import annotations

# Windows' default console is cp949, which dies on Korean/symbol output. Force UTF-8.
# Use reconfigure(): wrapping in a TextIOWrapper would take ownership of the
# underlying stream, so once the wrapper is GC'd after this module is imported,
# it closes the caller's stdout too (measured).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# Force stdout/stdin to UTF-8 so Korean text isn't corrupted on a Windows console (cp949)
for _stream in (sys.stdout, sys.stdin, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent.parent          # toolkit root
CATALOG_PATH = ROOT / "config" / "catalog.json"
SKILLS_DIR = ROOT / "skills"


def _shell_env_notice() -> None:
    """Warn before install if this machine can't run the plugin's hooks.

    Only relevant when this repo is loaded as a Claude Code plugin (hooks/hooks.json
    runs `sh ...`) -- the à-la-carte skill copy below works regardless. But a user
    who never sees this warning has no way to know their safety-guard hooks are
    silently inert (see scripts/env_detect.py for the full explanation).
    """
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import env_detect  # noqa: E402
        r = env_detect.detect()
    except Exception:
        return  # preflight is best-effort; never block install over it
    if r["shell_ok"]:
        return
    print("\n⚠ On this computer, if this repo is installed as a Claude Code plugin,")
    print("  its hooks (safety guards) may not run:")
    for line in r["advice"]:
        print(f"  {line}")
    print("  (this script, which only installs individual skills, works fine regardless of this issue)\n")


# ── catalog ────────────────────────────────────────────────────────────────
def load_catalog() -> dict:
    if not CATALOG_PATH.exists():
        sys.exit(f"[Error] Could not find the catalog: {CATALOG_PATH}")
    with CATALOG_PATH.open(encoding="utf-8") as f:
        cat = json.load(f)
    # sanity: every skill folder listed in catalog must exist on disk.
    # `external: true` skills are an exception — deliberately absent because
    # this repo cannot redistribute them, and they stay in the catalog only
    # to keep the dependency declaration alive.
    missing = [s for s, meta in cat["skills"].items()
               if not meta.get("external") and not (SKILLS_DIR / s).is_dir()]
    if missing:
        sys.exit(f"[Error] Skill(s) in the catalog with no actual folder: {', '.join(missing)}")
    return cat


def all_skill_names(cat: dict) -> list[str]:
    return sorted(cat["skills"].keys())


# ── dependency resolution ───────────────────────────────────────────────────
def resolve(selection: list[str], cat: dict) -> tuple[list[str], dict[str, list[str]]]:
    """Expand a selection to include all hard 'requires' deps (transitive).

    Returns (final_sorted_list, pulled_by) where pulled_by[dep] = [skills that
    pulled it in]. No cycles exist in the catalog, but we guard anyway.
    """
    skills = cat["skills"]
    final: set[str] = set()
    pulled_by: dict[str, list[str]] = {}

    def visit(name: str, chain: tuple[str, ...]) -> None:
        if name not in skills:
            sys.exit(f"[Error] Unknown skill: {name}")
        if name in chain:  # cycle guard (catalog has none, but be safe)
            return
        if name in final:
            return
        final.add(name)
        for dep in skills[name].get("requires", []):
            pulled_by.setdefault(dep, [])
            if name not in pulled_by[dep]:
                pulled_by[dep].append(name)
            visit(dep, chain + (name,))

    for s in selection:
        visit(s, ())
    # keep only deps that weren't explicitly chosen by the user
    pulled_by = {d: srcs for d, srcs in pulled_by.items() if d not in selection}
    return sorted(final), pulled_by


# ── selection expansion ─────────────────────────────────────────────────────
def expand_preset(preset_key: str, cat: dict) -> list[str]:
    presets = cat["presets"]
    if preset_key not in presets:
        sys.exit(f"[Error] Unknown preset: {preset_key} "
                 f"(available: {', '.join(presets)})")
    skills = presets[preset_key]["skills"]
    if skills == ["__ALL__"]:
        return all_skill_names(cat)
    return list(skills)


# ── size helpers ─────────────────────────────────────────────────────────────
def _cat_label(cat: dict, ckey: str) -> str:
    """Category label — supports both the old (string) and new (dict) formats."""
    c = cat["categories"].get(ckey, ckey)
    return c["label"] if isinstance(c, dict) else c


def fmt_size(kb: int) -> str:
    """KB -> a human-readable size."""
    if kb >= 1024:
        return f"{kb/1024:.1f} MB"
    return f"{kb} KB"


def total_size_kb(names, cat: dict) -> int:
    return sum(cat["skills"].get(n, {}).get("size_kb", 0) for n in names)


# ── printing ────────────────────────────────────────────────────────────────
def print_catalog(cat: dict) -> None:
    skills = cat["skills"]
    groups = cat.get("groups", {})
    total_kb = total_size_kb(skills.keys(), cat)
    print("\n=== Installable skills (%d total, %s) ===" % (len(skills), fmt_size(total_kb)))

    # Top-level group -> category -> skill (new-format structure). Categories only if no groups.
    cat_keys = list(cat["categories"].keys())
    if groups:
        for gkey, glabel in groups.items():
            if gkey == "connect":
                continue  # connectors get their own section
            print(f"\n▼ {glabel}")
            for ckey in cat_keys:
                c = cat["categories"][ckey]
                if isinstance(c, dict) and c.get("group") != gkey:
                    continue
                _print_category(cat, ckey)
    else:
        for ckey in cat_keys:
            _print_category(cat, ckey)

    # External-service connectors
    conns = {k: v for k, v in cat.get("connectors", {}).items() if not k.startswith("_")}
    if conns:
        print(f"\n▼ {groups.get('connect', 'External integrations (connectors)')}")
        print("  (scripts/connectors/ — needs credentials.json, draft-first/write-guard)")
        for name, m in conns.items():
            print(f"  - {name:10s} {m['role']}  [{m.get('needs','')}]")

    print("\n=== Presets ===")
    for pkey, p in cat["presets"].items():
        names = all_skill_names(cat) if p["skills"] == ["__ALL__"] else p["skills"]
        print(f"  - {pkey:16s} {p['label']} — {p['desc']} ({len(names)}, {fmt_size(total_size_kb(names, cat))})")


def _print_category(cat: dict, ckey: str) -> None:
    skills = cat["skills"]
    members = [n for n, m in skills.items() if m["category"] == ckey]
    if not members:
        return
    print(f"  [{_cat_label(cat, ckey)}]")
    for n in sorted(members):
        req = skills[n].get("requires", [])
        req_note = f"  (requires: {', '.join(req)})" if req else ""
        sz = fmt_size(skills[n].get("size_kb", 0))
        print(f"    - {n:26s} {sz:>8s}  {skills[n]['role']}{req_note}")


# ── interactive menu ────────────────────────────────────────────────────────
def interactive_select(cat: dict) -> list[str]:
    presets = list(cat["presets"].items())
    print("\nWhat would you like to do? Pick from below.\n")
    for i, (pkey, p) in enumerate(presets, 1):
        n = str(len(all_skill_names(cat) if p["skills"] == ["__ALL__"] else p["skills"]))
        print(f"  {i}. {p['label']} — {p['desc']} ({n})")
    print(f"  {len(presets)+1}. Choose individually (pick specific skills)")
    print()
    while True:
        raw = input("Enter a number (comma-separated for multiple, e.g. 1,3): ").strip()
        if not raw:
            continue
        try:
            picks = [int(x) for x in raw.replace(" ", "").split(",")]
        except ValueError:
            print("  Please enter numbers.")
            continue
        if any(p == len(presets) + 1 for p in picks):
            return interactive_individual(cat)
        chosen: list[str] = []
        ok = True
        for p in picks:
            if 1 <= p <= len(presets):
                chosen += expand_preset(presets[p - 1][0], cat)
            else:
                print(f"  {p}: out of range.")
                ok = False
        if ok and chosen:
            return sorted(set(chosen))


def interactive_individual(cat: dict) -> list[str]:
    names = all_skill_names(cat)
    print("\n=== Choose individual skills ===")
    for i, n in enumerate(names, 1):
        print(f"  {i:2d}. {n:28s} {cat['skills'][n]['role']}")
    print()
    while True:
        raw = input("Numbers to install (comma-separated, e.g. 1,5,12): ").strip()
        try:
            picks = [int(x) for x in raw.replace(" ", "").split(",") if x]
        except ValueError:
            print("  Please enter numbers.")
            continue
        chosen = [names[p - 1] for p in picks if 1 <= p <= len(names)]
        if chosen:
            return sorted(set(chosen))
        print("  Please choose at least one.")


# ── copy ────────────────────────────────────────────────────────────────────
# `.distignore` is the SSOT for "what must not be distributed." This
# installer used to not read that file, so the rule existed but had zero
# effect on the install path (measured 2026-08-07). Pattern parsing lives in
# exactly one place, scripts/distignore.py — copying it here would drift.
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from distignore import load_patterns, ignore_factory  # type: ignore
    _DISTIGNORE_OK = True
except ImportError:  # install must still work on a distribution missing this module
    _DISTIGNORE_OK = False

_FALLBACK_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".cache")


def _build_ignore():
    """The exclusion callback used when copying. Uses `.distignore`, falling back to a minimal cache exclusion if absent."""
    if not _DISTIGNORE_OK:
        return _FALLBACK_IGNORE
    return ignore_factory(SKILLS_DIR, load_patterns(ROOT))


def default_dest() -> tuple[Path, str]:
    """Decide the default install destination from the environment. Returns (path, reason).

    Always defaulting to `~/.claude/skills` would install into a folder that
    means nothing to a Codex user. So decide based on what's actually present.

    Codex has its own skill registry too — `$CODEX_HOME/skills` (default
    `~/.codex/skills`) is the user-scope canonical location, and that list is
    injected at session start (measured on 0.147.0). CODEX_HOME must be
    respected so a custom-home install still lands in the right place.
    """
    home = Path.home()
    claude = home / ".claude"
    codex_home = os.environ.get("CODEX_HOME")
    codex = Path(codex_home) if codex_home else home / ".codex"
    if claude.is_dir() and not codex.is_dir():
        return claude / "skills", "Claude Code environment detected"
    if codex.is_dir() and not claude.is_dir():
        return codex / "skills", "Codex environment detected"
    if claude.is_dir() and codex.is_dir():
        return claude / "skills", "Both Claude Code and Codex detected — defaulting to Claude"
    return Path.cwd() / "skills", "No agent detected — using the current folder"


_CATALOG_CACHE: dict | None = None


def _catalog_flag(skill: str, flag: str) -> bool:
    """Read a boolean flag for a skill from the catalog (False if absent).

    A skill with `external: true` has no files in this repo — because it's
    Anthropic-owned and cannot be redistributed. It isn't removed from the
    catalog entirely because `manuscript-pipeline` and others declare it as
    a `requires`, and removing it would make resolve() die with "unknown
    skill." The declaration stays; only the copy is skipped.
    """
    global _CATALOG_CACHE
    if _CATALOG_CACHE is None:
        try:
            with CATALOG_PATH.open(encoding="utf-8") as f:
                _CATALOG_CACHE = json.load(f).get("skills", {})
        except Exception:
            _CATALOG_CACHE = {}
    return bool(_CATALOG_CACHE.get(skill, {}).get(flag))


def install(final: list[str], dest: Path, apply: bool, force: bool = False) -> None:
    """Install skills into the destination folder.

    The default is a **non-destructive merge**: distribution files overwrite
    the destination, but files that exist only in the destination are left
    alone. An earlier version deleted the destination folder whole with
    `shutil.rmtree(dst)` before copying, so a script the user had dropped
    directly into their runtime disappeared in one install (measured
    2026-08-07: 7 manuscript-pipeline scripts, 3 endnote-citation-injection,
    3 scientific-validation).

    The old behavior (full replace) needs force=True stated explicitly.
    See tests/test_install_nondestructive.py for the contract and regression
    tests.
    """
    dest_skills = dest / "skills" if dest.name != "skills" else dest
    print(f"\nDestination folder: {dest_skills}")
    if force:
        print("  * --force: replacing the destination skill folder entirely (existing files deleted).")
    ignore_cb = _build_ignore()
    external = [n for n in final if _catalog_flag(n, "external")]
    final = [n for n in final if n not in external]
    for name in final:
        src = SKILLS_DIR / name
        dst = dest_skills / name
        exists = dst.exists()
        if not exists:
            tag = "new"
        elif force:
            tag = "replace"
        else:
            tag = "merge"
        if apply:
            dest_skills.mkdir(parents=True, exist_ok=True)
            if exists and force:
                shutil.rmtree(dst)
            # dirs_exist_ok=True -> overwrites only the distribution's files, leaving destination-only files intact
            shutil.copytree(src, dst, ignore=ignore_cb, dirs_exist_ok=True)
            print(f"  [installed] {name}  ({tag})")
        else:
            print(f"  [preview] {name}  (would {tag})")
    if external:
        print("\n── Skills not in this repo (need to be prepared manually) ──")
        for name in external:
            print(f"  ! {name}")
        print("  These are Anthropic-provided skills that cannot be redistributed under their license.")
        print("  Claude Code uses them automatically when working with the matching file type; if you")
        print("  don't have them, get them from Anthropic's own distribution and place them in ~/.claude/skills/.")
        print("  Details: docs/12_문서스킬_직접_준비하기.md")

    if not apply:
        print("\n* This is a preview. Re-run with --apply to actually install.")
    else:
        print(f"\nDone: installed {len(final)} skill(s).")
        _run_doctor_after_install()


def _run_doctor_after_install() -> None:
    """Automatically run doctor.py right after install.

    On a new machine, if the user only sees "install succeeded" and moves on,
    a problem like whether that environment has a shell the hooks can
    actually run on (check_shell_env) goes undiscovered unless someone
    separately remembers to run `python doctor.py`. The moment install
    finishes is the cheapest point to check that environment condition, so
    it runs right here. A failure does not roll back the install itself —
    doctor is a diagnostic tool, not an install-blocking gate.
    """
    import subprocess
    doctor_path = ROOT / "doctor.py"
    if not doctor_path.is_file():
        return

    # doctor.py owns the timeout for its own --quick mode; importing it (rather
    # than hardcoding a duplicate number here) keeps the two in sync if quick
    # mode's check list ever changes.
    timeout_sec = 60
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import doctor as _doctor_mod
        timeout_sec = _doctor_mod.QUICK_MODE_TIMEOUT_SEC
    except (ImportError, AttributeError):
        pass

    # NOTE: this header string must stay byte-identical to the marker
    # tests/test_install_doctor_onboarding.py checks for verbatim
    # ("설치 후 자동 점검 (doctor.py)") — do not translate it without
    # updating that test too (that file is outside this lane).
    print("\n── 설치 후 자동 점검 (doctor.py) ──")
    print("  (quick environment check only — for the full self-test, run `python doctor.py` directly)")
    try:
        proc = subprocess.run(
            [sys.executable, str(doctor_path), "--quick"], cwd=str(ROOT),
            timeout=timeout_sec)
        if proc.returncode != 0:
            print("  ⚠ doctor.py reported FAIL — check the output above.")
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"  ⚠ Automatic doctor.py run failed: {exc}")
        print(f"  Run it manually: python {doctor_path}")


# ── main ────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(
        description="sci-toolkit à la carte installer — install only the features you want")
    ap.add_argument("--list", action="store_true", help="Print the catalog/presets only, then exit")
    ap.add_argument("--preset", help="Preset key (paper-writing/literature/molbio/data-figures/documents/all)")
    ap.add_argument("--skills", help="Comma-separated list of individual skills (e.g. docx,xlsx)")
    ap.add_argument("--dest", default=None,
                    help="Install destination folder (auto-decided based on the detected agent if omitted)")
    ap.add_argument("--apply", action="store_true", help="Actually copy (preview if omitted)")
    ap.add_argument("--force", action="store_true",
                    help="Replace the destination skill folder entirely (also deletes destination-only files). "
                         "The default is a non-destructive merge; use this option only when explicitly needed.")
    args = ap.parse_args()

    _shell_env_notice()

    cat = load_catalog()

    if args.list:
        print_catalog(cat)
        return

    # 1) Decide the selection
    if args.preset:
        selection = expand_preset(args.preset, cat)
    elif args.skills:
        selection = [s.strip() for s in args.skills.split(",") if s.strip()]
    else:
        selection = interactive_select(cat)

    # 2) Resolve dependencies
    final, pulled_by = resolve(selection, cat)

    # 3) Summary
    print("\n── Install summary ──")
    print(f"Chosen skills ({len(selection)}): {', '.join(sorted(set(selection)))}")
    if pulled_by:
        print("Auto-added required dependencies:")
        for dep, srcs in sorted(pulled_by.items()):
            print(f"  + {dep}  <- needed by {', '.join(srcs)}")
    print(f"Final install target: {len(final)} ({fmt_size(total_size_kb(final, cat))})")

    # 4) Install
    if args.dest:
        dest = Path(args.dest).expanduser()
    else:
        dest, why = default_dest()
        # NOTE: "자동 결정" ("auto-decided") below is asserted on verbatim by
        # tests/test_install_nondestructive.py (outside this lane) — do not
        # translate/remove it without updating that test too.
        print(f"\nNo install location given, so it was 자동 결정 (auto-decided) — {why}")
        print(f"  {dest}")
        print("  To install elsewhere, use --dest <path>.")
    install(final, dest, args.apply, force=args.force)


if __name__ == "__main__":
    main()
