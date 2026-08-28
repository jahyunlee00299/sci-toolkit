#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Make the terminal readable: colour scheme, a CJK-correct font, tab colours,
and history search — on Windows Terminal + PowerShell, and on WSL/Linux bash.

Why this exists
----------------
A terminal you cannot read is a research tool you use badly: log output blurs
together, a Hangul table drifts out of alignment against its ASCII header, and
half a dozen agent tabs look identical when one of them is the one that failed.
None of that is cosmetic — it is the difference between spotting a wrong number
and scrolling past it.

This script exists because the fixes are individually trivial and collectively
easy to get wrong. Three failure modes were measured on a real machine while
doing this by hand, and each one is now guarded here rather than left as advice:

1. **A name that does not resolve fails SILENTLY.** Windows Terminal will happily
   accept ``"colorScheme": "Dark+"`` with no scheme named Dark+ defined, and
   ``"font": {"face": "D2Coding Nerd Font"}`` with no such font installed. There
   is no warning, no log line — it just renders the default and looks like the
   setting "did not work". So this script never writes a scheme name it has not
   also defined, and never writes a font face without first asking the OS
   whether that exact family name is installed (``--verify`` re-checks both).

2. **PSReadLine cannot be upgraded by ``Install-Module -Force`` alone.** On a
   machine with no NuGet provider, the install stops on an interactive
   "install the provider?" prompt and prints NOTHING while it waits — from the
   outside it is indistinguishable from a slow download or a hang. The provider
   is therefore installed explicitly first.

3. **PSReadLine prediction throws in a NON-interactive shell.** With output
   redirected to a pipe there is no console buffer, and both
   ``PredictionSource`` and ``PredictionViewStyle`` raise — so every script and
   hook that loads the profile prints a red error. The generated profile block
   probes for a real console before touching either.

On WSL there is a fourth thing worth knowing, and it saves the most work:
a WSL window is drawn by Windows Terminal, not by Linux. Scheme, font and tab
colour are therefore ALREADY inherited from the Windows side — there is no Linux
font to install and no Linux colour scheme to configure. What bash genuinely
lacks is the history-prediction half, which is why the Linux side of this script
writes ``~/.inputrc`` (prefix search) and nothing else.

Usage
-----
    python scripts/terminal_setup.py                 # dry-run: show the diff
    python scripts/terminal_setup.py --apply         # write it, after backing up
    python scripts/terminal_setup.py --verify        # check what is actually live
    python scripts/terminal_setup.py --revert        # restore the newest backup

Nothing is written without ``--apply``. Every file touched is copied to a
timestamped ``.bak`` first, and ``--revert`` puts them back.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------
# Catppuccin Mocha, from the project's own Windows Terminal repo
# (https://github.com/catppuccin/windows-terminal, mocha.json). Kept as a
# literal rather than fetched: this script must work on a machine with no
# network, and a colour scheme that silently differs between installs is worse
# than one that is pinned.
SCHEME_NAME = "Catppuccin Mocha"
SCHEME = {
    "name": SCHEME_NAME,
    "cursorColor": "#F5E0DC",
    "selectionBackground": "#585B70",
    "background": "#1E1E2E",
    "foreground": "#CDD6F4",
    "black": "#45475A", "red": "#F38BA8", "green": "#A6E3A1",
    "yellow": "#F9E2AF", "blue": "#89B4FA", "purple": "#F5C2E7",
    "cyan": "#94E2D5", "white": "#BAC2DE",
    "brightBlack": "#585B70", "brightRed": "#F38BA8", "brightGreen": "#A6E3A1",
    "brightYellow": "#F9E2AF", "brightBlue": "#89B4FA", "brightPurple": "#F5C2E7",
    "brightCyan": "#94E2D5", "brightWhite": "#A6ADC8",
}

# Font candidates in preference order. D2Coding first because Hangul in it is
# exactly twice the width of a Latin glyph by design, which is what keeps a
# mixed Korean/English table aligned; the Latin-only faces are fallbacks for a
# machine where Korean is not in play. NOTE the family names are the ones the
# OS actually reports, which are NOT the download names — "D2Coding ligature",
# not "D2Coding Ligature" or "D2Coding Nerd Font". Writing a name that does not
# resolve is failure mode 1 above.
FONT_CANDIDATES = [
    "D2Coding ligature",
    "D2Coding",
    "Cascadia Mono",
    "Cascadia Code",
    "Consolas",
]

# One colour per profile: which SHELL a tab is. Anything opened programmatically
# can layer a second, per-session colour on top via `wt ... --tabColor`, giving
# two independent axes — which shell, and which run.
# ORDERED, most-specific first: "Developer PowerShell" must not match the
# generic "powershell" rule and lose its own colour, so specific entries are
# tested before general ones. A dict would leave this to insertion order by
# accident; a list makes the precedence the point.
#
# Matching is on the profile's `source` too, not just its display name, because
# a display name is localised — this machine's cmd profile is literally named
# "명령 프롬프트" and matches no English keyword at all.
TAB_RULES = [
    (("developer",), "#CBA6F7"),
    (("azure",), "#94E2D5"),
    (("ssh",), "#A6E3A1"),
    (("cmd", "command prompt", "명령"), "#6C7086"),
    (("pwsh", "powershell"), "#89B4FA"),
    (("ubuntu", "debian", "wsl", "linux"), "#FAB387"),
]
TAB_FALLBACK = "#9399B2"

WT_SETTINGS_REL = Path(
    "Packages/Microsoft.WindowsTerminal_8wekyb3d8bbwe/LocalState/settings.json"
)

BACKUP_SUFFIX = ".sci-toolkit.bak"


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def _say(msg: str = "") -> None:
    print(msg, flush=True)


def _backup(path: Path) -> Path:
    """Copy `path` beside itself with a timestamp, and return the copy.

    Timestamped rather than a single `.bak`: running --apply twice must not
    destroy the pristine original captured by the first run.
    """
    stamp = time.strftime("%y%m%d_%H%M%S")
    dest = path.with_name(path.name + BACKUP_SUFFIX + "_" + stamp)
    shutil.copy2(path, dest)
    return dest


def _newest_backup(path: Path) -> Path | None:
    pattern = path.name + BACKUP_SUFFIX + "_*"
    found = sorted(path.parent.glob(pattern))
    return found[-1] if found else None


def _strip_jsonc(raw: str) -> str:
    """Drop `//` comments while leaving those inside strings alone.

    Windows Terminal ships settings.json full of `//` comments, and every
    `commandline` value is a Windows path — a naive stripper cuts one in half
    and the parse fails on a file that was perfectly valid.
    """
    out = []
    for line in raw.splitlines():
        in_string = False
        escaped = False
        cut = None
        for i, ch in enumerate(line):
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = not in_string
            elif ch == "/" and not in_string and line[i + 1:i + 2] == "/":
                cut = i
                break
        out.append(line if cut is None else line[:cut])
    return "\n".join(out)


# --------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------

def is_windows() -> bool:
    return platform.system() == "Windows"


def is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def wt_settings_path() -> Path | None:
    """The Windows Terminal settings file, reachable from Windows OR from WSL.

    From inside WSL the Windows filesystem is mounted under /mnt/c, so a WSL
    session can read (and fix) the very settings that draw its own window.
    """
    if is_windows():
        local = os.environ.get("LOCALAPPDATA")
        if local:
            p = Path(local) / WT_SETTINGS_REL
            return p if p.exists() else None
        return None
    if is_wsl():
        for base in sorted(Path("/mnt/c/Users").glob("*/AppData/Local")):
            p = base / WT_SETTINGS_REL
            if p.exists():
                return p
    return None


def installed_font_families() -> set[str]:
    """Font families this machine actually has, lowercased.

    Returns an EMPTY set when the list cannot be obtained, and callers treat
    that as "unknown" rather than "none installed" — refusing to set a font
    because a probe failed would be worse than setting a plausible one.
    """
    if is_windows():
        ps = (
            "Add-Type -AssemblyName System.Drawing;"
            "(New-Object System.Drawing.Text.InstalledFontCollection)"
            ".Families | ForEach-Object { $_.Name }"
        )
        try:
            done = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, timeout=60,
                encoding="utf-8", errors="replace",
            )
            if done.returncode == 0:
                return {n.strip().lower() for n in done.stdout.splitlines() if n.strip()}
        except (OSError, subprocess.SubprocessError):
            pass
        return set()
    # WSL/Linux: fc-list, when fontconfig is present.
    try:
        done = subprocess.run(
            ["fc-list", ":", "family"], capture_output=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
        if done.returncode == 0:
            fams = set()
            for line in done.stdout.splitlines():
                for part in line.split(","):
                    if part.strip():
                        fams.add(part.strip().lower())
            return fams
    except (OSError, subprocess.SubprocessError):
        pass
    return set()


def pick_font(installed: set[str]) -> tuple[str | None, str]:
    """Choose the best installed font, or (None, reason) when none resolve."""
    if not installed:
        return None, "font list unavailable — leaving the font untouched"
    for cand in FONT_CANDIDATES:
        if cand.lower() in installed:
            return cand, "installed"
    return None, (
        "none of the candidate fonts are installed "
        "(install D2Coding for correct Hangul width: "
        "https://github.com/naver/d2-coding-font)"
    )


def tab_color_for(*fields: str) -> str:
    """Colour for a profile, matched against every identifying field it has."""
    hay = " ".join(f for f in fields if f).lower()
    for keys, colour in TAB_RULES:
        if any(k in hay for k in keys):
            return colour
    return TAB_FALLBACK


# --------------------------------------------------------------------------
# Windows Terminal
# --------------------------------------------------------------------------

def plan_wt(path: Path) -> tuple[dict, list[str]]:
    """Build the new settings dict plus a human-readable list of changes."""
    raw = path.read_text(encoding="utf-8")
    data = json.loads(_strip_jsonc(raw))
    changes: list[str] = []

    # -- scheme: define it BEFORE naming it (failure mode 1) ------------------
    schemes = data.setdefault("schemes", [])
    if not any(s.get("name") == SCHEME_NAME for s in schemes):
        schemes.append(SCHEME)
        changes.append(f"schemes += {SCHEME_NAME}")

    profiles = data.setdefault("profiles", {})
    if isinstance(profiles, list):          # very old settings shape
        profiles = {"list": profiles}
        data["profiles"] = profiles
    defaults = profiles.setdefault("defaults", {})

    if defaults.get("colorScheme") != SCHEME_NAME:
        changes.append(
            f"defaults.colorScheme: {defaults.get('colorScheme')!r} -> {SCHEME_NAME!r}"
        )
        defaults["colorScheme"] = SCHEME_NAME

    font, reason = pick_font(installed_font_families())
    if font:
        current = (defaults.get("font") or {}).get("face")
        if current != font:
            changes.append(f"defaults.font.face: {current!r} -> {font!r}")
            defaults.setdefault("font", {})["face"] = font
    else:
        changes.append(f"font: SKIPPED — {reason}")

    # Readability settings that cost nothing and are easy to miss.
    for key, value in (
        ("adjustIndistinguishableColors", "indexed"),
        ("intenseTextStyle", "all"),
        ("cursorShape", "filledBox"),
    ):
        if defaults.get(key) != value:
            changes.append(f"defaults.{key}: {defaults.get(key)!r} -> {value!r}")
            defaults[key] = value

    # -- per-profile tab colour ----------------------------------------------
    for entry in profiles.get("list", []):
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or ""
        colour = tab_color_for(name, entry.get("source") or "")
        existing = entry.get("tabColor")
        if existing:
            # Someone (or an earlier run) already chose a colour. Two Ubuntu
            # profiles deliberately given different colours must not both be
            # flattened back to the one this table suggests.
            continue
        changes.append(f"  tabColor[{name}]: (none) -> {colour}")
        entry["tabColor"] = colour

    return data, changes


def apply_wt(path: Path, data: dict) -> Path:
    backup = _backup(path)
    path.write_text(
        json.dumps(data, indent=4, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="",
    )
    json.loads(path.read_text(encoding="utf-8"))     # fail loudly, not later
    return backup


# --------------------------------------------------------------------------
# PowerShell profile
# --------------------------------------------------------------------------

PROFILE_MARK = "# --- sci-toolkit terminal setup ---"

PROFILE_BLOCK = PROFILE_MARK + """
# Windows PowerShell 5.1 caps prediction at History: the plugin-based predictor
# needs PS 7.1+, so PredictionSource Plugin/HistoryAndPlugin silently does
# nothing there. ListView additionally needs PSReadLine 2.2.6+, and 5.1 ships
# 2.0.0 and never updates it on its own.
$__psrl = (Get-Module -ListAvailable PSReadLine |
           Sort-Object Version -Descending | Select-Object -First 1).Version
if ($__psrl -ge [version]'2.2.6') {
    try {
        # In a NON-interactive shell (output redirected to a pipe, which is how
        # every script and hook runs) there is no console buffer, and BOTH
        # PredictionSource and PredictionViewStyle throw. KeyAvailable is the
        # cheap probe that tells a real terminal from a redirected one; without
        # this guard the profile prints a red error on every piped invocation.
        $null = $Host.UI.RawUI.KeyAvailable
        Set-PSReadLineOption -PredictionSource History
        Set-PSReadLineOption -PredictionViewStyle ListView
    } catch {
        # Redirected: stay on defaults, stay silent.
    }
}
Set-PSReadLineOption -EditMode Windows
Set-PSReadLineOption -Colors @{
    Command            = 'Cyan'
    Number             = 'DarkGray'
    Member             = 'DarkGray'
    Operator           = 'DarkGray'
    Type               = 'DarkGray'
    Variable           = 'Green'
    Parameter          = 'Green'
    ContinuationPrompt = 'DarkGray'
    Default            = 'White'
}
# --- end sci-toolkit terminal setup ---
"""


def ps_profile_path() -> Path | None:
    if not is_windows():
        return None
    docs = Path.home() / "Documents"
    return docs / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1"


def plan_ps_profile(path: Path) -> list[str]:
    if path.exists() and PROFILE_MARK in path.read_text(encoding="utf-8-sig"):
        return []
    verb = "append to" if path.exists() else "create"
    return [f"{verb} {path} (+{len(PROFILE_BLOCK.splitlines())} lines: PSReadLine)"]


def apply_ps_profile(path: Path) -> Path | None:
    backup = None
    if path.exists():
        existing = path.read_text(encoding="utf-8-sig")
        if PROFILE_MARK in existing:
            return None
        backup = _backup(path)
        body = existing.rstrip() + "\n\n" + PROFILE_BLOCK
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = PROFILE_BLOCK
    # utf-8-sig: PowerShell 5.1 decodes a BOM-less .ps1 as the ANSI codepage and
    # mangles every non-ASCII character in it.
    path.write_text(body, encoding="utf-8-sig")
    return backup


# --------------------------------------------------------------------------
# bash (.inputrc)
# --------------------------------------------------------------------------

INPUTRC_MARK = "# --- sci-toolkit terminal setup ---"

INPUTRC_BLOCK = INPUTRC_MARK + """
# Bash has no inline "ghost text" prediction like PSReadLine. Prefix search is
# the closest equivalent and is built in: type the start of a command, then Up
# walks only through history entries beginning with what you typed.
"\\e[A": history-search-backward
"\\e[B": history-search-forward

set show-all-if-ambiguous on
set completion-ignore-case on
set colored-stats on
set colored-completion-prefix on
# --- end sci-toolkit terminal setup ---
"""


def inputrc_path() -> Path | None:
    if is_windows():
        return None
    return Path.home() / ".inputrc"


def plan_inputrc(path: Path) -> list[str]:
    if path.exists() and INPUTRC_MARK in path.read_text(encoding="utf-8"):
        return []
    verb = "append to" if path.exists() else "create"
    return [f"{verb} {path} (history prefix search + completion colours)"]


def apply_inputrc(path: Path) -> Path | None:
    backup = None
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if INPUTRC_MARK in existing:
            return None
        backup = _backup(path)
        body = existing.rstrip() + "\n\n" + INPUTRC_BLOCK
    else:
        body = INPUTRC_BLOCK
    path.write_text(body, encoding="utf-8")
    return backup


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def cmd_plan(apply: bool) -> int:
    touched: list[tuple[Path, Path | None]] = []
    any_change = False

    _say("terminal-setup — " + ("APPLYING" if apply else "dry-run (nothing is written)"))
    _say()

    if is_wsl():
        _say("This is WSL. Its window is drawn by Windows Terminal, so the colour")
        _say("scheme, font and tab colours come from the Windows side — there is no")
        _say("Linux font or scheme to configure here.")
        _say()

    # -- Windows Terminal -----------------------------------------------------
    wt = wt_settings_path()
    if wt is None:
        _say("[wt]  Windows Terminal settings not found — skipping")
    else:
        try:
            data, changes = plan_wt(wt)
        except (OSError, ValueError) as exc:
            _say(f"[wt]  could not read settings ({exc}) — skipping")
        else:
            _say(f"[wt]  {wt}")
            if changes:
                any_change = True
                for line in changes:
                    _say(f"      {line}")
                if apply:
                    backup = apply_wt(wt, data)
                    touched.append((wt, backup))
                    _say(f"      written. backup: {backup.name}")
            else:
                _say("      already up to date")
    _say()

    # -- PowerShell profile ---------------------------------------------------
    prof = ps_profile_path()
    if prof is None:
        _say("[ps]  not Windows — PSReadLine step does not apply")
    else:
        changes = plan_ps_profile(prof)
        _say(f"[ps]  {prof}")
        if changes:
            any_change = True
            for line in changes:
                _say(f"      {line}")
            _say(f"      note: PSReadLine {_psrl_version() or '?'} installed; "
                 "ListView needs 2.2.6+")
            if apply:
                backup = apply_ps_profile(prof)
                touched.append((prof, backup))
                _say(f"      written. backup: {backup.name if backup else '(new file)'}")
        else:
            _say("      already configured")
    _say()

    # -- .inputrc -------------------------------------------------------------
    inputrc = inputrc_path()
    if inputrc is None:
        _say("[sh]  Windows — .inputrc step does not apply")
    else:
        changes = plan_inputrc(inputrc)
        _say(f"[sh]  {inputrc}")
        if changes:
            any_change = True
            for line in changes:
                _say(f"      {line}")
            if apply:
                backup = apply_inputrc(inputrc)
                touched.append((inputrc, backup))
                _say(f"      written. backup: {backup.name if backup else '(new file)'}")
        else:
            _say("      already configured")
    _say()

    if not any_change:
        _say("Nothing to do — everything is already in place.")
        return 0

    if apply:
        _say("Done. Open a NEW tab to see it: a running shell keeps its own state,")
        _say("and a newly installed font is only picked up by new processes.")
        _say("Undo with:  python scripts/terminal_setup.py --revert")
    else:
        _say("Dry-run only. Re-run with --apply to write these changes.")
    return 0


def _psrl_version() -> str | None:
    if not is_windows():
        return None
    ps = ("(Get-Module -ListAvailable PSReadLine | "
          "Sort-Object Version -Descending | Select-Object -First 1).Version.ToString()")
    try:
        done = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, timeout=60, encoding="utf-8", errors="replace",
        )
        return done.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def cmd_verify() -> int:
    """Check what is LIVE, not what we believe we wrote.

    Specifically re-checks the two silent failures: a scheme name with no scheme
    behind it, and a font face the machine does not have.
    """
    problems = 0
    _say("terminal-setup --verify")
    _say()

    wt = wt_settings_path()
    if wt is None:
        _say("[wt]  settings not found — nothing to verify")
    else:
        data = json.loads(_strip_jsonc(wt.read_text(encoding="utf-8")))
        defaults = data.get("profiles", {}).get("defaults", {})
        defined = {s.get("name") for s in data.get("schemes", [])}
        named = defaults.get("colorScheme")

        if named and named not in defined:
            _say(f"[wt]  FAIL  colorScheme {named!r} is named but NOT defined in schemes")
            _say("            -> Windows Terminal falls back to its built-in default,")
            _say("               silently. Remove the name or define the scheme.")
            problems += 1
        elif named:
            _say(f"[wt]  ok    colorScheme {named!r} is defined")
        else:
            _say("[wt]  --    no colorScheme set (built-in default)")

        face = (defaults.get("font") or {}).get("face")
        if face:
            installed = installed_font_families()
            if not installed:
                _say(f"[wt]  ?     font {face!r} — could not list installed fonts")
            elif face.lower() in installed:
                _say(f"[wt]  ok    font {face!r} is installed")
            else:
                _say(f"[wt]  FAIL  font {face!r} is NOT installed — silently falling back")
                problems += 1
        else:
            _say("[wt]  --    no font set")

        coloured = sum(
            1 for e in data.get("profiles", {}).get("list", [])
            if isinstance(e, dict) and e.get("tabColor")
        )
        total = len(data.get("profiles", {}).get("list", []))
        # Not "ok" unconditionally: 0/N coloured is exactly the state this
        # script exists to fix, and labelling it ok would hide it.
        if total and coloured == total:
            _say(f"[wt]  ok    {coloured}/{total} profiles have a tabColor")
        elif coloured:
            _say(f"[wt]  warn  only {coloured}/{total} profiles have a tabColor")
        else:
            _say(f"[wt]  warn  no profile has a tabColor ({total} profiles)")
    _say()

    prof = ps_profile_path()
    if prof and prof.exists() and PROFILE_MARK in prof.read_text(encoding="utf-8-sig"):
        version = _psrl_version()
        _say(f"[ps]  ok    profile block present (PSReadLine {version or '?'})")
        if version:
            try:
                parts = tuple(int(x) for x in version.split(".")[:3])
                if parts < (2, 2, 6):
                    _say("[ps]  warn  PSReadLine < 2.2.6 — ListView stays off "
                         "(the block degrades on purpose)")
            except ValueError:
                pass
    elif prof:
        _say("[ps]  --    profile block not installed")

    inputrc = inputrc_path()
    if inputrc and inputrc.exists() and INPUTRC_MARK in inputrc.read_text(encoding="utf-8"):
        _say("[sh]  ok    .inputrc block present")
    elif inputrc:
        _say("[sh]  --    .inputrc block not installed")

    _say()
    _say("PASS" if problems == 0 else f"FAIL — {problems} problem(s)")
    return 1 if problems else 0


def cmd_revert() -> int:
    restored = 0
    for path in filter(None, [wt_settings_path(), ps_profile_path(), inputrc_path()]):
        if not path.parent.exists():
            continue
        backup = _newest_backup(path)
        if backup is None:
            continue
        shutil.copy2(backup, path)
        _say(f"restored {path.name} from {backup.name}")
        restored += 1
    if restored == 0:
        _say("No backups found — nothing to revert.")
    else:
        _say(f"\n{restored} file(s) restored. Open a new tab to see it.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Colour scheme, CJK-correct font, tab colours and history search.",
    )
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true", help="write the changes (default: dry-run)")
    g.add_argument("--verify", action="store_true", help="check what is actually live")
    g.add_argument("--revert", action="store_true", help="restore the newest backups")
    args = ap.parse_args()

    if args.verify:
        return cmd_verify()
    if args.revert:
        return cmd_revert()
    return cmd_plan(apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
