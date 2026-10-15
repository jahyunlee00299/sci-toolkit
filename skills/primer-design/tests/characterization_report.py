"""Characterization snapshot of generate_cloning_report (refactor batch 4).

`generate_cloning_report` draws four panels. Two of the functions it calls were the
longest drawing code left in cloning_report.py: `_draw_qc_table` (138 lines) and
`_draw_construct_map` (192 lines). They were split into drawing steps. This module
feeds the report literal design results (the dicts RestrictionCloningDesigner.design()
returns, so the snapshot needs neither primer3 nor the design code) and dumps what the
report hands to `Figure.savefig`: every axes, patch (with its box style) and text,
plus savefig's arguments, the return value and the files and figures it leaves behind.
Figures are compared as artists, not pixels, so the snapshot does not depend on the
matplotlib/freetype build; the header date is normalised. The golden file
(tests/golden/cloning_report.json) was produced from the unsplit functions.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden"
SRC = HERE.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from characterization import _r  # noqa: E402  (shared rounding helper)

# A design result as RestrictionCloningDesigner.design() returns it (BamHI/XhoI into
# pET-28a(+), frame check on, both primers PASS), trimmed to the keys the report reads.
BASE = {
    "re_5prime": "BamHI", "re_3prime": "XhoI", "insert_len": 243,
    "f_full": "GCGCGGATCCATGAAAGCTGCCATTGTTCTG", "r_full": "GCGCCTCGAGTTATTCCACATCGGTCGCTTTC",
    "f_tm": 63.0, "r_tm": 64.4, "f_gc": 42.9, "r_gc": 45.5, "f_len": 31, "r_len": 32,
    "f_ann": "ATGAAAGCTGCCATTGTTCTG", "r_ann": "TTATTCCACATCGGTCGCTTTC",
    "f_ann_len": 21, "r_ann_len": 22,
    "protection_5": "GCGC", "protection_3": "GCGC",
    "re_5prime_site": "GGATCC", "re_3prime_site": "CTCGAG",
    "spacer_5prime": "", "spacer_3prime": "", "include_stop_codon": False,
    "f_tail": "GCGCGGATCC", "r_tail": "GCGCCTCGAG",
    "f_qc": {"hairpin_dg": 0.0, "hairpin_tm": 0.0, "homodimer_dg": -6.5, "homodimer_tm": 20.6,
             "issues": [], "verdict": "PASS"},
    "r_qc": {"hairpin_dg": -0.6, "hairpin_tm": 40.5, "homodimer_dg": -6.2, "homodimer_tm": 19.3,
             "issues": [], "verdict": "PASS"},
    "het": {"dg": -5.5, "tm": 14.6}, "anneal_temp": 64.0, "warnings": [],
    "frame_check": {
        "vector_name": "pET-28a(+)",
        "topology": "[N-His6] [Thrombin] [T7-tag] (BamHI) [ATG-INSERT] (XhoI) [C-His6] [STOP]",
        "in_frame_5prime": True, "in_frame_3prime": True,
        "linker_5prime_aa": "MGSSHHHHHHSSGLVPRGSHMASMTGGQQMGRGS", "linker_3prime_aa": "LEHHHHHH"},
}
LONG_TOPOLOGY = ("[N-His6] [Thrombin] [T7-tag] (BamHI) [ATG-INSERT] (XhoI) [C-His6] [STOP] "
                 "[a topology line deliberately long enough to be cut]\nsecond line is never shown")
LONG_SEQ = "ACGTACGTAC" * 8
FIVE_WARNINGS = [f"warning number {i}" for i in range(1, 6)]


def case(**changes):
    """BASE with top-level keys replaced; a value of `...` deletes the key."""
    dr = copy.deepcopy(BASE)
    for key, value in changes.items():
        if value is ...:
            dr.pop(key, None)
        else:
            dr[key] = value
    return dr


def frame(**changes):
    fc = copy.deepcopy(BASE["frame_check"])
    fc.update(changes)
    return fc


# name -> (design result, keyword arguments of generate_cloning_report, how the output path is given)
SCENARIOS = {
    "pet28a_full": (case(), {"gene_name": "GeneX"}, "path"),
    "default_gene_name_str_path_new_dir": (case(), {}, "str_nested"),
    "warnings_overflow": (case(warnings=list(FIVE_WARNINGS)), {"gene_name": "G"}, "path"),
    "warnings_exactly_three": (case(warnings=FIVE_WARNINGS[:3]), {"gene_name": "G"}, "path"),
    "warnings_four": (case(warnings=FIVE_WARNINGS[:4]), {"gene_name": "G"}, "path"),
    "qc_warning_and_fail": (case(f_qc=dict(BASE["f_qc"], verdict="WARNING"),
                                 r_qc=dict(BASE["r_qc"], verdict="FAIL")), {"gene_name": "G"}, "path"),
    "qc_missing_and_unknown_verdict": (case(f_qc={}, r_qc={"verdict": "CHECK"}, het=..., anneal_temp=...),
                                       {"gene_name": "G"}, "path"),
    "stop_codon_spacers_no_protection": (
        case(re_5prime="NheI", re_3prime="NotI", re_5prime_site="GCTAGC", re_3prime_site="GCGGCCGC",
             protection_5="", protection_3="", spacer_5prime="GC", spacer_3prime="AA",
             include_stop_codon=True, f_tail="GCTAGCGC", r_tail="GCGGCCGCAATTA",
             frame_check=frame(vector_name="pET-21a(+)", topology="[T7-tag] (NheI) [ATG-INSERT-STOP] (NotI)",
                               linker_5prime_aa="MAS", linker_3prime_aa="AAALEHHHHHH")),
        {"gene_name": "GeneY"}, "path"),
    "no_frame_check": (case(frame_check=...), {"gene_name": "G"}, "path"),
    "frame_check_empty_dict": (case(frame_check={}), {"gene_name": "G"}, "path"),
    "out_of_frame_long_topology_5prime_linker_only": (
        case(frame_check=frame(in_frame_5prime=False, in_frame_3prime=False, topology=LONG_TOPOLOGY,
                               linker_3prime_aa="")), {"gene_name": "G"}, "path"),
    "mixed_frame_empty_topology_3prime_linker_only": (
        case(frame_check=frame(in_frame_5prime=True, in_frame_3prime=False, topology="",
                               linker_5prime_aa="", linker_3prime_aa="XYZ")), {"gene_name": "G"}, "path"),
    "topology_exactly_90_chars": (case(frame_check=frame(topology="T" * 90)), {"gene_name": "G"}, "path"),
    "topology_91_chars": (case(frame_check=frame(topology="T" * 91)), {"gene_name": "G"}, "path"),
    "frame_flags_absent_no_linkers_with_report_text": (
        case(frame_check={"topology": "short"}, frame_report="Frame report: nothing to add"),
        {"gene_name": "G"}, "path"),
    "long_sequences": (case(f_full=LONG_SEQ, r_full=LONG_SEQ + "ACG", protection_5="G" * 6, f_tail="G" * 6 + "GGATCC",
                            f_ann=LONG_SEQ[:30], f_ann_len=30, spacer_5prime="TTTTTTTTTTTTTTTTTT"),
                       {"gene_name": "LongGene"}, "path"),
    "zero_insert_empty_tails": (case(insert_len=0, f_tail="", r_tail=""), {"gene_name": "G"}, "path"),
    "insert_len_missing": (case(insert_len=...), {"gene_name": "G"}, "path"),
    "spacer_keys_absent": (case(spacer_5prime=..., spacer_3prime=...), {"gene_name": "G"}, "path"),
    "short_insert_wide_tails": (case(insert_len=30, f_tail="A" * 10, r_tail="C" * 10), {"gene_name": "G"}, "path"),
    "only_forward_tail_narrow": (case(insert_len=40, f_tail="AA", r_tail="C" * 20), {"gene_name": "G"}, "path"),
    "only_reverse_tail_narrow": (case(insert_len=40, f_tail="A" * 20, r_tail="CC"), {"gene_name": "G"}, "path"),
    "huge_insert_both_tails_min_width": (case(insert_len=5000), {"gene_name": "G"}, "path"),
}

# Inputs the report cannot draw; the exception and the figure it leaks are part of the snapshot.
ERROR_SCENARIOS = {
    "missing_3prime_enzyme_fails_in_header": case(re_3prime=...),
    "missing_r_tail_fails_in_construct_map": case(r_tail=...),
    "missing_forward_tm_fails_in_architecture": case(f_tm=...),
}

_DATE = re.compile(r"Date: \d{4}-\d{2}-\d{2}")


def _jsonable(obj):
    return json.loads(json.dumps(obj, sort_keys=True, default=str))


def _colors(value):
    return [_r(c) for c in value]


def _patch(p) -> dict:
    d = {"type": type(p).__name__, "z": p.get_zorder(), "fill": p.get_fill(), "lw": _r(p.get_linewidth()),
         "fc": _colors(p.get_facecolor()), "ec": _colors(p.get_edgecolor()), "alpha": p.get_alpha(),
         "ls": str(p.get_linestyle()), "xy": [_r(p.get_x()), _r(p.get_y())],
         "wh": [_r(p.get_width()), _r(p.get_height())]}
    if hasattr(p, "get_boxstyle"):
        style = p.get_boxstyle()
        d["boxstyle"] = {"class": type(style).__name__, **{k: _r(v) for k, v in sorted(vars(style).items())}}
    return d


def _text(t) -> dict:
    d = {"type": type(t).__name__, "text": _DATE.sub("Date: <date>", t.get_text()),
         "pos": [_r(v) for v in t.get_position()], "size": _r(t.get_fontsize()), "color": str(t.get_color()),
         "weight": str(t.get_fontweight()), "style": str(t.get_fontstyle()), "ha": t.get_ha(), "va": t.get_va(),
         "family": list(t.get_fontfamily()), "z": t.get_zorder(), "rotation": _r(t.get_rotation()),
         "alpha": t.get_alpha()}
    if hasattr(t, "xy"):
        d["xy"] = [_r(v) for v in t.xy]
        d["xytext"] = [_r(v) for v in getattr(t, "xyann", ())]
        d["arrowprops"] = _jsonable(getattr(t, "arrowprops", None))
    return d


def dump_report_figure(fig) -> dict:
    axes = []
    for ax in fig.axes:
        axes.append({
            "position": [_r(v) for v in ax.get_position().bounds],
            "xlim": [_r(x) for x in ax.get_xlim()], "ylim": [_r(y) for y in ax.get_ylim()],
            "axis_off": not ax.axison,
            "counts": {"lines": len(ax.lines), "collections": len(ax.collections), "images": len(ax.images)},
            "patches": [_patch(p) for p in ax.patches],
            "texts": [_text(t) for t in ax.texts],
        })
    return {"size": [_r(v) for v in fig.get_size_inches()], "facecolor": _colors(fig.get_facecolor()),
            "axes": axes}


# Scenarios whose every patch and text is written out; for the others each panel keeps its
# text list, element counts and a hash of the full detail (any changed position, colour,
# size, weight, style or box style changes the hash).
FULL_DETAIL = ("pet28a_full", "stop_codon_spacers_no_protection")

# Rendering a 16x11 in report takes about a second, so only these are really rendered
# (a drawing error can surface at draw time); for the others savefig is replaced by a
# stub that leaves a placeholder file. Pixels are matplotlib's business, not the report's.
REAL_RENDER = ("pet28a_full", "stop_codon_spacers_no_protection")


def summarize(figure: dict, full: bool) -> dict:
    panels = []
    for axes in figure["axes"]:
        panel = {"position": axes["position"], "xlim": axes["xlim"], "ylim": axes["ylim"],
                 "axis_off": axes["axis_off"], "counts": axes["counts"],
                 "n_patches": len(axes["patches"]), "n_texts": len(axes["texts"]),
                 "texts": [t["text"] for t in axes["texts"]],
                 "sha256": hashlib.sha256(json.dumps(
                     [axes["patches"], axes["texts"]], sort_keys=True).encode()).hexdigest()}
        if full:
            panel["patch_elements"] = [json.dumps(p, sort_keys=True) for p in axes["patches"]]
            panel["text_elements"] = [json.dumps(t, sort_keys=True) for t in axes["texts"]]
        panels.append(panel)
    return {"size": figure["size"], "facecolor": figure["facecolor"], "panels": panels}


def _output_path(tmp: Path, name: str, how: str):
    if how == "str_nested":
        return str(tmp / "nested" / "dir" / f"{name}.png")
    return tmp / f"{name}.png"


def snapshot_reports(tmp: Path) -> dict:
    import matplotlib.figure as mfig
    import matplotlib.pyplot as plt

    from primer_design.cloning_report import generate_cloning_report

    captured: list = []
    original = mfig.Figure.savefig
    state = {"render": True}

    def spy(self, *a, **k):
        dated = [t.get_text() for ax in self.axes for t in ax.texts if "Date:" in t.get_text()]
        captured.append({"figure": dump_report_figure(self), "positional": [type(x).__name__ for x in a],
                         "file_name": Path(str(a[0])).name if a else None, "kwargs": _jsonable(k),
                         "header_has_todays_date": bool(dated) and all(date.today().isoformat() in s for s in dated)})
        if state["render"]:
            return original(self, *a, **k)
        Path(a[0]).write_bytes(b"\x89PNG placeholder" + b"0" * 2048)
        return None

    mfig.Figure.savefig = spy
    out: dict = {}
    try:
        for name, (dr, kwargs, how) in SCENARIOS.items():
            captured.clear()
            plt.close("all")
            state["render"] = name in REAL_RENDER
            target = _output_path(tmp, name, how)
            pristine = copy.deepcopy(dr)
            result = generate_cloning_report(dr, target, **kwargs)
            assert len(captured) == 1, name
            out[name] = {
                "figure": summarize(captured[0]["figure"], name in FULL_DETAIL),
                **{k: v for k, v in captured[0].items() if k != "figure"},
                "returned_type": type(result).__name__,
                "returned_the_given_path": result == Path(target),
                "file_written": result.stat().st_size > 1000,
                "parent_dir_exists": result.parent.is_dir(),
                "open_figures_after": len(plt.get_fignums()),
                "design_result_unmodified": dr == pristine,
            }
        state["render"] = False
        for name, dr in ERROR_SCENARIOS.items():
            plt.close("all")
            try:
                generate_cloning_report(copy.deepcopy(dr), tmp / f"{name}.png", gene_name="G")
            except Exception as exc:  # noqa: BLE001 - the type and message are the snapshot
                out[name] = {"raised": [type(exc).__name__, str(exc)], "open_figures_after": len(plt.get_fignums()),
                             "file_written": (tmp / f"{name}.png").exists()}
            else:
                out[name] = {"raised": None}
        plt.close("all")
    finally:
        mfig.Figure.savefig = original
    return out


def build_all(tmp: Path) -> dict:
    return {"reports": snapshot_reports(tmp)}
