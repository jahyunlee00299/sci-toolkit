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
              "build_reference_map", "read_coverage", "construct_mw"):
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
construct_mw = _MODULES["construct_mw"]

import sys as _sys
from pathlib import Path as _Path
_sys.path.append(str(_Path(__file__).resolve().parents[1] / "scripts"))  # shared helper: scripts/_stdio.py
from _stdio import force_utf8  # noqa: E402
force_utf8()  # UTF-8 stdout/stderr on legacy Windows codepages

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

# --- 6. construct_mw: expressed fusion, native split, mass -----------------
import json

from Bio.Data.IUPACData import protein_weights as _AA_W


def indep_mass_kda(protein: str) -> float:
    """Mass from free amino-acid masses minus one water per bond; no ProtParam."""
    return (sum(_AA_W[a] for a in protein) - 18.0153 * (len(protein) - 1)) / 1000


LEAD_AA = "M" + "H" * 6 + "A"
FUSION = LEAD_AA + PROTEIN
r = run("construct_mw.py", str(WT_MAP), "--native-start", "MKTAYI", "--json")
j = json.loads(r.stdout) if r.returncode == 0 else {}
check(r.returncode == 0 and j.get("fusion", {}).get("aa") == len(FUSION)
      and j.get("stop_codon") == "TAA",
      "construct_mw: anchored ORF is the tagged fusion, not the bare CDS",
      f"exit {r.returncode} aa={j.get('fusion', {}).get('aa')}")
check(j and abs(j["fusion"]["mw_kda"] - indep_mass_kda(FUSION)) < 0.005
      and abs(j["native"]["mw_kda"] - indep_mass_kda(PROTEIN)) < 0.005,
      "construct_mw: fusion and native masses match an independent residue sum",
      f"{j.get('fusion', {}).get('mw_kda')} vs {indep_mass_kda(FUSION):.3f}")
check(j and j["leader_seq"] == LEAD_AA and j["n_terminal_his"] and not j["c_terminal_his"],
      "construct_mw: leader split and tag detection")

r = run("construct_mw.py", str(WT_MAP), "--native-start", "MKTAYI",
        f"--mutate", f"C{TARGET_RESIDUE}A", "--json")
j = json.loads(r.stdout) if r.returncode == 0 else {}
delta = j["native_mutant"]["mw_da"] - j["native"]["mw_da"] if j else 0
check(r.returncode == 0 and abs(delta - (_AA_W["A"] - _AA_W["C"])) < 0.02,
      "construct_mw: C->A shifts the mass by the residue difference (-32.07 Da)",
      f"delta {delta:.3f} Da")
r = run("construct_mw.py", str(WT_MAP), "--native-start", "MKTAYI",
        "--mutate", f"K{TARGET_RESIDUE}A")
check(r.returncode == 1 and "not 'K'" in r.stderr,
      "construct_mw: refuses a substitution whose base residue is wrong",
      f"exit {r.returncode}")
r = run("construct_mw.py", str(WT_MAP), "--mutate", f"C{TARGET_RESIDUE}A")
check(r.returncode == 1, "construct_mw: --mutate without --native-start is refused",
      f"exit {r.returncode}")
r = run("construct_mw.py", str(WT_MAP), "--native-start", "WWWWWW")
check(r.returncode == 1 and "not found" in r.stderr,
      "construct_mw: an absent native motif is refused, not guessed",
      f"exit {r.returncode}")
r = run("construct_mw.py", str(WT_MAP), "--mutate", "not-a-token")
check(r.returncode == 2, "construct_mw: malformed --mutate is a usage error",
      f"exit {r.returncode}")
r = run("construct_mw.py", str(tmp / "no_such.gb"))
check(r.returncode == 2, "construct_mw: missing map is a usage error", f"exit {r.returncode}")
BAD = tmp / "corrupt.gb"
BAD.write_text("not a genbank file\n", encoding="utf-8")
r = run("construct_mw.py", str(BAD))
check(r.returncode == 1, "construct_mw: corrupt map fails cleanly (exit 1)", f"exit {r.returncode}")

# no anchor feature: refuse, and --start-pos is the explicit alternative
r = run("construct_mw.py", str(MUT_MAP))
check(r.returncode == 1 and "no feature labelled" in r.stderr,
      "construct_mw: map without the anchor is refused, not guessed",
      f"exit {r.returncode}")
r = run("construct_mw.py", str(MUT_MAP), "--start-pos", "61", "--json")
check(r.returncode == 0 and json.loads(r.stdout)["fusion"]["aa"] == len(FUSION),
      "construct_mw: --start-pos reads the same fusion without an anchor",
      f"exit {r.returncode}")

# a real SnapGene label carries its description after the name
LONG = tmp / "long_label.gb"
LONG.write_text(gb_text("LONG", WT_PLASMID, [
    ("promoter", "T7 promoter promoter for bacteriophage T7 RNA p", 10, 30, 1)]),
    encoding="utf-8")
r = run("construct_mw.py", str(LONG), "--json")
check(r.returncode == 0 and json.loads(r.stdout)["fusion"]["aa"] == len(FUSION),
      "construct_mw: anchor matches a label with a description appended",
      f"exit {r.returncode}")

# the promoter on the reverse strand of the file (a map stored the other way round)
RC = tmp / "reverse.gb"
_n = len(WT_PLASMID)
RC.write_text(gb_text("RC", seqcommon.revcomp(WT_PLASMID), [
    ("promoter", "T7 promoter", _n - 30, _n - 10, -1)]), encoding="utf-8")
r = run("construct_mw.py", str(RC), "--json")
check(r.returncode == 0 and json.loads(r.stdout)["fusion_seq"] == FUSION
      and json.loads(r.stdout)["orf_strand"] == -1,
      "construct_mw: a map stored reverse-complement yields the same fusion",
      f"exit {r.returncode}")

# trap: 'longest ORF' picks a decoy; the anchor must not
DECOY = "ATG" + "GCT" * 150 + "TAA"
DEC = tmp / "decoy.gb"
DEC.write_text(gb_text("DEC", "GGCC" * 15 + "ATG" + HIS6 + "GCT" + WT_CDS + DECOY, [
    ("promoter", "T7 promoter", 10, 30, 1)]), encoding="utf-8")
r = run("construct_mw.py", str(DEC), "--json")
check(r.returncode == 0 and json.loads(r.stdout)["fusion"]["aa"] == len(FUSION),
      "construct_mw: a longer decoy ORF elsewhere does not displace the anchored one",
      f"exit {r.returncode}")

# no stop codon before the map ends
NOSTOP = tmp / "nostop.gb"
NOSTOP.write_text(gb_text("NOSTOP", build_plasmid(WT_CDS[:-3] + "GCT"), [
    ("promoter", "T7 promoter", 10, 30, 1)]), encoding="utf-8")
r = run("construct_mw.py", str(NOSTOP))
check(r.returncode == 1 and "no stop codon" in r.stderr,
      "construct_mw: an ORF with no stop is refused", f"exit {r.returncode}")

# C-terminal His6 before the stop is reported; thrombin site is cut at LVPR|GS
CT = tmp / "ctag.gb"
_thr = "CTGGTGCCGCGTGGTAGC"   # LVPRGS
CT.write_text(gb_text("CT", "GGCC" * 15 + "ATG" + HIS6 + _thr + WT_CDS[:-3] + HIS6 + "TAA"
                      + "TTAC" * 60, [("promoter", "T7 promoter", 10, 30, 1)]),
              encoding="utf-8")
r = run("construct_mw.py", str(CT), "--json")
j = json.loads(r.stdout) if r.returncode == 0 else {}
check(j and j["c_terminal_his"] and j["n_terminal_his"],
      "construct_mw: C-terminal His6 is detected when present")
check(j and j["thrombin_cleaved"]["aa"] == j["fusion"]["aa"] - len("MHHHHHHLVPR"),
      "construct_mw: thrombin cleavage removes through LVPR",
      f"{j.get('thrombin_cleaved', {}).get('aa')} vs {j.get('fusion', {}).get('aa')}")

# --------------------------------------------------------------------------
n_fail = sum(1 for ok, _, _ in results if not ok)
for ok, label, detail in results:
    tag = "OK  " if ok else "FAIL"
    extra = f"  {detail}" if (detail and not ok) else ""
    print(f"  [{tag}]  {label}{extra}")
print(f"\nSUMMARY: {len(results) - n_fail} passed, {n_fail} failed")
sys.exit(1 if n_fail else 0)
