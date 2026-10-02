#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lab cases for the vendored K-Dense scripts (uncertainty-and-units, doe-and-replication) — pytest style.

Why this exists
---------------
Both skills ship scripts that were adopted from an upstream MIT project with
their logic unchanged. "Unchanged" is only worth something while the answers
stay right, so every case below has an expected value derived by hand, never by
re-running the function under test:

  kcat = 10 +/- 0.5, Km = 2 +/- 0.1   -> kcat/Km = 5.0, u = 5*sqrt(0.05^2 + 0.05^2) = 0.35355
  1.000 g glucose (MW 180.156 g/mol)  -> 1/180.156 = 5.5507e-3 mol
  2.5 mM                              -> 2500 uM
  2^3 factorial                       -> 8 runs, every level on a stated bound
  CCD, face="inscribed", 3 factors    -> 8 + 6 + (4 + 2) = 20 runs, inside the bounds
  12 units, arms A/B, permuted blocks -> 6 and 6
  20 runs x 3 reps on 60 inner wells  -> 60 distinct wells

The SKILL.md recipes (correlated Michaelis-Menten parameters, HPLC calibration)
are executed here too, so the numbers printed in the skill text are not prose.

Missing optional packages SKIP the cases that need them (pint, uncertainties,
scipy, pydoe) instead of failing, which is how doctor treats them: a WARN, not
a broken toolkit.

Run: python -m pytest tests/test_uncertainty_doe_skills.py -q
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
UNC = ROOT / "skills" / "uncertainty-and-units"
DOE = ROOT / "skills" / "doe-and-replication"
LICENSE = ROOT / "licenses" / "K-Dense-MIT.txt"


def _have(*mods: str) -> bool:
    return all(importlib.util.find_spec(m) is not None for m in mods)


needs_unc = pytest.mark.skipif(not _have("pint", "uncertainties", "numpy", "scipy"),
                               reason="pint/uncertainties/numpy/scipy not installed")
needs_fit = pytest.mark.skipif(not _have("uncertainties", "numpy", "scipy"),
                               reason="uncertainties/numpy/scipy not installed")
needs_pydoe = pytest.mark.skipif(not _have("pydoe", "numpy", "pandas"),
                                 reason="pydoe/numpy/pandas not installed")
needs_pandas = pytest.mark.skipif(not _have("numpy", "pandas"), reason="numpy/pandas not installed")


def run_cli(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(UNC / "scripts" / script), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)


@pytest.fixture(scope="module")
def doe_modules():
    """Import the DoE scripts by path; restore sys.path afterwards."""
    sys.path.insert(0, str(DOE / "scripts"))
    try:
        import doe_designs  # noqa: PLC0415
        import randomization  # noqa: PLC0415
        yield doe_designs, randomization
    finally:
        sys.path.remove(str(DOE / "scripts"))


# --------------------------------------------------------------------------
# uncertainty-and-units: CLIs
# --------------------------------------------------------------------------

@needs_unc
def test_kcat_over_km_first_order_value_and_uncertainty():
    p = run_cli("propagate_uncertainty.py", "--expression", "kcat / Km",
                "--variable", "kcat=10,0.5", "--variable", "Km=2,0.1",
                "--measurand", "kcat_over_Km", "--unit", "1/(mM*s)", "--format", "json")
    assert p.returncode == 0, p.stderr
    gum = json.loads(p.stdout)["gum_framework"]
    assert gum["combined_standard_uncertainty"] == pytest.approx(0.35355, abs=1e-4)
    fractions = [i["variance_fraction"] for i in gum["inputs"]]
    assert fractions == pytest.approx([0.5, 0.5], abs=1e-9)   # both inputs are 5 % -> 50/50


@needs_unc
def test_glucose_grams_to_moles_needs_molecular_weight():
    p = run_cli("convert_units.py", "--value", "1.0", "--unit", "g", "--to", "mol",
                "--context", "chemistry", "--context-parameter", "mw=180.156 g/mol")
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["value"] == pytest.approx(1 / 180.156, rel=1e-9)  # 5.5507e-3 mol


@needs_unc
def test_mm_to_um():
    p = run_cli("convert_units.py", "--value", "2.5", "--unit", "mM", "--to", "uM")
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["value"] == pytest.approx(2500.0)


@needs_unc
def test_format_result_rounds_uncertainty_first():
    p = run_cli("format_result.py", "--value", "12.34567", "--uncertainty", "0.02345", "--unit", "mM")
    assert p.returncode == 0, p.stderr
    r = json.loads(p.stdout)
    assert r["renderings"]["plusminus"] == "12.346 ± 0.023 mM"
    assert r["renderings"]["parenthetic"] == "12.346(23) mM"


@needs_unc
def test_malformed_variable_is_a_clean_nonzero_error():
    p = run_cli("propagate_uncertainty.py", "--expression", "kcat / Km",
                "--variable", "kcat=abc", "--variable", "Km=2,0.1")
    assert p.returncode != 0
    assert "error:" in p.stderr
    assert "Traceback" not in p.stderr


@needs_unc
def test_convert_units_unknown_unit_is_a_clean_error():
    p = run_cli("convert_units.py", "--value", "1", "--unit", "notaunit", "--to", "mol")
    assert p.returncode != 0
    assert "Traceback" not in p.stderr


def test_audit_units_flags_stripped_unit(tmp_path):
    """The static auditor is standard-library only: it must work without pint."""
    sample = tmp_path / "sample.py"
    sample.write_text("import pint\nureg = pint.UnitRegistry()\nx = (3 * ureg.mM).magnitude\n",
                      encoding="utf-8")
    p = run_cli("audit_units.py", "--input", str(sample), "--format", "markdown")
    assert "UNIT003" in p.stdout, p.stdout + p.stderr


# --------------------------------------------------------------------------
# uncertainty-and-units: the SKILL.md recipes
# --------------------------------------------------------------------------

@needs_fit
def test_recipe_michaelis_menten_keeps_the_correlation():
    import numpy as np
    from scipy.optimize import curve_fit
    from uncertainties import correlated_values, ufloat

    S = np.array([0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0])
    v_mean = np.array([0.82, 1.45, 2.95, 4.40, 5.80, 7.05, 7.55])
    v_sem = np.array([0.06, 0.08, 0.12, 0.15, 0.20, 0.25, 0.30])
    E_tot = ufloat(0.050, 0.002)

    popt, pcov = curve_fit(lambda s, vmax, km: vmax * s / (km + s), S, v_mean,
                           p0=[8, 1], sigma=v_sem, absolute_sigma=True)
    vmax, km = correlated_values(popt, pcov)
    eff = vmax / E_tot / km
    naive = (ufloat(popt[0], np.sqrt(pcov[0, 0])) / E_tot) / ufloat(popt[1], np.sqrt(pcov[1, 1]))

    assert eff.nominal_value == pytest.approx(181, abs=1)
    assert eff.std_dev == pytest.approx(10, abs=1)        # the number printed in SKILL.md
    assert naive.std_dev > 1.2 * eff.std_dev              # dropping the correlation inflates it
    # Independent hand check: Vmax and Km are positively correlated here, so the ratio's
    # variance is smaller than the independent-parameter formula.
    assert pcov[0, 1] > 0


@needs_fit
def test_recipe_hplc_calibration_concentration():
    import numpy as np
    from scipy.optimize import curve_fit
    from uncertainties import correlated_values, ufloat

    std = np.array([0.5, 1, 2, 5, 10, 20])
    area = np.array([12.1, 24.5, 47.9, 121.0, 243.5, 480.2])
    popt, pcov = curve_fit(lambda c, m, b: m * c + b, std, area)
    m, b = correlated_values(popt, pcov)
    conc = (ufloat(100.3, 1.2) - b) / m * 10
    # Hand check: slope ~ 24 area per mM, so (100.3 - ~0.6) / ~24 = ~4.15 mM, x10 dilution.
    assert conc.nominal_value == pytest.approx(41.5, abs=0.3)
    assert conc.std_dev == pytest.approx(0.6, abs=0.15)


# --------------------------------------------------------------------------
# doe-and-replication
# --------------------------------------------------------------------------

FACTORS = {"pH": (6.0, 8.0), "temp_C": (30, 50), "NAD_ratio": (0.5, 2.0)}


@needs_pydoe
def test_two_level_factorial_is_8_runs_at_the_bounds(doe_modules):
    doe, _ = doe_modules
    d = doe.two_level_factorial(FACTORS, seed=1)
    assert len(d) == 8
    for name, (lo, hi) in FACTORS.items():
        assert set(d[name].round(6)) == {lo, hi}
    assert d.equals(doe.two_level_factorial(FACTORS, seed=1))   # the seed reproduces it


@needs_pydoe
def test_plackett_burman_screens_seven_factors_in_eight_runs(doe_modules):
    doe, _ = doe_modules
    assert len(doe.plackett_burman({f"x{i}": (0, 1) for i in range(7)}, seed=1)) == 8


@needs_pydoe
def test_inscribed_ccd_stays_inside_the_bounds_with_six_center_runs(doe_modules):
    doe, _ = doe_modules
    d = doe.central_composite(FACTORS, center=(4, 2), face="inscribed", seed=261002)
    assert len(d) == 20                                          # 8 corners + 6 axial + 6 center
    for name, (lo, hi) in FACTORS.items():
        assert d[name].min() >= lo - 1e-9 and d[name].max() <= hi + 1e-9
    centre = d[(d.pH == 7.0) & (d.temp_C == 40.0) & (d.NAD_ratio == 1.25)]
    assert len(centre) == 6


@needs_pydoe
def test_default_ccd_leaves_the_box_which_is_why_the_skill_says_inscribed(doe_modules):
    doe, _ = doe_modules
    d = doe.central_composite(FACTORS, center=(4, 2), seed=1)   # circumscribed default
    assert d["pH"].min() < 6.0 and d["pH"].max() > 8.0


@needs_pandas
def test_block_randomization_balances_two_arms(doe_modules):
    _, rnd = doe_modules
    sched = rnd.block_randomization(n=12, arms=["A", "B"], seed=7)
    assert sorted(rnd.arm_balance(sched).tolist()) == [6, 6]


@needs_pydoe
def test_plate_layout_recipe_uses_60_distinct_inner_wells(doe_modules):
    """The Step 4 recipe in SKILL.md: 20 runs x 3 positional replicates on rows B-G, columns 2-11."""
    import numpy as np
    doe, _ = doe_modules
    design = doe.central_composite(FACTORS, center=(4, 2), face="inscribed", seed=261002)
    inner = [f"{r}{c}" for r in "BCDEFG" for c in range(2, 12)]
    reps = 3
    layout = design.loc[design.index.repeat(reps)].reset_index(drop=True)
    layout["well"] = np.random.default_rng(261002).permutation(inner)
    assert len(layout) == 60 and layout["well"].nunique() == 60
    assert not any(w[0] in "AH" or w[1:] in ("1", "12") for w in layout["well"])  # no edge wells


# --------------------------------------------------------------------------
# provenance and attribution
# --------------------------------------------------------------------------

def test_vendored_scripts_carry_the_upstream_header_and_license_exists():
    scripts = sorted((UNC / "scripts").glob("*.py")) + sorted((DOE / "scripts").glob("*.py"))
    assert len(scripts) == 9
    for s in scripts:
        head = "\n".join(s.read_text(encoding="utf-8").splitlines()[:5])
        assert "K-Dense" in head and "MIT" in head and "upstream path" in head, s.name
    text = LICENSE.read_text(encoding="utf-8")
    assert text.startswith("MIT License") and "K-Dense Inc." in text
    assert "THE SOFTWARE IS PROVIDED \"AS IS\"" in text


def test_skills_dropped_the_upstream_auto_cite_instruction():
    for skill in (UNC, DOE):
        text = (skill / "SKILL.md").read_text(encoding="utf-8")
        assert "arXiv" not in text and "Citing Scientific Agent Skills" not in text, skill.name
        assert "한국어 트리거" in text.split("---")[1], skill.name   # trigger phrases live in description
