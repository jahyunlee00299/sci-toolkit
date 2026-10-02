"""Golden tests pinning scripts/fetch_academic.py across its split (refactor batch 3).

academic_snapshots.py drives every provider, the identity gate, both downloaders,
the institutional login (fake selenium) and the CLI against local fakes. The golden
file was produced from the unsplit 1638-line script; a behaviour-preserving split
leaves it untouched. A changed return value, warning text, filename, HTTP header,
exit code or CLI flag fails here.
"""
import json

import pytest

import academic_snapshots as acs

GOLDEN = json.loads((acs.GOLDEN / "fetch_academic.json").read_text(encoding="utf-8"))
HAS_PYPDF = True
try:
    import pypdf  # noqa: F401
except ImportError:  # the identity-gated groups need real PDF bytes
    HAS_PYPDF = False


@pytest.fixture(scope="module")
def snapshot(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    try:
        yield acs.build_all(mp, tmp_path_factory.mktemp("academic"))
    finally:
        mp.undo()


def _norm(value):
    return json.loads(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str))


@pytest.mark.parametrize("group", sorted(set(GOLDEN) - {"surface"}))
def test_group_matches_golden(snapshot, group):
    if group in acs.PDF_GROUPS and not HAS_PYPDF:
        pytest.skip("pypdf is required to build the fixture PDFs")
    assert _norm(snapshot[group]) == GOLDEN[group], f"{group} drifted from the golden snapshot"


def test_public_surface_is_preserved(snapshot):
    """Every name, class member and signature of the old module is still there."""
    old, new = GOLDEN["surface"], _norm(snapshot["surface"])
    missing = sorted(set(old["names"]) - set(new["names"]))
    assert not missing, f"names removed from fetch_academic: {missing}"
    for cls, members in old["classes"].items():
        for name, signature in members.items():
            assert new["classes"][cls].get(name) == signature, f"{cls}.{name} changed"
    for name, signature in old["functions"].items():
        assert new["functions"].get(name) == signature, f"{name}{signature} changed"


def test_scenarios_cover_the_waterfall():
    d = GOLDEN["downloader"]
    sources = {v["call"]["result"].get("download_source") for v in d.values()
               if isinstance(v, dict) and v.get("call", {}).get("result")}
    assert {"crossref_direct", "unpaywall", "pmc", "libkey_nomad", "ezproxy"} <= sources
    assert any(f.endswith(".REJECTED") for v in d.values() if isinstance(v, dict)
               for f in v.get("files", [])), "no scenario quarantines a mismatching PDF"
    ezproxy = json.dumps(GOLDEN["ezproxy"])
    for needle in ("identity mismatch", "identity not_pdf", "identity suspect", "too small",
                   "EZproxy download failed", "PDF URL not resolved", "not configured"):
        assert needle in ezproxy, f"scenario for {needle!r} lost"
