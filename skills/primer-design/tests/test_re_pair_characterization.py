"""Golden tests pinning RestrictionCloningDesigner.recommend_re_pair across its split (refactor batch 4).

tests/characterization_re_pair.py drives the method over the real vector registry and
over a synthetic registry that reaches every scoring and filter branch, and records the
reading-frame calls it makes. The golden file was produced from the unsplit 130-line
method; a behaviour-preserving split leaves it untouched, and a changed pair, score,
reason string, key order or order among equal scores fails here.
"""
import json

import pytest

import characterization_re_pair as cre

GOLDEN = json.loads((cre.GOLDEN / "re_pair.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def snapshot():
    return cre.build_all()


@pytest.mark.parametrize("group", sorted(GOLDEN))
def test_group_matches_golden(snapshot, group):
    actual = json.loads(json.dumps(snapshot[group], sort_keys=True, ensure_ascii=False, default=str))
    expected = GOLDEN[group]
    assert sorted(actual) == sorted(expected)
    for key in expected:
        assert actual[key] == expected[key], f"{group}/{key} drifted from the golden snapshot"


def test_synthetic_registry_reaches_every_scoring_rule():
    reasons = {part.split(" (")[0] for rec in GOLDEN["synthetic"]["plain|hf=True"]["recommendations"]
               for part in rec["reason"].split("; ")}
    for needle in ("Same buffer", "Both >= 75% in CutSmart", "Sequential digest recommended",
                   "Both 100% in CutSmart", "Reading frame compatible", "Frame mismatch",
                   "Frame check N/A", "HF available: IiiI-HF, JjjI-HF"):
        assert any(needle in r for r in reasons) or any(
            needle in rec["reason"] for rec in GOLDEN["synthetic"]["plain|hf=True"]["recommendations"]), \
            f"scenario for {needle!r} lost"
    pairs = GOLDEN["synthetic"]["plain|hf=True"]["pairs"]
    assert not any("DddI>EeeI" in p or "GggI" in p for p in pairs), "filtered pairs came back"
    assert any(rec["buffer"] is None and rec["double_digest_ok"] is False
               for rec in GOLDEN["synthetic"]["plain|hf=True"]["recommendations"]), "no-buffer-info case lost"


def test_real_registry_prunes_pairs_that_cut_the_insert():
    matrix = GOLDEN["registry"]["matrix"]
    assert matrix["pET-28a(+)|empty|hf=True"]["n"] == 36
    assert matrix["pET-28a(+)|all_sites|hf=True"]["n"] == 0
    assert matrix["pET-28a(+)|with_bamhi|hf=True"]["n"] < matrix["pET-28a(+)|empty|hf=True"]["n"]


def test_digest_is_sensitive_to_a_score_change():
    # Refutation of the harness itself: a one-point change in one entry must change the hash.
    recs = cre.RestrictionCloningDesigner().recommend_re_pair(cre.ch.TEST_INSERT, "pET-28a(+)", True)
    expected = GOLDEN["registry"]["matrix"]["pET-28a(+)|test_insert|hf=True"]["sha256"]
    assert cre._digest(recs) == expected
    recs[3]["score"] += 1
    assert cre._digest(recs) != expected
