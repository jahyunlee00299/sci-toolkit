#!/usr/bin/env python3
"""Regression test for the si_fetch.py / institutional_access.py / ref_fetch.py
collection gate.

Run: python tests/test_si_institutional.py   (exit 0 = pass)

Same convention as the existing test_doi_verify.py:
  1) parts that run without network (always executed)
  2) parts that need network — SKIP if unavailable, but must print "SKIP"
     (never pass silently)
"""
import importlib.util
import json
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, str(SCRIPTS / f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


si_fetch = _load("si_fetch")
institutional_access = _load("institutional_access")

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# --------------------------------------------------------------------------- #
section("Institutional link generation (institutional_access)")

reg = institutional_access.InstitutionRegistry.load()
check("config/institutions.json is read", "korea-univ" in reg.available(),
      f"got={reg.available()}")

link = reg.build_link("korea-univ", "https://example.com/article/1")
check("proxy link wraps the target URL",
      link is not None and link.url == "https://oca.korea.ac.kr/link.n2s?url=https://example.com/article/1",
      f"got={link.url if link else None}")

check("policy link and limits are included together",
      link is not None and link.fair_use_url and link.daily_limits.get("per_publisher") == 30,
      f"got={link.daily_limits if link else None}")

check("the notice states this is not an auto-download",
      link is not None and "공정이용 위반" in link.human_summary())

check("unknown institution key -> None (never silently builds the wrong link)",
      reg.build_link("no-such-institution", "https://example.com") is None)

check("empty target URL -> None", reg.build_link("korea-univ", "") is None)

# A template without the placeholder must not build a link (prevents a silently broken link).
bad = institutional_access.InstitutionRegistry(
    {"institutions": {"broken": {"proxy_url_template": "https://proxy.example/no-placeholder"}}}
)
check("template without the {url} placeholder -> None",
      bad.build_link("broken", "https://example.com/x") is None)

# Must not crash even without a config file (institutional config is optional).
missing = institutional_access.InstitutionRegistry.load(Path("does-not-exist-12345.json"))
check("missing config file -> empty registry (not an exception)", missing.available() == [])


# --------------------------------------------------------------------------- #
section("SI file detection / publisher branching (si_fetch)")

check("a MOESM file is classified as supplementary",
      si_fetch._looks_supplementary("13321_2015_69_MOESM1_ESM.docx"))
check("an _ESM file is classified as supplementary",
      si_fetch._looks_supplementary("12010_2021_3624_MOESM2_ESM.pdf"))
check("a body figure (Fig1_HTML.jpg) is not supplementary",
      not si_fetch._looks_supplementary("13321_2015_69_Fig1_HTML.jpg"))
check("an equation image (Article_IEq1.gif) is not supplementary either",
      not si_fetch._looks_supplementary("13321_2015_69_Article_IEq1.gif"))

check("Elsevier prefix is on the blocked list", "10.1016" in si_fetch.BLOCKED_PREFIXES)
check("ACS prefix is on the blocked list", "10.1021" in si_fetch.BLOCKED_PREFIXES)
check("Springer prefix is on the blocked list too (urllib only gets a reduced page)",
      "10.1007" in si_fetch.BLOCKED_PREFIXES)
check("DOI prefix extraction", si_fetch._prefix("10.1016/j.biortech.2019.122213") == "10.1016")

# Trusting an archive's internal path as-is lets the write location leak outside
# the target directory (zip-slip). Build a fake archive and check the real
# extraction path.
import io as _io
import zipfile as _zipfile

_buf = _io.BytesIO()
with _zipfile.ZipFile(_buf, "w") as _z:
    _z.writestr("nested/../../escaped_MOESM1_ESM.txt", "payload")
_fake = si_fetch.SIResult(
    doi="10.9999/zipslip-test",
    status="found",
    files=[si_fetch.SIFile(name="nested/../../escaped_MOESM1_ESM.txt", size=7,
                           is_supplementary=True)],
)
_fake._blob = _buf.getvalue()

with tempfile.TemporaryDirectory() as _td:
    _root = Path(_td)
    _got = si_fetch.download_si(_fake, _root, extract=True, si_only=True)
    _paths = [Path(f.extracted_path) for f in _got.files if f.extracted_path]
    _inside = all(_root.resolve() in p.resolve().parents for p in _paths)
    check("archive-internal paths stay inside the target directory (zip-slip prevented)",
          bool(_paths) and _inside,
          f"paths={[str(p) for p in _paths]}")


# --------------------------------------------------------------------------- #
section("collection gate (ref_fetch.py CLI) — no network required")

with tempfile.TemporaryDirectory() as td:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "ref_fetch.py"),
         "--doi", "10.1016/j.biortech.2019.122213",
         "--doi-source", "model",
         "--output", str(Path(td) / "r.json")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    out = proc.stdout + proc.stderr
    check("model source + no declared title -> collection blocked at entry (exit 2, BLOCKED)",
          proc.returncode == 2 and "BLOCKED" in out,
          f"got exit={proc.returncode}, out={out[-200:]!r}")

    # Confirm the gate blocks before the lookup — there must be no trace of network use.
    check("the block happens 'before' the lookup (no processing log printed)",
          "처리 중:" not in out,
          f"out={out[-200:]!r}")


# --------------------------------------------------------------------------- #
section("network tests")


def _network_available() -> bool:
    try:
        socket.create_connection(("www.ebi.ac.uk", 443), timeout=5).close()
        return True
    except OSError:
        return False


if _network_available():
    print("  network available — running the live API-call tests")

    # OA paper on PMC: it actually has 3 supplementary files (measured 260807).
    res = si_fetch.discover_si("10.1186/s13321-015-0069-3")
    check("[network] PMC paper -> status=found",
          res.status == "found", f"got={res.status} note={res.note}")
    check("[network] PMCID resolved", res.pmcid == "PMC4456712", f"got={res.pmcid}")
    check("[network] picks out 3 supplementary files from the archive",
          len(res.supplementary_files) == 3,
          f"got={len(res.supplementary_files)} / total {len(res.files)}")
    check("[network] body figures are not counted as supplementary",
          len(res.files) > len(res.supplementary_files),
          f"files={len(res.files)} si={len(res.supplementary_files)}")

    # Confirm the extracted file is actually that format — not judged by size alone.
    with tempfile.TemporaryDirectory() as td:
        got = si_fetch.download_si(res, Path(td), extract=True, si_only=True)
        docx = [f for f in got.supplementary_files if f.name.endswith(".docx")]
        ok = False
        if docx and docx[0].extracted_path:
            import zipfile
            p = Path(docx[0].extracted_path)
            ok = p.exists() and zipfile.is_zipfile(p) and \
                "word/document.xml" in zipfile.ZipFile(p).namelist()
        check("[network] the extracted .docx is a real Word document (magic bytes + internal structure)",
              ok, f"docx={[f.name for f in docx]}")

    # Blocked publisher: must be reported as 'something a human does', not a failure.
    blocked = si_fetch.discover_si("10.1016/j.enzmictec.2021.109747")
    check("[network] Elsevier -> status=blocked + browser guidance",
          blocked.status == "blocked" and bool(blocked.manual_hint),
          f"got={blocked.status}")
    check("[network] the notice states this is not because SI is paywalled",
          "유료라서가 아닙니다" in (blocked.manual_hint or ""))
else:
    print("  [SKIP] no network connection — skipping the Europe PMC call tests "
          "(the file-detection/branching logic was already verified above)")


print(f"\n=== results: {PASS} passed / {FAIL} failed ===")
sys.exit(0 if FAIL == 0 else 1)
