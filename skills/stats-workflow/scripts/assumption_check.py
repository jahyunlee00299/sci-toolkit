#!/usr/bin/env python3
"""Actually checks statistical-test assumptions before testing, and names the right test.

This is the decision tree and assumption checks from `SKILL.md` Phase 2,
carried over into an executable form. The goal is to stop the point where a
human eyeballs a plot, thinks "looks normal enough," and moves on.

What it does
------------
1. Reads the data (csv/tsv/xlsx) and splits it by group
2. **Normality** — Shapiro-Wilk if n < 50, D'Agostino-Pearson if n >= 50
3. **Equal variance** — Levene (when there are 2+ groups)
4. Follows the SKILL.md decision tree from the above results to **name the
   test that should be used**
5. If requested, actually runs that test and prints **APA 7th-edition
   formatting + effect size**

Usage
-----
    # Check assumptions only, and see which test to use
    python assumption_check.py data.csv --value od600 --group strain

    # Also run the test and print APA-formatted output
    python assumption_check.py data.csv --value od600 --group strain --run

    # Paired samples
    python assumption_check.py data.csv --value delta --group timepoint --paired --run

    # Compare a single group against a reference value
    python assumption_check.py data.csv --value yield --mu 100 --run

Exit codes
----------
    0  No assumption violated (or a violation exists but the matching
       nonparametric test was named)
    1  Cannot decide due to a data problem (only one group, insufficient n,
       too many missing values, etc.)
    2  Input/dependency error

**Important**: this tool only decides "which test to use" — it does not judge
whether that test fits your research question. Paired-vs-independent status
and repeated-measures structure come from the experimental design, so **a
human** must state them via flags like `--paired`.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

def _force_utf8_stdout() -> None:
    """Prevent Windows' default console (cp949) from dying on Korean/symbol output.

    Uses `reconfigure`. Wrapping in a TextIOWrapper would take ownership of
    the underlying stream, so once the wrapper is GC'd after this module is
    imported, it closes the caller's stdout too (this actually happened in a
    test). reconfigure mutates the same object, so it is safe.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError, io.UnsupportedOperation):
                pass

ALPHA = 0.05
SHAPIRO_MAX_N = 50          # SKILL.md: Shapiro if n < 50, normaltest otherwise

# Effect-size interpretation thresholds (SKILL.md Phase 3 table)
EFFECT_BANDS = {
    "d":   [(0.2, "small"), (0.5, "medium"), (0.8, "large")],
    "eta2": [(0.01, "small"), (0.06, "medium"), (0.14, "large")],
    "r":   [(0.1, "small"), (0.3, "medium"), (0.5, "large")],
}


def band(kind: str, value: float) -> str:
    """Interpret an effect-size value as small/medium/large."""
    v = abs(value)
    label = "negligible"
    for cut, name in EFFECT_BANDS[kind]:
        if v >= cut:
            label = name
    return label


def fmt_p(p: float) -> str:
    """APA style: write p < .001, otherwise three decimal digits with the leading 0 dropped."""
    if p < 0.001:
        return "p < .001"
    return f"p = {p:.3f}".replace("0.", ".")


def load_table(path: Path):
    try:
        import pandas as pd
    except ImportError:
        print("Error: pandas is required (pip install pandas)", file=sys.stderr)
        raise SystemExit(2)
    suf = path.suffix.lower()
    if suf in (".csv", ".txt"):
        return pd.read_csv(path)
    if suf == ".tsv":
        return pd.read_csv(path, sep="\t")
    if suf in (".xlsx", ".xls"):
        return pd.read_excel(path)
    print(f"Error: unsupported format '{suf}' (.csv/.tsv/.xlsx)", file=sys.stderr)
    raise SystemExit(2)


def check_normality(values, label):
    """Normality test. Picks Shapiro / D'Agostino based on n (SKILL.md rule)."""
    from scipy import stats
    n = len(values)
    if n < 3:
        return {"group": label, "n": n, "test": None, "p": None,
                "normal": None, "note": "n < 3 — cannot assess normality"}
    if n < SHAPIRO_MAX_N:
        stat, p = stats.shapiro(values)
        test = "Shapiro-Wilk"
    else:
        stat, p = stats.normaltest(values)
        test = "D'Agostino-Pearson"
    return {"group": label, "n": n, "test": test, "statistic": float(stat),
            "p": float(p), "normal": bool(p >= ALPHA),
            "note": "" if p >= ALPHA else "normality violated"}


def decide(n_groups, paired, all_normal, equal_var, one_sample):
    """A direct implementation of the SKILL.md Phase 2 decision tree."""
    if one_sample:
        return ("One-sample t-test" if all_normal
                else "Wilcoxon signed-rank (one-sample)")
    if n_groups == 2:
        if paired:
            return "Paired t-test" if all_normal else "Wilcoxon signed-rank"
        if not all_normal:
            return "Mann-Whitney U"
        return "Independent t-test" if equal_var else "Welch's t-test"
    # 3+ groups
    if paired:
        return "Repeated-measures ANOVA" if all_normal else "Friedman test"
    if not all_normal:
        return "Kruskal-Wallis"
    return "One-way ANOVA" if equal_var else "Welch's ANOVA"


def run_test(name, groups, mu=None):
    """Actually run the named test and build the APA string + effect size."""
    from scipy import stats
    import numpy as np

    out = {"test": name}

    if name.startswith("One-sample t"):
        x = groups[0]
        t, p = stats.ttest_1samp(x, mu)
        d = (np.mean(x) - mu) / np.std(x, ddof=1)
        out.update(statistic=float(t), p=float(p), df=len(x) - 1,
                   effect={"kind": "d", "value": float(d), "band": band("d", d)},
                   apa=f"t({len(x)-1}) = {t:.2f}, {fmt_p(p)}, d = {d:.2f}")

    elif name.startswith("Wilcoxon signed-rank (one-sample)"):
        x = np.asarray(groups[0])
        stat, p = stats.wilcoxon(x - mu)
        out.update(statistic=float(stat), p=float(p),
                   apa=f"W = {stat:.1f}, {fmt_p(p)}")

    elif name == "Paired t-test":
        a, b = groups[0], groups[1]
        if len(a) != len(b):
            # NOTE: "크기가 다르다" ("sizes differ") below is asserted on verbatim by
            # tests/test_assumption_check.py — do not translate/remove it without
            # updating that test too.
            raise ValueError(f"Paired samples, but the two groups' 크기가 다르다 (sizes differ) ({len(a)} vs {len(b)}). "
                             "Check that the pairing is correct.")
        t, p = stats.ttest_rel(a, b)
        diff = np.asarray(a) - np.asarray(b)
        d = np.mean(diff) / np.std(diff, ddof=1)
        out.update(statistic=float(t), p=float(p), df=len(a) - 1,
                   effect={"kind": "d", "value": float(d), "band": band("d", d)},
                   apa=f"t({len(a)-1}) = {t:.2f}, {fmt_p(p)}, d = {d:.2f}")

    elif name == "Wilcoxon signed-rank":
        a, b = groups[0], groups[1]
        if len(a) != len(b):
            # NOTE: same "크기가 다르다" test dependency as above.
            raise ValueError(f"Paired samples, but the two groups' 크기가 다르다 (sizes differ) ({len(a)} vs {len(b)}).")
        stat, p = stats.wilcoxon(a, b)
        out.update(statistic=float(stat), p=float(p),
                   apa=f"W = {stat:.1f}, {fmt_p(p)}")

    elif name in ("Independent t-test", "Welch's t-test"):
        a, b = groups[0], groups[1]
        equal = (name == "Independent t-test")
        t, p = stats.ttest_ind(a, b, equal_var=equal)
        n1, n2 = len(a), len(b)
        sp = np.sqrt(((n1 - 1) * np.var(a, ddof=1) + (n2 - 1) * np.var(b, ddof=1))
                     / (n1 + n2 - 2))
        d = (np.mean(a) - np.mean(b)) / sp if sp else float("nan")
        df = (n1 + n2 - 2) if equal else float("nan")
        df_str = f"{df}" if equal else "Welch-adjusted"
        out.update(statistic=float(t), p=float(p), df=df,
                   effect={"kind": "d", "value": float(d), "band": band("d", d)},
                   apa=f"t({df_str}) = {t:.2f}, {fmt_p(p)}, d = {d:.2f}")

    elif name == "Mann-Whitney U":
        a, b = groups[0], groups[1]
        stat, p = stats.mannwhitneyu(a, b, alternative="two-sided")
        n1, n2 = len(a), len(b)
        r = 1 - (2 * stat) / (n1 * n2)      # rank-biserial correlation
        out.update(statistic=float(stat), p=float(p),
                   effect={"kind": "r", "value": float(r), "band": band("r", r)},
                   apa=f"U = {stat:.1f}, {fmt_p(p)}, r = {r:.2f}")

    elif name in ("One-way ANOVA", "Welch's ANOVA"):
        f, p = stats.f_oneway(*groups)
        k = len(groups)
        n_tot = sum(len(g) for g in groups)
        grand = np.mean(np.concatenate(groups))
        ss_b = sum(len(g) * (np.mean(g) - grand) ** 2 for g in groups)
        ss_t = sum(((np.asarray(g) - grand) ** 2).sum() for g in groups)
        eta2 = ss_b / ss_t if ss_t else float("nan")
        out.update(statistic=float(f), p=float(p), df=(k - 1, n_tot - k),
                   effect={"kind": "eta2", "value": float(eta2),
                           "band": band("eta2", eta2)},
                   apa=f"F({k-1}, {n_tot-k}) = {f:.2f}, {fmt_p(p)}, "
                       f"η² = {eta2:.2f}".replace("0.", ".", 1))
        if name == "Welch's ANOVA":
            out["warning"] = ("The equal-variance assumption is violated, so Welch's ANOVA is "
                              "appropriate, but this computed the ordinary F statistic. "
                              "Re-verify with pingouin.welch_anova or similar.")

    elif name == "Kruskal-Wallis":
        h, p = stats.kruskal(*groups)
        out.update(statistic=float(h), p=float(p), df=len(groups) - 1,
                   apa=f"H({len(groups)-1}) = {h:.2f}, {fmt_p(p)}")

    elif name == "Friedman test":
        stat, p = stats.friedmanchisquare(*groups)
        out.update(statistic=float(stat), p=float(p), df=len(groups) - 1,
                   apa=f"χ²({len(groups)-1}) = {stat:.2f}, {fmt_p(p)}")

    else:
        out["note"] = (f"'{name}' is not automatically run by this script "
                       f"(a repeated-measures structure needs design information). "
                       f"Run it directly via statsmodels/pingouin.")
    return out


def main() -> int:
    _force_utf8_stdout()
    ap = argparse.ArgumentParser(
        description="Check statistical-test assumptions and name the test to use (SKILL.md Phase 2 implementation)")
    ap.add_argument("data", help="Data file (.csv/.tsv/.xlsx)")
    ap.add_argument("--value", required=True, help="Name of the measurement column")
    ap.add_argument("--group", help="Name of the group column (single sample if omitted)")
    ap.add_argument("--mu", type=float,
                    help="Reference value to compare against for a single sample")
    ap.add_argument("--paired", action="store_true",
                    help="Data is paired/repeated-measures (comes from the experimental design — cannot be auto-detected)")
    ap.add_argument("--run", action="store_true",
                    help="Actually run the named test and print APA-formatted output")
    ap.add_argument("--json", help="Save the result as JSON at this path")
    args = ap.parse_args()

    try:
        from scipy import stats  # noqa: F401
        import numpy as np
    except ImportError:
        print("Error: scipy and numpy are required (pip install scipy numpy)", file=sys.stderr)
        return 2

    path = Path(args.data).expanduser().resolve()
    if not path.is_file():
        print(f"Error: file not found — {path}", file=sys.stderr)
        return 2
    df = load_table(path)

    if args.value not in df.columns:
        # NOTE: "있는 열" ("columns that exist") below is asserted on verbatim by
        # tests/test_assumption_check.py — do not translate/remove it without
        # updating that test too.
        print(f"Error: no '{args.value}' column. 있는 열 (columns that exist): {list(df.columns)}", file=sys.stderr)
        return 2

    report = {"file": str(path), "value_col": args.value,
              "group_col": args.group, "paired": args.paired, "alpha": ALPHA}

    # --- split into groups ---
    if args.group:
        if args.group not in df.columns:
            # NOTE: same "있는 열" test dependency as above.
            print(f"Error: no '{args.group}' column. 있는 열 (columns that exist): {list(df.columns)}",
                  file=sys.stderr)
            return 2
        labels, groups = [], []
        for key, sub in df.groupby(args.group, sort=True):
            v = sub[args.value].dropna().to_numpy(dtype=float)
            labels.append(str(key))
            groups.append(v)
        one_sample = False
    else:
        labels = ["(all)"]
        groups = [df[args.value].dropna().to_numpy(dtype=float)]
        one_sample = True
        if args.mu is None and args.run:
            print("Error: --mu (the reference value) is required when there is no group column", file=sys.stderr)
            return 2

    n_groups = len(groups)
    print(f"Data: {path.name}  |  value={args.value}"
          + (f"  group={args.group} ({n_groups})" if args.group else "  (single sample)"))
    for lab, g in zip(labels, groups):
        print(f"  {lab}: n={len(g)}, mean={np.mean(g):.4g}, SD={np.std(g, ddof=1):.4g}"
              if len(g) > 1 else f"  {lab}: n={len(g)}")

    if n_groups > 1 and any(len(g) < 3 for g in groups):
        print("\n[Stopped] A group has n < 3, so assumption checks cannot be run. "
              "Increase the sample size or reconsider the design.")
        return 1

    # --- normality ---
    print(f"\n[1] Normality (α = {ALPHA})")
    norms = [check_normality(g, lab) for lab, g in zip(labels, groups)]
    for nm in norms:
        if nm["test"] is None:
            print(f"  {nm['group']}: {nm['note']}")
        else:
            verdict = "normal" if nm["normal"] else "**violated**"
            print(f"  {nm['group']}: {nm['test']} p = {nm['p']:.4f} → {verdict}")
    report["normality"] = norms
    all_normal = all(nm["normal"] for nm in norms if nm["normal"] is not None)

    # --- equal variance ---
    equal_var = True
    if n_groups > 1:
        from scipy import stats as _st
        lev_stat, lev_p = _st.levene(*groups)
        equal_var = bool(lev_p >= ALPHA)
        print(f"\n[2] Equal variance (Levene)")
        print(f"  W = {lev_stat:.4f}, p = {lev_p:.4f} → "
              f"{'equal variance' if equal_var else '**violated**'}")
        report["levene"] = {"statistic": float(lev_stat), "p": float(lev_p),
                            "equal_var": equal_var}
    else:
        print("\n[2] Equal variance — not applicable, only one group")

    # --- name the test ---
    chosen = decide(n_groups, args.paired, all_normal, equal_var, one_sample)
    report["recommended_test"] = chosen
    print(f"\n[3] Recommended test: **{chosen}**")
    if not all_normal:
        print("     (normality violated → switched to a nonparametric test)")
    if n_groups > 1 and not equal_var and all_normal:
        print("     (equal variance violated → switched to the Welch family)")
    if not args.paired and n_groups == 2:
        print("     ⚠ If this is paired data, add --paired. Design information cannot be auto-detected.")

    # --- actually run it ---
    if args.run:
        print(f"\n[4] Running the test")
        try:
            res = run_test(chosen, groups, mu=args.mu)
        except ValueError as exc:
            print(f"  [Stopped] {exc}")
            return 1
        report["result"] = res
        if "apa" in res:
            print(f"  APA: {res['apa']}")
            if res.get("effect"):
                e = res["effect"]
                print(f"  Effect size: {e['kind']} = {e['value']:.3f} ({e['band']})")
            sig = res["p"] < ALPHA
            # NOTE: "유의함"/"유의하지 않음" ("significant"/"not significant") below are
            # asserted on verbatim by tests/test_assumption_check.py — do not
            # translate/remove them without updating that test too.
            print(f"  Verdict: at α={ALPHA}, "
                  f"{'유의함 (significant)' if sig else '유의하지 않음 (ns) (not significant)'}")
            if not sig:
                print("  * '유의하지 않음' (not significant) is not proof of 'no difference'. "
                      "Report statistical power alongside n.")
            if n_groups > 2 and sig:
                # NOTE: "사후검정" ("post-hoc test") below is asserted on verbatim by
                # tests/test_assumption_check.py — do not translate/remove it without
                # updating that test too.
                print("  * With 3+ groups and a significant result, a 사후검정 (post-hoc test, e.g. Tukey HSD) is needed.")
        if res.get("warning"):
            print(f"  ⚠ {res['warning']}")
        if res.get("note"):
            print(f"  {res['note']}")
    else:
        print("\n  (add --run to actually run this test and print APA-formatted output)")

    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        print(f"\nReport saved: {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
