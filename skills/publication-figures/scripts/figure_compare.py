#!/usr/bin/env python3
"""figure_compare.py — quantify design similarity between a reconstructed figure
and a reference image (e.g. the version embedded in a manuscript).

Part of the publication-figures skill, Route 5 (Figure Reconstruction & Verification).

Computes, per figure pair:
  - SSIM   : grayscale structural similarity index (skimage), data_range=1.0
  - MAE    : normalized mean absolute pixel error (0-1)
  - verdict: high / good / moderate / low band

This measures DESIGN similarity only. It does NOT verify data correctness — a figure
can score SSIM 0.99 and still plot the wrong numbers. Always pair this with an
independent data-integrity check (re-read the source data, assert values match).

3D surface plots legitimately score low (viewing angle / render engine differ); a low
score there is not by itself a defect. For 2D line/scatter/bar plots a low score
means a genuine mismatch to fix.

Vector references (EMF/WMF/SVG/EPS/PDF) cannot be rasterized by this script and are
flagged explicitly. On this WSL setup neither libreoffice/inkscape nor ImageMagick
is installed, so the practical fallback is the data-integrity check, or extracting
the chart from Word/PowerPoint on the Windows side ("Save as Picture") and pointing
the script at that PNG.

Usage:
  # one pair
  python figure_compare.py recon.png reference.jpeg

  # batch: scan a figures dir, pair figure.png with embedded_reference.{jpeg,png}
  python figure_compare.py --batch /path/to/figures

  # batch with machine-readable summary
  python figure_compare.py --batch /path/to/figures --json out.json

Requires: numpy, pillow, scikit-image.  (`pip install scikit-image`)
"""
from __future__ import annotations
import sys, os, argparse, io, json

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

import numpy as np
from PIL import Image, UnidentifiedImageError
from skimage.metrics import structural_similarity as ssim

BANDS = [(0.85, "high"), (0.70, "good"), (0.55, "moderate"), (0.0, "low")]
VECTOR_EXTS = {".emf", ".wmf", ".svg", ".eps", ".pdf"}


def verdict(s: float) -> str:
    for thr, name in BANDS:
        if s >= thr:
            return name
    return "low"


def _open_raster(path: str) -> Image.Image:
    """Open path as a raster image. Raises ValueError with a clear message
    for vector formats (EMF/WMF/SVG/EPS/PDF) that we can't rasterize here."""
    ext = os.path.splitext(path)[1].lower()
    if ext in VECTOR_EXTS:
        raise ValueError(
            f"vector format {ext!r}: cannot rasterize for SSIM. "
            f"Use the data-integrity check instead, or extract the chart on the "
            f"Windows side (Word/PowerPoint → Save as Picture) and re-point to "
            f"that PNG. WSL has no working .emf rasterizer by default."
        )
    try:
        im = Image.open(path)
    except UnidentifiedImageError as e:
        raise ValueError(f"unrecognized image format for {path!r} ({e})") from e
    # palette-with-transparency PNGs emit a PIL UserWarning when going straight to L;
    # route through RGBA to silence it without changing pixel values.
    if im.mode == "P":
        im = im.convert("RGBA")
    return im


def _gray(im: Image.Image, size: tuple[int, int]) -> np.ndarray:
    return np.asarray(im.convert("L").resize(size, Image.LANCZOS),
                      dtype=np.float64) / 255.0


def compare(recon: str, ref: str) -> dict:
    """Compare two image files. Returns dict with ssim, mae, verdict, size, ar_*.
    Raises ValueError for vector / unrecognized inputs (callers should catch)."""
    ri = _open_raster(recon)
    ei = _open_raster(ref)
    # common width = smaller of the two, capped at 1000 px; keep recon aspect ratio.
    # 1000-px cap controls runtime and SSIM noise; for panorama refs (>4000 px wide)
    # this loses some text detail — see references/figure_verification.md §3.
    w = min(ri.width, ei.width, 1000)
    h = max(1, int(round(w * ri.height / ri.width)))
    # skimage SSIM needs a window (default 7) <= min(h,w); guard tiny images.
    if min(h, w) < 7:
        raise ValueError(
            f"images too small to score: resized to {w}x{h}, need >=7 px each side. "
            f"Save figures at publication size (>=300 px wide minimum)."
        )
    size = (w, h)
    g_recon, g_ref = _gray(ri, size), _gray(ei, size)
    s = float(ssim(g_recon, g_ref, data_range=1.0))
    mae = float(np.mean(np.abs(g_recon - g_ref)))
    ar_recon = ri.width / ri.height
    ar_ref = ei.width / ei.height
    ar_ratio = max(ar_recon, ar_ref) / min(ar_recon, ar_ref)
    return {
        "ssim": s, "mae": mae, "verdict": verdict(s), "size": size,
        "src_recon": (ri.width, ri.height), "src_ref": (ei.width, ei.height),
        "ar_recon": ar_recon, "ar_ref": ar_ref, "ar_ratio": ar_ratio,
    }


def find_reference(folder: str) -> str | None:
    """Locate embedded_reference.{jpeg,jpg,png} in a unit folder."""
    for ext in ("jpeg", "jpg", "png"):
        p = os.path.join(folder, f"embedded_reference.{ext}")
        if os.path.exists(p):
            return p
    return None


def batch(figdir: str, json_out: str | None = None) -> int:
    """Scan figdir for unit folders, compare figure.png vs embedded_reference."""
    units = sorted(
        d for d in os.listdir(figdir)
        if os.path.isdir(os.path.join(figdir, d)) and d.startswith("F_")
    )
    print(f"{'Figure':<28}{'SSIM':>8}{'MAE':>9}  verdict")
    print("-" * 62)
    scores = []
    rows = []
    for u in units:
        folder = os.path.join(figdir, u)
        recon = os.path.join(folder, "figure.png")
        ref = find_reference(folder)
        if not os.path.exists(recon):
            print(f"{u:<28}{'—':>8}{'—':>9}  no figure.png (vector/photo art?)")
            rows.append({"figure": u, "status": "no_recon"})
            continue
        if ref is None:
            print(f"{u:<28}{'—':>8}{'—':>9}  EMF/no raster ref — use data-integrity check")
            rows.append({"figure": u, "status": "vector_ref_only"})
            continue
        try:
            r = compare(recon, ref)
        except ValueError as e:
            print(f"{u:<28}{'—':>8}{'—':>9}  skip — {e}")
            rows.append({"figure": u, "status": "skip", "reason": str(e)})
            continue
        scores.append(r["ssim"])
        ar_flag = "  AR!" if r["ar_ratio"] > 1.10 else ""
        print(f"{u:<28}{r['ssim']:>8.3f}{r['mae']:>9.4f}  {r['verdict']}{ar_flag}")
        rows.append({
            "figure": u, "status": "ok",
            "ssim": r["ssim"], "mae": r["mae"], "verdict": r["verdict"],
            "ar_ratio": r["ar_ratio"], "ar_warn": r["ar_ratio"] > 1.10,
            "src_recon": list(r["src_recon"]), "src_ref": list(r["src_ref"]),
        })
    print("-" * 62)
    summary = {"figdir": figdir, "n_scored": len(scores), "rows": rows}
    if scores:
        summary["mean_ssim"] = float(np.mean(scores))
        moderate = [s for s in scores if s < 0.70]
        summary["n_below_0.70"] = len(moderate)
        print(f"{'mean SSIM':<28}{np.mean(scores):>8.3f}    (n={len(scores)})")
        if moderate:
            print(f"\n{len(moderate)} figure(s) below 0.70 — inspect for design drift "
                  f"(broken axis / spines / panel labels / legend overlap).")
    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"\nJSON summary → {json_out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recon", nargs="?", help="reconstructed figure image")
    ap.add_argument("ref", nargs="?", help="reference image")
    ap.add_argument("--batch", metavar="FIGDIR",
                    help="scan a figures dir of F_* unit folders")
    ap.add_argument("--json", metavar="PATH",
                    help="write machine-readable summary JSON (with --batch)")
    args = ap.parse_args()

    if args.batch:
        return batch(args.batch, args.json)
    if args.recon and args.ref:
        try:
            r = compare(args.recon, args.ref)
        except ValueError as e:
            print(f"! cannot compare: {e}", file=sys.stderr)
            return 2
        if args.json:
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump({
                    "recon": args.recon, "ref": args.ref,
                    "ssim": r["ssim"], "mae": r["mae"], "verdict": r["verdict"],
                    "ar_ratio": r["ar_ratio"], "ar_warn": r["ar_ratio"] > 1.10,
                    "src_recon": list(r["src_recon"]), "src_ref": list(r["src_ref"]),
                }, f, indent=2, ensure_ascii=False)
        print(f"SSIM    {r['ssim']:.4f}  ({r['verdict']})")
        print(f"MAE     {r['mae']:.4f}")
        print(f"compared at {r['size'][0]}x{r['size'][1]} px grayscale")
        print(f"src     recon {r['src_recon'][0]}x{r['src_recon'][1]} "
              f"(AR {r['ar_recon']:.2f})  |  "
              f"ref {r['src_ref'][0]}x{r['src_ref'][1]} (AR {r['ar_ref']:.2f})")
        if r["ar_ratio"] > 1.10:
            print(f"\n! aspect-ratio mismatch ({r['ar_ratio']:.2f}x) — the ref was "
                  f"resized to recon's AR. Low SSIM may reflect stretch, not real "
                  f"design difference. Re-save recon with the reference's figsize.")
        if r["ssim"] < 0.55:
            print("\n! low — for a 2D plot this is a real mismatch; for a 3D surface "
                  "it may just be viewing angle. Confirm via data integrity.")
        elif r["ssim"] < 0.70:
            print("\n~ moderate — inspect for design drift (broken axis, spine style, "
                  "panel-label size, legend overlap).")
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
