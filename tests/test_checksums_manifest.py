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


def check_single_sha256_implementation() -> None:
    """The manifest writer and the manifest verifier must hash with ONE function.

    Both used to carry their own copy of the loop (make_checksums.sha256,
    doctor_lib.checks_repo._sha256_of). They now import doctor_lib.filehash.
    Checked three ways: identity (no second implementation crept back), known
    vectors + chunk-boundary files against hashlib, and the adverse cases (one
    flipped byte changes the digest; an unreadable path raises instead of
    returning a digest of nothing).
    """
    global checks
    import hashlib
    import importlib.util
    import tempfile

    checks += 1

    sys.path.insert(0, str(ROOT))
    from doctor_lib import checks_repo
    from doctor_lib.filehash import sha256_file

    spec = importlib.util.spec_from_file_location(
        "make_checksums_under_test", ROOT / "scripts" / "make_checksums.py")
    mc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mc)
    if mc.sha256 is not sha256_file:
        failures.append("scripts/make_checksums.py hashes with its own function, not doctor_lib.filehash.sha256_file")
    if checks_repo._sha256_of is not sha256_file:
        failures.append("doctor_lib/checks_repo.py verifies with its own function, not doctor_lib.filehash.sha256_file")

    chunk = 1 << 20
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        cases = {"empty": b"", "abc": b"abc", "one-chunk": b"x" * chunk,
                 "chunk+1": b"y" * (chunk + 1), "two-chunks": bytes(range(256)) * (2 * chunk // 256)}
        for label, data in cases.items():
            f = base / label
            f.write_bytes(data)
            if sha256_file(f) != hashlib.sha256(data).hexdigest():
                failures.append(f"sha256_file({label}) disagrees with hashlib")
        if sha256_file(base / "abc") != "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad":
            failures.append("sha256_file(b'abc') is not the published SHA-256 test vector")
        # Adverse: flip the byte that sits exactly on the chunk boundary.
        flipped = bytearray(cases["chunk+1"])
        flipped[chunk] ^= 0x01
        g = base / "flipped"
        g.write_bytes(bytes(flipped))
        if sha256_file(g) == sha256_file(base / "chunk+1"):
            failures.append("a one-bit change at the chunk boundary did not change the digest")
        # Adverse: unreadable path must raise, not hash nothing.
        try:
            sha256_file(base / "does-not-exist")
        except OSError:
            pass
        else:
            failures.append("sha256_file on a missing path returned instead of raising OSError")


def main() -> int:
    check_single_sha256_implementation()
    if not MANIFEST.exists() or not in_git_repo():
        why = ("no SHA256SUMS present" if not MANIFEST.exists()
               else "not a git repository (treating this as a distributed copy)")
        if failures:  # the hasher check above does not need git
            print(f"FAIL — {len(failures)} issue(s)")
            for f in failures:
                print(f"  - {f}")
            return 1
        print(f"SKIP — {why}")
        return 0

    check_no_untracked_entries()
    check_worktree_eol_matches_policy()
    check_manifest_is_current()

    if failures:
        print(f"FAIL — {len(failures)} issue(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"ALL PASS — {checks} manifest check(s) (hasher / untracked / line-endings / freshness)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
