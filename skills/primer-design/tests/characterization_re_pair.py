"""Characterization snapshot of RestrictionCloningDesigner.recommend_re_pair (refactor batch 4).

`recommend_re_pair` was one 130-line method: the pair walk, the internal-site filter
and four scoring rules inside a nested loop. This module drives it over the real vector
registry and over a SYNTHETIC registry (the module's enzyme and buffer tables, the vector
lookup and the reading-frame check are swapped for scripted ones) that reaches every branch
the real data cannot, so tests/test_re_pair_characterization.py can prove that splitting
it changed no recommendation, no score, no reason string, no key order and no order among
equal scores. The golden file (tests/golden/re_pair.json) was produced from the unsplit
method.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden"
SRC = HERE.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import characterization as ch  # noqa: E402  (shared insert sequences)
from primer_design import restriction_cloning_mode as rcm  # noqa: E402
from primer_design.restriction_cloning_mode import RestrictionCloningDesigner  # noqa: E402
from primer_design.vector_registry import EXPRESSION_VECTORS, RESTRICTION_ENZYMES  # noqa: E402

# Every recognition site of the registry in one insert: no pair can survive the filter.
ALL_SITES = "".join(info["recognition"] for info in RESTRICTION_ENZYMES.values())
SPACED_LOWERCASE = " ".join([ch.TEST_INSERT[:30].lower(), ch.TEST_INSERT[30:90].lower(),
                             ch.TEST_INSERT[90:]])
INSERTS = {
    "test_insert": ch.TEST_INSERT,
    "with_bamhi": ch.WITH_BAMHI,
    "with_xhoi": ch.WITH_XHOI,
    "all_sites": ALL_SITES,
    "empty": "",
    "spaced_lowercase": SPACED_LOWERCASE,
}
VECTOR_ALIASES = ("pET28a", "pet-28a(+)", "PET 28A (+)", "petduet1:mcs2")
DETAILED = (("pET-28a(+)", True), ("pET-21a(+)", False), ("pMAL-c6T", True), ("pETDuet-1:MCS2", True))


def _jsonable(obj):
    return json.loads(json.dumps(obj, sort_keys=True, default=str))


def _try(fn, *a, **kw):
    try:
        return _jsonable(fn(*a, **kw))
    except Exception as exc:  # noqa: BLE001 - the type and message are the snapshot
        return ["raised", type(exc).__name__, str(exc)]


def _digest(recs: list) -> str:
    """Hash of the result exactly as returned: values, key order and list order."""
    return hashlib.sha256(json.dumps(recs, default=str).encode()).hexdigest()


def _brief(recs: list) -> dict:
    return {"n": len(recs), "types": [type(recs).__name__, sorted({type(r).__name__ for r in recs})],
            "pairs": [f"{r['re_5prime']}>{r['re_3prime']}:{r['score']}" for r in recs],
            "sha256": _digest(recs)}


# --------------------------------------------------------------------------
# real registry
# --------------------------------------------------------------------------
def snapshot_registry() -> dict:
    d = RestrictionCloningDesigner()
    tables_before = copy.deepcopy((RESTRICTION_ENZYMES, rcm.RE_BUFFER_INFO, EXPRESSION_VECTORS))
    out: dict = {"matrix": {}, "detailed": {}, "aliases": {}}
    for vector in EXPRESSION_VECTORS:
        for iname, seq in INSERTS.items():
            for hf in (True, False):
                out["matrix"][f"{vector}|{iname}|hf={hf}"] = _brief(d.recommend_re_pair(seq, vector, hf))
    for vector, hf in DETAILED:
        recs = d.recommend_re_pair(ch.TEST_INSERT, vector, hf)
        out["detailed"][f"{vector}|hf={hf}"] = {"keys": list(recs[0]) if recs else None,
                                                "recommendations": _jsonable(recs)}
    for alias in VECTOR_ALIASES:
        out["aliases"][alias] = _brief(d.recommend_re_pair(ch.TEST_INSERT, alias))
    out["default_prefer_hf"] = _digest(d.recommend_re_pair(ch.TEST_INSERT, "pET-28a(+)")) == \
        _digest(d.recommend_re_pair(ch.TEST_INSERT, "pET-28a(+)", prefer_hf=True))
    out["tables_unchanged"] = tables_before == (RESTRICTION_ENZYMES, rcm.RE_BUFFER_INFO, EXPRESSION_VECTORS)
    return out


# --------------------------------------------------------------------------
# synthetic registry: every scoring branch, the filter branches and the call log
# --------------------------------------------------------------------------
SYN_SITES = {            # name -> position in the synthetic MCS; the dict order is NOT the MCS order
    "CccI": 30, "AaaI": 10, "EeeI": 40, "BbbI": 20, "DddI": 40, "KkkI": 100, "FffI": 50,
    "HhhI": 70, "GggI": 60, "LllI": 110, "NnnI": 120, "IiiI": 80, "JjjI": 90,
}
SYN_ENZYMES = {          # GggI is deliberately missing: a vector site with no enzyme record
    "AaaI": {"recognition": "GGGGCC"}, "BbbI": {"recognition": "CCCCGG"},
    "CccI": {"recognition": "TTTTAA"}, "DddI": {"recognition": "AATTTT"},
    "EeeI": {"recognition": "GATGAT"}, "FffI": {"recognition": "TCATCA"},
    "HhhI": {"recognition": "CGCGAT"}, "IiiI": {"recognition": "ATATGG"},
    "JjjI": {"recognition": "GGATAT"}, "KkkI": {"recognition": "AGAGAG"},
    "LllI": {"recognition": "TAGTAG"}, "NnnI": {"recognition": "CTGCTG"},
}
SYN_BUFFERS = {          # HhhI and LllI have no buffer record; IiiI/JjjI/KkkI have HF variants
    "AaaI": {"buffer": "B1", "activity_cutsmart": 80, "hf": False},
    "BbbI": {"buffer": "B1", "activity_cutsmart": 75, "hf": False},   # exactly on the 75% boundary
    "CccI": {"buffer": "B2", "activity_cutsmart": 90, "hf": False},
    "DddI": {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": False},
    "EeeI": {"buffer": "B3", "activity_cutsmart": 100, "hf": False},
    "FffI": {"buffer": "B4", "activity_cutsmart": 10, "hf": False},
    "IiiI": {"buffer": "B5", "activity_cutsmart": 50, "hf": False},
    "IiiI-HF": {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": True},
    "JjjI-HF": {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": True},
    "KkkI": {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": False},
    "KkkI-HF": {"buffer": "CutSmart", "activity_cutsmart": 100, "hf": True},
    "NnnI": {"buffer": "B7", "activity_cutsmart": 75, "hf": False},   # 75% boundary as the 3' enzyme
}
# (re5, re3) -> in-frame flags, or "raise" for the ValueError a vector without tags gives.
# (DddI, KkkI) answers with truthy non-bool values: frame_ok must still come out as True.
SYN_FRAMES = {
    ("AaaI", "BbbI"): (True, True), ("AaaI", "CccI"): (True, False), ("BbbI", "CccI"): (False, True),
    ("CccI", "DddI"): "raise", ("DddI", "FffI"): (True, True), ("HhhI", "IiiI"): (True, True),
    ("DddI", "KkkI"): (1, "yes"), ("EeeI", "KkkI"): (0, "yes"),
}
SYN_INSERTS = {
    "plain": "ATGAAACCCAAACCCTAA",
    "cut_by_aaai": "ATGGGGGCCAAATAA",
    "cut_by_fffi_and_kkki": "ATGTCATCAAAGAGAGTAA",
    "spaced_lowercase": "atg aaa ccc aaa ccc taa",
    "spaced_site": "atg ggg gcc aaa taa",
}


def _install_synthetic(monkeypatch, frame_log: list) -> None:
    def get_vector(name):
        if name != "synthetic":
            raise ValueError(f"Unknown vector: {name}")
        return {"re_sites": dict(SYN_SITES)}

    def check_reading_frame(**kwargs):
        frame_log.append(dict(sorted(kwargs.items())))
        verdict = SYN_FRAMES.get((kwargs["re_5prime"], kwargs["re_3prime"]), (True, True))
        if verdict == "raise":
            raise ValueError("no tags on this vector")
        return {"in_frame_5prime": verdict[0], "in_frame_3prime": verdict[1]}

    monkeypatch.setattr(rcm, "get_vector", get_vector)
    monkeypatch.setattr(rcm, "check_reading_frame", check_reading_frame)
    monkeypatch.setattr(rcm, "RESTRICTION_ENZYMES", copy.deepcopy(SYN_ENZYMES))
    monkeypatch.setattr(rcm, "RE_BUFFER_INFO", copy.deepcopy(SYN_BUFFERS))


def _call_shapes(frame_log: list) -> dict:
    """What the method passes to check_reading_frame: argument names and the values that vary."""
    return {"keyword_sets": sorted({tuple(call) for call in frame_log}),
            "insert_has_atg": sorted({call["insert_has_atg"] for call in frame_log}),
            "insert_has_stop": sorted({call["insert_has_stop"] for call in frame_log}),
            "vector_name": sorted({call["vector_name"] for call in frame_log})}


def snapshot_synthetic(monkeypatch) -> dict:
    frame_log: list = []
    _install_synthetic(monkeypatch, frame_log)
    d = RestrictionCloningDesigner()
    out: dict = {}
    for iname, seq in SYN_INSERTS.items():
        for hf in (True, False):
            del frame_log[:]
            recs = d.recommend_re_pair(seq, "synthetic", hf)
            entry = _brief(recs)
            entry["keys"] = list(recs[0]) if recs else None
            entry["reading_frame_pairs"] = [f"{c['re_5prime']}>{c['re_3prime']}" for c in frame_log]
            entry["reading_frame_call_shapes"] = _call_shapes(frame_log)
            if iname == "plain":  # the full recommendations for the insert that reaches every branch
                entry["recommendations"] = _jsonable(recs)
            out[f"{iname}|hf={hf}"] = entry
    out["spaced_lowercase_equals_plain"] = all(
        out[f"spaced_lowercase|hf={hf}"]["sha256"] == out[f"plain|hf={hf}"]["sha256"] for hf in (True, False))
    out["spaced_site_equals_cut_by_aaai"] = all(
        out[f"spaced_site|hf={hf}"]["sha256"] == out[f"cut_by_aaai|hf={hf}"]["sha256"] for hf in (True, False))
    out["tables_unchanged"] = (rcm.RESTRICTION_ENZYMES == SYN_ENZYMES and rcm.RE_BUFFER_INFO == SYN_BUFFERS)
    return out


# --------------------------------------------------------------------------
# errors, signature, delegation
# --------------------------------------------------------------------------
def snapshot_errors() -> dict:
    d = RestrictionCloningDesigner()
    return {
        "unknown_vector": _try(d.recommend_re_pair, ch.TEST_INSERT, "no-such-vector"),
        "insert_is_none": _try(d.recommend_re_pair, None, "pET-28a(+)"),
        "vector_is_none": _try(d.recommend_re_pair, ch.TEST_INSERT, None),
        "empty_insert_is_valid": _brief(d.recommend_re_pair("", "pET-28a(+)")),
    }


def snapshot_signature() -> dict:
    method = RestrictionCloningDesigner.recommend_re_pair
    sig = inspect.signature(method)
    return {
        "parameters": [[p.name, str(p.kind), str(p.annotation),
                        "<required>" if p.default is inspect.Parameter.empty else repr(p.default)]
                       for p in sig.parameters.values()],
        "returns": str(sig.return_annotation),
        "is_plain_method": inspect.isfunction(method),
    }


def snapshot_delegation() -> dict:
    """The MCP tool function is a thin wrapper over the designer method."""
    from primer_design import mcp_cloning_tools as tools

    d = RestrictionCloningDesigner()
    same = {}
    for vector, hf in (("pET-28a(+)", True), ("pET-21a(+)", False), ("pMAL-c6T", True)):
        same[f"{vector}|hf={hf}"] = _digest(tools.recommend_re_pair(ch.TEST_INSERT, vector, hf)) == \
            _digest(d.recommend_re_pair(ch.TEST_INSERT, vector, hf))
    wrapper = inspect.signature(tools.recommend_re_pair)
    return {"wrapper_equals_designer": same,
            "wrapper_parameters": [[p.name, str(p.annotation), repr(p.default)]
                                   for p in wrapper.parameters.values()],
            "wrapper_error": _try(tools.recommend_re_pair, ch.TEST_INSERT, "no-such-vector")}


def build_all() -> dict:
    out = {
        "registry": snapshot_registry(),
        "errors": snapshot_errors(),
        "signature": snapshot_signature(),
        "delegation": snapshot_delegation(),
    }
    mp = pytest.MonkeyPatch()  # the synthetic registry must not outlive this call
    try:
        out["synthetic"] = snapshot_synthetic(mp)
    finally:
        mp.undo()
    return out
