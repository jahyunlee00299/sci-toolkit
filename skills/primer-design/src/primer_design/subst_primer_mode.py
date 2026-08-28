#!/usr/bin/env python3
"""
iPCR Primer Designer — modular structure
====================================
iPCRDesignerBase : shared utilities (Tm, GC%, hairpin/homodimer judgment, annealing design)
iPCRSubstDesigner : substitution primer design

Design principle (substitution):
  overlap = upstream k1 bp + new_seq + downstream k2 bp
  F: 5'-[up_tail]-[new_seq]-[dn_tail]-[annealing]-3'
  R: 5'-RC(dn_tail)-RC(new_seq)-RC(up_tail)-[annealing]-3'
  Tm calculation: since the tail matches the template, the entire effective
  binding region is used.

Quality judgment (Tm-based):
  FAIL: structure Tm > anneal_temp - 10C
  WARNING: structure Tm > anneal_temp - 20C
  PASS: structure Tm <= anneal_temp - 20C or no structure

Hairpin avoidance:
  On FAIL, automatically retries with an alternate annealing length (2-pass).
"""

# The default Windows console is cp949, which crashes on Korean/symbol
# output. Force UTF-8. Use reconfigure: wrapping with TextIOWrapper makes it
# own the underlying stream, so once this module is imported and the
# wrapper is later garbage collected, it closes the caller's stdout too
# (measured).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import os
from pathlib import Path

from Bio.Seq import Seq
from Bio.SeqUtils.MeltingTemp import Tm_NN


class iPCRDesignerBase:
    """Shared iPCR primer utilities + Tm-based quality judgment.

    Parameters
    ----------
    na : float      Na+ concentration (mM)
    mg : float      Mg2+ concentration (mM)
    dnac1 : float   primer concentration (nM)
    dntps : float   dNTPs concentration (mM)
    """

    def __init__(self, na=50, mg=2, dnac1=500, dntps=0.2):
        self.na = na
        self.mg = mg
        self.dnac1 = dnac1
        self.dntps = dntps

    # ── Tm / utility ─────────────────────────────────────────────────────

    def calc_tm(self, seq_str):
        """Nearest-neighbor Tm (Owczarzy 2008, saltcorr=7, Mg2+ direct)."""
        return Tm_NN(
            seq_str, Na=self.na, Mg=self.mg,
            dnac1=self.dnac1, dnac2=0, dNTPs=self.dntps,
            saltcorr=7,
        )

    @staticmethod
    def gc_pct(seq_str):
        s = seq_str.upper()
        return (s.count("G") + s.count("C")) / len(s) * 100 if s else 0.0

    @staticmethod
    def gc_clamp_ok(seq_str):
        return seq_str[-1].upper() in "GC"

    @staticmethod
    def homopolymer_run(seq_str, n=4):
        s = seq_str.upper()
        for base in "ATGC":
            if base * n in s:
                return base * n
        return ""

    # ── Quality check (Tm-based) ─────────────────────────────────────────

    def check_primer(self, seq_str, anneal_temp):
        """Hairpin/homodimer Tm-based quality check.

        FAIL    : structure Tm > anneal_temp - 10C
        WARNING : structure Tm > anneal_temp - 20C
        PASS    : structure Tm <= anneal_temp - 20C or no structure
        """
        issues = []
        try:
            import primer3
            hp = primer3.calc_hairpin(
                seq_str, mv_conc=float(self.na), dv_conc=float(self.mg),
                dntp_conc=float(self.dntps), dna_conc=float(self.dnac1),
            )
            hd = primer3.calc_homodimer(
                seq_str, mv_conc=float(self.na), dv_conc=float(self.mg),
                dntp_conc=float(self.dntps), dna_conc=float(self.dnac1),
            )
            hp_dg = hp.dg / 1000
            hd_dg = hd.dg / 1000
            hp_tm = hp.tm
            hd_tm = hd.tm

            if hp_dg < 0:
                margin = anneal_temp - hp_tm
                if margin < 10:
                    issues.append(f"Hairpin risk (Tm={hp_tm:.1f}C, dG={hp_dg:.1f}, {margin:.0f}C below anneal)")
                elif margin < 20:
                    issues.append(f"Hairpin marginal (Tm={hp_tm:.1f}C, dG={hp_dg:.1f}, {margin:.0f}C below anneal)")

            if hd_dg < 0:
                margin = anneal_temp - hd_tm
                if margin < 10:
                    issues.append(f"Homodimer risk (Tm={hd_tm:.1f}C, dG={hd_dg:.1f}, {margin:.0f}C below anneal)")
                elif margin < 20:
                    issues.append(f"Homodimer marginal (Tm={hd_tm:.1f}C, dG={hd_dg:.1f}, {margin:.0f}C below anneal)")

            fail = any("risk" in i for i in issues)
            warn = any("marginal" in i for i in issues)

            return {
                "hairpin_dg": round(hp_dg, 1),
                "hairpin_tm": round(hp_tm, 1),
                "homodimer_dg": round(hd_dg, 1),
                "homodimer_tm": round(hd_tm, 1),
                "issues": issues,
                "verdict": "FAIL" if fail else "WARNING" if warn else "PASS",
            }
        except ImportError:
            return {"issues": ["primer3 not available"], "verdict": "N/A"}

    def check_heterodimer(self, seq1, seq2):
        """F-R primer heterodimer check."""
        try:
            import primer3
            result = primer3.calc_heterodimer(
                seq1, seq2, mv_conc=float(self.na), dv_conc=float(self.mg),
                dntp_conc=float(self.dntps), dna_conc=float(self.dnac1),
            )
            return {"dg": round(result.dg / 1000, 1), "tm": round(result.tm, 1)}
        except ImportError:
            return {"dg": None, "tm": None}

    # ── Core design ──────────────────────────────────────────────────────

    def _design_annealing(self, template, anchor, direction,
                          target_tm, min_len, max_len, tail_seq="",
                          anneal_temp=None):
        """Annealing region design with tail contribution to Tm.

        anneal_temp=None : default mode — shortest candidate meeting the Tm
                           target, preferring a GC clamp.
        anneal_temp=float: hairpin-avoidance mode — among all candidates
                           meeting the Tm target, select first by quality
                           verdict, then GC clamp, then shortest length.
        """
        best_no_clamp = None
        candidates = []

        for length in range(min_len, max_len + 1):
            if direction == "+":
                if anchor + length > len(template):
                    break
                seg = template[anchor: anchor + length]
            else:
                seg_start = anchor - length
                if seg_start < 0:
                    continue
                seg = str(Seq(template[seg_start:anchor]).reverse_complement())

            if len(seg) < min_len:
                continue

            eff_seq = tail_seq + seg if tail_seq else seg
            tm = self.calc_tm(eff_seq)
            if tm < target_tm:
                continue

            gc = self.gc_pct(eff_seq)
            clamp = self.gc_clamp_ok(seg)

            if anneal_temp is None:
                # Default mode: immediately return the shortest candidate that has a GC clamp
                if clamp:
                    return seg, tm, gc, length
                elif best_no_clamp is None:
                    best_no_clamp = (seg, tm, gc, length)
            else:
                candidates.append((seg, tm, gc, length, clamp))

        if anneal_temp is None:
            return best_no_clamp if best_no_clamp else (None, None, None, None)

        if not candidates:
            return None, None, None, None

        # Hairpin avoidance: rank all candidates by quality verdict
        verdict_rank = {"PASS": 2, "WARNING": 1, "FAIL": 0, "N/A": 1}
        scored = []
        for seg, tm, gc, length, clamp in candidates:
            eff_seq = tail_seq + seg if tail_seq else seg
            qc = self.check_primer(eff_seq, anneal_temp)
            score = verdict_rank.get(qc['verdict'], 0)
            scored.append((score, int(clamp), length, seg, tm, gc))

        # Sort: highest verdict first -> GC clamp present -> shortest
        scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
        best = scored[0]
        return best[3], best[4], best[5], best[2]


class iPCRSubstDesigner(iPCRDesignerBase):
    """Substitution primer design (includes quality judgment + hairpin avoidance)."""

    def design(self, seq, subst_pos, old_seq, new_seq,
               target_tm=61.0, overlap_len=18, min_len=18, max_len=35):
        """Main primer design method.

        Parameters
        ----------
        seq : str           the full template sequence
        subst_pos : int     substitution start position (0-indexed)
        old_seq : str       the original sequence (for verification)
        new_seq : str       the sequence after substitution
        target_tm : float   target effective-binding Tm (degC)
        overlap_len : int   total overlap length (bp)
        min_len : int       minimum effective-binding length
        max_len : int       maximum annealing length

        Returns
        -------
        dict : f_full, r_full, f_qc, r_qc, het, anneal_temp, warnings, ...
        """
        warnings = []
        old_len = len(old_seq)
        new_len = len(new_seq)

        # 1. Verify
        actual = seq[subst_pos:subst_pos + old_len].upper()
        if actual != old_seq.upper():
            raise ValueError(
                f"Mismatch: seq[{subst_pos}:{subst_pos + old_len}] = '{actual}', "
                f"expected '{old_seq.upper()}'"
            )

        # 2. Overlap split
        k1 = (overlap_len - new_len) // 2
        k2 = overlap_len - new_len - k1

        if k1 < 0 or k2 < 0:
            raise ValueError(f"overlap_len ({overlap_len}) < new_seq ({new_len})")
        if k1 < 5:
            warnings.append(f"upstream overlap (k1={k1} bp) short")
        if k2 < 5:
            warnings.append(f"downstream overlap (k2={k2} bp) short")
        if subst_pos - k1 < 0:
            raise ValueError("Upstream space insufficient")
        if subst_pos + old_len + k2 > len(seq):
            raise ValueError("Downstream space insufficient")

        # 3. Overlap
        up_tail = seq[subst_pos - k1: subst_pos]
        dn_tail = seq[subst_pos + old_len: subst_pos + old_len + k2]
        overlap_region = up_tail + new_seq + dn_tail

        dn_tail_rc = str(Seq(dn_tail).reverse_complement())
        new_seq_rc = str(Seq(new_seq).reverse_complement())
        up_tail_rc = str(Seq(up_tail).reverse_complement())

        # 4. F primer annealing (pass 1: default — shortest + GC clamp)
        f_ann_start = subst_pos + old_len + k2
        f_min_len = max(8, min_len - k2)
        f_ann, f_tm, f_gc, _ = self._design_annealing(
            seq, f_ann_start, "+", target_tm, f_min_len, max_len, tail_seq=dn_tail,
        )
        if f_ann is None:
            raise RuntimeError("Forward primer annealing design failed")

        # 5. R primer annealing (pass 1: default)
        r_ann_anchor = subst_pos - k1
        r_min_len = max(8, min_len - k1)
        r_ann, r_tm, r_gc, _ = self._design_annealing(
            seq, r_ann_anchor, "-", target_tm, r_min_len, max_len, tail_seq=up_tail_rc,
        )
        if r_ann is None:
            raise RuntimeError("Reverse primer annealing design failed")

        # 6. Preliminary anneal temp & quality check
        anneal_temp = min(f_tm, r_tm) + 1.0
        f_eff_bind = dn_tail + f_ann
        r_eff_bind = up_tail_rc + r_ann
        f_qc = self.check_primer(f_eff_bind, anneal_temp)
        r_qc = self.check_primer(r_eff_bind, anneal_temp)

        # 7. Hairpin avoidance: on FAIL, retry with an alternate annealing length
        if f_qc['verdict'] == 'FAIL':
            alt = self._design_annealing(
                seq, f_ann_start, "+", target_tm, f_min_len, max_len,
                tail_seq=dn_tail, anneal_temp=anneal_temp,
            )
            if alt[0] is not None and alt[0] != f_ann:
                f_ann, f_tm, f_gc = alt[0], alt[1], alt[2]
                warnings.append(
                    f"F annealing adjusted for hairpin avoidance ({len(f_ann)} bp)")
            else:
                warnings.append(
                    "F hairpin: stem in dn_tail+template boundary, "
                    "annealing length adjustment cannot resolve")

        if r_qc['verdict'] == 'FAIL':
            alt = self._design_annealing(
                seq, r_ann_anchor, "-", target_tm, r_min_len, max_len,
                tail_seq=up_tail_rc, anneal_temp=anneal_temp,
            )
            if alt[0] is not None and alt[0] != r_ann:
                r_ann, r_tm, r_gc = alt[0], alt[1], alt[2]
                warnings.append(
                    f"R annealing adjusted for hairpin avoidance ({len(r_ann)} bp)")
            else:
                warnings.append(
                    "R hairpin: stem in up_tail+template boundary, "
                    "annealing length adjustment cannot resolve")

        # 8. Assemble final primers
        f_full = up_tail + new_seq + dn_tail + f_ann
        f_eff_bind = dn_tail + f_ann
        r_full = dn_tail_rc + new_seq_rc + up_tail_rc + r_ann
        r_eff_bind = up_tail_rc + r_ann

        # 9. Primer-level warnings
        hp = self.homopolymer_run(f_full)
        if hp:
            warnings.append(f"F primer homopolymer: {hp}")
        if not self.gc_clamp_ok(f_full):
            warnings.append("F primer no 3' G/C clamp")
        if len(f_full) > 60:
            warnings.append(f"F primer length ({len(f_full)} nt) > 60 nt")

        hp = self.homopolymer_run(r_full)
        if hp:
            warnings.append(f"R primer homopolymer: {hp}")
        if not self.gc_clamp_ok(r_full):
            warnings.append("R primer no 3' G/C clamp")
        if len(r_full) > 60:
            warnings.append(f"R primer length ({len(r_full)} nt) > 60 nt")

        # 10. Overlap verification
        overlap_rc = str(Seq(overlap_region).reverse_complement())
        r_5prime = r_full[:len(overlap_region)]
        overlap_verified = (r_5prime == overlap_rc)
        if not overlap_verified:
            warnings.append("Overlap complementarity mismatch!")

        # 11. Final anneal temp & quality check
        anneal_temp = min(f_tm, r_tm) + 1.0
        f_qc = self.check_primer(f_eff_bind, anneal_temp)
        r_qc = self.check_primer(r_eff_bind, anneal_temp)
        het = self.check_heterodimer(f_full, r_full)

        return {
            "f_full": f_full, "r_full": r_full,
            "f_ann": f_ann, "r_ann": r_ann,
            "f_tm": round(f_tm, 1), "r_tm": round(r_tm, 1),
            "f_gc": round(f_gc, 1), "r_gc": round(r_gc, 1),
            "f_len": len(f_full), "r_len": len(r_full),
            "f_eff_bind": f_eff_bind,
            "r_eff_bind": r_eff_bind,
            "overlap_region": overlap_region,
            "overlap_verified": overlap_verified,
            "anneal_temp": round(anneal_temp, 1),
            "k1": k1, "k2": k2,
            "up_tail": up_tail, "dn_tail": dn_tail,
            "new_seq_rc": new_seq_rc,
            "f_qc": f_qc, "r_qc": r_qc, "het": het,
            "warnings": warnings,
        }


# ── Tests ─────────────────────────────────────────────────────────────────

def _run_tests():
    """Tests for iPCRSubstDesigner."""
    import os

    sep = "=" * 70
    designer = iPCRSubstDesigner()

    # SnapGene parser (minimal)
    def parse_snapgene(filepath):
        with open(filepath, "rb") as fh:
            data = fh.read()
        sequence = None
        i = 0
        while i < len(data) - 5:
            btype = data[i]
            blen = int.from_bytes(data[i + 1:i + 5], "big")
            if i + 5 + blen > len(data):
                break
            if btype == 0:
                sequence = data[i + 6:i + 5 + blen].decode("ascii")
            i += 5 + blen
        return sequence

    dna_file = str(
        Path.home() / "your_project" / "Genes"
        / "parent_construct.dna"
    )

    if not os.path.exists(dna_file):
        template = (
            "ATGCGTAACCTGGCGATCAAGCTGTTCGACGGTACC"
            "GATATCCTGCAGAAATTTGCGCCGGATCTGAACGAA"
            "TGGCTGCACATCGGTCCTGCGATTGGCACCGATTTC"
            "AATCGCCTGATGCAG"
        )
    else:
        template = parse_snapgene(dna_file)
        print(f"Template loaded: {len(template)} bp")

    # Test 1: 1 bp substitution
    print(f"\n{sep}\n  Test 1: 1 bp substitution at pos 100\n{sep}")
    pos = 100
    old_base = template[pos]
    new_base = {"A": "C", "T": "G", "G": "T", "C": "A"}[old_base.upper()]
    r = designer.design(seq=template, subst_pos=pos, old_seq=old_base, new_seq=new_base)
    print(f"  F: 5'-{r['f_full']}-3'  ({r['f_len']} nt, Tm={r['f_tm']}C)")
    print(f"     eff_bind: {r['f_eff_bind']}  ({len(r['f_eff_bind'])} bp)")
    print(f"     QC: {r['f_qc']['verdict']}  "
          f"hairpin Tm={r['f_qc'].get('hairpin_tm','N/A')}C  "
          f"homodimer Tm={r['f_qc'].get('homodimer_tm','N/A')}C")
    print(f"  R: 5'-{r['r_full']}-3'  ({r['r_len']} nt, Tm={r['r_tm']}C)")
    print(f"     QC: {r['r_qc']['verdict']}  "
          f"hairpin Tm={r['r_qc'].get('hairpin_tm','N/A')}C  "
          f"homodimer Tm={r['r_qc'].get('homodimer_tm','N/A')}C")
    print(f"  Anneal temp: {r['anneal_temp']}C")
    print(f"  Overlap verified: {'YES' if r['overlap_verified'] else 'NO'}")
    if r['warnings']:
        for w in r['warnings']:
            print(f"  WARNING: {w}")
    assert r['overlap_verified'], "Test 1 FAILED"
    print("  -> Test 1 PASSED")

    # Test 2: 3 bp substitution
    print(f"\n{sep}\n  Test 2: 3 bp substitution at pos 50\n{sep}")
    old_3 = template[50:53]
    new_3 = str(Seq(old_3).complement())
    r2 = designer.design(seq=template, subst_pos=50, old_seq=old_3, new_seq=new_3, overlap_len=20)
    print(f"  F: 5'-{r2['f_full']}-3'  ({r2['f_len']} nt)")
    print(f"  Overlap verified: {'YES' if r2['overlap_verified'] else 'NO'}")
    assert r2['overlap_verified'], "Test 2 FAILED"
    print("  -> Test 2 PASSED")

    # Test 3: validation error
    print(f"\n{sep}\n  Test 3: Validation error\n{sep}")
    try:
        designer.design(seq=template, subst_pos=100, old_seq="X", new_seq="A")
        print("  -> Test 3 FAILED")
    except ValueError as e:
        print(f"  Caught: {e}")
        print("  -> Test 3 PASSED")

    print(f"\n{sep}\n  All tests PASSED\n{sep}")


if __name__ == "__main__":
    _run_tests()
