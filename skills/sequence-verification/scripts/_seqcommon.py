"""Shared sequence loading for the sequence-verification scripts.

Reads SnapGene `.dna` and GenBank `.gb`/`.gbk` through one interface, so the
callers never branch on file format. SnapGene support is borrowed from the
primer-design skill rather than reimplemented — that parser is the one already
under test, and two parsers for one binary format is how they drift apart.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

# primer-design owns the SnapGene binary format. Locate it next to this skill.
_PD_SRC = Path(__file__).resolve().parents[2] / "primer-design" / "src"
if _PD_SRC.is_dir() and str(_PD_SRC) not in sys.path:
    sys.path.insert(0, str(_PD_SRC))

CODON_TABLE = {}
_BASES = "TCAG"
_AAS = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG"
for _i, _aa in enumerate(_AAS):
    CODON_TABLE[_BASES[_i // 16] + _BASES[(_i // 4) % 4] + _BASES[_i % 4]] = _aa

_COMP = str.maketrans("ACGTacgtNn", "TGCAtgcaNn")


def revcomp(seq: str) -> str:
    return seq.translate(_COMP)[::-1]


def translate(seq: str, to_stop: bool = False) -> str:
    out = []
    for i in range(0, len(seq) - len(seq) % 3, 3):
        aa = CODON_TABLE.get(seq[i:i + 3].upper(), "X")
        if to_stop and aa == "*":
            break
        out.append(aa)
    return "".join(out)


@dataclass
class Feature:
    name: str
    type: str
    start: int          # 0-based, inclusive
    end: int            # 0-based, exclusive
    strand: int         # +1 / -1


@dataclass
class Record:
    path: Path
    seq: str
    circular: bool
    features: list

    def extract(self, feat: Feature) -> str:
        sub = self.seq[feat.start:feat.end]
        return revcomp(sub) if feat.strand < 0 else sub

    def find_feature(self, label: str, ftype: str | None = None):
        """First feature whose name matches `label` (case-insensitive)."""
        for f in self.features:
            if f.name.lower() == label.lower() and (ftype is None or f.type == ftype):
                return f
        return None


def load(path) -> Record:
    """Load a .dna / .gb / .gbk file into a Record with 0-based half-open coords."""
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".dna":
        from primer_design.snapgene_parser import parse_snapgene
        seq, circular, raw = parse_snapgene(path)
        feats = [
            # SnapGene ranges are 1-based inclusive; strand 2 means reverse.
            Feature(f["name"], f["type"], f["start"] - 1, f["end"],
                    -1 if f.get("strand") == 2 else 1)
            for f in raw
        ]
        return Record(path, (seq or "").upper(), circular, feats)

    if suffix in (".gb", ".gbk", ".genbank"):
        from Bio import SeqIO
        rec = next(SeqIO.parse(str(path), "genbank"))
        feats = []
        for ft in rec.features:
            q = ft.qualifiers
            name = (q.get("label") or q.get("gene") or q.get("note") or [""])[0]
            feats.append(Feature(name, ft.type, int(ft.location.start),
                                 int(ft.location.end),
                                 -1 if ft.location.strand == -1 else 1))
        circular = rec.annotations.get("topology", "") == "circular"
        return Record(path, str(rec.seq).upper(), circular, feats)

    raise ValueError(f"unsupported sequence format: {path.name}")


def load_primers(path) -> list:
    """Primer records (name + own sequence) from a SnapGene file; [] otherwise."""
    if Path(path).suffix.lower() != ".dna":
        return []
    from primer_design.snapgene_parser import parse_snapgene_primers
    return parse_snapgene_primers(path)


def residue_at(cds_nt: str, residue: int) -> str:
    """1-based residue of an in-frame CDS; '?' when out of range."""
    i = (residue - 1) * 3
    return CODON_TABLE.get(cds_nt[i:i + 3].upper(), "?") if i + 3 <= len(cds_nt) else "?"


def align_offset(protein: str, reference: str, probe: int = 30) -> int | None:
    """Residue offset of `protein` against `reference` (0 = same numbering).

    Returns the number that must be ADDED to a reference residue index to find
    it in `protein`, or None when no anchor matches. Uses an interior probe so a
    trimmed start codon (a vector fusion drops it) does not defeat the match.
    """
    for start in (0, 1, 2, 30, 60, 100):
        if start + probe > len(reference):
            break
        hit = protein.find(reference[start:start + probe])
        if hit >= 0:
            return hit - start
    return None
