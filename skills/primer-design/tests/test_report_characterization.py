"""Golden tests pinning generate_cloning_report across the split of its drawing functions (refactor batch 4).

tests/characterization_report.py feeds the report literal design results and dumps
the artists it hands to Figure.savefig (positions, colours, sizes, weights, box styles,
texts), savefig's arguments, the return value and the files and figures left behind.
The golden file was produced from the unsplit `_draw_qc_table` (138 lines) and
`_draw_construct_map` (192 lines); a behaviour-preserving split leaves it untouched,
and a moved box, a recoloured cell or a changed string fails here.
"""
import json

import pytest

import characterization_report as chrep

GOLDEN = json.loads((chrep.GOLDEN / "cloning_report.json").read_text(encoding="utf-8"))["reports"]


@pytest.fixture(scope="module")
def snapshot(tmp_path_factory):
    return chrep.build_all(tmp_path_factory.mktemp("report"))["reports"]


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_report_matches_golden(snapshot, name):
    actual = json.loads(json.dumps(snapshot[name], sort_keys=True, ensure_ascii=False, default=str))
    assert actual == GOLDEN[name], f"{name} drifted from the golden snapshot"


def test_scenarios_cover_every_drawing_branch():
    def texts(name):
        return [t for panel in GOLDEN[name]["figure"]["panels"] for t in panel["texts"]]

    assert any("(+2 more)" in t for t in texts("warnings_overflow"))
    assert not any("more)" in t for t in texts("warnings_exactly_three"))
    assert any("N/A°C" in t for t in texts("qc_missing_and_unknown_verdict"))
    assert "Stop(RC)" in texts("stop_codon_spacers_no_protection")
    assert "Stop(RC)" not in texts("pet28a_full")
    for name in ("no_frame_check", "frame_check_empty_dict"):
        assert "Reading frame: (no vector specified)" in texts(name)
    assert any(t.startswith("5' linker: MGSS") and "3' linker: N/A" in t
               for t in texts("out_of_frame_long_topology_5prime_linker_only"))
    assert any("3' linker: N/A" not in t and t.startswith("5' linker: N/A")
               for t in texts("mixed_frame_empty_topology_3prime_linker_only"))
    assert any(t.endswith("...") and len(t) == 90 for t in texts("out_of_frame_long_topology_5prime_linker_only"))
    assert "T" * 90 in texts("topology_exactly_90_chars")
    assert "T" * 87 + "..." in texts("topology_91_chars")
    assert any("(+1 more)" in t for t in texts("warnings_four"))
    assert any(t.startswith("5'-") and "..." in t for t in texts("long_sequences"))


def test_failed_reports_leave_their_figure_open():
    # Existing behaviour, pinned as found: an exception while drawing skips plt.close().
    for name in ("missing_3prime_enzyme_fails_in_header", "missing_r_tail_fails_in_construct_map",
                 "missing_forward_tm_fails_in_architecture"):
        assert GOLDEN[name]["raised"][0] == "KeyError" and GOLDEN[name]["open_figures_after"] == 1


def test_successful_reports_close_their_figure_and_keep_their_input():
    for name, entry in GOLDEN.items():
        if "raised" in entry:
            continue
        assert entry["open_figures_after"] == 0 and entry["design_result_unmodified"], name
        assert entry["returned_type"] == "PosixPath" or entry["returned_type"] == "WindowsPath"
        assert entry["returned_the_given_path"] and entry["file_written"] and entry["header_has_todays_date"]


def test_summary_is_sensitive_to_a_moved_box():
    # Refutation of the harness itself: nudging one patch must change the panel hash.
    import copy
    dump = {"size": [1, 1], "facecolor": [1, 1, 1, 1], "axes": [{
        "position": [0, 0, 1, 1], "xlim": [0, 1], "ylim": [0, 1], "axis_off": True,
        "counts": {"lines": 0, "collections": 0, "images": 0},
        "patches": [{"xy": [0.0, 0.0]}], "texts": [{"text": "t"}]}]}
    moved = copy.deepcopy(dump)
    moved["axes"][0]["patches"][0]["xy"] = [0.0001, 0.0]
    assert (chrep.summarize(dump, False)["panels"][0]["sha256"]
            != chrep.summarize(moved, False)["panels"][0]["sha256"])
