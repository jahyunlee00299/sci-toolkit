#!/usr/bin/env python3
"""Rosetta ddG batch scanner - screens protein variant stability with PyRosetta's ddG_monomer.

Usage:
    python ddg_screen.py --pdb structure.pdb --variants variants.csv
    python ddg_screen.py --pdb structure.pdb --variants variants.csv --threshold 2.0 --output results.csv

Import:
    from ddg_screen import screen_variants
    results = screen_variants("structure.pdb", [{"variant": "G134A", "chain": "A"}])

Notes:
    - Runs in the 'pyrosetta' conda env under WSL Ubuntu
    - On Windows, invoked automatically via a wsl subprocess
    - Required variants.csv columns: variant (e.g. G134A), chain (default: A)
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

# Inner script used to run PyRosetta directly (executed inside WSL)
_PYROSETTA_INNER = """
import sys, json, re, os

try:
    import pyrosetta
    from pyrosetta.toolbox import cleanATOM
except ImportError as e:
    print(json.dumps({"error": f"PyRosetta import failed: {e}"}))
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
                "pass_fail": "FAIL", "notes": f"Invalid variant notation: {variant_str}"}

    pyrosetta.init("-mute all")
    pose = pyrosetta.pose_from_pdb(pdb_path)

    scorefxn = pyrosetta.get_fa_scorefxn()

    # Locate the residue number within the chain
    pdb_info = pose.pdb_info()
    res_num = None
    for i in range(1, pose.total_residue() + 1):
        if pdb_info.chain(i) == chain and pdb_info.number(i) == pos:
            res_num = i
            break

    if res_num is None:
        return {"variant": variant_str, "ddG_fold": None, "ddG_bind": None,
                "pass_fail": "FAIL", "notes": f"Residue not found: {chain}{pos}"}

    # WT energy
    score_wt = scorefxn(pose)

    # Apply the mutation (PackMutants style)
    mutant_pose = pose.clone()
    mutant = pyrosetta.rosetta.protocols.simple_moves.MutateResidue()
    mutant.set_res_selector(
        pyrosetta.rosetta.core.select.residue_selector.ResidueIndexSelector(str(res_num))
    )
    mutant.set_res_name(mut_aa)
    mutant.apply(mutant_pose)

    # Side-chain repack
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
    """Convert a Windows path to a WSL path."""
    p = Path(windows_path).resolve()
    drive = p.drive.rstrip(":").lower()
    rest = str(p)[len(p.drive):].replace("\\", "/")
    return f"/mnt/{drive}{rest}"


def screen_variants(
    pdb_path: str,
    variants: list[dict],
    threshold: float = THRESHOLD_DEFAULT,
) -> list[dict]:
    """Screen protein variant ddG stability.

    Args:
        pdb_path: path to the input PDB file
        variants: list of dicts shaped like [{"variant": "G134A", "chain": "A"}, ...]
        threshold: ddG threshold (REU) for a PASS, default 2.0

    Returns:
        a list of [{"variant", "ddG_fold", "ddG_bind", "pass_fail", "notes"}, ...]
    """
    pdb_file = Path(pdb_path)
    if not pdb_file.exists():
        raise FileNotFoundError(f"PDB file not found: {pdb_path}")

    # Validate variant notation
    import re
    for v in variants:
        vname = v.get("variant", "")
        if not re.match(r'^[A-Z]\d+[A-Z]$', vname.strip()):
            raise ValueError(f"Invalid variant notation (must be e.g. G134A format): {vname!r}")

    payload = {
        "pdb_path": str(pdb_file.resolve()),
        "variants": variants,
        "threshold": threshold,
    }

    if _is_windows():
        # Run PyRosetta via a WSL subprocess
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
                    f"WSL PyRosetta run failed:\n{result.stderr}"
                )
            output = result.stdout.strip()
            # Extract only JSON lines (the last JSON array)
            lines = [l for l in output.splitlines() if l.strip().startswith("[")]
            if not lines:
                raise RuntimeError(f"No JSON found in PyRosetta output:\n{output}")
            return json.loads(lines[-1])
        finally:
            Path(tmp_script).unlink(missing_ok=True)

    else:
        # WSL/Linux environment: run PyRosetta directly
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
                raise RuntimeError(f"PyRosetta run failed:\n{result.stderr}")
            lines = [l for l in result.stdout.splitlines() if l.strip().startswith("[")]
            if not lines:
                raise RuntimeError(f"No JSON found in PyRosetta output:\n{result.stdout}")
            return json.loads(lines[-1])
        finally:
            Path(tmp_script).unlink(missing_ok=True)


def _read_variants_csv(path: str) -> list[dict]:
    """Read the variants CSV and return a list of dicts."""
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if "variant" not in row:
                raise ValueError("CSV is missing the 'variant' column.")
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
        description="Batch-screen protein variant stability with Rosetta ddG_monomer."
    )
    parser.add_argument("--pdb", required=True, help="path to the input PDB structure file")
    parser.add_argument("--variants", required=True, help="variants CSV file (columns: variant, chain)")
    parser.add_argument(
        "--threshold", type=float, default=THRESHOLD_DEFAULT,
        help=f"ddG threshold REU for a PASS (default: {THRESHOLD_DEFAULT})"
    )
    parser.add_argument("--output", "-o", default=None, help="output path for the results CSV")
    args = parser.parse_args()

    variants = _read_variants_csv(args.variants)
    print(f"Screening {len(variants)} variant(s) (threshold: {args.threshold} REU)...", file=sys.stderr)

    results = screen_variants(args.pdb, variants, threshold=args.threshold)

    pass_count = sum(1 for r in results if r.get("pass_fail") == "PASS")
    fail_count = len(results) - pass_count
    print(f"Done: PASS {pass_count}, FAIL {fail_count}", file=sys.stderr)

    output_path = args.output or "ddg_results.csv"
    _write_results_csv(results, output_path)
    print(f"Results saved to {output_path}.", file=sys.stderr)


if __name__ == "__main__":
    main()
