#!/usr/bin/env python3
"""통계 검정 전 가정(assumption)을 실제로 검사하고, 맞는 검정을 지목한다.

`SKILL.md` Phase 2 의 결정 트리와 가정 검정을 그대로 실행 가능한 형태로 옮긴 것이다.
사람이 눈으로 "정규분포 같아 보인다" 하고 넘어가는 지점을 막는 게 목적이다.

무엇을 하는가
-------------
1. 데이터를 읽고(csv/tsv/xlsx) 그룹별로 나눈다
2. **정규성** — n < 50 이면 Shapiro-Wilk, n >= 50 이면 D'Agostino-Pearson
3. **등분산성** — Levene (2군 이상일 때)
4. 위 결과로 SKILL.md 결정 트리를 따라 **써야 할 검정을 지목**한다
5. 요청하면 그 검정을 실제로 수행하고 **APA 7판 서식 + 효과크기**까지 출력한다

사용
----
    # 가정만 검사하고 어떤 검정을 써야 하는지 보기
    python assumption_check.py data.csv --value od600 --group strain

    # 검정까지 수행하고 APA 형식으로 출력
    python assumption_check.py data.csv --value od600 --group strain --run

    # 대응표본(paired)
    python assumption_check.py data.csv --value delta --group timepoint --paired --run

    # 단일 그룹을 기준값과 비교
    python assumption_check.py data.csv --value yield --mu 100 --run

종료 코드
---------
    0  가정 위배 없음 (또는 위배가 있어도 그에 맞는 비모수 검정을 지목함)
    1  데이터 문제로 판단 불가 (그룹이 하나뿐, n 부족, 결측 과다 등)
    2  입력/의존성 오류

**중요**: 이 도구는 "어떤 검정을 쓸지"를 정해줄 뿐, 그 검정이 연구 질문에 맞는지는
판단하지 않는다. 대응/독립 여부, 반복측정 구조는 실험 설계에서 나오는 것이므로
`--paired` 같은 플래그로 **사람이** 알려줘야 한다.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

def _force_utf8_stdout() -> None:
    """Windows 기본 콘솔(cp949)에서 한글·기호 출력에 죽지 않게 한다.

    `reconfigure` 를 쓴다. TextIOWrapper 로 감싸면 원본 스트림을 소유하게 되어,
    이 모듈이 import 된 뒤 래퍼가 GC 될 때 호출자의 stdout 까지 닫아버린다
    (테스트에서 실제로 발생했다). reconfigure 는 같은 객체를 바꾸므로 안전하다.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError, io.UnsupportedOperation):
                pass

ALPHA = 0.05
SHAPIRO_MAX_N = 50          # SKILL.md: n < 50 이면 Shapiro, 그 이상은 normaltest

# 효과크기 해석 기준 (SKILL.md Phase 3 표)
EFFECT_BANDS = {
    "d":   [(0.2, "small"), (0.5, "medium"), (0.8, "large")],
    "eta2": [(0.01, "small"), (0.06, "medium"), (0.14, "large")],
    "r":   [(0.1, "small"), (0.3, "medium"), (0.5, "large")],
}


def band(kind: str, value: float) -> str:
    """효과크기 수치를 small/medium/large 로 해석."""
    v = abs(value)
    label = "negligible"
    for cut, name in EFFECT_BANDS[kind]:
        if v >= cut:
            label = name
    return label


def fmt_p(p: float) -> str:
    """APA: p < .001 로 쓰고, 그 외에는 소수점 앞 0 을 뺀 세 자리."""
    if p < 0.001:
        return "p < .001"
    return f"p = {p:.3f}".replace("0.", ".")


def load_table(path: Path):
    try:
        import pandas as pd
    except ImportError:
        print("오류: pandas 가 필요하다 (pip install pandas)", file=sys.stderr)
        raise SystemExit(2)
    suf = path.suffix.lower()
    if suf in (".csv", ".txt"):
        return pd.read_csv(path)
    if suf == ".tsv":
        return pd.read_csv(path, sep="\t")
    if suf in (".xlsx", ".xls"):
        return pd.read_excel(path)
    print(f"오류: 지원하지 않는 형식 '{suf}' (.csv/.tsv/.xlsx)", file=sys.stderr)
    raise SystemExit(2)


def check_normality(values, label):
    """정규성 검정. n에 따라 Shapiro / D'Agostino 를 고른다 (SKILL.md 규칙)."""
    from scipy import stats
    n = len(values)
    if n < 3:
        return {"group": label, "n": n, "test": None, "p": None,
                "normal": None, "note": "n < 3 — 정규성 판단 불가"}
    if n < SHAPIRO_MAX_N:
        stat, p = stats.shapiro(values)
        test = "Shapiro-Wilk"
    else:
        stat, p = stats.normaltest(values)
        test = "D'Agostino-Pearson"
    return {"group": label, "n": n, "test": test, "statistic": float(stat),
            "p": float(p), "normal": bool(p >= ALPHA),
            "note": "" if p >= ALPHA else "정규성 위배"}


def decide(n_groups, paired, all_normal, equal_var, one_sample):
    """SKILL.md Phase 2 결정 트리를 그대로 구현."""
    if one_sample:
        return ("One-sample t-test" if all_normal
                else "Wilcoxon signed-rank (one-sample)")
    if n_groups == 2:
        if paired:
            return "Paired t-test" if all_normal else "Wilcoxon signed-rank"
        if not all_normal:
            return "Mann-Whitney U"
        return "Independent t-test" if equal_var else "Welch's t-test"
    # 3군 이상
    if paired:
        return "Repeated-measures ANOVA" if all_normal else "Friedman test"
    if not all_normal:
        return "Kruskal-Wallis"
    return "One-way ANOVA" if equal_var else "Welch's ANOVA"


def run_test(name, groups, mu=None):
    """지목된 검정을 실제로 수행하고 APA 문자열 + 효과크기를 만든다."""
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
            raise ValueError(f"대응표본인데 두 그룹 크기가 다르다 ({len(a)} vs {len(b)}). "
                             "짝이 맞는지 확인하라.")
        t, p = stats.ttest_rel(a, b)
        diff = np.asarray(a) - np.asarray(b)
        d = np.mean(diff) / np.std(diff, ddof=1)
        out.update(statistic=float(t), p=float(p), df=len(a) - 1,
                   effect={"kind": "d", "value": float(d), "band": band("d", d)},
                   apa=f"t({len(a)-1}) = {t:.2f}, {fmt_p(p)}, d = {d:.2f}")

    elif name == "Wilcoxon signed-rank":
        a, b = groups[0], groups[1]
        if len(a) != len(b):
            raise ValueError(f"대응표본인데 두 그룹 크기가 다르다 ({len(a)} vs {len(b)}).")
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
            out["warning"] = ("등분산 가정이 깨져 Welch's ANOVA 가 적절하나, "
                              "여기서는 일반 F 통계량을 계산했다. "
                              "pingouin.welch_anova 등으로 재확인하라.")

    elif name == "Kruskal-Wallis":
        h, p = stats.kruskal(*groups)
        out.update(statistic=float(h), p=float(p), df=len(groups) - 1,
                   apa=f"H({len(groups)-1}) = {h:.2f}, {fmt_p(p)}")

    elif name == "Friedman test":
        stat, p = stats.friedmanchisquare(*groups)
        out.update(statistic=float(stat), p=float(p), df=len(groups) - 1,
                   apa=f"χ²({len(groups)-1}) = {stat:.2f}, {fmt_p(p)}")

    else:
        out["note"] = (f"'{name}' 은 이 스크립트가 자동 수행하지 않는다 "
                       f"(반복측정 구조는 설계 정보가 필요하다). "
                       f"statsmodels/pingouin 으로 직접 수행하라.")
    return out


def main() -> int:
    _force_utf8_stdout()
    ap = argparse.ArgumentParser(
        description="통계 검정 전 가정 검사 + 검정 지목 (SKILL.md Phase 2 구현)")
    ap.add_argument("data", help="데이터 파일 (.csv/.tsv/.xlsx)")
    ap.add_argument("--value", required=True, help="측정값 열 이름")
    ap.add_argument("--group", help="그룹 열 이름 (없으면 단일 표본)")
    ap.add_argument("--mu", type=float,
                    help="단일 표본일 때 비교할 기준값")
    ap.add_argument("--paired", action="store_true",
                    help="대응표본/반복측정이다 (실험 설계에서 나오는 정보 — 자동 판별 불가)")
    ap.add_argument("--run", action="store_true",
                    help="지목된 검정을 실제로 수행하고 APA 형식으로 출력")
    ap.add_argument("--json", help="결과를 이 경로에 JSON 으로 저장")
    args = ap.parse_args()

    try:
        from scipy import stats  # noqa: F401
        import numpy as np
    except ImportError:
        print("오류: scipy, numpy 가 필요하다 (pip install scipy numpy)", file=sys.stderr)
        return 2

    path = Path(args.data).expanduser().resolve()
    if not path.is_file():
        print(f"오류: 파일이 없다 — {path}", file=sys.stderr)
        return 2
    df = load_table(path)

    if args.value not in df.columns:
        print(f"오류: '{args.value}' 열이 없다. 있는 열: {list(df.columns)}", file=sys.stderr)
        return 2

    report = {"file": str(path), "value_col": args.value,
              "group_col": args.group, "paired": args.paired, "alpha": ALPHA}

    # --- 그룹 나누기 ---
    if args.group:
        if args.group not in df.columns:
            print(f"오류: '{args.group}' 열이 없다. 있는 열: {list(df.columns)}",
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
            print("오류: 그룹 열이 없으면 --mu (비교 기준값) 가 필요하다", file=sys.stderr)
            return 2

    n_groups = len(groups)
    print(f"데이터: {path.name}  |  값={args.value}"
          + (f"  그룹={args.group} ({n_groups}개)" if args.group else "  (단일 표본)"))
    for lab, g in zip(labels, groups):
        print(f"  {lab}: n={len(g)}, mean={np.mean(g):.4g}, SD={np.std(g, ddof=1):.4g}"
              if len(g) > 1 else f"  {lab}: n={len(g)}")

    if n_groups > 1 and any(len(g) < 3 for g in groups):
        print("\n[중단] n < 3 인 그룹이 있어 가정 검정을 할 수 없다. "
              "표본을 늘리거나 설계를 재검토하라.")
        return 1

    # --- 정규성 ---
    print(f"\n[1] 정규성 (α = {ALPHA})")
    norms = [check_normality(g, lab) for lab, g in zip(labels, groups)]
    for nm in norms:
        if nm["test"] is None:
            print(f"  {nm['group']}: {nm['note']}")
        else:
            verdict = "정규" if nm["normal"] else "**위배**"
            print(f"  {nm['group']}: {nm['test']} p = {nm['p']:.4f} → {verdict}")
    report["normality"] = norms
    all_normal = all(nm["normal"] for nm in norms if nm["normal"] is not None)

    # --- 등분산 ---
    equal_var = True
    if n_groups > 1:
        from scipy import stats as _st
        lev_stat, lev_p = _st.levene(*groups)
        equal_var = bool(lev_p >= ALPHA)
        print(f"\n[2] 등분산성 (Levene)")
        print(f"  W = {lev_stat:.4f}, p = {lev_p:.4f} → "
              f"{'등분산' if equal_var else '**위배**'}")
        report["levene"] = {"statistic": float(lev_stat), "p": float(lev_p),
                            "equal_var": equal_var}
    else:
        print("\n[2] 등분산성 — 그룹이 하나라 해당 없음")

    # --- 검정 지목 ---
    chosen = decide(n_groups, args.paired, all_normal, equal_var, one_sample)
    report["recommended_test"] = chosen
    print(f"\n[3] 권장 검정: **{chosen}**")
    if not all_normal:
        print("     (정규성 위배 → 비모수 검정으로 전환됨)")
    if n_groups > 1 and not equal_var and all_normal:
        print("     (등분산 위배 → Welch 계열로 전환됨)")
    if not args.paired and n_groups == 2:
        print("     ⚠ 대응표본이면 --paired 를 붙여라. 설계 정보는 자동 판별할 수 없다.")

    # --- 실제 수행 ---
    if args.run:
        print(f"\n[4] 검정 수행")
        try:
            res = run_test(chosen, groups, mu=args.mu)
        except ValueError as exc:
            print(f"  [중단] {exc}")
            return 1
        report["result"] = res
        if "apa" in res:
            print(f"  APA: {res['apa']}")
            if res.get("effect"):
                e = res["effect"]
                print(f"  효과크기: {e['kind']} = {e['value']:.3f} ({e['band']})")
            sig = res["p"] < ALPHA
            print(f"  판정: α={ALPHA} 기준 "
                  f"{'유의함' if sig else '유의하지 않음 (ns)'}")
            if not sig:
                print("  ※ '유의하지 않음'은 '차이가 없음'의 증명이 아니다. "
                      "검정력과 n 을 함께 보고하라.")
            if n_groups > 2 and sig:
                print("  ※ 3군 이상에서 유의하면 사후검정(Tukey HSD 등)이 필요하다.")
        if res.get("warning"):
            print(f"  ⚠ {res['warning']}")
        if res.get("note"):
            print(f"  {res['note']}")
    else:
        print("\n  (--run 을 붙이면 이 검정을 실제로 수행하고 APA 형식으로 출력한다)")

    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        print(f"\n리포트 저장: {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
