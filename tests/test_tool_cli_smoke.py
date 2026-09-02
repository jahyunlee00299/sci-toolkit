#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke tests for the standalone research tools under scripts/ and skills/*/scripts/.

Why this exists
---------------
Measured 2026-09-02: hplc_parser, jcr_batch_verify, excel_formula_check,
fetch_public_vector, primer_structure_check, variant_filter, convert_literature
and fetch_github shipped with no test and no doc naming them. A tool nobody
runs can break at import time and nobody notices until a user needs it.

What "smoke" means here
-----------------------
Every tool: ``--help`` exits 0 (imports resolve, argparse wiring intact).
Tools that work offline additionally run ONE real case end to end and the
output is re-parsed (never the tool's own success message):

  hplc_parser            synthetic two-peak chromatogram CSV -> JSON with 2 peaks
  primer_structure_check a hairpin-prone primer FAILS, a clean primer PASSES
  variant_filter         two tiny CSVs -> matrix with the expected PASS/FAIL rows

Network tools (jcr_batch_verify, fetch_public_vector, fetch_github) and the
Excel-COM tool (excel_formula_check) stop at ``--help``; their real path is
covered by the owning workflow, not here.

Run: python tests/test_tool_cli_smoke.py
"""
from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

ROOT = Path(__file__).resolve().parent.parent

TOOLS = {
    "hplc_parser": ROOT / "scripts" / "hplc_parser.py",
    "primer_structure_check": ROOT / "scripts" / "primer_structure_check.py",
    "variant_filter": ROOT / "scripts" / "variant_filter.py",
    "jcr_batch_verify": ROOT / "scripts" / "jcr_batch_verify.py",
    "fetch_public_vector": ROOT / "scripts" / "fetch_public_vector.py",
    "excel_formula_check": ROOT / "scripts" / "excel_formula_check.py",
    "convert_literature": ROOT / "skills" / "markitdown" / "scripts" / "convert_literature.py",
    "fetch_github": ROOT / "skills" / "web-scraping" / "scripts" / "fetch_github.py",
}

_results: list[tuple[bool, str]] = []


def check(name: str, cond: bool, note: str = "") -> None:
    _results.append((cond, name))
    tag = "[OK]  " if cond else "[FAIL]"
    print(f"  {tag} {name}" + (f"  {note}" if note and not cond else ""))


def skip(name: str, why: str) -> None:
    print(f"  [SKIP] {name}  {why}")


def section(title: str) -> None:
    print(f"\n== {title}")


def run(tool: Path, *args: str, cwd: Path | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(tool), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(cwd or ROOT), timeout=120)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


# --------------------------------------------------------------------------
section("--help exits 0 for every tool (imports + argparse wiring)")

for name, path in TOOLS.items():
    if not path.is_file():
        check(f"{name}: file present", False, str(path))
        continue
    rc, out, err = run(path, "--help")
    if name == "convert_literature" and rc != 0 and "markitdown" in (out + err):
        skip(f"{name}: --help", "markitdown package not installed on this machine")
        continue
    check(f"{name}: --help exits 0", rc == 0 and "usage" in (out + err).lower(),
          (out + err)[-300:])


# --------------------------------------------------------------------------
section("hplc_parser: synthetic two-peak chromatogram")

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    src = tmp / "sample.csv"
    rows = ["time,signal"]
    for i in range(0, 1200):
        t = i * 0.01  # 0 .. 12 min
        y = 100 * math.exp(-((t - 3.0) ** 2) / (2 * 0.05 ** 2)) \
            + 60 * math.exp(-((t - 7.5) ** 2) / (2 * 0.08 ** 2)) \
            + 0.2 * math.sin(i)  # tiny deterministic noise
        rows.append(f"{t:.3f},{y:.4f}")
    src.write_text("\n".join(rows) + "\n", encoding="utf-8")

    rc, out, err = run(TOOLS["hplc_parser"], str(src), "--json")
    check("exit 0", rc == 0, err[-300:])
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        data = None
    check("stdout is JSON", data is not None, out[:200])
    if data:
        rec = data[0]
        check("chromatogram has 1200 points", len(rec.get("chromatogram", [])) == 1200,
              str(len(rec.get("chromatogram", []))))
        peaks = rec.get("peaks", [])
        check("exactly 2 peaks detected", len(peaks) == 2, f"got {len(peaks)}")
        rts = sorted(p.get("retention_time", -1) for p in peaks)
        check("retention times ~3.0 and ~7.5 min",
              len(rts) == 2 and abs(rts[0] - 3.0) < 0.1 and abs(rts[1] - 7.5) < 0.1, str(rts))
        check("area percents sum to ~100",
              abs(sum(p.get("area_percent", 0) for p in peaks) - 100) < 1.0,
              str([p.get("area_percent") for p in peaks]))

    # adverse: a file with no numeric rows must fail loudly, not emit an empty CSV
    bad = tmp / "bad.csv"
    bad.write_text("this is not a chromatogram\n", encoding="utf-8")
    rc, out, err = run(TOOLS["hplc_parser"], str(bad), "--json")
    check("non-chromatogram input -> nonzero exit or zero points, never a silent 2-peak result",
          rc != 0 or (out.strip() and len(json.loads(out)[0].get("peaks", [])) == 0),
          f"rc={rc} out={out[:120]}")


# --------------------------------------------------------------------------
section("primer_structure_check: hairpin FAIL vs clean PASS")

hairpin = "GGGGGGCCCCAAAAGGGGCCCCCC"   # strong self-complementary stem
clean = "ATGACCGATTAGCTTCAGCATCAAG"
rc, out, err = run(TOOLS["primer_structure_check"], hairpin, clean, "--threshold-hairpin", "-2.0")
check("exit 0", rc == 0, err[-300:])
try:
    res = json.loads(out)
except json.JSONDecodeError:
    res = None
check("stdout is a JSON list of 2", isinstance(res, list) and len(res) == 2, out[:200])
if isinstance(res, list) and len(res) == 2:
    by_seq = {r.get("seq") or r.get("sequence"): r for r in res}
    hp = by_seq.get(hairpin) or res[0]
    cl = by_seq.get(clean) or res[1]
    check("hairpin-prone primer fails hairpin check", hp.get("hairpin_pass") is False, str(hp))
    check("clean primer passes both checks",
          cl.get("hairpin_pass") is True and cl.get("homodimer_pass") is True, str(cl))
    check("dG reported as a number for the hairpin",
          isinstance(hp.get("hairpin_dg", hp.get("hairpin_dG")), (int, float)), str(hp))

# adverse: no input at all must be a usage error, not a traceback
rc, out, err = run(TOOLS["primer_structure_check"])
check("no sequences -> argparse error (exit 2), no traceback",
      rc == 2 and "Traceback" not in err, f"rc={rc} err={err[-200:]}")


# --------------------------------------------------------------------------
section("variant_filter: PASS/FAIL matrix from two CSVs")

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    ddg = tmp / "ddg.csv"
    ddg.write_text("variant,ddG_fold,pass_fail\nA10G,-1.2,PASS\nL55P,3.4,FAIL\nK90R,-0.3,PASS\n",
                   encoding="utf-8")
    pq = tmp / "primer.csv"
    pq.write_text("variant,pass\nA10G,True\nL55P,True\nK90R,False\n", encoding="utf-8")
    out_csv = tmp / "matrix.csv"
    rc, out, err = run(TOOLS["variant_filter"], "--ddg", str(ddg), "--primer-qc", str(pq),
                       "--output", str(out_csv))
    check("exit 0", rc == 0, err[-300:])
    check("matrix.csv written", out_csv.is_file())
    if out_csv.is_file():
        with out_csv.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        by_v = {r["variant"]: r for r in rows}
        check("3 variants in matrix", len(rows) == 3, str(rows))
        check("A10G overall PASS (both pass)", by_v.get("A10G", {}).get("overall_pass") == "PASS", str(by_v.get("A10G")))
        check("L55P overall FAIL (ddG fail)", by_v.get("L55P", {}).get("overall_pass") == "FAIL", str(by_v.get("L55P")))
        check("K90R overall FAIL (primer fail)", by_v.get("K90R", {}).get("overall_pass") == "FAIL", str(by_v.get("K90R")))

    # adverse: missing file must not produce an empty "all pass" matrix
    rc, out, err = run(TOOLS["variant_filter"], "--ddg", str(tmp / "nope.csv"),
                       "--output", str(tmp / "m2.csv"))
    check("missing input -> nonzero exit or no rows, never a silent PASS matrix",
          rc != 0 or not (tmp / "m2.csv").is_file()
          or len(list(csv.DictReader((tmp / "m2.csv").open(encoding="utf-8")))) == 0,
          f"rc={rc} err={err[-200:]}")


# --------------------------------------------------------------------------
n_fail = sum(1 for ok, _ in _results if not ok)
print(f"\nSUMMARY: {len(_results) - n_fail} passed, {n_fail} failed")
sys.exit(1 if n_fail else 0)
