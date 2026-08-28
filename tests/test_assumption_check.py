#!/usr/bin/env python3
"""assumption_check.py regression test — verifies its verdicts against data whose answer is known.

For a statistics tool, "it runs" and "it's correct" are different claims.
Here we feed in data built from a known distribution and check whether the
tool **names the test that is known to be the right answer**. The data is
built from quantiles rather than random draws, so it's identical across any
numpy/scipy version.

Run:
    python tests/test_assumption_check.py     # exit 0 = pass
"""
import importlib.util
import io
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "stats-workflow" / "scripts" / "assumption_check.py"

# The target module replaces sys.stdout with a UTF-8 wrapper at import time
# (to handle cp949). So wrapping it here first would just get that wrapper
# closed — always import first, and only then finalize stdout to UTF-8.
spec = importlib.util.spec_from_file_location("assumption_check", str(SCRIPT))
mod = importlib.util.module_from_spec(spec)
sys.modules["assumption_check"] = mod
spec.loader.exec_module(mod)

# The default Windows console is cp949, which crashes on Korean/symbol
# output. Force UTF-8. Use reconfigure rather than TextIOWrapper — a wrapper
# owns the underlying stream, so once garbage collected after import it
# closes the caller's stdout along with it (measured).
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _normal_quantiles(mean: float, sd: float, n: int) -> list[float]:
    """Build a 'sample following a normal distribution' without randomness — i/(n+1) quantiles.

    `np.random.default_rng(seed)` can produce a different stream across
    numpy versions even with the seed fixed. That shifts the normality
    p-value back and forth across 0.05, which changes which test gets
    selected — making a test of the selection logic itself hostage to random
    luck. It actually broke this way in CI (different numpy/scipy) (260807).
    A quantile-based sample is byte-identical in any environment.
    """
    from statistics import NormalDist
    nd = NormalDist(mean, sd)
    return [nd.inv_cdf((i + 1) / (n + 1)) for i in range(n)]


def _exponential_quantiles(scale: float, n: int) -> list[float]:
    """Exponential-distribution quantiles — heavily skewed, so normality reliably fails."""
    import math
    return [-scale * math.log(1.0 - (i + 1) / (n + 1)) for i in range(n)]


fails = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"        expected: {want!r}")
        print(f"        got:      {got!r}")
        fails.append(label)


# ---------------------------------------------------------------- decision tree
# Verify this matches the tree in SKILL.md Phase 2 exactly.
print("=== Decision tree (SKILL.md Phase 2) ===")
check("2 groups, independent, normal, equal variance -> Independent t-test",
      mod.decide(2, False, True, True, False), "Independent t-test")
check("2 groups, independent, normal, unequal variance -> Welch's t-test",
      mod.decide(2, False, True, False, False), "Welch's t-test")
check("2 groups, independent, non-normal -> Mann-Whitney U",
      mod.decide(2, False, False, True, False), "Mann-Whitney U")
check("2 groups, paired, normal -> Paired t-test",
      mod.decide(2, True, True, True, False), "Paired t-test")
check("2 groups, paired, non-normal -> Wilcoxon",
      mod.decide(2, True, False, True, False), "Wilcoxon signed-rank")
check("3 groups, normal, equal variance -> One-way ANOVA",
      mod.decide(3, False, True, True, False), "One-way ANOVA")
check("3 groups, normal, unequal variance -> Welch's ANOVA",
      mod.decide(3, False, True, False, False), "Welch's ANOVA")
check("3 groups, non-normal -> Kruskal-Wallis",
      mod.decide(3, False, False, True, False), "Kruskal-Wallis")
check("3 groups, repeated measures, non-normal -> Friedman",
      mod.decide(3, True, False, True, False), "Friedman test")
check("single sample, normal -> One-sample t-test",
      mod.decide(1, False, True, True, True), "One-sample t-test")

# ---------------------------------------------------------------- normality test selection
print("\n=== Normality test selection (by n) ===")
try:
    import numpy as np
except ImportError:
    print("  SKIP — numpy not available")
    np = None

if np is not None:
    small_normal = _normal_quantiles(10.0, 2.0, 20)
    big_normal = _normal_quantiles(10.0, 2.0, 80)
    check("n=20 -> uses Shapiro-Wilk",
          mod.check_normality(small_normal, "a")["test"], "Shapiro-Wilk")
    check("n=80 -> uses D'Agostino-Pearson",
          mod.check_normality(big_normal, "b")["test"], "D'Agostino-Pearson")
    check("normally-distributed data -> normal=True",
          mod.check_normality(small_normal, "a")["normal"], True)
    # An exponential distribution is heavily skewed, so normality must fail
    skewed = _exponential_quantiles(3.0, 40)
    check("exponential-distribution data -> normal=False",
          mod.check_normality(skewed, "c")["normal"], False)

# ---------------------------------------------------------------- APA p-value formatting
print("\n=== APA p-value formatting ===")
check("p=.0004 -> 'p < .001'", mod.fmt_p(0.0004), "p < .001")
check("p=.032 -> 'p = .032'", mod.fmt_p(0.032), "p = .032")
check("p=.5 -> 'p = .500'", mod.fmt_p(0.5), "p = .500")

print("\n=== Effect-size interpretation (Cohen) ===")
check("d=0.9 -> large", mod.band("d", 0.9), "large")
check("d=0.55 -> medium", mod.band("d", 0.55), "medium")
check("d=0.25 -> small", mod.band("d", 0.25), "small")
check("d=0.05 -> negligible", mod.band("d", 0.05), "negligible")
check("d=-0.9 (magnitude applies to negatives too) -> large", mod.band("d", -0.9), "large")

# ---------------------------------------------------------------- end-to-end
print("\n=== Actual execution (data with a known answer) ===")
if np is None:
    print("  SKIP — numpy not available")
else:
    tmp = Path(tempfile.mkdtemp())

    # (1) Two normal distributions, equal variance, clearly different means
    #     -> Independent t-test, significant
    #
    # No randomness used. `default_rng(seed)` can produce a different stream
    # even with a fixed seed **once the numpy version changes**, which shifts
    # the normality p-value across 0.05 and changes which test gets picked —
    # this case actually broke in CI (different numpy/scipy) (260807). A test
    # of the selection logic itself must not depend on random luck.
    #
    # Instead, build deterministic quantiles of a normal distribution. The
    # sample follows the theoretical distribution almost exactly, so
    # Shapiro-Wilk reliably reports "normal," the two groups have equal
    # variance so Levene reliably reports "equal variance," and the mean
    # difference is 4 sigma or more, so the significance call is nowhere
    # near the boundary either.
    a = _normal_quantiles(10.0, 1.5, 30)
    b = _normal_quantiles(14.0, 1.5, 30)
    f1 = tmp / "two_normal.csv"
    f1.write_text("value,group\n" +
                  "".join(f"{v},A\n" for v in a) +
                  "".join(f"{v},B\n" for v in b), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPT), str(f1),
                        "--value", "value", "--group", "group", "--run"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = r.stdout
    check("normal, equal-variance 2 groups -> names Independent t-test",
          "Independent t-test" in out, True)
    check("  APA string printed", "APA: t(" in out, True)
    # NOTE: "유의함"/"유의하지 않음" are asserted verbatim because that's what
    # assumption_check.py itself prints (see its NOTE at line ~377) — not
    # translated here, since this file (assumption_check.py) is out of scope.
    check("  large difference -> significant", "유의함" in out and "유의하지 않음" not in out, True)
    check("  exit 0", r.returncode, 0)

    # (2) One side exponential -> must switch to a non-parametric test
    c = _exponential_quantiles(2.0, 30)
    d = _normal_quantiles(10.0, 1.5, 30)
    f2 = tmp / "skewed.csv"
    f2.write_text("value,group\n" +
                  "".join(f"{v},A\n" for v in c) +
                  "".join(f"{v},B\n" for v in d), encoding="utf-8")
    r2 = subprocess.run([sys.executable, str(SCRIPT), str(f2),
                         "--value", "value", "--group", "group", "--run"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("includes non-normal group -> switches to Mann-Whitney U",
          "Mann-Whitney U" in r2.stdout, True)

    # (3) Equal-variance assumption violated -> switch to Welch
    # 36x variance ratio — Levene reliably rejects equal variance.
    e = _normal_quantiles(10.0, 1.0, 30)
    f = _normal_quantiles(10.5, 6.0, 30)
    f3 = tmp / "unequal_var.csv"
    f3.write_text("value,group\n" +
                  "".join(f"{v},A\n" for v in e) +
                  "".join(f"{v},B\n" for v in f), encoding="utf-8")
    r3 = subprocess.run([sys.executable, str(SCRIPT), str(f3),
                         "--value", "value", "--group", "group"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("unequal variance -> switches to Welch's t-test",
          "Welch's t-test" in r3.stdout, True)

    # (4) 3 groups, normal, equal variance -> ANOVA
    g1 = _normal_quantiles(10.0, 1.5, 25)
    g2 = _normal_quantiles(12.0, 1.5, 25)
    g3 = _normal_quantiles(14.0, 1.5, 25)
    f4 = tmp / "three.csv"
    f4.write_text("value,group\n" +
                  "".join(f"{v},A\n" for v in g1) +
                  "".join(f"{v},B\n" for v in g2) +
                  "".join(f"{v},C\n" for v in g3), encoding="utf-8")
    r4 = subprocess.run([sys.executable, str(SCRIPT), str(f4),
                         "--value", "value", "--group", "group", "--run"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("3 groups, normal, equal variance -> One-way ANOVA", "One-way ANOVA" in r4.stdout, True)
    # NOTE: "사후검정" ("post-hoc test") is asserted verbatim — matches
    # assumption_check.py's own output; that file is out of scope here.
    check("  3-group significant result -> recommends post-hoc test", "사후검정" in r4.stdout, True)

    # (5) Mismatched sizes in a paired sample must be blocked, not silently ignored
    f5 = tmp / "mismatched.csv"
    f5.write_text("value,group\n" +
                  "".join(f"{v},A\n" for v in _normal_quantiles(10.0, 1.0, 20)) +
                  "".join(f"{v},B\n" for v in _normal_quantiles(11.0, 1.0, 15)), encoding="utf-8")
    r5 = subprocess.run([sys.executable, str(SCRIPT), str(f5),
                         "--value", "value", "--group", "group",
                         "--paired", "--run"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("paired-sample size mismatch -> aborts (exit 1)", r5.returncode, 1)
    # NOTE: "크기가 다르다" ("sizes differ") is asserted verbatim — matches
    # assumption_check.py's own output; that file is out of scope here.
    check("  states the reason", "크기가 다르다" in r5.stdout, True)

    # (6) Nonexistent column -> a helpful error + exit 2
    r6 = subprocess.run([sys.executable, str(SCRIPT), str(f1),
                         "--value", "nonexistent_column"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("nonexistent column -> exit 2", r6.returncode, 2)
    # NOTE: "있는 열" ("columns that exist") is asserted verbatim — matches
    # assumption_check.py's own output; that file is out of scope here.
    check("  lists the columns that do exist", "있는 열" in (r6.stdout + r6.stderr), True)

print()
if fails:
    print(f"{len(fails)} FAILURE(S): {fails}")
    sys.exit(1)
print("ALL PASS")
