"""dilution_calc.py via `reaction_matrix.py calc`: exact arithmetic, the transcript failure cases,
and refusal of physically impossible input."""
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import dilution_calc as dc  # noqa: E402


def run_cli(*args):
    r = subprocess.run([sys.executable, str(HERE / "reaction_matrix.py"), "calc", *args],
                       capture_output=True, encoding="utf-8")
    return r.returncode, r.stdout


def test_topup_failure_case_exact():
    add, line = dc.topup("31.03", "29.53")
    assert add == Decimal("1.50") and "31.03 - 29.53 = 1.5" in line  # float would give 1.5000000000000036


def test_df_compound_stages_multiply():
    assert dc.dilution_factor(stages=["2", "10"])[0] == 20          # the "희석배수 20" case


def test_df_single_step_short_volume():
    assert dc.dilution_factor(sample="10", total="80")[0] == 8
    assert dc.dilution_factor(sample="10", total="75")[0] == Decimal("7.5")


def test_c1v1_solves_each_unknown():
    assert dc.c1v1(c1="1000", c2="100", v2="50")[1] == 5
    assert dc.c1v1(c1="1000", v1="5", v2="50")[1] == 100
    assert dc.c1v1(v1="5", c2="100", v2="50")[1] == 1000
    assert dc.c1v1(c1="1000", v1="5", c2="100")[1] == 50


def test_back_calc():
    assert dc.back_calc("0.17108", "20")[0] == Decimal("3.4216")


def test_topup_conc_reaches_target():
    x, _ = dc.topup_conc("0.8", "1.0", "100", "100")
    assert abs((Decimal("0.8") * 100 + 100 * x) / (100 + x) - 1) < Decimal("1e-20")


@pytest.mark.parametrize("call", [
    lambda: dc.topup("29", "30"),                                  # overfilled
    lambda: dc.topup("-1", "0"),
    lambda: dc.topup("abc", "1"),
    lambda: dc.topup("nan", "1"),
    lambda: dc.c1v1(c1="100", c2="1000", v2="10"),                 # diluting upward
    lambda: dc.c1v1(c1="100", v1="50", c2="10", v2="20"),          # aliquot larger than final volume
    lambda: dc.c1v1(c1="100", v1="5"),                             # under-determined
    lambda: dc.c1v1(c1="1", v1="1", c2="1", v2="1"),               # over-determined
    lambda: dc.c1v1(c1="0", v1="1", c2="1"),                       # zero concentration
    lambda: dc.topup_conc("1", "0.5", "100", "100"),               # target below current
    lambda: dc.topup_conc("0.1", "1", "100", "1"),                 # stock cannot reach target
    lambda: dc.dilution_factor(stages=["0.5"]),                    # factor below 1
    lambda: dc.dilution_factor(sample="100", total="10"),
    lambda: dc.dilution_factor(),
    lambda: dc.dilution_factor(stages=["2"], sample="1", total="2"),
    lambda: dc.back_calc("1", "0.5"),
])
def test_impossible_inputs_raise(call):
    with pytest.raises(dc.CalcError):
        call()


def test_cli_end_to_end_and_exit_codes():
    rc, out = run_cli("topup", "--target", "31.03", "--have", "29.53")
    assert rc == 0 and out.splitlines()[0] == "add = 1.5"
    rc, out = run_cli("df", "--stages", "2", "10")
    assert rc == 0 and out.splitlines()[0] == "DF = 20"
    rc, out = run_cli("topup", "--target", "29", "--have", "30")
    assert rc == 2 and "overfilled" in out
    rc, _ = run_cli("c1v1", "--c1", "1000")
    assert rc == 2
    rc, _ = run_cli("nonsense")
    assert rc == 2
