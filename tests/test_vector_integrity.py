#!/usr/bin/env python3
"""동봉된 SnapGene 벡터가 실제로 읽히는지 검사한다.

260807 실측: `.gitattributes` 가 `* text=auto eol=lf` 만 두고 `*.dna` 를 바이너리로
선언하지 않아, 줄바꿈 정규화가 벡터 파일 **안쪽**의 CRLF 두 바이트를 접었다.
`.dna` 는 `[1B type][4B big-endian length][payload]` 연쇄라 payload 에서 바이트가
사라지면 그 뒤 오프셋이 전부 밀린다. 결과:

    pACYCDuet-1  features 19 → 0
    pET-21a(+)   features 15 → 0
    pET-28a(+)   features 16 → 0
    pMAL-c6T     features 18 → 0      (pETDuet-1 만 무사)

**서열은 그대로 남고 파서는 예외를 던지지 않는다.** `parse_snapgene()` 은 빈
feature 목록을 정상 반환하고, `colony_pcr_mode.suggest_from_snapgene()` 은 CDS
feature 로 동작하므로 프라이머 설계가 "아무것도 못 찾음" 으로 조용히 틀린다.
doctor·테스트 전부와 CI 가 초록불인 채였다 — 아무도 이 축을 보지 않았다.

그래서 검사는 **파일이 존재하는가**가 아니라 **파싱해서 내용이 나오는가**를 본다.
바이트 손상은 크기나 해시로는 "달라졌다"만 알 수 있고 "쓸 수 있는가"는 알 수 없다.
"""
from __future__ import annotations

import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
VECTORS = ROOT / "skills" / "primer-design" / "vectors"
SRC = ROOT / "skills" / "primer-design" / "src"

# 각 벡터가 최소한 이만큼의 feature 를 가져야 한다. 실측값보다 낮게 잡아 두어
# SnapGene 버전 차이로 주석이 한둘 늘고 주는 것은 통과시키되, 0 으로 무너지는
# 손상은 반드시 잡는다.
MIN_FEATURES = 5
MIN_SEQUENCE = 1000


def main() -> int:
    if not VECTORS.is_dir():
        print("SKIP — primer-design 벡터 폴더가 없다 (선택 설치)")
        return 0

    sys.path.insert(0, str(SRC))
    try:
        from primer_design.snapgene_parser import parse_snapgene
    except Exception as e:                      # noqa: BLE001
        print(f"SKIP — 파서를 불러올 수 없다: {type(e).__name__}: {e}")
        return 0

    files = sorted(VECTORS.glob("*.dna"))
    if not files:
        print("SKIP — .dna 벡터가 없다")
        return 0

    failures: list[str] = []
    for f in files:
        try:
            seq, _circular, feats = parse_snapgene(str(f))
        except Exception as e:                  # noqa: BLE001
            failures.append(f"{f.name}: 파싱 실패 — {type(e).__name__}: {e}")
            continue
        n_seq = len(seq or "")
        n_feat = len(feats or [])
        if n_seq < MIN_SEQUENCE:
            failures.append(f"{f.name}: 서열이 {n_seq}bp — 최소 {MIN_SEQUENCE} 기대")
        if n_feat < MIN_FEATURES:
            failures.append(
                f"{f.name}: feature {n_feat}개 — 최소 {MIN_FEATURES} 기대. "
                "바이너리가 줄바꿈 정규화로 손상됐을 때 나타나는 값이다 "
                "(.gitattributes 의 `*.dna binary` 선언을 확인하라)")

    if failures:
        print(f"FAIL — 벡터 무결성 {len(failures)}건")
        for x in failures:
            print(f"  - {x}")
        return 1

    total = sum(len(parse_snapgene(str(f))[2] or []) for f in files)
    print(f"ALL PASS — 벡터 {len(files)}개, feature 총 {total}개 파싱됨")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
