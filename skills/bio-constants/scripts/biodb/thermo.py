"""Reaction thermodynamics with EXPLICIT conditions (pH, ionic strength, T, pMg).

Two routes, both reported with every condition on every output line:
  * package: ``equilibrator-api`` ComponentContribution (needs the 1.34 GB compounds.sqlite
    cache; this module NEVER triggers the download, ``package_status`` only inspects).
  * web: the public eQuilibrator result page (``/search?query=...&p_h=..``). There is no
    documented JSON API (``/api/`` is 404), so this is an HTML read: brittle, corroboration only.
K'eq is always recomputed here from dG'0 (the page rounds K'eq to one digit).
"""
from __future__ import annotations

import html
import json
import subprocess
import importlib.util
import math
import os
import re
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from . import http
from .errors import BlindError

R_KJ = 8.314462618e-3               # kJ / (mol K)
WEB = "https://equilibrator.weizmann.ac.il/search"
CACHE_FILE = "compounds.sqlite"
CACHE_BYTES = 1337335808            # Zenodo 10.5281/zenodo.4128543 (md5 9b66b85a...)


@dataclass(frozen=True)
class Conditions:
    pH: float
    ionic_strength_M: float
    temperature_K: float
    pMg: float

    def tag(self) -> str:
        return (f"pH={self.pH:g} I={self.ionic_strength_M:g} M "
                f"T={self.temperature_K:g} K pMg={self.pMg:g}")


def keq_from_dg(dg_kj: float, temperature_K: float) -> float:
    return math.exp(-dg_kj / (R_KJ * temperature_K))


def format_result(source: str, reaction: str, dg: float, err: float | None,
                  cond: Conditions) -> str:
    keq = keq_from_dg(dg, cond.temperature_K)
    unc = ""
    if err is not None:
        lo = keq_from_dg(dg + err, cond.temperature_K)
        hi = keq_from_dg(dg - err, cond.temperature_K)
        unc = f" +/- {err:g} kJ/mol (Keq 1-sigma range {lo:.3g}..{hi:.3g})"
    else:
        unc = " kJ/mol"
    return f"thermo source={source} reaction=\"{reaction}\" dG'0={dg:g}{unc} Keq={keq:.4g} {cond.tag()}"


# ---------------------------------------------------------------- web route
def parse_web(page: str) -> dict:
    """Pure: eQuilibrator result page -> dG'0, error, and the conditions the page used."""
    txt = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    txt = html.unescape(re.sub(r"<[^>]+>", " ", txt))
    txt = re.sub(r"\s+", " ", txt)
    m = re.search(r"Estimated Δ r G'° (-?[\d.]+) ± ([\d.]+) \[kJ/mol\]", txt)
    if not m:
        raise BlindError("eQuilibrator page has no 'Estimated dG'0' (page layout changed, "
                         "reaction not parsed, or compound unknown)")

    def field(name: str) -> float:
        f = re.search(r'name="%s"[^>]*value="([^"]*)"' % name, page)
        if not f:
            raise BlindError(f"eQuilibrator page lacks field {name}")
        return float(f.group(1))
    t = re.search(r"temperature=([\d.]+) kelvin", html.unescape(page))
    if not t:
        raise BlindError("eQuilibrator page lacks temperature")
    return {"dg": float(m.group(1)), "err": float(m.group(2)),
            "page_conditions": Conditions(field("p_h"), field("ionic_strength"),
                                          float(t.group(1)), field("p_mg"))}


def web_dg(reaction: str, cond: Conditions) -> dict:
    q = urllib.parse.urlencode({"query": reaction, "p_h": cond.pH, "p_mg": cond.pMg,
                                "ionic_strength": cond.ionic_strength_M,
                                "temperature": cond.temperature_K}, quote_via=urllib.parse.quote)
    r = http.get(f"{WEB}?{q}", accept="text/html")
    if r.status != 200:
        raise BlindError(f"eQuilibrator web HTTP {r.status}")
    res = parse_web(r.text())
    if res["page_conditions"] != cond:
        raise BlindError(f"page used {res['page_conditions'].tag()} but {cond.tag()} was "
                         "requested (query parameters not honored)")
    return res


# ------------------------------------------------------------ package route
# equilibrator-api is heavy, so it lives in its own venv (~/.venvs/equilibrator); the interpreter
# running this CLI stays stdlib-only and calls the venv python for the package route.
_VENV = Path.home() / ".venvs" / "equilibrator"
VENV_PY = _VENV / "Scripts" / "python.exe" if os.name == "nt" else _VENV / "bin" / "python"
_RUNNER = """
import json, sys, warnings
warnings.filterwarnings('ignore')
from equilibrator_api import ComponentContribution, Q_
a = json.loads(sys.argv[1])
cc = ComponentContribution()
cc.p_h = Q_(a['pH'])
cc.p_mg = Q_(a['pMg'])
cc.ionic_strength = Q_(str(a['I']) + ' M')
cc.temperature = Q_(str(a['T']) + ' K')
d = cc.standard_dg_prime(cc.parse_reaction_formula(a['rx']))
print(json.dumps({'dg': d.value.m_as('kJ/mol'), 'err': d.error.m_as('kJ/mol')}))
"""


def _python_with_package() -> str | None:
    if importlib.util.find_spec("equilibrator_api") is not None:
        return sys.executable
    return str(VENV_PY) if VENV_PY.exists() else None


def package_status() -> dict:
    """Feature check only: never imports the heavy stack, never downloads."""
    out = {"installed": _python_with_package() is not None, "cache_path": None, "cache_ok": False}
    try:
        import appdirs
        p = Path(appdirs.user_cache_dir(appname="equilibrator")) / CACHE_FILE
    except ImportError:
        return {**out, "reason": "appdirs missing"}
    out["cache_path"] = p.name       # file name only; the directory is machine-specific
    out["cache_ok"] = p.exists() and p.stat().st_size == CACHE_BYTES
    out["reason"] = None if (out["installed"] and out["cache_ok"]) else (
        "equilibrator-api not installed" if not out["installed"] else
        f"{CACHE_FILE} ({CACHE_BYTES / 1e9:.2f} GB, Zenodo 10.5281/zenodo.4128543) not cached; "
        "first ComponentContribution() would download it")
    return out


def package_dg(reaction: str, cond: Conditions) -> dict:
    """Precise route: equilibrator-api ComponentContribution run in the package interpreter."""
    st = package_status()
    if st["reason"]:
        raise BlindError(f"package route unavailable: {st['reason']}")
    arg = json.dumps({"rx": reaction, "pH": cond.pH, "pMg": cond.pMg,
                      "I": cond.ionic_strength_M, "T": cond.temperature_K})
    try:
        r = subprocess.run([_python_with_package(), "-I", "-c", _RUNNER, arg], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=300)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise BlindError(f"package route failed to run: {type(e).__name__}")
    if r.returncode != 0:
        raise BlindError("package route error: " + (r.stderr.strip().splitlines() or ["unknown"])[-1][:160])
    try:
        d = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise BlindError("package route returned no JSON")
    return {"dg": float(d["dg"]), "err": float(d["err"]), "page_conditions": cond}
