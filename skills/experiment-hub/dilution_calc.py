"""One-off pipetting / dilution arithmetic for experiment-hub (reached as `reaction_matrix.py calc ...`).

Pure functions + a tiny argparse front end. Exact decimal arithmetic, so 31.03 - 29.53 prints 1.5,
not 1.5000000000000036. Every result prints the formula with the numbers in it, so the user can see
which quantity was subtracted from which.

  reaction_matrix.py calc c1v1 --c1 1000 --c2 100 --v2 50          # solves the missing one (v1 = 5)
  reaction_matrix.py calc topup --target 31.03 --have 29.53        # volume still to add (1.5)
  reaction_matrix.py calc topup-conc --have 0.8 --target 1.0 --vol 100 --stock 100   # stock to add
  reaction_matrix.py calc df --stages 2 10                         # compound dilution factor (20)
  reaction_matrix.py calc df --sample 10 --total 80                # single step (8)
  reaction_matrix.py calc back --measured 0.171 --df 20            # concentration before dilution

Exit 0 ok, 2 invalid input (negative or non-numeric value, over-determined or under-determined,
physically impossible such as diluting upward or overfilled). Never guesses a missing number.
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal, InvalidOperation, getcontext

getcontext().prec = 28


class CalcError(ValueError):
    pass


def num(x, name: str = "value") -> Decimal:
    try:
        d = Decimal(str(x))
    except InvalidOperation:
        raise CalcError(f"{name}: not a number: {x!r}") from None
    if not d.is_finite():
        raise CalcError(f"{name}: not finite: {x!r}")
    return d


def pos(x, name: str, allow_zero: bool = False) -> Decimal:
    d = num(x, name)
    if d < 0 or (d == 0 and not allow_zero):
        raise CalcError(f"{name} must be {'>= 0' if allow_zero else '> 0'}, got {d}")
    return d


def fmt(d: Decimal) -> str:
    s = format(d.quantize(Decimal("0.000001")).normalize(), "f")
    return s if s != "-0" else "0"


def c1v1(c1=None, v1=None, c2=None, v2=None) -> tuple[str, Decimal, str]:
    """C1*V1 = C2*V2: exactly one of the four is None and is solved for."""
    given = {"c1": c1, "v1": v1, "c2": c2, "v2": v2}
    missing = [k for k, v in given.items() if v is None]
    if len(missing) != 1:
        raise CalcError(f"give exactly three of c1 v1 c2 v2 (missing: {', '.join(missing) or 'none'})")
    vals = {k: pos(v, k) for k, v in given.items() if v is not None}
    k = missing[0]
    if k == "c1":
        out = vals["c2"] * vals["v2"] / vals["v1"]
    elif k == "v1":
        out = vals["c2"] * vals["v2"] / vals["c1"]
    elif k == "c2":
        out = vals["c1"] * vals["v1"] / vals["v2"]
    else:
        out = vals["c1"] * vals["v1"] / vals["c2"]
    c1_, c2_ = vals.get("c1", out if k == "c1" else None), vals.get("c2", out if k == "c2" else None)
    v1_, v2_ = vals.get("v1", out if k == "v1" else None), vals.get("v2", out if k == "v2" else None)
    if c2_ > c1_:
        raise CalcError(f"C2 ({fmt(c2_)}) > C1 ({fmt(c1_)}): that is a concentration, not a dilution")
    if v1_ > v2_:
        raise CalcError(f"V1 ({fmt(v1_)}) > V2 ({fmt(v2_)}): the aliquot does not fit the final volume")
    diluent = v2_ - v1_
    line = f"C1*V1 = C2*V2 -> {fmt(c1_)} * {fmt(v1_)} = {fmt(c2_)} * {fmt(v2_)}; diluent = V2 - V1 = {fmt(diluent)}"
    return k, out, line


def topup(target, have) -> tuple[Decimal, str]:
    """Volume still to add to reach a per-tube target when `have` is already in."""
    t, h = pos(target, "target"), pos(have, "have", allow_zero=True)
    add = t - h
    if add < 0:
        raise CalcError(f"already added {fmt(h)} > target {fmt(t)}: overfilled by {fmt(-add)}")
    return add, f"top-up = target - already added = {fmt(t)} - {fmt(h)} = {fmt(add)}"


def topup_conc(have, target, vol, stock) -> tuple[Decimal, str]:
    """Stock volume x to add to `vol` of solution at `have` so the mixture reaches `target`.
    (have*vol + stock*x)/(vol + x) = target  ->  x = vol*(target-have)/(stock-target)."""
    h, t = pos(have, "have", allow_zero=True), pos(target, "target")
    v, s = pos(vol, "vol"), pos(stock, "stock")
    if t <= h:
        raise CalcError(f"target {fmt(t)} <= current {fmt(h)}: nothing to add (this would be a dilution)")
    if s <= t:
        raise CalcError(f"stock {fmt(s)} <= target {fmt(t)}: the stock cannot reach the target")
    x = v * (t - h) / (s - t)
    return x, (f"x = vol*(target-have)/(stock-target) = {fmt(v)}*({fmt(t)}-{fmt(h)})/({fmt(s)}-{fmt(t)}) = {fmt(x)}; "
               f"new total volume {fmt(v + x)}")


def dilution_factor(stages=None, sample=None, total=None) -> tuple[Decimal, str]:
    """Overall dilution factor: product of the per-step factors, or total/sample for one step.
    The factor is the TOTAL divided by the SAMPLE volume (10 uL in 90 uL diluent = 100/10 = 10)."""
    if stages and (sample is not None or total is not None):
        raise CalcError("use either --stages or --sample/--total, not both")
    if stages:
        fs = [pos(s, "stage") for s in stages]
        if any(f < 1 for f in fs):
            raise CalcError("a dilution stage factor must be >= 1 (2 means 2-fold)")
        out = Decimal(1)
        for f in fs:
            out *= f
        return out, "DF = " + " * ".join(fmt(f) for f in fs) + f" = {fmt(out)}"
    if sample is None or total is None:
        raise CalcError("give --stages, or both --sample and --total")
    s, t = pos(sample, "sample"), pos(total, "total")
    if s > t:
        raise CalcError(f"sample {fmt(s)} > total {fmt(t)}")
    return t / s, f"DF = total / sample = {fmt(t)} / {fmt(s)} = {fmt(t / s)}"


def back_calc(measured, df) -> tuple[Decimal, str]:
    m, d = pos(measured, "measured", allow_zero=True), pos(df, "df")
    if d < 1:
        raise CalcError("df must be >= 1")
    return m * d, f"original = measured * DF = {fmt(m)} * {fmt(d)} = {fmt(m * d)}"


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="reaction_matrix.py calc", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="op", required=True)
    p = sub.add_parser("c1v1")
    for k in ("c1", "v1", "c2", "v2"):
        p.add_argument(f"--{k}")
    p = sub.add_parser("topup")
    p.add_argument("--target", required=True)
    p.add_argument("--have", required=True)
    p = sub.add_parser("topup-conc")
    for k in ("have", "target", "vol", "stock"):
        p.add_argument(f"--{k}", required=True)
    p = sub.add_parser("df")
    p.add_argument("--stages", nargs="+")
    p.add_argument("--sample")
    p.add_argument("--total")
    p = sub.add_parser("back")
    p.add_argument("--measured", required=True)
    p.add_argument("--df", required=True)
    return ap


def cli(argv: list[str]) -> int:
    try:
        a = build_parser().parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    try:
        if a.op == "c1v1":
            k, val, line = c1v1(a.c1, a.v1, a.c2, a.v2)
            print(f"{k} = {fmt(val)}\n{line}")
        elif a.op == "topup":
            val, line = topup(a.target, a.have)
            print(f"add = {fmt(val)}\n{line}")
        elif a.op == "topup-conc":
            val, line = topup_conc(a.have, a.target, a.vol, a.stock)
            print(f"add stock volume = {fmt(val)}\n{line}")
        elif a.op == "df":
            val, line = dilution_factor(a.stages, a.sample, a.total)
            print(f"DF = {fmt(val)}\n{line}")
        else:
            val, line = back_calc(a.measured, a.df)
            print(f"original = {fmt(val)}\n{line}")
    except CalcError as e:
        print(f"INVALID: {e}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
