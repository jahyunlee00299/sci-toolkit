"""Characterization snapshot of the primer-design MCP server (refactor batch 3).

`primer_design.mcp_server` (1073 lines) was split into tool-group modules. This
module drives every tool function DIRECTLY (no MCP transport, no network:
Entrez is replaced by a scripted fake) and dumps the registered tool list with
its JSON schemas, so tests/test_mcp_characterization.py can prove that the
split changed neither a tool name/schema nor a returned value. The golden file
(tests/golden/mcp_server.json) was produced from the unsplit module.
"""
from __future__ import annotations

import asyncio
import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden"
SRC = HERE.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import characterization as ch  # noqa: E402  (shared scenario sequences)

ECOLI_RARE = "ATGAGGAGAAGGCGGAGAAGGAGAAGGCGGAGAAGGAGAAGGTAA"


def _jsonable(obj):
    return json.loads(json.dumps(obj, sort_keys=True, default=str))


def _norm_paths(obj, tmp: Path):
    """Replace the temp dir by <TMP> (any slash spelling) so paths are stable."""
    text = json.dumps(obj, sort_keys=True, default=str)
    raw = str(tmp)
    for variant in (raw, raw.replace("\\", "\\\\"), tmp.as_posix()):
        text = text.replace(variant, "<TMP>")
    return json.loads(text)


def tool_registry(mod) -> list:
    tools = asyncio.run(mod.mcp.list_tools())
    return sorted(
        ({"name": t.name, "description": t.description, "inputSchema": t.inputSchema}
         for t in tools), key=lambda d: d["name"])


def tool_order(mod) -> list:
    return [t.name for t in asyncio.run(mod.mcp.list_tools())]


# --------------------------------------------------------------------------
# Fake Entrez (scripted NCBI answers)
# --------------------------------------------------------------------------
class _Handle:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return self.payload

    def close(self):
        pass


def _genbank_record(genes) -> str:
    """GenBank text with one CDS per (gene, locus_tag, product, cds_dna)."""
    from Bio import SeqIO
    from Bio.Seq import Seq
    from Bio.SeqFeature import FeatureLocation, SeqFeature
    from Bio.SeqRecord import SeqRecord
    seq = "".join(g[3] for g in genes)
    rec = SeqRecord(Seq(seq), id="NC_FAKE.1", name="NC_FAKE", description="fake record",
                    annotations={"molecule_type": "DNA"})
    pos = 0
    for gene, locus, product, dna in genes:
        rec.features.append(SeqFeature(
            FeatureLocation(pos, pos + len(dna), strand=1), type="CDS",
            qualifiers={"gene": [gene], "locus_tag": [locus], "product": [product]}))
        pos += len(dna)
    buf = io.StringIO()
    SeqIO.write(rec, buf, "genbank")
    return buf.getvalue()


GENE_XML = ("<Entrezgene-Set><Entrezgene><Entrezgene_gene><Gene-ref>"
            "<Gene-ref_locus>gudD</Gene-ref_locus><Gene-ref_desc>glucarate dehydratase"
            "</Gene-ref_desc></Gene-ref></Entrezgene_gene></Entrezgene></Entrezgene-Set>")


def install_fake_entrez(monkeypatch, *, search_ids, links, records):
    """search_ids: {query-substring: [ids]}; links: {linkname: [ids]}; records: {id: genbank}."""
    import time

    from Bio import Entrez
    calls = []

    def esearch(db, term, retmax):
        calls.append(("esearch", term))
        for key, ids in search_ids.items():
            if key in term:
                return _Handle({"IdList": ids})
        return _Handle({"IdList": []})

    def efetch(db, id, rettype, retmode=None):
        calls.append(("efetch", db, id))
        if db == "gene":
            return _Handle(GENE_XML)
        if id not in records:
            raise RuntimeError("no such record")
        return io.StringIO(records[id])

    def elink(dbfrom, db, id, linkname):
        calls.append(("elink", linkname))
        return _Handle([{"LinkSetDb": [{"Link": [{"Id": i} for i in links.get(linkname, [])]}]}])

    monkeypatch.setattr(Entrez, "esearch", esearch)
    monkeypatch.setattr(Entrez, "efetch", efetch)
    monkeypatch.setattr(Entrez, "elink", elink)
    monkeypatch.setattr(Entrez, "read", lambda handle: handle.payload)
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    return calls


CDS_A = "ATGAAAGCTGCCATTGTTCTGAGCGAATAA"       # gudD
CDS_B = "GTGGCGCTGGGTAAACGTTTCCTGACCTAA"       # other gene, GTG start


# --------------------------------------------------------------------------
# Snapshot
# --------------------------------------------------------------------------
def _try(fn, *a, **kw):
    try:
        return _jsonable(fn(*a, **kw))
    except Exception as exc:  # noqa: BLE001 - type and message are the snapshot
        return ["raised", type(exc).__name__, str(exc)]


def _snap_cloning(mod, tmp: Path) -> dict:
    cloning = {}
    scenarios = {
        "pet28a_bamhi_xhoi": dict(insert_seq=ch.TEST_INSERT, re_5prime="BamHI", re_3prime="XhoI",
                                  vector_name="pET-28a(+)", gene_name="geneX",
                                  gene_description="test protein"),
        "pet21a_nhei_noti_stop": dict(insert_seq=ch.TEST_INSERT, re_5prime="NheI", re_3prime="NotI",
                                      vector_name="pET-21a(+)", include_stop_codon=True,
                                      gene_name="gene Y"),
        "no_vector": dict(insert_seq=ch.TEST_INSERT, re_5prime="BamHI", re_3prime="XhoI"),
        "internal_site": dict(insert_seq=ch.WITH_BAMHI, re_5prime="BamHI", re_3prime="XhoI",
                              vector_name="pET-28a(+)"),
        "unknown_vector": dict(insert_seq=ch.TEST_INSERT, re_5prime="BamHI", re_3prime="XhoI",
                               vector_name="no-such-vector"),
        "duet_mcs1": dict(insert_seq=ch.TEST_INSERT, re_5prime="NcoI", re_3prime="HindIII",
                          vector_name="pETDuet-1:MCS1", include_start_codon=False),
        "pmal": dict(insert_seq=ch.TEST_INSERT, re_5prime="BamHI", re_3prime="HindIII",
                     vector_name="pMAL-c6T", gene_name="mal"),
    }
    for name, kw in scenarios.items():
        sub = tmp / name
        res = _try(mod.design_re_cloning_primers, output_dir=str(sub), **kw)
        files = sorted(p.name for p in sub.iterdir()) if sub.exists() else None
        cloning[name] = {"result": _norm_paths(res, tmp), "files": files}
    sub = tmp / "png"
    res = mod.design_re_cloning_primers(
        ch.TEST_INSERT, "BamHI", "XhoI", vector_name="pET-28a(+)", output_dir=str(sub),
        generate_report_png=True)
    cloning["png_flag"] = {
        "has_report_path": "report_image_path" in res,
        "report_error": res.get("report_image_error"),
        "files": sorted(p.name for p in sub.iterdir()),
        "png_nonempty": all(p.stat().st_size > 0 for p in sub.glob("*.png")),
    }
    return cloning


def _fc(vector, topo, f5, f3, l5="", l3=""):
    return {"vector_name": vector, "topology": topo, "in_frame_5prime": f5,
            "in_frame_3prime": f3, "linker_5prime_aa": l5, "linker_3prime_aa": l3}


VIABILITY_INSERTS = {
    "good_stop": ch.TEST_INSERT,
    "internal_both": "ATGAAAGGATCCGCTCTCGAGGCAAAATAA",
    "premature_stop": "ATGAAATAAGCTGCCATTAAATAA",
    "bad_length": "ATGAAAGCTGCCATTG",
    "no_atg": "GCTGCCATTGTTCTGAGCGAATAA",
    "rare": ECOLI_RARE,
    "no_stop": "ATGAAAGCTGCCATTGTTCTGAGCGAAGAA",
}
VIABILITY_DESIGNS = {
    "plain": {"frame_check": {}},
    "n_his_tags": {"frame_check": _fc("pET-28a(+)", "N-His6-Thrombin-T7-tag-insert-C-His6",
                                      True, True, "MGSSHHHHHHSSGLVPRGSH", "LEHHHHHH"),
                   "re_5prime_site": "GGATCC", "re_3prime_site": "CTCGAG"},
    "frame_mismatch5": {"frame_check": _fc("pET-28a(+)", "N-His6-insert", False, True, "MGS", "")},
    "frame_mismatch3": {"frame_check": _fc("pET-21a(+)", "insert-C-His6", True, False, "", "LEH"),
                        "include_stop_codon": False},
    "c_tag_blocked": {"frame_check": _fc("pET-21a(+)", "insert-C-His6", True, True, "", "LEH"),
                      "include_stop_codon": True},
    "mbp": {"frame_check": _fc("pMAL-c6T", "MBP-TEV-insert", True, True, "MKIEE", ""),
            "re_5prime_site": "GGATCC", "re_3prime_site": "AAGCTT"},
    "duet_fuzzy": {"frame_check": _fc("petduet1:mcs1", "N-His6-S-tag-insert-S-tag", True, True, "MGSS", "GS"),
                   "re_5prime_site": "CCATGG", "re_3prime_site": "AAGCTT"},
    "unknown_vec": {"frame_check": _fc("mystery", "x", None, None)},
}


def snapshot_tools(mod, tmp: Path, monkeypatch) -> dict:
    out: dict = {}
    out["design_re_cloning_primers"] = _snap_cloning(mod, tmp)

    out["_check_expression_viability"] = {
        f"{iname}|{dname}": _try(
            mod._check_expression_viability, insert_seq=seq, gene_name="g",
            re_5prime="BamHI", re_3prime="XhoI", design_result=dict(dr))
        for iname, seq in VIABILITY_INSERTS.items() for dname, dr in VIABILITY_DESIGNS.items()}
    out["vector_context"] = {
        n: _try(mod._get_vector_expression_context, n)
        for n in ("", "pET-28a(+)", "pet28a", "PET 28A (+)", "pETDuet-1:MCS2", "pacycduet1mcs1", "nope")}

    out["recommend_re_pair"] = {
        f"{v}|{hf}": _try(mod.recommend_re_pair, ch.TEST_INSERT, v, prefer_hf=hf)
        for v, hf in (("pET-28a(+)", True), ("pET-21a(+)", False), ("pMAL-c6T", True),
                      ("no-such-vector", True))}
    out["suggest_colony_pcr"] = {
        f"{v}|{n}": _try(mod.suggest_colony_pcr, v, n)
        for v, n in (("pET-28a(+)", 1000), ("pET28a", 500), ("pETDuet-1:MCS1", 800),
                     ("pMAL-c6T", 1200), ("bad", 100))}
    out["analyze_expression"] = {
        "test_insert": _try(mod.analyze_expression, ch.TEST_INSERT),
        "rare": _try(mod.analyze_expression, ECOLI_RARE),
        "spaces_newlines": _try(mod.analyze_expression, ch.TEST_INSERT[:30] + " \n" + ch.TEST_INSERT[30:]),
    }
    frame_cases = {
        "pet28a_bamhi_xhoi": dict(vector_name="pET-28a(+)", re_5prime="BamHI", re_3prime="XhoI"),
        "pet21a_stop": dict(vector_name="pET-21a(+)", re_5prime="NheI", re_3prime="NotI",
                            insert_has_stop=True, insert_cds_bp=300),
        "no_atg": dict(vector_name="pET-28a(+)", re_5prime="NdeI", re_3prime="XhoI", insert_has_atg=False),
        "unknown": dict(vector_name="zzz", re_5prime="BamHI", re_3prime="XhoI"),
    }
    out["check_reading_frame_tool"] = {k: _try(mod.check_reading_frame_tool, **kw)
                                       for k, kw in frame_cases.items()}
    out["list_vectors"] = _jsonable(mod.list_vectors())
    out["list_restriction_enzymes"] = _jsonable(mod.list_restriction_enzymes())

    prim = [{"name": "gudD_BamHI_F", "sequence": "GCGCGGATCCATGAAAGCTGCC"},
            {"name": "gudD_XhoI_R", "sequence": "GCGCCTCGAGTTATTCGCTCAG"}]
    orders = {}
    for key, kw in {"default_project": dict(output_dir=str(tmp / "orders")),
                    "named_project": dict(project_name="projX", output_dir=str(tmp / "orders2"))}.items():
        res = mod.generate_macrogen_order(prim, **kw)
        info = {k: v for k, v in res.items() if k != "file_path"}
        info["file_stem"] = Path(res["file_path"]).name.split("_20")[0]
        info["in_dir"] = Path(res["file_path"]).parent.name
        try:
            import openpyxl
            ws = openpyxl.load_workbook(res["file_path"]).active
            info["cells"] = [[c.value for c in row] for row in ws.iter_rows()]
        except Exception as exc:  # noqa: BLE001
            info["cells_error"] = type(exc).__name__
        orders[key] = _jsonable(info)
    out["generate_macrogen_order"] = orders

    out["codon_optimize"] = {
        "ok": mod._codon_optimize_for_ecoli("MKAWRC*"),
        "lower": mod._codon_optimize_for_ecoli("mkv"),
        "bad": _try(mod._codon_optimize_for_ecoli, "MKB"),
    }
    out["fetch_gene_sequence"] = _snap_gene(mod, monkeypatch)
    return out


def _snap_gene(mod, monkeypatch) -> dict:
    rec_multi = _genbank_record([("lacA", "b1", "other", CDS_B), ("gudD", "b2", "glucarate dehydratase", CDS_A)])
    rec_single = _genbank_record([("zzz", "b9", "lonely", CDS_B)])
    rec_nomatch = _genbank_record([("lacA", "b1", "other", CDS_B), ("lacB", "b3", "x", CDS_B)])
    cases = {
        "found_by_search": dict(search_ids={"gudD": ["111"]}, links={"gene_nuccore_refseqrna": ["N1"]},
                                records={"N1": rec_multi}, args=dict(gene_name="gudD")),
        "optimized": dict(search_ids={"gudD": ["111"]}, links={"gene_nuccore_refseqrna": ["N1"]},
                          records={"N1": rec_multi}, args=dict(gene_name="gudD", codon_optimize=True)),
        "explicit_id_single_cds": dict(search_ids={}, links={"gene_nuccore": ["N2"]},
                                       records={"N2": rec_single}, args=dict(gene_name="gudD", gene_id=5)),
        "second_query_hits": dict(search_ids={"[All Fields]": ["7"]}, links={"gene_nuccore_refseqgene": ["N1"]},
                                  records={"N1": rec_multi}, args=dict(gene_name="gudD")),
        "not_found": dict(search_ids={}, links={}, records={}, args=dict(gene_name="nope")),
        "no_links": dict(search_ids={"gudD": ["1"]}, links={}, records={}, args=dict(gene_name="gudD")),
        "no_name_match": dict(search_ids={"gudD": ["1"]}, links={"gene_nuccore": ["N3"]},
                              records={"N3": rec_nomatch}, args=dict(gene_name="qqq", gene_id=1)),
        "fetch_fails": dict(search_ids={"gudD": ["1"]}, links={"gene_nuccore": ["N9"]},
                            records={}, args=dict(gene_name="gudD")),
    }
    gene = {}
    for key, c in cases.items():
        calls = install_fake_entrez(monkeypatch, search_ids=c["search_ids"], links=c["links"],
                                    records=c["records"])
        gene[key] = {"result": _try(mod.fetch_gene_sequence, **c["args"]),
                     "calls": [list(x) for x in calls]}
    return gene
