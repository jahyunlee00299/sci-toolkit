#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_raw.py — Raw-data provenance & version-control gate (scientific-validation Axis 0).

Before a fit/model result is trusted, the RAW it came from must be:
  (1) committed to version control (not floating in Downloads / chat attachments),
  (2) hash-pinned so we can prove later WHICH bytes produced the number,
  (3) documented with a column map (header label -> meaning), because column-position
      mis-reads silently corrupt results (e.g. a byproduct column read as the product column).

This is the generalization of the pattern:
  data/<dataset>/{raw .xlsx} + README.md (provenance + column map + mis-read caveats).

USAGE
  check_raw.py <raw_file> [<raw_file> ...]
      For each raw file, check: tracked by git? clean (committed, not modified)? hash. And
      whether a sibling README/.md documents it + carries a column map.
  check_raw.py --dir <data_dir>
      Check every data-like file (.xlsx/.csv/.tsv/.json) under <data_dir> (non-recursive by
      default; --recursive to descend) the same way, plus warn on any file NOT in git.

It does NOT read the spreadsheet cells (that's the extraction step's job) — it audits the
*housekeeping* around the raw so a downstream number is reproducible and attributable.

EXIT CODE: 0 if every raw is git-COMMITTED, 1 otherwise (gate a pipeline / pre-commit).
"""
import sys
import os
import io
import json
import hashlib
import argparse
import subprocess

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

DATA_EXTS = {".xlsx", ".xls", ".csv", ".tsv", ".json", ".parquet", ".feather", ".h5", ".dat"}
# Column-map signal words: a README documenting raw columns tends to carry these.
COLMAP_HINTS = ("컬럼", "column", "col", "헤더", "header", "라벨", "label", "species", "timepoint", "단위", "unit")


def _git(args, cwd):
    try:
        out = subprocess.run(["git", "-C", cwd] + args, capture_output=True, text=True, timeout=15)
        return out.returncode, out.stdout.strip(), out.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def _repo_root(path):
    d = path if os.path.isdir(path) else os.path.dirname(path) or "."
    rc, root, _ = _git(["rev-parse", "--show-toplevel"], d)
    return root if rc == 0 else None


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_readme(path):
    """Look for a README/.md in the same directory that mentions the raw filename or columns."""
    d = os.path.dirname(os.path.abspath(path)) or "."
    base = os.path.basename(path)
    found = []
    for fn in os.listdir(d):
        if fn.lower().endswith((".md", ".txt")):
            full = os.path.join(d, fn)
            try:
                txt = open(full, encoding="utf-8", errors="replace").read()
            except Exception:
                continue
            # Mention = full filename present, or stem as a backticked/quoted token (not a bare English
            # word like 'data' matching anywhere).
            stem = os.path.splitext(base)[0]
            mentions_file = base in txt or any(f"{q}{stem}{q}" in txt for q in ("`", '"', "'")) or f"{stem}." in txt
            # Column-map signal: needs several hint words AND a structural marker (a markdown table pipe),
            # so generic prose ("a music label ... as a unit") no longer trivially counts as a column map.
            tl = txt.lower()
            hints = sum(1 for w in COLMAP_HINTS if w.lower() in tl)
            has_table = "|" in txt and txt.count("|") >= 3
            has_colmap = hints >= 3 and has_table
            if mentions_file or has_colmap:
                found.append((fn, mentions_file, has_colmap))
    return found


def check_one(path):
    """Return (verdict, rows) for a single raw file."""
    rows = []
    order = {"PASS": 0, "CAUTION": 1, "FAIL": 2}
    worst = "PASS"

    def bump(v):
        nonlocal worst
        if order[v] > order[worst]:
            worst = v

    if not os.path.exists(path):
        return ("FAIL", [f"  ❌ file not found: {path}"])

    root = _repo_root(path)
    if not root:
        bump("FAIL")
        rows.append(f"  ❌ NOT inside any git repo — raw must be version-controlled (committed)")
        return (worst, rows)

    rel = os.path.relpath(os.path.abspath(path), root).replace(os.sep, "/")
    # tracked?
    rc, _, _ = _git(["ls-files", "--error-unmatch", rel], root)
    if rc != 0:
        bump("FAIL")
        rows.append(f"  ❌ UNTRACKED by git ({rel}) — `git add` + commit it (no floating raw)")
    else:
        # COMMITTED check: ls-files reports staged-but-never-committed files as tracked too, but the
        # contract is "committed". Verify the path actually exists in HEAD; if not, it's staged-only.
        rc_head, _, _ = _git(["cat-file", "-e", f"HEAD:{rel}"], root)
        if rc_head != 0:
            bump("FAIL")
            rows.append(f"  ❌ STAGED but NOT committed ({rel}) — commit it; a staged-only raw is still floating")
        else:
            rows.append(f"  ✅ committed to git: {rel}")
        # modified vs committed?
        rc2, st, _ = _git(["status", "--porcelain", "--", rel], root)
        if st:
            bump("CAUTION")
            rows.append(f"  ⚠️  working copy DIFFERS from last commit ({st.split()[0]}) — commit before trusting downstream numbers")

    # hash for attribution
    try:
        rows.append(f"  🔑 sha256={_sha256(path)[:16]}…  (record this with the result for reproducibility)")
    except Exception as e:
        rows.append(f"  (hash failed: {e})")

    # README / column map
    readmes = _find_readme(path)
    if not readmes:
        bump("CAUTION")
        rows.append(f"  ⚠️  no sibling README/.md documents this raw — add provenance + COLUMN MAP (header label→meaning) to avoid col mis-read")
    else:
        has_map = any(cm for _, _, cm in readmes)
        named = [fn for fn, m, _ in readmes if m]
        if named:
            rows.append(f"  ✅ documented in: {', '.join(named)}")
        if has_map:
            rows.append(f"  ✅ a sibling doc carries a column-map signal (header labels / units)")
        else:
            bump("CAUTION")
            rows.append(f"  ⚠️  sibling doc exists but no clear COLUMN MAP — confirm columns by header LABEL, never by position")

    return (worst, rows)


def main():
    ap = argparse.ArgumentParser(description="Raw-data provenance & version-control gate.")
    ap.add_argument("raw", nargs="*", help="raw file(s) to audit")
    ap.add_argument("--dir", help="audit all data files in a directory")
    ap.add_argument("--recursive", action="store_true", help="with --dir, descend into subdirs")
    ap.add_argument("--emit-json", action="store_true")
    args = ap.parse_args()

    targets = list(args.raw)
    if args.dir:
        for dirpath, dirnames, filenames in os.walk(args.dir):
            for fn in filenames:
                if os.path.splitext(fn)[1].lower() in DATA_EXTS:
                    targets.append(os.path.join(dirpath, fn))
            if not args.recursive:
                break
    if not targets:
        print("usage: check_raw.py <raw_file> ... | --dir <data_dir>", file=sys.stderr)
        sys.exit(2)

    print("=" * 70)
    print("RAW PROVENANCE & VERSION CONTROL  (scientific-validation Axis 0)")
    print("=" * 70)
    any_fail = False
    out = {}
    for t in targets:
        verdict, rows = check_one(t)
        icon = {"PASS": "✅", "CAUTION": "⚠️ ", "FAIL": "❌"}[verdict]
        print(f"{icon} {os.path.basename(t)}: {verdict}")
        for r in rows:
            print(r)
        out[t] = verdict
        if verdict == "FAIL":
            any_fail = True

    print("-" * 70)
    if any_fail:
        print("❌ At least one raw is NOT properly version-controlled. Commit it before trusting any number derived from it.")
    else:
        print("✅ All raw files are git-tracked. (Still confirm columns by header label, not position.)")
    if args.emit_json:
        print("\n--- JSON ---")
        print(json.dumps(out, ensure_ascii=False))
    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
