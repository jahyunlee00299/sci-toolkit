"""neb_tm guards — offline. No network call is made by this file.

The live endpoint is exercised by hand (it sends sequences out); what is tested here is
everything that must hold BEFORE a request leaves the machine, plus the response-shaping
that encodes the measurement (NEB caps Q5 Ta at 72 C).
"""
import pytest

from primer_design.neb_tm import (
    CALC_TM_OFFSET_C,
    NEB_PRODCODES,
    NEB_TA_CAP_C,
    NebTmError,
    lookup_pair,
    lookup_pairs,
)

S1 = "ATGACCGGTCTGAAGCTGAC"
S2 = "TTACGCTTCAGCGATGGTCA"


def test_consent_is_required():
    """Sequences must not leave the machine on a default-argument call."""
    with pytest.raises(ValueError, match="consent"):
        lookup_pair(S1, S2, consent=False)


def test_consent_is_keyword_only():
    with pytest.raises(TypeError):
        lookup_pair(S1, S2, True)  # type: ignore[misc]


@pytest.mark.parametrize("bad", ["", "ACGU", "ACGT ACGT", "acgtx", None])
def test_rejects_non_acgt(bad):
    with pytest.raises((ValueError, TypeError, AttributeError)):
        lookup_pair(bad, S2, consent=True)


def test_rejects_unknown_product():
    with pytest.raises(ValueError, match="unknown product"):
        lookup_pair(S1, S2, consent=True, product="pfu")


def test_q5_is_the_documented_default():
    """Q5 is the documented default; the default must not silently be another enzyme."""
    import inspect

    assert inspect.signature(lookup_pair).parameters["product"].default == "q5"
    assert NEB_PRODCODES["q5"] == "q5-0"


def test_ta_cap_is_flagged(monkeypatch):
    """ta at the cap means 'too hot to anneal' -> 2-step, not a literal 72 C anneal step."""
    import primer_design.neb_tm as mod

    monkeypatch.setattr(mod, "_get", lambda *a, **k: {"tm1": 79, "tm2": 76, "ta": 72.0})
    row = lookup_pair(S1, S2, consent=True)
    assert row["ta_is_capped"] is True
    assert row["prodcode"] == "q5-0"

    monkeypatch.setattr(mod, "_get", lambda *a, **k: {"tm1": 66, "tm2": 68, "ta": 66.9})
    assert lookup_pair(S1, S2, consent=True)["ta_is_capped"] is False


def test_cap_and_offset_match_the_measurement():
    assert NEB_TA_CAP_C == 72.0
    # calc_tm reads LOW against NEB Q5, so the offset is negative.
    assert CALC_TM_OFFSET_C < 0


def test_lookup_pairs_collects_errors(monkeypatch):
    import primer_design.neb_tm as mod

    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise NebTmError("boom")
        return {"tm1": 66, "tm2": 68, "ta": 66.9}

    monkeypatch.setattr(mod, "_get", flaky)
    rows = lookup_pairs(
        [("a", S1, S2), ("b", S1, S2)],
        consent=True,
        delay_s=0,
        on_error="collect",
    )
    assert len(rows) == 2
    assert "error" in rows[0] and rows[0]["label"] == "a"
    assert rows[1]["ta"] == 66.9


def test_lookup_pairs_rejects_bad_on_error():
    with pytest.raises(ValueError, match="on_error"):
        lookup_pairs([], consent=True, on_error="ignore")
