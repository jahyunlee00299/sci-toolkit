#!/usr/bin/env python3
"""figure_lint.py — enforce figure_aesthetics_rules.md on a figure render script.

THE enforcement layer. The rules SSOT + helpers existed but were opt-in, so every
hand-authored render script re-derived layout/color logic with raw ax.legend(loc=...)
and literal hex — which is why "rules get ignored." This lint turns the rules doc from
advisory into a checked gate.

Scans a render script (text + light AST) and reports rule violations as JSON:
  raw_legend_calls       : ax.legend / plt.legend NOT via smart_legend  (R: legend)
  hardcoded_hex          : '#RRGGBB' literals outside an allowed SSOT line (R: color)
  hardcoded_fontsize     : numeric fontsize=  not theme.FS_*             (R: font)
  set_title_descriptive  : ax.set_title with >3-char non-panel text      (R2: no title)
  layout_manager         : constrained_layout / tight_layout present?    (R4)
  savefig_ok             : every savefig has dpi(=300) + bbox_inches='tight'
  external_legend        : bbox_to_anchor outside axes / loc contains 'center'

Exit code: 0 if no HIGH-severity findings, 1 otherwise. Use as a pre-"figure done" gate.

Usage:
    python figure_lint.py render_figN.py [render_figM.py ...]
    python figure_lint.py --json render_figN.py      # machine-readable
"""
from __future__ import annotations

# Windows 기본 콘솔은 cp949 라서 한글/기호 출력에서 죽는다. UTF-8로 맞춘다.
# reconfigure 를 쓴다: TextIOWrapper 로 감싸면 원본 스트림을 소유하게 되어,
# 이 모듈이 import 된 뒤 래퍼가 GC 될 때 호출자의 stdout 까지 닫는다(실측).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
import sys
import re
import json
from pathlib import Path

HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}\b")
# 라인이 color-SSOT 정의(허용)인지: SERIES_COLORS/OKABE_ITO/팔레트 dict 안의 리터럴은 허용.
SSOT_COLOR_HINT = re.compile(r"OKABE_ITO|SERIES_COLORS|_COLORS\s*=|PALETTE|NEUTRAL")
# fontsize=<숫자> (theme.FS_* 가 아닌 리터럴)
FONTSIZE_LIT_RE = re.compile(r"fontsize\s*=\s*([0-9]+(?:\.[0-9]+)?)")
# raw legend 호출
RAW_LEGEND_RE = re.compile(r"\b(?:ax\w*|axes\[[^\]]*\]|plt)\.legend\s*\(")
EXTERNAL_LEGEND_RE = re.compile(r"bbox_to_anchor|loc\s*=\s*['\"][^'\"]*center")
SETTITLE_RE = re.compile(r"\.set_title\s*\(\s*([fr]?['\"])(.*?)\1")
SAVEFIG_RE = re.compile(r"\.savefig\s*\(")
SUPTITLE_RE = re.compile(r"\.suptitle\s*\(")
# in-axes 텍스트 주석 호출. ax.text(...) — transAxes가 같은 줄/다음 줄이어도 잡도록
# `.text(` 호출 자체를 본다(set_xlabel/ylabel/title은 .text가 아니라 무관). 조건어와 결합해 판정.
AXTEXT_RE = re.compile(r"\b\w*ax\w*\.text\s*\(|\baxes\[[^\]]*\]\.text\s*\(")
# R3 forbidden: 조건/시나리오/설명 키워드 (caption material). 효소명 단독은 면제.
# 🔴 데이터 값성 라벨(reference-line의 'X% yield', 도넛 중앙 수율/시간 등 핵심 수치)은 제외 —
#    "쓸데없는 설명/조건"만 잡는다. yield/titer/selectivity는 값이 흔해 제외(시나리오어만).
COND_WORDS = re.compile(
    r"\b(flask|fermentor|bioreactor|deterministic|marginal\w*|variants?|"
    r"medium|induction|IPTG|substrate|hydrolysate|env\.|scenario|condition)\b", re.I)
# 측정조건 단위 표기(데이터영역에 떠다니는 '8 g DCW/L' 류). reference-line %는 제외(끝이 yield 등 단독값).
COND_UNIT = re.compile(r"\b\d+\s*(?:°C|rpm|g\s*DCW|DCW\s*/?\s*L)\b|pH\s*\d")


def _strip_comment(line: str) -> str:
    """주석(#) 뒤 제거 — 단, 문자열 안 # 은 단순 처리로 무시(근사). 리터럴 감지용."""
    # 따옴표 밖 첫 # 위치
    in_s = None
    for i, ch in enumerate(line):
        if ch in ("'", '"'):
            if in_s is None:
                in_s = ch
            elif in_s == ch:
                in_s = None
        elif ch == "#" and in_s is None:
            return line[:i]
    return line


def lint_script(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    findings = {
        "raw_legend_calls": [], "hardcoded_hex": [], "hardcoded_fontsize": [],
        "set_title_descriptive": [], "external_legend": [],
        "suptitle": [], "condition_label": [],
    }
    is_theme_module = path.name in ("theme.py", "aesthetic_helpers.py")
    # schematic/construct 도식(SBOL 글리프 아트워크)은 데이터 플롯이 아니므로
    # 스타일 규칙(하드코딩 hex/fontsize, layout manager)을 면제한다. 도식 전용 글리프 색
    # (backbone/promoter/RBS/zebra)과 imshow 합성용 정밀 배치는 theme.FS_*/constrained_layout과
    # 무관. 단 의미 규칙(suptitle·external/center legend·조건라벨 R3)은 그대로 적용한다.
    nm = path.name.lower()
    is_schematic = any(k in nm for k in ("construct", "schematic", "scheme", "diagram"))

    for i, raw in enumerate(lines, 1):
        line = _strip_comment(raw)
        if not line.strip():
            continue
        # raw legend (smart_legend 경유는 OK). schematic 도식(축 off 아트워크)은 범례가
        # 곧 글리프 캡션 역할 → 하단 가로배치가 관례, 코너규칙 무의미하므로 면제.
        if not is_schematic and RAW_LEGEND_RE.search(line) and "smart_legend" not in line:
            findings["raw_legend_calls"].append({"line": i, "text": line.strip()[:90]})
        # external / center legend (schematic은 면제 — 축 off라 코너 개념 없음)
        if not is_schematic and EXTERNAL_LEGEND_RE.search(line) and ".legend(" in line:
            findings["external_legend"].append({"line": i, "text": line.strip()[:90]})
        # 하드코딩 hex (theme 모듈·색 SSOT 정의 라인·schematic 도식은 면제)
        if not is_theme_module and not is_schematic and HEX_RE.search(line) and not SSOT_COLOR_HINT.search(line):
            for m in HEX_RE.findall(line):
                findings["hardcoded_hex"].append({"line": i, "hex": m, "text": line.strip()[:90]})
        # 하드코딩 fontsize (theme.FS_* 가 아닌 숫자; schematic 도식은 면제)
        if not is_schematic:
            for m in FONTSIZE_LIT_RE.finditer(line):
                findings["hardcoded_fontsize"].append({"line": i, "value": m.group(1), "text": line.strip()[:90]})
        # descriptive set_title (패널레터 '(a)' 'a' 같은 3자 이하 제외)
        mt = SETTITLE_RE.search(line)
        if mt:
            title_txt = mt.group(2)
            stripped = re.sub(r"[()\s]", "", title_txt)
            if len(stripped) > 3 and "loc" not in line.split(".set_title")[0][-30:]:
                # loc='left' 패널레터 용법도 본문이 길면 위반
                if len(stripped) > 3:
                    findings["set_title_descriptive"].append({"line": i, "title": title_txt[:40]})
        # suptitle 금지(R3: figure 제목 금지)
        if SUPTITLE_RE.search(line):
            findings["suptitle"].append({"line": i, "text": line.strip()[:80]})
        # in-axes 조건/설명 라벨(R3: caption material). 두 경로:
        #  (1) ax.text(...transAxes...) 직접 호출에 조건어/단위
        #  (2) panel_tag/tag/label 류 헬퍼 호출에 조건 문자열 (호출부와 ax.text 분리된 경우)
        # 효소/샘플명 단독(어느 패널인지 식별용)은 면제 — 조건어/단위가 함께 있을 때만 잡음.
        is_axtext = AXTEXT_RE.search(line)
        is_tag_call = re.search(r"\b(panel_tag|panel_subtitle|cond_label|annotate_cond)\s*\(", line)
        if (is_axtext or is_tag_call) and (COND_WORDS.search(line) or COND_UNIT.search(line)):
            strs = re.findall(r"['\"]([^'\"]{2,60})['\"]", line)
            label = " ".join(s for s in strs if "transAxes" not in s and s != "%" and "$" not in s)
            findings["condition_label"].append({"line": i, "label": (label or line.strip())[:60]})

    # layout manager / savefig 전역 검사 (schematic 도식은 subplots_adjust 정밀배치 → 면제)
    layout_manager = is_schematic or bool(re.search(
        r"constrained_layout\s*=\s*True|\.tight_layout\s*\(|fig\.set_layout_engine|subplots_adjust", text))
    savefig_calls = [i for i, ln in enumerate(lines, 1) if SAVEFIG_RE.search(_strip_comment(ln))]
    savefig_issues = []
    for ln_no in savefig_calls:
        # savefig 호출이 여러 줄일 수 있어 ±2줄 합쳐 검사
        ctx = " ".join(lines[max(0, ln_no - 1):ln_no + 2])
        has_dpi = "dpi=300" in ctx.replace(" ", "") or "dpi=300" in ctx
        has_bbox = "bbox_inches" in ctx and "tight" in ctx
        if not (has_dpi and has_bbox):
            savefig_issues.append({"line": ln_no, "has_dpi300": has_dpi, "has_bbox_tight": has_bbox})

    # 심각도 집계
    high = (len(findings["raw_legend_calls"]) + len(findings["external_legend"])
            + len(findings["hardcoded_hex"]) + len(findings["set_title_descriptive"])
            + len(findings["suptitle"]) + len(findings["condition_label"])
            + (0 if layout_manager else 1) + len(savefig_issues))
    med = len(findings["hardcoded_fontsize"])

    return {
        "file": str(path.name),
        "findings": findings,
        "layout_manager_present": layout_manager,
        "savefig_issues": savefig_issues,
        "counts": {
            "raw_legend_calls": len(findings["raw_legend_calls"]),
            "hardcoded_hex": len(findings["hardcoded_hex"]),
            "hardcoded_fontsize": len(findings["hardcoded_fontsize"]),
            "set_title_descriptive": len(findings["set_title_descriptive"]),
            "external_legend": len(findings["external_legend"]),
            "suptitle": len(findings["suptitle"]),
            "condition_label": len(findings["condition_label"]),
            "savefig_issues": len(savefig_issues),
        },
        "high_severity": high,
        "med_severity": med,
        "pass": high == 0,
    }


def _print_human(r: dict):
    mark = "PASS" if r["pass"] else "FAIL"
    print(f"\n=== {r['file']}  [{mark}]  high={r['high_severity']} med={r['med_severity']} ===")
    c = r["counts"]
    if c["raw_legend_calls"]:
        print(f"  [HIGH] raw ax.legend(loc=...) x{c['raw_legend_calls']} — use smart_legend()")
        for f in r["findings"]["raw_legend_calls"]:
            print(f"         L{f['line']}: {f['text']}")
    if c["external_legend"]:
        print(f"  [HIGH] external/center legend x{c['external_legend']} — corners only, inside axes")
        for f in r["findings"]["external_legend"]:
            print(f"         L{f['line']}: {f['text']}")
    if c["hardcoded_hex"]:
        print(f"  [HIGH] hardcoded hex x{c['hardcoded_hex']} — route via series_color()/SERIES_COLORS")
        for f in r["findings"]["hardcoded_hex"][:12]:
            print(f"         L{f['line']}: {f['hex']}  ({f['text']})")
    if c["set_title_descriptive"]:
        print(f"  [HIGH] descriptive set_title x{c['set_title_descriptive']} — R2: no graph title")
        for f in r["findings"]["set_title_descriptive"]:
            print(f"         L{f['line']}: {f['title']}")
    if c["suptitle"]:
        print(f"  [HIGH] suptitle x{c['suptitle']} — R3: no figure title")
        for f in r["findings"]["suptitle"]:
            print(f"         L{f['line']}: {f['text']}")
    if c["condition_label"]:
        print(f"  [HIGH] on-figure condition/description label x{c['condition_label']} — R3: move to caption")
        for f in r["findings"]["condition_label"]:
            print(f"         L{f['line']}: \"{f['label']}\"  (strip condition; keep bare entity name only)")
    if not r["layout_manager_present"]:
        print("  [HIGH] no layout manager — add constrained_layout=True or tight_layout()")
    if r["savefig_issues"]:
        print(f"  [HIGH] savefig missing dpi=300/bbox_inches='tight' x{len(r['savefig_issues'])}")
        for f in r["savefig_issues"]:
            print(f"         L{f['line']}: dpi300={f['has_dpi300']} bbox_tight={f['has_bbox_tight']}")
    if c["hardcoded_fontsize"]:
        print(f"  [MED]  hardcoded fontsize x{c['hardcoded_fontsize']} — use theme.FS_*")
        for f in r["findings"]["hardcoded_fontsize"][:8]:
            print(f"         L{f['line']}: fontsize={f['value']}")
    if r["pass"] and not r["med_severity"]:
        print("  clean.")


def main(argv):
    as_json = "--json" in argv
    files = [a for a in argv if not a.startswith("--")]
    if not files:
        print("usage: figure_lint.py [--json] render_figN.py ...", file=sys.stderr)
        return 2
    results = [lint_script(Path(f)) for f in files]
    if as_json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for r in results:
            _print_human(r)
        total_high = sum(r["high_severity"] for r in results)
        n_fail = sum(1 for r in results if not r["pass"])
        print(f"\n{'='*50}\nTOTAL: {len(results)} files, {n_fail} FAIL, {total_high} high-severity findings")
    return 0 if all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
