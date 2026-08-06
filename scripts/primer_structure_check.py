#!/usr/bin/env python3
"""프라이머 구조 체크 - hairpin 및 homodimer 검사 (nearest-neighbor 열역학).

사용법:
    python primer_structure_check.py ATCGATCGATCG
    python primer_structure_check.py ATCG... GCTA... --threshold-hairpin -2.0
    python primer_structure_check.py --file primers.json

임포트:
    from primer_structure_check import check_primer, check_primers
    result = check_primer("ATCGATCG")

결과 형식:
    [{"seq", "hairpin_dG", "homodimer_dG", "hairpin_pass", "homodimer_pass"}]

판정 기준:
    - hairpin: 자기보완 ≥4 bp AND ΔG < -2.0 kcal/mol → FAIL
    - homodimer: ≥6 bp 상보 → FAIL (ΔG 기준 별도 적용)
"""
import argparse
import json
import math
import sys
from pathlib import Path
from typing import Optional

# Nearest-neighbor 파라미터 (SantaLucia 1998, 1M NaCl, 37°C)
# 키: 5'→3' 이중가닥 dinucleotide (상위/하위 가닥)
# 값: (ΔH kcal/mol, ΔS cal/mol/K)
_NN_PARAMS: dict[str, tuple[float, float]] = {
    "AA/TT": (-7.9, -22.2),
    "AT/TA": (-7.2, -20.4),
    "TA/AT": (-7.2, -21.3),
    "CA/GT": (-8.5, -22.7),
    "GT/CA": (-8.4, -22.4),
    "CT/GA": (-7.8, -21.0),
    "GA/CT": (-8.2, -22.2),
    "CG/GC": (-10.6, -27.2),
    "GC/CG": (-9.8, -24.4),
    "GG/CC": (-8.0, -19.9),
    # 역방향 (complement)
    "TT/AA": (-7.9, -22.2),
    "TA/AT": (-7.2, -21.3),
    "AT/TA": (-7.2, -20.4),
    "AC/TG": (-7.8, -21.0),  # CA/GT 역
    "TG/AC": (-8.5, -22.7),
    "AG/TC": (-8.4, -22.4),
    "TC/AG": (-8.2, -22.2),
    "GC/CG": (-9.8, -24.4),
    "CG/GC": (-10.6, -27.2),
    "CC/GG": (-8.0, -19.9),
}

# 말단 AT 패널티 (initiation)
_INIT_AT = (2.3, 4.1)
_INIT_GC = (0.1, -2.8)

_COMPLEMENT = str.maketrans("ACGTacgt", "TGCAtgca")
_R = 1.987e-3  # kcal/mol/K


def _complement(seq: str) -> str:
    return seq.translate(_COMPLEMENT)


def _reverse_complement(seq: str) -> str:
    return _complement(seq)[::-1]


def _nn_dg(seq: str, temp_c: float = 37.0) -> float:
    """nearest-neighbor 모델로 이중가닥 ΔG (kcal/mol) 계산.

    seq는 5'→3' 단일가닥 서열. 자신의 역상보 서열과 결합하는 경우를 가정.
    """
    seq = seq.upper()
    T = temp_c + 273.15
    dH = 0.0
    dS = 0.0

    for i in range(len(seq) - 1):
        dinuc = seq[i:i+2]
        rc_dinuc = _reverse_complement(dinuc)
        key = f"{dinuc}/{rc_dinuc}"
        if key in _NN_PARAMS:
            h, s = _NN_PARAMS[key]
            dH += h
            dS += s
        else:
            # 파라미터 없으면 평균값 사용
            dH += -8.0
            dS += -21.0

    # 말단 패널티
    for end_base in (seq[0], seq[-1]):
        if end_base in "AT":
            dH += _INIT_AT[0]
            dS += _INIT_AT[1]
        else:
            dH += _INIT_GC[0]
            dS += _INIT_GC[1]

    dG = dH - T * (dS / 1000.0)
    return round(dG, 2)


def _find_hairpin(seq: str, min_bp: int = 4, min_loop: int = 3) -> tuple[float, int]:
    """hairpin 구조의 최소 ΔG와 stem 길이를 반환.

    Args:
        seq: 프라이머 서열 (5'→3')
        min_bp: 최소 stem 염기쌍 수
        min_loop: 최소 루프 크기

    Returns:
        (최소_dG, 최대_stem_length) 튜플
    """
    seq = seq.upper()
    n = len(seq)
    best_dg = 0.0
    best_stem = 0

    for stem_len in range(min_bp, n // 2 + 1):
        for i in range(n - stem_len * 2 - min_loop + 1):
            stem5 = seq[i:i + stem_len]
            # 루프 이후 위치
            for loop_len in range(min_loop, n - i - stem_len * 2 + 1):
                j = i + stem_len + loop_len
                if j + stem_len > n:
                    break
                stem3 = seq[j:j + stem_len]
                # stem3은 stem5의 역상보와 비교
                rc_stem5 = _reverse_complement(stem5)
                if stem3 == rc_stem5:
                    dg = _nn_dg(stem5)
                    if dg < best_dg:
                        best_dg = dg
                        best_stem = stem_len

    return best_dg, best_stem


def _find_homodimer(seq: str, min_bp: int = 6) -> tuple[float, int]:
    """homodimer 상보 결합의 최소 ΔG와 최대 상보 길이를 반환.

    두 동일 프라이머 사이의 3' 말단 상보성을 중심으로 검사.
    """
    seq = seq.upper()
    n = len(seq)
    rc_seq = _reverse_complement(seq)
    best_dg = 0.0
    best_bp = 0

    # 슬라이딩 윈도우로 상보 영역 탐색
    for window in range(min_bp, n + 1):
        for i in range(n - window + 1):
            subseq = seq[i:i + window]
            rc_sub = _reverse_complement(subseq)
            # rc_sub가 원래 서열에 있으면 homodimer 가능
            if rc_sub in seq:
                dg = _nn_dg(subseq)
                if dg < best_dg:
                    best_dg = dg
                    best_bp = window

    return best_dg, best_bp


def check_primer(
    seq: str,
    threshold_hairpin_dg: float = -2.0,
    threshold_homodimer_bp: int = 6,
    temp_c: float = 37.0,
) -> dict:
    """단일 프라이머의 hairpin 및 homodimer 구조를 검사한다.

    Args:
        seq: 프라이머 서열 (5'→3', ACGT only)
        threshold_hairpin_dg: hairpin FAIL 기준 ΔG (kcal/mol), 기본값 -2.0
        threshold_homodimer_bp: homodimer FAIL 기준 최소 bp 수, 기본값 6
        temp_c: 계산 온도 (°C), 기본값 37.0

    Returns:
        {"seq", "hairpin_dG", "homodimer_dG", "hairpin_pass", "homodimer_pass"}
    """
    seq = seq.strip().upper()
    invalid = set(seq) - set("ACGT")
    if invalid:
        return {
            "seq": seq,
            "hairpin_dG": None,
            "homodimer_dG": None,
            "hairpin_pass": False,
            "homodimer_pass": False,
            "notes": f"유효하지 않은 염기: {invalid}",
        }

    hairpin_dg, hairpin_stem = _find_hairpin(seq)
    homodimer_dg, homodimer_bp = _find_homodimer(seq, min_bp=threshold_homodimer_bp)

    # hairpin FAIL: ≥4bp stem AND ΔG < threshold
    hairpin_pass = not (hairpin_stem >= 4 and hairpin_dg < threshold_hairpin_dg)
    # homodimer FAIL: ≥min_bp 상보
    homodimer_pass = homodimer_bp < threshold_homodimer_bp

    return {
        "seq": seq,
        "hairpin_dG": hairpin_dg,
        "homodimer_dG": homodimer_dg,
        "hairpin_pass": hairpin_pass,
        "homodimer_pass": homodimer_pass,
    }


def check_primers(
    seqs: list[str],
    threshold_hairpin_dg: float = -2.0,
    threshold_homodimer_bp: int = 6,
    temp_c: float = 37.0,
) -> list[dict]:
    """여러 프라이머를 일괄 검사한다."""
    return [
        check_primer(seq, threshold_hairpin_dg, threshold_homodimer_bp, temp_c)
        for seq in seqs
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="프라이머 hairpin/homodimer 구조를 nearest-neighbor 모델로 검사한다."
    )
    parser.add_argument(
        "sequences", nargs="*", default=[],
        help="프라이머 서열 (직접 입력, 공백 구분)"
    )
    parser.add_argument(
        "--file", "-f", default=None,
        help="프라이머 JSON 파일 (문자열 배열 또는 [{seq:...}] 배열)"
    )
    parser.add_argument(
        "--threshold-hairpin", type=float, default=-2.0, metavar="DG",
        help="hairpin FAIL 기준 ΔG kcal/mol (기본값: -2.0)"
    )
    parser.add_argument(
        "--threshold-homodimer", type=int, default=6, metavar="BP",
        help="homodimer FAIL 기준 최소 bp 수 (기본값: 6)"
    )
    parser.add_argument(
        "--temp", type=float, default=37.0, metavar="C",
        help="계산 온도 °C (기본값: 37.0)"
    )
    parser.add_argument("--output", "-o", default=None, help="출력 JSON 파일 경로")
    args = parser.parse_args()

    if not args.sequences and not args.file:
        parser.error("서열을 직접 입력하거나 --file을 지정해야 합니다.")
    if args.sequences and args.file:
        parser.error("서열 직접 입력과 --file은 동시에 사용할 수 없습니다.")

    if args.file:
        raw = json.loads(Path(args.file).read_text(encoding="utf-8"))
        if isinstance(raw, list):
            seqs = [
                item["seq"] if isinstance(item, dict) else str(item)
                for item in raw
            ]
        else:
            parser.error("JSON 파일은 문자열 배열 또는 [{seq:...}] 형태여야 합니다.")
    else:
        seqs = args.sequences

    results = check_primers(
        seqs,
        threshold_hairpin_dg=args.threshold_hairpin,
        threshold_homodimer_bp=args.threshold_homodimer,
        temp_c=args.temp,
    )

    output_json = json.dumps(results, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
        print(f"{len(results)}개 프라이머 검사 완료 → {args.output}", file=sys.stderr)
    else:
        print(output_json)

    pass_all = sum(1 for r in results if r.get("hairpin_pass") and r.get("homodimer_pass"))
    print(
        f"\n요약: 전체 {len(results)}개 중 {pass_all}개 통과 "
        f"(hairpin+homodimer 모두 통과)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
