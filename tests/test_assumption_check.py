#!/usr/bin/env python3
"""assumption_check.py 회귀 테스트 — 정답을 아는 데이터로 판정을 검증한다.

통계 도구는 "돌아간다"와 "맞다"가 다르다. 여기서는 분포를 알고 만든 데이터를
넣어서, 도구가 **정답으로 알려진 검정을 지목하는지** 확인한다.
난수 시드를 고정하므로 결과는 재현 가능하다.

실행:
    python tests/test_assumption_check.py     # exit 0 = 통과
"""
import importlib.util
import io
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "stats-workflow" / "scripts" / "assumption_check.py"

# 대상 모듈은 import 시점에 sys.stdout 을 UTF-8 래퍼로 교체한다(cp949 대응).
# 그래서 여기서 먼저 래핑해 두면 그 래퍼가 닫혀 버린다 — 반드시 import 를 먼저 하고,
# 그 뒤에 최종 stdout 을 UTF-8 로 맞춘다.
spec = importlib.util.spec_from_file_location("assumption_check", str(SCRIPT))
mod = importlib.util.module_from_spec(spec)
sys.modules["assumption_check"] = mod
spec.loader.exec_module(mod)

# Windows 기본 콘솔은 cp949 라서 한글/기호 출력에서 죽는다. UTF-8로 맞춘다.
# TextIOWrapper 대신 reconfigure — 래퍼는 원본 스트림을 소유해서,
# import 후 GC 되면 호출자의 stdout 까지 닫아버린다(실측).
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

fails = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"        기대: {want!r}")
        print(f"        실제: {got!r}")
        fails.append(label)


# ---------------------------------------------------------------- 결정 트리
# SKILL.md Phase 2 의 트리를 그대로 옮겼는지 확인한다.
print("=== 결정 트리 (SKILL.md Phase 2) ===")
check("2군·독립·정규·등분산 → Independent t-test",
      mod.decide(2, False, True, True, False), "Independent t-test")
check("2군·독립·정규·이분산 → Welch's t-test",
      mod.decide(2, False, True, False, False), "Welch's t-test")
check("2군·독립·비정규 → Mann-Whitney U",
      mod.decide(2, False, False, True, False), "Mann-Whitney U")
check("2군·대응·정규 → Paired t-test",
      mod.decide(2, True, True, True, False), "Paired t-test")
check("2군·대응·비정규 → Wilcoxon",
      mod.decide(2, True, False, True, False), "Wilcoxon signed-rank")
check("3군·정규·등분산 → One-way ANOVA",
      mod.decide(3, False, True, True, False), "One-way ANOVA")
check("3군·정규·이분산 → Welch's ANOVA",
      mod.decide(3, False, True, False, False), "Welch's ANOVA")
check("3군·비정규 → Kruskal-Wallis",
      mod.decide(3, False, False, True, False), "Kruskal-Wallis")
check("3군·반복측정·비정규 → Friedman",
      mod.decide(3, True, False, True, False), "Friedman test")
check("단일표본·정규 → One-sample t-test",
      mod.decide(1, False, True, True, True), "One-sample t-test")

# ---------------------------------------------------------------- 정규성 판정
print("\n=== 정규성 검정 선택 (n 기준) ===")
try:
    import numpy as np
except ImportError:
    print("  SKIP — numpy 없음")
    np = None

if np is not None:
    rng = np.random.default_rng(20260723)
    small_normal = rng.normal(10, 2, 20)
    big_normal = rng.normal(10, 2, 80)
    check("n=20 → Shapiro-Wilk 사용",
          mod.check_normality(small_normal, "a")["test"], "Shapiro-Wilk")
    check("n=80 → D'Agostino-Pearson 사용",
          mod.check_normality(big_normal, "b")["test"], "D'Agostino-Pearson")
    check("정규분포 데이터 → normal=True",
          mod.check_normality(small_normal, "a")["normal"], True)
    # 지수분포는 강하게 치우쳐 있어 정규성이 깨져야 한다
    skewed = rng.exponential(3, 40)
    check("지수분포 데이터 → normal=False",
          mod.check_normality(skewed, "c")["normal"], False)

# ---------------------------------------------------------------- APA 서식
print("\n=== APA p 값 서식 ===")
check("p=.0004 → 'p < .001'", mod.fmt_p(0.0004), "p < .001")
check("p=.032 → 'p = .032'", mod.fmt_p(0.032), "p = .032")
check("p=.5 → 'p = .500'", mod.fmt_p(0.5), "p = .500")

print("\n=== 효과크기 해석 (Cohen) ===")
check("d=0.9 → large", mod.band("d", 0.9), "large")
check("d=0.55 → medium", mod.band("d", 0.55), "medium")
check("d=0.25 → small", mod.band("d", 0.25), "small")
check("d=0.05 → negligible", mod.band("d", 0.05), "negligible")
check("d=-0.9 (음수도 크기로) → large", mod.band("d", -0.9), "large")

# ---------------------------------------------------------------- end-to-end
print("\n=== 실제 실행 (정답을 아는 데이터) ===")
if np is None:
    print("  SKIP — numpy 없음")
else:
    rng = np.random.default_rng(4242)
    tmp = Path(tempfile.mkdtemp())

    # (1) 두 정규분포, 등분산, 평균이 뚜렷이 다름 → Independent t-test, 유의
    a = rng.normal(10, 1.5, 30)
    b = rng.normal(14, 1.5, 30)
    f1 = tmp / "two_normal.csv"
    f1.write_text("value,group\n" +
                  "".join(f"{v},A\n" for v in a) +
                  "".join(f"{v},B\n" for v in b), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPT), str(f1),
                        "--value", "value", "--group", "group", "--run"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = r.stdout
    check("정규·등분산 2군 → Independent t-test 지목",
          "Independent t-test" in out, True)
    check("  APA 문자열 출력됨", "APA: t(" in out, True)
    check("  큰 차이 → 유의함", "유의함" in out and "유의하지 않음" not in out, True)
    check("  exit 0", r.returncode, 0)

    # (2) 한쪽이 지수분포 → 비모수로 전환되어야 한다
    c = rng.exponential(2, 30)
    d = rng.normal(10, 1.5, 30)
    f2 = tmp / "skewed.csv"
    f2.write_text("value,group\n" +
                  "".join(f"{v},A\n" for v in c) +
                  "".join(f"{v},B\n" for v in d), encoding="utf-8")
    r2 = subprocess.run([sys.executable, str(SCRIPT), str(f2),
                         "--value", "value", "--group", "group", "--run"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("비정규 포함 → Mann-Whitney U 로 전환",
          "Mann-Whitney U" in r2.stdout, True)

    # (3) 등분산 위배 → Welch 로 전환
    e = rng.normal(10, 1.0, 30)
    f = rng.normal(10.5, 6.0, 30)
    f3 = tmp / "unequal_var.csv"
    f3.write_text("value,group\n" +
                  "".join(f"{v},A\n" for v in e) +
                  "".join(f"{v},B\n" for v in f), encoding="utf-8")
    r3 = subprocess.run([sys.executable, str(SCRIPT), str(f3),
                         "--value", "value", "--group", "group"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("등분산 위배 → Welch's t-test 로 전환",
          "Welch's t-test" in r3.stdout, True)

    # (4) 3군 정규·등분산 → ANOVA
    g1 = rng.normal(10, 1.5, 25)
    g2 = rng.normal(12, 1.5, 25)
    g3 = rng.normal(14, 1.5, 25)
    f4 = tmp / "three.csv"
    f4.write_text("value,group\n" +
                  "".join(f"{v},A\n" for v in g1) +
                  "".join(f"{v},B\n" for v in g2) +
                  "".join(f"{v},C\n" for v in g3), encoding="utf-8")
    r4 = subprocess.run([sys.executable, str(SCRIPT), str(f4),
                         "--value", "value", "--group", "group", "--run"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("3군 정규·등분산 → One-way ANOVA", "One-way ANOVA" in r4.stdout, True)
    check("  3군 유의 시 사후검정 안내", "사후검정" in r4.stdout, True)

    # (5) 대응표본인데 크기가 다르면 조용히 넘어가지 말고 막아야 한다
    f5 = tmp / "mismatched.csv"
    f5.write_text("value,group\n" +
                  "".join(f"{v},A\n" for v in rng.normal(10, 1, 20)) +
                  "".join(f"{v},B\n" for v in rng.normal(11, 1, 15)), encoding="utf-8")
    r5 = subprocess.run([sys.executable, str(SCRIPT), str(f5),
                         "--value", "value", "--group", "group",
                         "--paired", "--run"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("대응표본 크기 불일치 → 중단(exit 1)", r5.returncode, 1)
    check("  이유를 밝힘", "크기가 다르다" in r5.stdout, True)

    # (6) 없는 열 → 친절한 오류 + exit 2
    r6 = subprocess.run([sys.executable, str(SCRIPT), str(f1),
                         "--value", "nonexistent_column"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("없는 열 → exit 2", r6.returncode, 2)
    check("  있는 열 목록을 알려줌", "있는 열" in (r6.stdout + r6.stderr), True)

print()
if fails:
    print(f"{len(fails)} FAILURE(S): {fails}")
    sys.exit(1)
print("ALL PASS")
