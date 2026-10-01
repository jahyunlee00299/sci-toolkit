"""Tests for PrimerOrderSheet (converted from order_sheet._run_tests).

Tests 4-9 of the inline version shared one sheet built by tests 1-2; here that
sheet is the module-scoped `sheet` fixture, so every test is independent of
execution order.
"""
import pytest

from primer_design.order_sheet import PrimerOrderSheet

MOCK_RESULT_1 = {
    "f_full": "ATGCGTAACCTGGCGATCAAGCTG",
    "r_full": "CAGCTTGATCGCCAGGTTACGCAT",
    "f_tm": 62.5, "r_tm": 62.5,
    "f_gc": 54.2, "r_gc": 54.2,
    "f_qc": {"verdict": "PASS"}, "r_qc": {"verdict": "PASS"},
}
MOCK_RESULT_2 = {
    "f_full": "GGATCCATGAAAGCTGCCATTGTTCTG",
    "r_full": "CTCGAGTTATTCAACATCGGTCGC",
    "f_tm": 63.1, "r_tm": 61.8,
    "f_gc": 51.9, "r_gc": 50.0,
    "f_qc": {"verdict": "PASS"}, "r_qc": {"verdict": "WARNING"},
    "re_5prime": "BamHI", "re_3prime": "XhoI",
}


@pytest.fixture(scope="module")
def sheet():
    """Five primers: two design pairs + one custom sequencing primer."""
    s = PrimerOrderSheet(project_name="test_order")
    s.add_from_design_result(MOCK_RESULT_1, experiment="site-directed mutagenesis",
                             parent="GeneX_WT", mutation="A123T")
    s.add_from_design_result(MOCK_RESULT_2, experiment="restriction cloning")
    s.add_custom_primer(name="T7_promoter_F", sequence="TAATACGACTCACTATAGGG",
                        experiment="sequencing", direction="F",
                        notes="standard sequencing primer")
    return s


@pytest.fixture(scope="module")
def outdir(tmp_path_factory):
    return tmp_path_factory.mktemp("order_sheet")


def test_add_from_design_result_and_xlsx_export(tmp_path):
    s = PrimerOrderSheet(project_name="test_order")
    f1, r1 = s.add_from_design_result(
        MOCK_RESULT_1, experiment="site-directed mutagenesis",
        parent="GeneX_WT", mutation="A123T")
    assert f1.name == "iPCR_GeneX_WT_A123T_F"
    assert r1.name == "iPCR_GeneX_WT_A123T_R"
    assert f1.sequence == "ATGCGTAACCTGGCGATCAAGCTG"
    assert f1.tm == 62.5
    assert f1.qc_verdict == "PASS"

    f2, r2 = s.add_from_design_result(MOCK_RESULT_2, experiment="restriction cloning")
    assert f2.name == "iPCR_BamHI_XhoI_F"
    assert r2.name == "iPCR_BamHI_XhoI_R"
    assert r2.qc_verdict == "WARNING"

    xlsx_path = s.to_xlsx(tmp_path / "test_order.xlsx")
    assert xlsx_path.exists(), f"XLSX not created: {xlsx_path}"


def test_add_custom_primer():
    s = PrimerOrderSheet(project_name="custom")
    custom = s.add_custom_primer(
        name="T7_promoter_F", sequence="TAATACGACTCACTATAGGG",
        experiment="sequencing", direction="F", notes="standard sequencing primer")
    assert custom.name == "T7_promoter_F"
    assert custom.length == 20
    assert custom.sequence == "TAATACGACTCACTATAGGG"
    assert custom.notes == "standard sequencing primer"


def test_deduplicate_is_case_insensitive_and_keeps_first():
    s = PrimerOrderSheet(project_name="dup_test")
    s.add_custom_primer(name="primer_A", sequence="ATGCGTAACCTGGCG")
    s.add_custom_primer(name="primer_B", sequence="atgcgtaacctggcg")  # same, lowercase
    s.add_custom_primer(name="primer_C", sequence="GGATCCATGAAAGCT")
    assert len(s.entries) == 3

    removed = s.deduplicate()
    assert len(s.entries) == 2
    assert len(removed) == 1
    assert removed[0] == ("primer_B", "primer_A")


def test_summary_statistics(sheet):
    summary = sheet.summary()
    assert summary["total_primers"] == 5
    expected_length = 24 + 24 + 27 + 24 + 20
    assert summary["total_length_nt"] == expected_length

    # Cost: each primer = max(length * 400, 5000)
    expected_cost = (
        max(24 * 400, 5000)    # iPCR_GeneX_WT_A123T_F
        + max(24 * 400, 5000)  # iPCR_GeneX_WT_A123T_R
        + max(27 * 400, 5000)  # iPCR_BamHI_XhoI_F
        + max(24 * 400, 5000)  # iPCR_BamHI_XhoI_R
        + max(20 * 400, 5000)  # T7_promoter_F
    )
    assert summary["estimated_cost_krw"] == expected_cost
    assert summary["scale_counts"]["50 nmol"] == 5
    assert summary["purification_counts"]["Desalting"] == 5
    assert set(summary["unique_experiments"]) == {
        "site-directed mutagenesis", "restriction cloning", "sequencing"}


def test_markdown_export(sheet, outdir):
    md_path = sheet.to_markdown(outdir / "test_order.md")
    assert md_path.exists()
    md_content = md_path.read_text(encoding="utf-8")
    assert "# Primer Order: test_order" in md_content
    assert "iPCR_GeneX_WT_A123T_F" in md_content
    assert "iPCR_BamHI_XhoI_F" in md_content
    assert "T7_promoter_F" in md_content
    assert "## QC Summary" in md_content
    assert "## Summary" in md_content


def test_csv_export_has_utf8_bom(sheet, outdir):
    csv_path = sheet.to_csv(outdir / "test_order.csv")
    assert csv_path.exists()
    csv_bytes = csv_path.read_bytes()
    assert csv_bytes[:3] == b"\xef\xbb\xbf", "CSV missing UTF-8 BOM"
    csv_content = csv_bytes.decode("utf-8-sig")
    assert "iPCR_GeneX_WT_A123T_F" in csv_content
    assert "T7_promoter_F" in csv_content


def test_batch_add_and_dataframe():
    s = PrimerOrderSheet(project_name="batch_test")
    pairs = s.add_batch_from_results([MOCK_RESULT_1, MOCK_RESULT_2])
    assert len(pairs) == 2
    assert len(s.entries) == 4

    df = s.to_dataframe()
    assert len(df) == 4
    assert list(df.columns) == [
        "No.", "Primer Name", "Sequence (5'->3')", "Scale", "Purification",
        "Length (nt)", "Tm", "GC%", "QC Verdict", "Experiment", "Direction", "Notes",
    ]


def test_macrogen_oligo_xls_biff8(sheet, outdir):
    xlrd = pytest.importorskip("xlrd")
    pytest.importorskip("xlwt")
    xls_path = sheet.to_macrogen_oligo(outdir / "macrogen_oligo_test.xls")
    assert xls_path.exists()
    assert xls_path.suffix == ".xls"

    ws = xlrd.open_workbook(str(xls_path)).sheet_by_name("Sheet")
    assert ws.nrows == 1001
    assert ws.ncols == 5

    # header
    assert ws.cell_value(0, 0) == "No."
    assert ws.cell_value(0, 1) == "Oligo Name"
    assert ws.cell_value(0, 2) == "5` - Oligo Seq - 3`"
    assert ws.cell_value(0, 3) == "Amount"
    assert ws.cell_value(0, 4) == "Purification"

    # data row (first of 5 primers)
    assert ws.cell_value(1, 1) == "iPCR_GeneX_WT_A123T_F"
    assert ws.cell_value(1, 2) == "ATGCGTAACCTGGCGATCAAGCTG"
    assert ws.cell_value(1, 3) == 0.05  # 50 nmol = 0.05 umol
    assert ws.cell_value(1, 4) == "MOPC"

    # blank rows (row 6 onward = no data) still carry the No. column
    assert ws.cell_value(6, 1) == ""
    assert ws.cell_value(6, 0) == 6.0

    # OLE2 magic bytes = BIFF8 container
    with open(str(xls_path), "rb") as f:
        magic = f.read(8)
    assert magic == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "Not a valid OLE2/BIFF8 file"


def test_macrogen_oligo_xlsx_fallback(sheet, outdir):
    path = sheet.to_macrogen_oligo(outdir / "macrogen_oligo_test.xlsx")
    assert path.exists()
    assert path.suffix == ".xlsx"


def test_auto_filename_generation(tmp_path):
    s = PrimerOrderSheet(project_name="autoname")
    path1 = s._generate_filename(tmp_path, "xls")
    assert "autoname_" in path1.name
    assert "_001_order.xls" in path1.name
