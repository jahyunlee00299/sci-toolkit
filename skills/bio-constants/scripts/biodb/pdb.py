"""RCSB PDB core REST (key-less): entry -> resolution, method, chains + UniProt, ligands."""
from __future__ import annotations

import json
import re

from . import http
from .errors import BlindError

BASE = "https://data.rcsb.org/rest/v1/core/"
ID_RE = re.compile(r"^[0-9][A-Za-z0-9]{3}$")


def _json(path: str):
    r = http.get(BASE + path)
    if r.status != 200:
        raise BlindError(f"RCSB HTTP {r.status} for {path}: {r.text()[:120]}")
    try:
        return json.loads(r.text())
    except ValueError as e:
        raise BlindError(f"RCSB returned non-JSON for {path}: {e}") from e


def parse(entry: dict, polymers: list[dict], nonpolymers: list[dict]) -> dict:
    """Pure function over the three response shapes (see tests/fixtures)."""
    res = (entry.get("rcsb_entry_info") or {}).get("resolution_combined") or []
    chains = []
    for p in polymers:
        ids = p.get("rcsb_polymer_entity_container_identifiers", {})
        chains.append({
            "entity_id": ids.get("entity_id"),
            "description": (p.get("rcsb_polymer_entity") or {}).get("pdbx_description"),
            "chains": ids.get("auth_asym_ids", []),
            "uniprot": ids.get("uniprot_ids", []),
            "type": (p.get("entity_poly") or {}).get("rcsb_entity_polymer_type"),
        })
    ligands = []
    for n in nonpolymers:
        ids = n["rcsb_nonpolymer_entity_container_identifiers"]
        ligands.append({"comp_id": ids["nonpolymer_comp_id"],
                        "name": (n.get("pdbx_entity_nonpoly") or {}).get("name"),
                        "chains": ids.get("auth_asym_ids", [])})
    return {
        "id": entry["rcsb_id"], "title": (entry.get("struct") or {}).get("title"),
        "method": [e["method"] for e in entry.get("exptl", [])],
        "resolution_a": res[0] if res else None,   # None for NMR / no resolution
        "polymers": chains, "ligands": ligands,
    }


def fetch(pdb_id: str) -> dict:
    pid = pdb_id.strip().upper()
    if not ID_RE.match(pid):
        raise BlindError(f"'{pdb_id}' is not a valid PDB id")
    entry = _json(f"entry/{pid}")
    ids = entry.get("rcsb_entry_container_identifiers", {})
    pol = [_json(f"polymer_entity/{pid}/{i}") for i in ids.get("polymer_entity_ids", [])]
    non = [_json(f"nonpolymer_entity/{pid}/{i}") for i in ids.get("non_polymer_entity_ids", [])]
    return parse(entry, pol, non)
