#!/usr/bin/env python3
"""Guards that the SHA256SUMS manifest is also correct **in someone else's clone**.

doctor's integrity check always passes when run on the machine that built the
manifest — the hashes are generated from that working tree and verified
against that same working tree. So two kinds of bug stayed invisible locally
and only blew up in CI (260807, measured):

1. **Local build artifacts end up in the manifest.** Six files under `out/`
   had been recorded, and a fresh clone doesn't have them, so it fails
   unconditionally with "6 missing." `.gitignore` did have `out/*`, but
   make_checksums only reads `.distignore`.
2. **Line endings differ per platform.** Building the manifest from a
   Windows working tree left in CRLF produces 125 mismatches once CI/Linux
   checks it out as LF. `.gitattributes` already pinned
   `* text=auto eol=lf`, but the existing checkout hadn't been
   renormalized, so policy and disk had drifted apart.

Both checks measure against git. If git isn't present or this isn't inside a
repo, skip — this might be running from a USB copy, and treating that as a
failure would be a false positive.
"""
from __future__ import annotations

import subprocess
import sys

# A Korean Windows console is cp949, which cannot encode the em dash this file
# prints on failure. Without this the test dies with UnicodeEncodeError *while
# reporting a failure*, so doctor.py showed a red self-test whose only visible
# detail was the encoding crash — hiding whatever the real verdict was.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "SHA256SUMS"

failures: list[str] = []
checks = 0


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args],
                          capture_output=True, timeout=60)


def in_git_repo() -> bool:
    try:
        return git("rev-parse", "--git-dir").returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def tracked_files() -> set[str]:
    out = git("ls-files", "-z").stdout
    return {p.decode("utf-8", "surrogateescape") for p in out.split(b"\0") if p}


def manifest_paths() -> list[str]:
    paths = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        _, _, name = line.partition(" *")
        name = name.strip()
        if name.startswith("./"):
            name = name[2:]
        if name:
            paths.append(name)
    return paths


def check_no_untracked_entries() -> None:
    """Every entry in the manifest must be committed to git."""
    global checks
    checks += 1
    stray = sorted(set(manifest_paths()) - tracked_files())
    if stray:
        failures.append(
            f"{len(stray)} untracked file(s) in the manifest: {stray[:5]}"
            " — a fresh clone won't have these, so doctor is guaranteed to fail")


def check_worktree_eol_matches_policy() -> None:
    """The working tree's line endings must match the .gitattributes policy."""
    global checks
    checks += 1
    out = git("ls-files", "--eol").stdout.decode("utf-8", "surrogateescape")
    bad = [ln for ln in out.splitlines()
           if " w/crlf" in ln and "eol=crlf" not in ln]
    if bad:
        failures.append(
            f"{len(bad)} file(s) are CRLF in the working tree but the policy says LF"
            " — building the manifest in this state mismatches everything on Linux/CI")


def check_manifest_is_current() -> None:
    """The manifest must match the current tree (make_checksums must be a no-op)."""
    global checks
    checks += 1
    script = ROOT / "scripts" / "make_checksums.py"
    proc = subprocess.run([sys.executable, str(script)],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300, cwd=str(ROOT))
    if proc.returncode != 0:
        failures.append(f"make_checksums was rejected (exit {proc.returncode}) — "
                        f"{(proc.stdout or '').strip().splitlines()[-1:] or ''}")
        return
    text = proc.stdout or ""
    # NOTE: these three labels are grepped literally from make_checksums.py's
    # own stdout (scripts/make_checksums.py:188-192), which prints them in
    # Korean by design — do not translate these three literals, only the
    # surrounding failure message.
    for label in ("[추가]", "[변경]", "[제거]"):
        if label in text:
            failures.append(
                f"SHA256SUMS is stale (has a {label} entry) — "
                "run `python scripts/make_checksums.py --apply` and commit the result")
            break


def main() -> int:
    if not MANIFEST.exists():
        print("SKIP — no SHA256SUMS present")
        return 0
    if not in_git_repo():
        print("SKIP — not a git repository (treating this as a distributed copy)")
        return 0

    check_no_untracked_entries()
    check_worktree_eol_matches_policy()
    check_manifest_is_current()

    if failures:
        print(f"FAIL — {len(failures)} issue(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"ALL PASS — {checks} manifest check(s) (untracked / line-endings / freshness)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
