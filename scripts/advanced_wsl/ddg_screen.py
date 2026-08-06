#!/usr/bin/env python3
"""Rosetta ddG 배치 스캐너 - PyRosetta ddG_monomer으로 단백질 변이체 안정성 스크리닝.

사용법:
    python ddg_screen.py --pdb structure.pdb --variants variants.csv
    python ddg_screen.py --pdb structure.pdb --variants variants.csv --threshold 2.0 --output results.csv

임포트:
    from ddg_screen import screen_variants
    results = screen_variants("structure.pdb", [{"variant": "G134A", "chain": "A"}])

참고:
    - WSL Ubuntu의 conda env 'pyrosetta'에서 실행됨
    - Windows에서는 wsl subprocess를 통해 자동 호출
    - variants.csv 필수 컬럼: variant (예: G134A), chain (기본값: A)
"""
import argparse
import csv
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

THRESHOLD_DEFAULT = 2.0

# PyRosetta를 직접 실행할 때 쓰는 내부 스크립트 (WSL에서 실행)
_PYROSETTA_INNER = """
import sys, json, re, os

try:
    import pyrosetta
    from pyrosetta.toolbox import cleanATOM
except ImportError as e:
    print(json.dumps({"error": f"PyRosetta import 실패: {e}"}))
    sys.exit(1)

def parse_variant(variant_str):
    m = re.match(r'^([A-Z])([0-9]+)([A-Z])$', variant_str.strip())
    if not m:
        return None, None, None
    return m.group(1), int(m.group(2)), m.group(3)

def calc_ddg(pdb_path, variant_str, chain, threshold):
    wt_aa, pos, mut_aa = parse_variant(variant_str)
    if wt_aa is None:
        return {"variant": variant_str, "ddG_fold": None, "ddG_bind": None,
                "pass_fail": "FAIL", "notes": f"잘못된 변이 표기: {variant_str}"}

    pyrosetta.init("-mute all")
    pose = pyrosetta.pose_from_pdb(pdb_path)

    scorefxn = pyrosetta.get_fa_scorefxn()

    # 체인에서 잔기 번호 찾기
    pdb_info = pose.pdb_info()
    res_num = None
    for i in range(1, pose.total_residue() + 1):
        if pdb_info.chain(i) == chain and pdb_info.number(i) == pos:
            res_num = i
            break

    if res_num is None:
        return {"variant": variant_str, "ddG_fold": None, "ddG_bind": None,
                "pass_fail": "FAIL", "notes": f"잔기를 찾을 수 없음: {chain}{pos}"}

    # WT 에너지
    score_wt = scorefxn(pose)

    # 변이 적용 (PackMutants 방식)
    mutant_pose = pose.clone()
    mutant = pyrosetta.rosetta.protocols.simple_moves.MutateResidue()
    mutant.set_res_selector(
        pyrosetta.rosetta.core.select.residue_selector.ResidueIndexSelector(str(res_num))
    )
    mutant.set_res_name(mut_aa)
    mutant.apply(mutant_pose)

    # 측쇄 repack
    task_factory = pyrosetta.rosetta.core.pack.task.TaskFactory()
    task_factory.push_back(pyrosetta.rosetta.core.pack.task.operation.RestrictToRepacking())
    packer = pyrosetta.rosetta.protocols.minimization_packing.PackRotamersMover(scorefxn)
    packer.task_factory(task_factory)
    packer.apply(mutant_pose)

    score_mut = scorefxn(mutant_pose)
    ddg = score_mut - score_wt

    pass_fail = "PASS" if ddg < threshold else "FAIL"
    return {"variant": variant_str, "ddG_fold": round(ddg, 3), "ddG_bind": None,
            "pass_fail": pass_fail, "notes": ""}

import sys, json
args = json.loads(sys.argv[1])
pdb_path = args["pdb_path"]
variants = args["variants"]
threshold = args["threshold"]

results = []
for v in variants:
    try:
        r = calc_ddg(pdb_path, v["variant"], v.get("chain", "A"), threshold)
    except Exception as e:
        r = {"variant": v["variant"], "ddG_fold": None, "ddG_bind": None,
             "pass_fail": "FAIL", "notes": str(e)}
    results.append(r)

print(json.dumps(results))
"""


def _is_windows() -> bool:
    return platform.system() == "Windows"


def _wsl_path(windows_path: str) -> str:
    """Windows 경로를 WSL 경로로 변환."""
    p = Path(windows_path).resolve()
    drive = p.drive.rstrip(":").lower()
    rest = str(p)[len(p.drive):].replace("\\", "/")
    return f"/mnt/{drive}{rest}"


def screen_variants(
    pdb_path: str,
    variants: list[dict],
    threshold: float = THRESHOLD_DEFAULT,
) -> list[dict]:
    """단백질 변이체 ddG 안정성 스크리닝.

    Args:
        pdb_path: 입력 PDB 파일 경로
        variants: [{"variant": "G134A", "chain": "A"}, ...] 형태의 딕셔너리 목록
        threshold: PASS 기준 ddG 임계값 (REU), 기본값 2.0

    Returns:
        [{"variant", "ddG_fold", "ddG_bind", "pass_fail", "notes"}, ...] 목록
    """
    pdb_file = Path(pdb_path)
    if not pdb_file.exists():
        raise FileNotFoundError(f"PDB 파일을 찾을 수 없습니다: {pdb_path}")

    # 변이 표기 검증
    import re
    for v in variants:
        vname = v.get("variant", "")
        if not re.match(r'^[A-Z]\d+[A-Z]$', vname.strip()):
            raise ValueError(f"잘못된 변이 표기 (예: G134A 형식이어야 함): {vname!r}")

    payload = {
        "pdb_path": str(pdb_file.resolve()),
        "variants": variants,
        "threshold": threshold,
    }

    if _is_windows():
        # WSL subprocess를 통해 PyRosetta 실행
        wsl_pdb = _wsl_path(str(pdb_file.resolve()))
        payload["pdb_path"] = wsl_pdb

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(_PYROSETTA_INNER)
            tmp_script = tf.name

        wsl_script = _wsl_path(tmp_script)
        cmd = [
            "wsl", "-d", "Ubuntu", "--",
            "conda", "run", "-n", "pyrosetta", "--no-capture-output",
            "python", wsl_script, json.dumps(payload),
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"WSL PyRosetta 실행 실패:\n{result.stderr}"
                )
            output = result.stdout.strip()
            # JSON 라인만 추출 (마지막 JSON 배열)
            lines = [l for l in output.splitlines() if l.strip().startswith("[")]
            if not lines:
                raise RuntimeError(f"PyRosetta 출력에서 JSON을 찾을 수 없음:\n{output}")
            return json.loads(lines[-1])
        finally:
            Path(tmp_script).unlink(missing_ok=True)

    else:
        # WSL/Linux 환경: PyRosetta 직접 실행
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(_PYROSETTA_INNER)
            tmp_script = tf.name
        try:
            result = subprocess.run(
                ["python", tmp_script, json.dumps(payload)],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode != 0:
                raise RuntimeError(f"PyRosetta 실행 실패:\n{result.stderr}")
            lines = [l for l in result.stdout.splitlines() if l.strip().startswith("[")]
            if not lines:
                raise RuntimeError(f"PyRosetta 출력에서 JSON을 찾을 수 없음:\n{result.stdout}")
            return json.loads(lines[-1])
        finally:
            Path(tmp_script).unlink(missing_ok=True)


def _read_variants_csv(path: str) -> list[dict]:
    """variants CSV를 읽어 딕셔너리 목록으로 반환."""
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if "variant" not in row:
                raise ValueError("CSV에 'variant' 컬럼이 없습니다.")
            rows.append({
                "variant": row["variant"].strip(),
                "chain": row.get("chain", "A").strip() or "A",
            })
    return rows


def _write_results_csv(results: list[dict], path: str) -> None:
    fieldnames = ["variant", "ddG_fold", "ddG_bind", "pass_fail", "notes"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rosetta ddG_monomer으로 단백질 변이체 안정성을 배치 스크리닝한다."
    )
    parser.add_argument("--pdb", required=True, help="입력 PDB 구조 파일 경로")
    parser.add_argument("--variants", required=True, help="변이체 CSV 파일 (컬럼: variant, chain)")
    parser.add_argument(
        "--threshold", type=float, default=THRESHOLD_DEFAULT,
        help=f"PASS 기준 ddG 임계값 REU (기본값: {THRESHOLD_DEFAULT})"
    )
    parser.add_argument("--output", "-o", default=None, help="결과 CSV 출력 경로")
    args = parser.parse_args()

    variants = _read_variants_csv(args.variants)
    print(f"{len(variants)}개 변이체 스크리닝 시작 (임계값: {args.threshold} REU)...", file=sys.stderr)

    results = screen_variants(args.pdb, variants, threshold=args.threshold)

    pass_count = sum(1 for r in results if r.get("pass_fail") == "PASS")
    fail_count = len(results) - pass_count
    print(f"완료: PASS {pass_count}개, FAIL {fail_count}개", file=sys.stderr)

    output_path = args.output or "ddg_results.csv"
    _write_results_csv(results, output_path)
    print(f"결과를 {output_path}에 저장했습니다.", file=sys.stderr)


if __name__ == "__main__":
    main()
