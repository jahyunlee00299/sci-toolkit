"""Rhea (key-less): reaction by master Rhea id or EC number.

Verified shape (2026-10-13): host ``https://www.rhea-db.org/rhea`` (``rest.rhea-db.org`` did
not resolve from this machine). Two GETs per query:
  * ``format=tsv&columns=rhea-id,equation,chebi-id,ec``  -> equation, ChEBI ids, EC
  * ``format=json``                                      -> status, balanced, transport
Only MASTER ids (e.g. RHEA:21432) are queryable; directional ids (21433..21435) return empty,
so ``direction`` is reported as 'undirected (master reaction)' and never inferred.
"""
from __future__ import annotations

import json
import re
import urllib.parse

from . import http
from .errors import BlindError

BASE = "https://www.rhea-db.org/rhea"
COLS = "rhea-id,equation,chebi-id,ec"
EC_RE = re.compile(r"^\d+\.(?:\d+|-)\.(?:\d+|-)\.(?:\d+|-)$")


def _q(query: str, fmt: str) -> str:
    cols = f"&columns={COLS}" if fmt == "tsv" else ""
    return f"{BASE}?query={urllib.parse.quote(query, safe=':')}{cols}&format={fmt}"


def parse(tsv: str, js: str) -> list[dict]:
    """Pure: merge the TSV and JSON responses of one query into reaction records."""
    meta = {str(r["id"]): r for r in json.loads(js).get("results", [])} if js.strip().startswith(
        "{") else {str(r["id"]): r for r in json.loads(js)}
    lines = [ln for ln in tsv.splitlines() if ln.strip()]
    out = []
    for ln in lines[1:]:
        cols = ln.split("\t")
        if len(cols) < 4:
            raise BlindError(f"unexpected Rhea TSV row: {ln[:80]!r}")
        rid = cols[0].split(":")[1]
        m = meta.get(rid, {})
        out.append({
            "rhea_id": cols[0], "equation": cols[1],
            "chebi": [c for c in cols[2].split(";") if c],      # same order as the equation
            "ec": [e.replace("EC:", "") for e in cols[3].split(";") if e],
            "status": m.get("status"), "balanced": m.get("balanced"),
            "transport": m.get("transport"),
            "direction": "undirected (master reaction)",
        })
    return out


def fetch(rhea_id: str | None = None, ec: str | None = None) -> list[dict]:
    if bool(rhea_id) == bool(ec):
        raise BlindError("give exactly one of rhea_id / ec")
    if rhea_id:
        m = re.fullmatch(r"(?:RHEA:)?(\d+)", rhea_id.strip(), re.I)
        if not m:
            raise BlindError(f"'{rhea_id}' is not a Rhea id")
        query = f"rhea:{m.group(1)}"
    else:
        if not EC_RE.match(ec.strip()):
            raise BlindError(f"'{ec}' is not an EC number")
        query = f"ec:{ec.strip()}"
    pair = []
    for fmt in ("tsv", "json"):
        r = http.get(_q(query, fmt), accept="*/*")
        if r.status != 200:
            raise BlindError(f"Rhea HTTP {r.status} for {query} ({fmt})")
        pair.append(r.text())
    try:
        res = parse(*pair)
    except ValueError as e:
        raise BlindError(f"Rhea returned unparsable JSON: {e}") from e
    if not res:
        raise BlindError(f"Rhea has no master reaction for {query} "
                         "(directional ids and unknown ids return empty)")
    return res
