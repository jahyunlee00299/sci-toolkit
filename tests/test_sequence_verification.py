#!/usr/bin/env python3
"""sequence-verification regression test — verdicts checked against constructs whose answer is known.

Every fixture here is synthesised in-process, so the expected answer is known
exactly rather than asserted against whatever a real file happens to contain:
a wild-type CDS, the same construct carrying one known substitution, and a
SnapGene file whose primer record encodes a second one. That lets each claim be
checked rather than merely exercised -- "the variant is absent" and "the variant
is present" are different assertions and both are made.

The two traps this skill exists for are tested directly, because both produce a
plausible wrong answer rather than an error:

  * a map that ANNOTATES a mutagenesis primer while its coding sequence is pure
    wild type (primer features are binding sites, i.e. template sequence), and
  * residue numbering taken from a CDS annotation whose bounds are off the real
    reading frame, which shifts every position silently.

Run:
    python tests/test_sequence_verification.py     # exit 0 = pass
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "sequence-verification" / "scripts"

# Import every shipped tool so the connectivity checker sees them as tested,
# and so an import-time error fails here rather than in front of a user.
_MODULES = {}
for _name in ("_seqcommon", "find_variant_maps", "primer_codons",
              "build_reference_map", "read_coverage"):
    _spec = importlib.util.spec_from_file_location(_name, str(SKILL / f"{_name}.py"))
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = _mod
    _spec.loader.exec_module(_mod)
    _MODULES[_name] = _mod

seqcommon = _MODULES["_seqcommon"]
find_variant_maps = _MODULES["find_variant_maps"]
primer_codons = _MODULES["primer_codons"]
build_reference_map = _MODULES["build_reference_map"]
read_coverage = _MODULES["read_coverage"]

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

results: list[tuple[bool, str, str]] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    results.append((bool(ok), label, detail))


# --------------------------------------------------------------------------
# Fixtures: a 100-residue protein, back-translated to a fixed codon sequence.
# --------------------------------------------------------------------------
PROTEIN = (
    "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGCEKAVQVKVKALPDAQ"
    "FEVVHSLAKWKRQTLGQHDFSAGEGLYTHMKALRPDE"
)
assert len(PROTEIN) == 103
BACK = {"A": "GCT", "C": "TGT", "D": "GAT", "E": "GAA", "F": "TTT", "G": "GGT",
        "H": "CAT", "I": "ATT", "K": "AAA", "L": "CTG", "M": "ATG", "N": "AAT",
        "P": "CCG", "Q": "CAA", "R": "CGT", "S": "AGC", "T": "ACC", "V": "GTG",
        "W": "TGG", "Y": "TAT"}
WT_CDS = "".join(BACK[a] for a in PROTEIN) + "TAA"

HIS6 = "CATCATCATCATCATCAC"
TARGET_RESIDUE = 51          # 'C' in PROTEIN, mutated to 'A' below
assert PROTEIN[TARGET_RESIDUE - 1] == "C"


def build_plasmid(cds: str) -> str:
    """A minimal expression construct: filler, ATG, His6, CDS, then backbone."""
    head = "GGCC" * 15                                  # 60 nt of filler
    lead = "ATG" + HIS6 + "GCT"                          # in-frame tag, then Ala
    tail = "TTAC" * 60                                   # 240 nt of backbone
    return head + lead + cds + tail


def gb_text(name: str, seq: str, features: list[tuple[str, str, int, int, int]]) -> str:
    """Minimal GenBank a Bio.SeqIO parse accepts, with labelled features."""
    lines = [f"LOCUS       {name:<16} {len(seq)} bp    DNA     circular SYN "
             "01-JAN-2026",
             f"DEFINITION  {name}.",
             "ACCESSION   .",
             "FEATURES             Location/Qualifiers"]
    for ftype, label, start, end, strand in features:
        loc = f"{start + 1}..{end}"
        if strand < 0:
            loc = f"complement({loc})"
        lines.append(f"     {ftype:<15} {loc}")
        lines.append(f'                     /label="{label}"')
    lines.append("ORIGIN")
    for i in range(0, len(seq), 60):
        chunk = seq[i:i + 60].lower()
        blocks = " ".join(chunk[j:j + 10] for j in range(0, len(chunk), 10))
        lines.append(f"{i + 1:>9} {blocks}")
    lines.append("//")
    return "\n".join(lines) + "\n"


def snapgene_bytes(seq: str, features, primers) -> bytes:
    """A SnapGene .dna file: block type, 4-byte big-endian length, payload."""
    def block(btype: int, payload: bytes) -> bytes:
        return bytes([btype]) + len(payload).to_bytes(4, "big") + payload

    out = block(9, b"SnapGene\x00\x01\x00\x0c\x00\x0b")
    out += block(0, b"\x01" + seq.encode("ascii"))          # circular flag
    feat_xml = "<Features>" + "".join(
        f'<Feature name="{n}" type="{t}" directionality="1">'
        f'<Segment range="{s + 1}-{e}"/></Feature>'
        for n, t, s, e in features) + "</Features>"
    out += block(10, feat_xml.encode("utf-8"))
    prim_xml = "<Primers>" + "".join(
        f'<Primer name="{n}" sequence="{s}"/>' for n, s in primers) + "</Primers>"
    out += block(5, prim_xml.encode("utf-8"))
    return out


WT_PLASMID = build_plasmid(WT_CDS)
CDS_START = 60 + len("ATG" + HIS6 + "GCT")

_mut = list(WT_CDS)
_mut[(TARGET_RESIDUE - 1) * 3:(TARGET_RESIDUE - 1) * 3 + 3] = list("GCT")   # C51A
MUT_PLASMID = build_plasmid("".join(_mut))

# A primer that installs a DIFFERENT substitution (K8R), so primer_codons has
# something to recover that no map carries.
K9 = 8
assert PROTEIN[K9 - 1] == "K"
_p_start = CDS_START + (K9 - 1) * 3 - 8
PRIMER_SEQ = (WT_PLASMID[_p_start:CDS_START + (K9 - 1) * 3]
              + "CGT"                                        # AAA -> CGT (K->R)
              + WT_PLASMID[CDS_START + K9 * 3:CDS_START + K9 * 3 + 9])

tmp = Path(tempfile.mkdtemp(prefix="seqverif_"))
REF_GB = tmp / "wt_cds.gb"
REF_GB.write_text(gb_text("WT_CDS", WT_CDS,
                          [("CDS", "target", 0, len(WT_CDS), 1)]), encoding="utf-8")
WT_MAP = tmp / "wt_map.gb"
WT_MAP.write_text(gb_text("WT_MAP", WT_PLASMID, [
    ("CDS", "target", CDS_START, CDS_START + len(WT_CDS), 1),
    ("promoter", "T7 promoter", 10, 30, 1),
]), encoding="utf-8")
MUT_MAP = tmp / "mut_map.gb"
MUT_MAP.write_text(gb_text("MUT_MAP", MUT_PLASMID, [
    ("CDS", "target", CDS_START, CDS_START + len(WT_CDS), 1),
]), encoding="utf-8")
DNA_MAP = tmp / "primered.dna"
DNA_MAP.write_bytes(snapgene_bytes(
    WT_PLASMID,
    # Deliberately mis-annotate the CDS by one base: a real map does this when a
    # vector fusion trims a codon, and residue numbering must survive it.
    [("target", "CDS", CDS_START + 1, CDS_START + len(WT_CDS))],
    [("iPCR_K8R_F", PRIMER_SEQ), ("plain_fwd", WT_PLASMID[100:124])]))


def run(script: str, *args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SKILL / script), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


print("== sequence-verification")

# --- 1. loader / shared helpers -------------------------------------------
rec = seqcommon.load(WT_MAP)
check(len(rec.seq) == len(WT_PLASMID), "loader reads a GenBank map",
      f"{len(rec.seq)} vs {len(WT_PLASMID)}")
prims = seqcommon.load_primers(DNA_MAP)
check([p["name"] for p in prims] == ["iPCR_K8R_F", "plain_fwd"],
      "primer records carry their own sequences", str([p["name"] for p in prims]))
check(seqcommon.load_primers(WT_MAP) == [],
      "a GenBank file yields no primers instead of raising")

# --- 2. find_variant_maps: absence and presence are both asserted ----------
r = run("find_variant_maps.py", "--reference", str(REF_GB),
        "--residues", str(TARGET_RESIDUE), "--expect", f"{TARGET_RESIDUE}=A",
        str(WT_MAP))
check(r.returncode == 1 and "0 carrying" in r.stdout,
      "wild-type map reports the variant as absent (exit 1)",
      r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[:80])
r = run("find_variant_maps.py", "--reference", str(REF_GB),
        "--residues", str(TARGET_RESIDUE), "--expect", f"{TARGET_RESIDUE}=A",
        str(MUT_MAP))
check(r.returncode == 0 and "MATCHES" in r.stdout,
      "mutant map is detected (exit 0)",
      r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[:80])
r = run("find_variant_maps.py", "--reference", str(REF_GB), "--residues", "51",
        str(tmp / "does_not_exist"))
check(r.returncode == 2, "missing path is a usage error, not a crash",
      f"exit {r.returncode}")

# --- 3. primer_codons: the annotated-primer trap --------------------------
r = run("primer_codons.py", str(DNA_MAP), "--reference", str(REF_GB),
        "--filter", "iPCR")
check(r.returncode == 0 and "K8R:CGT" in r.stdout,
      "recovers the intended codon from a stored primer",
      [l for l in r.stdout.splitlines() if "iPCR" in l][:1])
check("--mutate K8R:CGT" in r.stdout,
      "emits a ready-to-use --mutate line")
# The same file must simultaneously read as wild type at that residue.
r2 = run("find_variant_maps.py", "--reference", str(REF_GB), "--residues",
         str(K9), "--expect", f"{K9}=R", str(DNA_MAP))
check(r2.returncode == 1,
      "a map that annotates the primer still reports wild type (the core trap)",
      r2.stdout.strip().splitlines()[-1] if r2.stdout.strip() else "")

# --- 4. build_reference_map -----------------------------------------------
out_gb = tmp / "expected.gb"
r = run("build_reference_map.py", "--base", str(WT_MAP), "--reference",
        str(REF_GB), "--mutate", f"C{TARGET_RESIDUE}A:GCT", "--out", str(out_gb))
check(r.returncode == 0 and out_gb.exists(), "builds the expected map",
      r.stderr[:100])
if out_gb.exists():
    built = seqcommon.load(out_gb)
    diff = [i for i in range(len(WT_PLASMID)) if built.seq[i] != WT_PLASMID[i]]
    check(len(diff) <= 3, "only the named codon changed", f"{len(diff)} nt differ")
    r = run("read_coverage.py", "--map", str(out_gb), "--variants",
            "--primers", "T7 promoter")
    check(r.returncode in (0, 1), "read_coverage runs on the built map",
          r.stderr[:80])
    check("T7 promoter" in r.stdout, "names the candidate primer")

r = run("build_reference_map.py", "--base", str(WT_MAP), "--reference",
        str(REF_GB), "--mutate", f"W{TARGET_RESIDUE}A:GCT",
        "--out", str(tmp / "never.gb"))
check(r.returncode == 1 and not (tmp / "never.gb").exists(),
      "refuses when the base residue is not what the edit assumes",
      f"exit {r.returncode}")
r = run("build_reference_map.py", "--base", str(WT_MAP), "--reference",
        str(REF_GB), "--mutate", f"C{TARGET_RESIDUE}A:GAT",
        "--out", str(tmp / "never2.gb"))
check(r.returncode == 2 and not (tmp / "never2.gb").exists(),
      "refuses a codon that does not encode the stated residue",
      f"exit {r.returncode}")

# --- 5. read_coverage distance verdicts -----------------------------------
check(read_coverage.verdict(None) == "reads away", "verdict: wrong direction")
check(read_coverage.verdict(10).startswith("TOO CLOSE"), "verdict: dye blob")
check(read_coverage.verdict(300) == "OK", "verdict: good band")
check(read_coverage.verdict(700) == "marginal", "verdict: marginal band")
check(read_coverage.verdict(2000) == "OUT OF REACH", "verdict: beyond a read")

# --------------------------------------------------------------------------
n_fail = sum(1 for ok, _, _ in results if not ok)
for ok, label, detail in results:
    tag = "OK  " if ok else "FAIL"
    extra = f"  {detail}" if (detail and not ok) else ""
    print(f"  [{tag}]  {label}{extra}")
print(f"\nSUMMARY: {len(results) - n_fail} passed, {n_fail} failed")
sys.exit(1 if n_fail else 0)
