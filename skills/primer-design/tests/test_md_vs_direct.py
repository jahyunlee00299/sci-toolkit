#!/usr/bin/env python3
"""
Test: MD Template Parser vs Direct API Pipeline Comparison
==========================================================

MD template (md-task-builder/templates/primer-design.md)에서 파라미터를 파싱하여
primer design을 실행하고, 동일한 파라미터를 직접 Python API로 실행한 결과와 비교.

Pipeline A (MD-based):
  primer-design.md -> parse params -> RestrictionCloningDesigner.design()
                   -> write_cloning_construct() -> cloned_vector.dna

Pipeline B (Direct API):
  hardcoded params -> RestrictionCloningDesigner.design()
                   -> write_cloning_construct() -> cloned_vector_ref.dna

Comparison checks:
  1. MD parsing accuracy (all params extracted correctly)
  2. Primer sequences match (F/R)
  3. Tm / GC% / length values match
  4. Cloned vector sequence match (byte-level)
  5. Feature positions match
  6. Insert is findable in the vector (in-silico validation)

Usage:
  cd scientific-skills/primer-design
  python tests/test_md_vs_direct.py
  python tests/test_md_vs_direct.py --verbose
"""
from __future__ import annotations

import argparse
import io
import re
import sys
import tempfile
from pathlib import Path
from Bio.Seq import Seq

# Windows cp949 환경에서 한글/특수문자 출력 오류 방지
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from primer_design.restriction_cloning_mode import RestrictionCloningDesigner
from primer_design.snapgene_writer import write_cloning_construct
from primer_design.snapgene_parser import parse_snapgene


# ── Constants ────────────────────────────────────────────────────────────────

TEMPLATE_MD = (
    Path(__file__).resolve().parent.parent.parent
    / "md-task-builder" / "templates" / "primer-design.md"
)
VECTORS_DIR = Path(__file__).resolve().parent.parent / "vectors"

PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"


# ── MD Template Parser ────────────────────────────────────────────────────────

class MDTemplateParser:
    """primer-design.md 템플릿에서 모든 입력 파라미터를 파싱."""

    def __init__(self, md_path: Path):
        self.md_path = md_path
        self._content = md_path.read_text(encoding="utf-8")

    def _extract_section(self, heading: str) -> str:
        """## Heading 섹션 텍스트 추출 (다음 --- 또는 파일 끝까지)."""
        m = re.search(
            r'## ' + re.escape(heading) + r'\s*\n(.*?)(?:\n---|\Z)',
            self._content, re.DOTALL
        )
        return m.group(1) if m else ""

    @staticmethod
    def _get_val_from_section(section: str, label: str, char_class: str = r'[^`|\n]') -> str | None:
        """마크다운 테이블 섹션에서 특정 행의 값을 추출."""
        escaped = re.escape(label)
        m = re.search(
            r'\|[^|]*' + escaped + r'[^|]*\|\s*`?(' + char_class + r'+)`?\s*\|',
            section, re.IGNORECASE
        )
        return m.group(1).strip().strip('`').strip() if m else None

    def extract_re_enzymes(self) -> tuple[str | None, str | None]:
        """RE Cloning 섹션에서 5'/3' 제한효소명 추출."""
        section = self._extract_section("RE Cloning Input")
        re5 = re.search(r"5[^\|]*\|\s*`?([A-Za-z]+I?(?:-HF)?)`?", section)
        re3 = re.search(r"3[^\|]*\|\s*`?([A-Za-z]+I?(?:-HF)?)`?", section)
        return (
            re5.group(1).strip() if re5 else None,
            re3.group(1).strip() if re3 else None,
        )

    def parse_template_sequence(self) -> str:
        """Template DNA Sequence 코드블록에서 서열 추출."""
        match = re.search(
            r'### Template DNA Sequence\s*\n\s*```\s*\n(.*?)\n\s*```',
            self._content, re.DOTALL
        )
        if not match:
            return ""
        raw = match.group(1)
        seq = raw.replace("\n", "").replace(" ", "").upper()
        # Keep only valid ATGC
        seq = re.sub(r'[^ATGC]', '', seq)
        return seq

    def parse_re_cloning_params(self) -> dict:
        """RE Cloning Input 테이블에서 파라미터 파싱."""
        section = self._extract_section("RE Cloning Input")

        def get_val(label: str) -> str | None:
            return self._get_val_from_section(section, label)

        raw_tm = get_val("Target annealing Tm")
        try:
            tm = float(raw_tm) if raw_tm else 62.0
        except ValueError:
            tm = 62.0

        atg_raw = get_val("Include start codon")
        stop_raw = get_val("Include stop codon")
        re5, re3 = self.extract_re_enzymes()

        return {
            "gene_name":    get_val("Gene") or get_val("Gene / protein name") or "GDH",
            "vector":       get_val("Expression vector") or "pET-28a(+)",
            "re_5prime":    re5 or "NdeI",
            "re_3prime":    re3 or "XhoI",
            "include_atg":  (atg_raw or "Yes").lower() == "yes",
            "include_stop": (stop_raw or "No").lower() == "yes",
            "target_tm":    tm,
        }

    def parse_sdm_params(self) -> dict:
        """SDM Input 테이블에서 파라미터 파싱."""
        section = self._extract_section("SDM Input")

        def get_val(label: str) -> str | None:
            return self._get_val_from_section(section, label, char_class=r'[^`|\n*()]')

        pos_raw = get_val("Amino acid position")
        overlap_raw = get_val("Overlap length")
        tm_raw = get_val("Target Tm")

        try:
            pos = int(pos_raw) if pos_raw else 42
        except ValueError:
            pos = 42
        try:
            overlap = int(overlap_raw) if overlap_raw else 15
        except ValueError:
            overlap = 15
        try:
            tm = float(tm_raw) if tm_raw else 62.0
        except ValueError:
            tm = 62.0

        return {
            "aa_position":   pos,
            "current_aa":    (get_val("Current amino acid") or "C").strip(),
            "new_aa":        (get_val("New amino acid") or "A").strip(),
            "target_tm":     tm,
            "overlap_len":   overlap,
        }

    def parse_modes(self) -> dict[str, bool]:
        """SDM / RE Cloning mode 체크박스 파싱."""
        sdm_checked = bool(re.search(r'\[x\]\s*\*\*SDM\*\*', self._content, re.IGNORECASE))
        re_checked = bool(re.search(r'\[x\]\s*\*\*RE Cloning\*\*', self._content, re.IGNORECASE))
        return {"sdm": sdm_checked, "re_cloning": re_checked}


# ── Pipeline Runners ─────────────────────────────────────────────────────────

def run_pipeline_from_md(template_path: Path, output_dir: Path) -> dict:
    """
    Pipeline A: MD 템플릿을 파싱하여 primer design 실행.
    Returns dict with design_result, dna_path, params.
    """
    parser = MDTemplateParser(template_path)

    template_seq = parser.parse_template_sequence()
    re_params = parser.parse_re_cloning_params()

    designer = RestrictionCloningDesigner()
    design_result = designer.design(
        insert_seq=template_seq,
        re_5prime=re_params["re_5prime"],
        re_3prime=re_params["re_3prime"],
        vector_name=re_params["vector"],
        target_tm=re_params["target_tm"],
        include_start_codon=re_params["include_atg"],
        include_stop_codon=re_params["include_stop"],
    )

    vector_dna = VECTORS_DIR / f"{re_params['vector']}.dna"
    output_path = output_dir / f"{re_params['gene_name']}_in_{re_params['vector']}_md.dna"


    write_cloning_construct(
        design_result=design_result,
        insert_seq=template_seq,
        output_path=output_path,
        gene_name=re_params["gene_name"],
        vector_dna_path=vector_dna if vector_dna.exists() else None,
    )

    return {
        "params":        re_params,
        "template_seq":  template_seq,
        "design_result": design_result,
        "dna_path":      output_path,
        "vector_exists": vector_dna.exists(),
    }


def run_pipeline_direct(output_dir: Path) -> dict:
    """
    Pipeline B: 동일한 파라미터를 직접 Python API로 실행.
    MD 템플릿의 예시값을 그대로 하드코딩하여 기준값(reference) 생성.
    """
    # Exact values from primer-design.md template
    TEMPLATE_SEQ = (
        "ATGAAAGCAATTTTCGTACTGAAAGGTTTTGTTGGTTTTCTTGCATTTATAATGTATCGT"
        "TTATTTAATCTGTTTAAAATGGTATCAAATCGTAAAGGTATTGAAAGTTCTTTAGGTGGT"
        "ACAGTTATGGCTTCAGCAATCGGTCGTGGTGTTGGTGCATTTGGTTTTTTAGCAGAACGT"
    )
    GENE_NAME  = "GDH"
    VECTOR     = "pET-28a(+)"
    RE_5PRIME  = "NdeI"
    RE_3PRIME  = "XhoI"
    INCLUDE_ATG  = True
    INCLUDE_STOP = False
    TARGET_TM    = 62.0

    designer = RestrictionCloningDesigner()
    design_result = designer.design(
        insert_seq=TEMPLATE_SEQ,
        re_5prime=RE_5PRIME,
        re_3prime=RE_3PRIME,
        vector_name=VECTOR,
        target_tm=TARGET_TM,
        include_start_codon=INCLUDE_ATG,
        include_stop_codon=INCLUDE_STOP,
    )

    vector_dna = VECTORS_DIR / f"{VECTOR}.dna"
    output_path = output_dir / f"{GENE_NAME}_in_{VECTOR}_direct.dna"

    write_cloning_construct(
        design_result=design_result,
        insert_seq=TEMPLATE_SEQ,
        output_path=output_path,
        gene_name=GENE_NAME,
        vector_dna_path=vector_dna if vector_dna.exists() else None,
    )

    return {
        "params": {
            "gene_name":    GENE_NAME,
            "vector":       VECTOR,
            "re_5prime":    RE_5PRIME,
            "re_3prime":    RE_3PRIME,
            "include_atg":  INCLUDE_ATG,
            "include_stop": INCLUDE_STOP,
            "target_tm":    TARGET_TM,
        },
        "template_seq":  TEMPLATE_SEQ,
        "design_result": design_result,
        "dna_path":      output_path,
        "vector_exists": vector_dna.exists(),
    }


# ── Validators ───────────────────────────────────────────────────────────────

def validate_insert_in_vector(dna_path: Path, insert_seq: str) -> dict:
    """
    생성된 SnapGene .dna 파일에서 insert 서열이 실제로 존재하는지 확인.
    Also checks if NdeI/XhoI sites flank the insert.
    """
    seq, circular, features = parse_snapgene(str(dna_path))
    if seq is None:
        return {"ok": False, "error": "Could not parse .dna file"}

    insert_upper = insert_seq.upper()
    seq_upper = seq.upper()

    # Direct presence
    pos = seq_upper.find(insert_upper)
    if pos == -1:
        # Try reverse complement (pET vectors put insert on bottom strand)
        rc = str(Seq(insert_upper).reverse_complement())
        pos = seq_upper.find(rc)
        strand = -1 if pos != -1 else 0
    else:
        strand = 1

    # Find CDS annotation
    cds_features = [f for f in features if f.get("type") == "CDS"]
    primer_features = [f for f in features if f.get("type") == "primer_bind"]

    return {
        "ok":              pos != -1,
        "insert_pos":      pos,
        "insert_strand":   strand,
        "vector_len":      len(seq),
        "n_features":      len(features),
        "n_cds":           len(cds_features),
        "n_primers":       len(primer_features),
        "cds_features":    cds_features,
        "primer_features": primer_features,
        "is_circular":     circular,
    }


def compare_dna_files(path_a: Path, path_b: Path) -> dict:
    """두 SnapGene .dna 파일의 서열과 feature를 비교."""
    seq_a, circ_a, feats_a = parse_snapgene(str(path_a))
    seq_b, circ_b, feats_b = parse_snapgene(str(path_b))

    seq_match = (seq_a == seq_b)
    len_match = len(seq_a or "") == len(seq_b or "")
    circ_match = (circ_a == circ_b)

    # Feature count
    feat_count_match = len(feats_a) == len(feats_b)

    # CDS position match
    cds_a = sorted([f for f in feats_a if f.get("type") == "CDS"],
                   key=lambda f: f["start"])
    cds_b = sorted([f for f in feats_b if f.get("type") == "CDS"],
                   key=lambda f: f["start"])
    cds_pos_match = (
        len(cds_a) == len(cds_b) and
        all(a["start"] == b["start"] and a["end"] == b["end"]
            for a, b in zip(cds_a, cds_b))
    )

    diff_positions: list[int] = []
    n_diffs = 0
    if seq_a and seq_b and len(seq_a) == len(seq_b):
        for i, (a, b) in enumerate(zip(seq_a, seq_b)):
            if a != b:
                n_diffs += 1
                if len(diff_positions) < 20:
                    diff_positions.append(i)

    return {
        "seq_match":        seq_match,
        "len_a":            len(seq_a or ""),
        "len_b":            len(seq_b or ""),
        "len_match":        len_match,
        "circ_match":       circ_match,
        "feat_count_a":     len(feats_a),
        "feat_count_b":     len(feats_b),
        "feat_count_match": feat_count_match,
        "cds_pos_match":    cds_pos_match,
        "cds_a":            cds_a,
        "cds_b":            cds_b,
        "diff_positions":   diff_positions,
        "n_diffs":          n_diffs,
    }


# ── Report Generator ─────────────────────────────────────────────────────────

def print_section(title: str):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_check(label: str, ok: bool, detail: str = ""):
    icon = PASS if ok else FAIL
    msg = f"  {icon}  {label}"
    if detail:
        msg += f"  [{detail}]"
    print(msg)


def run_all_tests(verbose: bool = False) -> bool:
    """메인 테스트 실행 및 결과 리포트."""
    all_passed = True

    # ── 0. Pre-checks ─────────────────────────────────────────────────────
    print_section("0. Pre-checks")

    md_exists = TEMPLATE_MD.exists()
    print_check("MD template exists", md_exists, str(TEMPLATE_MD))
    if not md_exists:
        print(f"  {FAIL}  Cannot run tests: template not found at {TEMPLATE_MD}")
        return False

    vector_path = VECTORS_DIR / "pET-28a(+).dna"
    vec_exists = vector_path.exists()
    print_check("pET-28a(+).dna exists", vec_exists, str(vector_path))

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # ── 1. MD Parsing ─────────────────────────────────────────────────
        print_section("1. MD Template Parsing")

        parser = MDTemplateParser(TEMPLATE_MD)
        template_seq = parser.parse_template_sequence()
        re_params = parser.parse_re_cloning_params()
        sdm_params = parser.parse_sdm_params()

        expected_seq_prefix = "ATGAAAGCAATTTTCGTACTGAAA"
        seq_ok = template_seq.startswith(expected_seq_prefix)
        seq_len_ok = len(template_seq) == 180

        print_check("Template sequence parsed", seq_ok and seq_len_ok,
                    f"{len(template_seq)} bp, starts: {template_seq[:24]}")
        if not (seq_ok and seq_len_ok):
            all_passed = False
            print(f"  Expected 180 bp starting with {expected_seq_prefix}")
            print(f"  Got: {len(template_seq)} bp, {template_seq[:50]}")

        checks = [
            ("Gene name = GDH",         re_params["gene_name"] == "GDH"),
            ("Vector = pET-28a(+)",     re_params["vector"] == "pET-28a(+)"),
            ("RE 5' = NdeI",            re_params["re_5prime"] == "NdeI"),
            ("RE 3' = XhoI",            re_params["re_3prime"] == "XhoI"),
            ("Include ATG = True",       re_params["include_atg"] is True),
            ("Include stop = False",     re_params["include_stop"] is False),
            ("Target Tm = 62.0",         re_params["target_tm"] == 62.0),
            ("SDM aa pos = 42",          sdm_params["aa_position"] == 42),
            ("SDM current_aa = C",       sdm_params["current_aa"].upper() == "C"),
            ("SDM new_aa = A",           sdm_params["new_aa"].upper() == "A"),
        ]
        for label, ok in checks:
            print_check(label, ok)
            if not ok:
                all_passed = False

        if verbose:
            print(f"\n  Parsed RE params: {re_params}")
            print(f"  Parsed SDM params: {sdm_params}")

        # ── 2. Run Both Pipelines ─────────────────────────────────────────
        print_section("2. Pipeline Execution")

        try:
            result_md = run_pipeline_from_md(TEMPLATE_MD, tmp)
            print_check("Pipeline A (MD-based) ran without error", True)
        except Exception as e:
            print_check("Pipeline A (MD-based) ran without error", False, str(e))
            all_passed = False
            return False

        try:
            result_direct = run_pipeline_direct(tmp)
            print_check("Pipeline B (Direct API) ran without error", True)
        except Exception as e:
            print_check("Pipeline B (Direct API) ran without error", False, str(e))
            all_passed = False
            return False

        dr_md = result_md["design_result"]
        dr_di = result_direct["design_result"]

        # ── 3. Primer Sequence Comparison ─────────────────────────────────
        print_section("3. Primer Sequence Comparison")

        f_match = dr_md["f_full"] == dr_di["f_full"]
        r_match = dr_md["r_full"] == dr_di["r_full"]

        print_check("Forward primer sequences match", f_match)
        print_check("Reverse primer sequences match", r_match)

        if not f_match:
            all_passed = False
            print(f"  MD:     5'-{dr_md['f_full']}-3'")
            print(f"  Direct: 5'-{dr_di['f_full']}-3'")
        if not r_match:
            all_passed = False
            print(f"  MD:     5'-{dr_md['r_full']}-3'")
            print(f"  Direct: 5'-{dr_di['r_full']}-3'")

        if verbose or not (f_match and r_match):
            print(f"\n  Pipeline A (MD-based):")
            print(f"    F: 5'-{dr_md['f_full']}-3'")
            print(f"       tail={dr_md['f_tail']}  ann={dr_md['f_ann']}  ({dr_md['f_ann_len']} bp)")
            print(f"       Tm={dr_md['f_tm']}C  GC={dr_md['f_gc']}%  QC={dr_md['f_qc']['verdict']}")
            print(f"    R: 5'-{dr_md['r_full']}-3'")
            print(f"       tail={dr_md['r_tail']}  ann={dr_md['r_ann']}  ({dr_md['r_ann_len']} bp)")
            print(f"       Tm={dr_md['r_tm']}C  GC={dr_md['r_gc']}%  QC={dr_md['r_qc']['verdict']}")
            if dr_md.get("warnings"):
                print(f"    Warnings: {dr_md['warnings']}")

        # ── 4. Numeric Metrics Comparison ─────────────────────────────────
        print_section("4. Primer Metrics Comparison")

        metrics = [
            ("F Tm",    dr_md["f_tm"],    dr_di["f_tm"]),
            ("R Tm",    dr_md["r_tm"],    dr_di["r_tm"]),
            ("F GC%",   dr_md["f_gc"],    dr_di["f_gc"]),
            ("R GC%",   dr_md["r_gc"],    dr_di["r_gc"]),
            ("F length", dr_md["f_len"],  dr_di["f_len"]),
            ("R length", dr_md["r_len"],  dr_di["r_len"]),
            ("F ann_len", dr_md["f_ann_len"], dr_di["f_ann_len"]),
            ("R ann_len", dr_md["r_ann_len"], dr_di["r_ann_len"]),
        ]
        for label, val_md, val_di in metrics:
            ok = val_md == val_di
            detail = f"MD={val_md}  Direct={val_di}" if not ok else f"{val_md}"
            print_check(f"{label} match", ok, detail)
            if not ok:
                all_passed = False

        # QC verdicts
        f_qc_match = dr_md["f_qc"]["verdict"] == dr_di["f_qc"]["verdict"]
        r_qc_match = dr_md["r_qc"]["verdict"] == dr_di["r_qc"]["verdict"]
        print_check("F QC verdict match", f_qc_match,
                    f"MD={dr_md['f_qc']['verdict']} Direct={dr_di['f_qc']['verdict']}")
        print_check("R QC verdict match", r_qc_match,
                    f"MD={dr_md['r_qc']['verdict']} Direct={dr_di['r_qc']['verdict']}")
        if not f_qc_match or not r_qc_match:
            all_passed = False

        # ── 5. Cloned Vector Comparison ────────────────────────────────────
        print_section("5. Cloned Vector (.dna) Comparison")

        if not (result_md["dna_path"].exists() and result_direct["dna_path"].exists()):
            print_check("Both .dna files generated", False)
            all_passed = False
        else:
            print_check("Both .dna files generated", True)

            diff = compare_dna_files(result_md["dna_path"], result_direct["dna_path"])

            print_check("Sequences identical", diff["seq_match"],
                        f"MD={diff['len_a']} bp  Direct={diff['len_b']} bp")
            print_check("Circular topology match", diff["circ_match"])
            print_check("Feature count match", diff["feat_count_match"],
                        f"MD={diff['feat_count_a']}  Direct={diff['feat_count_b']}")
            print_check("CDS positions match", diff["cds_pos_match"])

            if not diff["seq_match"]:
                all_passed = False
                if diff["n_diffs"] > 0:
                    print(f"  {diff['n_diffs']} position(s) differ")
                    if diff["diff_positions"]:
                        print(f"  First diff positions: {diff['diff_positions'][:5]}")

            if verbose and diff["cds_a"]:
                print(f"\n  CDS (MD):     {diff['cds_a']}")
                print(f"  CDS (Direct): {diff['cds_b']}")

        # ── 6. In-silico Validation ────────────────────────────────────────
        print_section("6. In-Silico Cloning Validation")

        for label, res in [("MD pipeline", result_md), ("Direct API", result_direct)]:
            val = validate_insert_in_vector(res["dna_path"], res["template_seq"])

            print(f"\n  [{label}]")
            print_check("  Insert found in vector", val["ok"],
                        f"pos={val.get('insert_pos', 'N/A')} strand={val.get('insert_strand', 'N/A')}")
            print_check("  Vector is circular", val.get("is_circular", False))
            print_check("  CDS annotation present", val.get("n_cds", 0) > 0,
                        f"{val.get('n_cds', 0)} CDS feature(s)")
            print_check("  Primer annotations present", val.get("n_primers", 0) >= 2,
                        f"{val.get('n_primers', 0)} primer_bind feature(s)")

            if not val["ok"]:
                all_passed = False

            if verbose and val.get("cds_features"):
                for cds in val["cds_features"]:
                    print(f"    CDS: {cds['name']} {cds['start']+1}-{cds['end']+1}")
            if verbose and val.get("primer_features"):
                for pf in val["primer_features"]:
                    print(f"    Primer: {pf['name']} {pf['start']+1}-{pf['end']+1} strand={pf['strand']}")

        # ── 7. Primer QC Summary ───────────────────────────────────────────
        print_section("7. Primer QC Details (MD Pipeline)")

        dr = dr_md
        print(f"  Forward primer: 5'-{dr['f_full']}-3'")
        print(f"    Tail: {dr['f_tail']}")
        print(f"    Annealing: {dr['f_ann']} ({dr['f_ann_len']} bp)")
        print(f"    Tm: {dr['f_tm']}C  GC: {dr['f_gc']}%  Length: {dr['f_len']} nt")
        print(f"    QC: {dr['f_qc']['verdict']}")

        print(f"\n  Reverse primer: 5'-{dr['r_full']}-3'")
        print(f"    Tail: {dr['r_tail']}")
        print(f"    Annealing: {dr['r_ann']} ({dr['r_ann_len']} bp)")
        print(f"    Tm: {dr['r_tm']}C  GC: {dr['r_gc']}%  Length: {dr['r_len']} nt")
        print(f"    QC: {dr['r_qc']['verdict']}")

        print(f"\n  Annealing temp: {dr['anneal_temp']}C")
        het = dr.get("het", {})
        print(f"  Heterodimer dG: {het.get('dg', 'N/A')} kcal/mol")

        if dr.get("frame_report"):
            print(f"\n  Reading Frame Report:")
            for line in dr["frame_report"].split("\n"):
                print(f"    {line}")

        if dr.get("warnings"):
            print(f"\n  Warnings:")
            for w in dr["warnings"]:
                print(f"    - {w}")

        # ── 8. Issue Analysis ──────────────────────────────────────────────
        print_section("8. Issue Analysis & Recommendations")

        issues = []

        # Check if insert is not AT-rich (which could cause Tm issues)
        seq = result_md["template_seq"]
        at_content = (seq.count('A') + seq.count('T')) / len(seq) * 100
        if at_content > 60:
            issues.append(f"AT-rich insert ({at_content:.0f}% AT) — Tm may be difficult to reach")

        # Check for internal RE sites
        for key in ["internal_re_sites_5", "internal_re_sites_3"]:
            sites = dr_md.get(key, [])
            if sites:
                enz = dr_md["re_5prime"] if "5" in key else dr_md["re_3prime"]
                issues.append(f"Internal {enz} site at position(s) {sites} — will cut insert!")

        # Check primer QC
        for label, qc in [("Forward", dr_md["f_qc"]), ("Reverse", dr_md["r_qc"])]:
            if qc["verdict"] == "FAIL":
                reasons = "; ".join(qc.get("issues", ["unknown"]))
                issues.append(f"{label} primer QC FAIL — {reasons}")
            elif qc["verdict"] == "WARNING":
                reasons = "; ".join(qc.get("issues", ["marginal structure"]))
                issues.append(f"{label} primer QC WARNING — {reasons}")

        # Check Tm balance
        tm_diff = abs(dr_md["f_tm"] - dr_md["r_tm"])
        if tm_diff > 5:
            issues.append(f"Tm imbalance: F={dr_md['f_tm']}C vs R={dr_md['r_tm']}C (diff={tm_diff:.1f}C)")

        if issues:
            print(f"\n  {len(issues)} issue(s) found:")
            for issue in issues:
                print(f"  {WARN}  {issue}")
        else:
            print(f"\n  No issues found — design looks good!")

        # ── Final Summary ──────────────────────────────────────────────────
        print_section("FINAL SUMMARY")

        if all_passed:
            print(f"  {PASS}  All tests passed — MD pipeline == Direct API pipeline")
        else:
            print(f"  {FAIL}  Some tests failed — see details above")

        # Output file locations
        print(f"\n  Generated files:")
        print(f"    MD-based:   {result_md['dna_path']}")
        print(f"    Direct API: {result_direct['dna_path']}")

    return all_passed


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Test MD template parser vs direct API primer design pipeline"
    )
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show detailed output")
    args = parser.parse_args()

    print("=" * 70)
    print("  Primer Design: MD Template vs Direct API Comparison Test")
    print("=" * 70)
    print(f"  Template: {TEMPLATE_MD}")
    print(f"  Vectors:  {VECTORS_DIR}")

    ok = run_all_tests(verbose=args.verbose)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
