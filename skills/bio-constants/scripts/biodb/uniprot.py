"""UniProt REST (key-less): one accession -> a flat, explicit record.

Never silently swaps numbers: ``mass_da`` is always UniProt's own ``sequence.molWeight``;
mature-chain masses are computed locally from the sequence slice and live in ``chains``.
"""
from __future__ import annotations

import json
import re

from . import http
from .errors import BlindError

BASE = "https://rest.uniprot.org/uniprotkb/"
ACC_RE = re.compile(
    r"^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})(?:-[0-9]+)?$")

# Average residue masses (Da; residue = amino acid minus H2O) and water, ExPASy convention.
RESIDUE_MASS = {
    "G": 57.0519, "A": 71.0788, "S": 87.0782, "P": 97.1167, "V": 99.1326, "T": 101.1051,
    "C": 103.1388, "L": 113.1594, "I": 113.1594, "N": 114.1038, "D": 115.0886, "Q": 128.1307,
    "K": 128.1741, "E": 129.1155, "M": 131.1926, "H": 137.1411, "F": 147.1766, "R": 156.1875,
    "Y": 163.1760, "W": 186.2132, "U": 150.0379, "O": 237.3018,
}
WATER = 18.01524


def seq_mass(seq: str) -> float | None:
    """Average mass of a peptide; None if it holds ambiguous residues (X, B, Z, J)."""
    try:
        return round(sum(RESIDUE_MASS[c] for c in seq) + WATER, 2)
    except KeyError:
        return None


def _loc(f: dict) -> tuple[int, int]:
    return int(f["location"]["start"]["value"]), int(f["location"]["end"]["value"])


def _name(pd: dict) -> str | None:
    if "recommendedName" in pd:
        return pd["recommendedName"]["fullName"]["value"]
    for key in ("submissionNames", "alternativeNames"):
        if pd.get(key):
            return pd[key][0]["fullName"]["value"]
    return None


def _ecs(d: dict) -> list[str]:
    pd = d.get("proteinDescription", {})
    out = [e["value"] for e in pd.get("recommendedName", {}).get("ecNumbers", [])]
    for n in pd.get("alternativeNames", []) + pd.get("submissionNames", []):
        out += [e["value"] for e in n.get("ecNumbers", [])]
    for c in d.get("comments", []):
        if c.get("commentType") == "CATALYTIC ACTIVITY":
            ec = c.get("reaction", {}).get("ecNumber")
            if ec:
                out.append(ec)
    return list(dict.fromkeys(out))


def _gene(d: dict) -> str | None:
    for g in d.get("genes", []):
        if "geneName" in g:
            return g["geneName"]["value"]
        for k in ("orderedLocusNames", "orfNames"):
            if g.get(k):
                return g[k][0]["value"]
    return None


def parse_entry(d: dict, requested: str) -> dict:
    """Pure function: UniProt JSON -> record. Ambiguous inactive entries raise BlindError."""
    if d.get("entryType") == "Inactive":
        r = d.get("inactiveReason", {})
        kind, to = r.get("inactiveReasonType"), r.get("mergeDemergeTo", [])
        if kind == "MERGED" and len(to) == 1:
            return {"accession": requested, "status": "inactive", "reason": "MERGED",
                    "merged_to": to[0]}
        raise BlindError(f"{requested} is inactive: {kind} -> {to or 'no target'} (ambiguous)")
    seq = d["sequence"]["value"]
    rec = {
        "accession": requested, "primary_accession": d["primaryAccession"], "status": "active",
        "isoform": "-" in requested,
        "reviewed": d["entryType"].startswith("UniProtKB reviewed"),
        "entry_type": d["entryType"],
        "name": _name(d.get("proteinDescription", {})), "gene": _gene(d),
        "organism": d["organism"]["scientificName"], "taxon_id": d["organism"]["taxonId"],
        "length": d["sequence"]["length"], "mass_da": d["sequence"]["molWeight"],
        "mass_check_da": seq_mass(seq), "ec": _ecs(d), "notes": [],
    }
    feats = d.get("features", [])
    chains = []
    for f in feats:
        if f["type"] == "Chain":
            s, e = _loc(f)
            chains.append({"start": s, "end": e, "description": f.get("description"),
                           "mass_da_computed": seq_mass(seq[s - 1:e]),
                           "basis": "computed from sequence slice, average residue masses"})
    rec["chains"] = chains
    rec["processing"] = [f"{f['type']} {_loc(f)[0]}-{_loc(f)[1]}" for f in feats
                         if f["type"] in ("Signal peptide", "Propeptide", "Transit peptide",
                                          "Initiator methionine")]
    if rec["isoform"]:
        rec["notes"].append("isoform record: UniProt provides no feature annotation; "
                            "canonical entry may differ in mass")
    if chains and not (len(chains) == 1 and chains[0]["start"] == 1
                       and chains[0]["end"] == rec["length"]):
        rec["notes"].append(
            "mass_da is the full precursor sequence; mature chain(s) differ: "
            + "; ".join(f"{c['start']}-{c['end']} = {c['mass_da_computed']} Da (computed)"
                        for c in chains))
    return rec


def fetch(accession: str) -> dict:
    acc = accession.strip().upper()
    if not ACC_RE.match(acc):
        raise BlindError(f"'{accession}' is not a valid UniProtKB accession")
    r = http.get(f"{BASE}{acc}.json")
    if r.status != 200:
        raise BlindError(f"UniProt HTTP {r.status} for {acc}: {r.text()[:120]}")
    try:
        d = json.loads(r.text())
    except ValueError as e:
        raise BlindError(f"UniProt returned non-JSON for {acc}: {e}") from e
    return parse_entry(d, acc)
