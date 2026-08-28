#!/usr/bin/env python3
"""HPLC chromatography data parser.

Ports the peak detection/integration algorithm to stdlib-only:
  - .ch binary: decodes Agilent ChemStation format 130/131 delta-compression
  - text formats: ChemStation tab export .txt, header CSV, .arw
  - peak detection: automatic detection based on MAD noise + prominence (valley boundary)
  - peak integration: valley drop-line baseline + trapezoid rule

Usage:
    python hplc_parser.py data.ch [--output parsed.csv] [--peaks]
    python hplc_parser.py *.txt --output combined.csv --peaks
    python hplc_parser.py data.ch --json

Import:
    from hplc_parser import parse_hplc
    result = parse_hplc("vwd1A.ch")
    # result: {
    #   'chromatogram': [{'time': float, 'signal': float}, ...],
    #   'peaks':        [{'peak_number', 'retention_time', 'rt_start', 'rt_end',
    #                     'height', 'area', 'width', 'width_fwhm', 'area_percent'}, ...],
    #   'metadata':     {...},
    #   'sample_name':  str,
    #   'file_source':  str,
    # }
"""

# Windows' default console is cp949, which dies on Korean/symbol output.
# Force UTF-8. Use reconfigure(): wrapping the stream in a TextIOWrapper
# instead takes ownership of the underlying stream, so once this module is
# imported, the caller's stdout gets closed when that wrapper is later
# garbage-collected (measured).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
import argparse
import csv
import re
import struct
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# .ch binary parser (ChemStation binary parser — no numpy)
# ---------------------------------------------------------------------------

def _read_pascal_string(raw: bytes, offset: int) -> str:
    """Read a Pascal string (length byte + chars)."""
    length = raw[offset]
    if length == 0 or length > 64:
        return ""
    return raw[offset + 1: offset + 1 + length].decode("ascii", errors="ignore")


def _decompress_segments(raw: bytes, data_start: int) -> list:
    """
    Decode Agilent format-130 delta-compression.

    Segment structure: (label:u8, count:u8) followed by count int16 values.
      - int16 == -32768 (0x8000): the next 4 bytes are a new absolute int32 value
      - otherwise: accumulate the delta onto the previous value
    label==0, count==0 -> end of data
    """
    values = []
    current = 0
    pos = data_start

    while pos + 1 < len(raw):
        label = raw[pos]
        count = raw[pos + 1]
        pos += 2

        if label == 0 and count == 0:
            break

        for _ in range(count):
            if pos + 2 > len(raw):
                break
            v16 = struct.unpack(">h", raw[pos: pos + 2])[0]
            pos += 2

            if v16 == -32768:  # absolute marker
                if pos + 4 > len(raw):
                    break
                current = struct.unpack(">i", raw[pos: pos + 4])[0]
                pos += 4
            else:
                current += v16

            values.append(current)

    return values


def _parse_ch_binary(filepath: str) -> dict:
    """Parse an Agilent .ch binary file (format 130/131)."""
    raw = Path(filepath).read_bytes()

    # Version check (offset 0: Pascal string "130" or "131")
    version = _read_pascal_string(raw, 0)
    if version not in ("130", "131"):
        raise ValueError(
            f"Unsupported ChemStation version: '{version}' "
            f"(first 4 bytes: {raw[:4].hex()})"
        )

    # Time range (offset 0x11A, 0x11E: big-endian uint32 ms)
    start_ms = struct.unpack(">I", raw[0x11A:0x11E])[0]
    end_ms   = struct.unpack(">I", raw[0x11E:0x122])[0]
    start_time = start_ms / 60000.0
    end_time   = end_ms   / 60000.0

    # Y-scale factor (offset 0x127C: big-endian double)
    y_scale = struct.unpack(">d", raw[0x127C:0x1284])[0]
    if y_scale == 0.0:
        y_scale = 1.0

    # Data block (offset 0x1800)
    raw_values = _decompress_segments(raw, 0x1800)
    n = len(raw_values)
    if n == 0:
        raise ValueError("No data points found.")

    signal_list = [v * y_scale for v in raw_values]

    if end_time <= start_time:
        end_time = n / 100.0
    step = (end_time - start_time) / (n - 1) if n > 1 else 0.0
    time_list = [start_time + i * step for i in range(n)]

    # Sample name (offset 0x18: Pascal string)
    sample_name = _read_pascal_string(raw, 0x18) or Path(filepath).stem

    metadata = {
        "version": version,
        "start_time_min": start_time,
        "end_time_min": end_time,
        "num_points": n,
        "y_scale": y_scale,
    }

    return {
        "time_list":   time_list,
        "signal_list": signal_list,
        "metadata":    metadata,
        "sample_name": sample_name,
        "file_source": str(filepath),
    }


# ---------------------------------------------------------------------------
# Text-format parser (ChemStation tab, CSV with header, .arw)
# ---------------------------------------------------------------------------

def _detect_text_format(lines: list) -> str:
    for line in lines[:20]:
        s = line.strip()
        if re.match(r"^\[.*\]$", s) or s.lower().startswith("sample name"):
            return "arw"
    for line in lines[:30]:
        if "\t" in line and not line.startswith("#"):
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                try:
                    float(parts[0])
                    return "chemstation_tab"
                except ValueError:
                    pass
    return "csv_header"


def _parse_arw(lines: list, filepath: str) -> dict:
    metadata, chromatogram = {}, []
    sample_name = Path(filepath).stem
    in_data = in_peak = False
    peak_header: list = []
    peaks_raw: list = []

    for line in lines:
        s = line.strip()
        if not s:
            continue
        if re.match(r"^\[.*\]$", s):
            sect = s.lower()
            in_data = "data" in sect
            in_peak = "peak" in sect
            peak_header = []
            continue
        if not in_data and not in_peak:
            if "\t" in s:
                k, _, v = s.partition("\t")
                metadata[k.strip()] = v.strip()
            elif "=" in s:
                k, _, v = s.partition("=")
                metadata[k.strip()] = v.strip()
            m = re.search(r"sample name\s*[=:\t]\s*(.+)", s, re.IGNORECASE)
            if m:
                sample_name = m.group(1).strip()
            continue
        if in_data:
            parts = re.split(r"[\t,]+", s)
            if len(parts) >= 2:
                try:
                    chromatogram.append((float(parts[0]), float(parts[1])))
                except ValueError:
                    pass
            continue
        if in_peak:
            parts = re.split(r"[\t,]+", s)
            if not peak_header:
                peak_header = [p.lower().strip() for p in parts]
            elif len(parts) >= len(peak_header):
                peaks_raw.append(dict(zip(peak_header, [p.strip() for p in parts])))

    return {
        "time_list":   [pt[0] for pt in chromatogram],
        "signal_list": [pt[1] for pt in chromatogram],
        "metadata":    metadata,
        "sample_name": sample_name,
        "file_source": str(filepath),
        "_peaks_raw":  peaks_raw,
    }


def _parse_chemstation_tab(lines: list, filepath: str) -> dict:
    metadata = {}
    chromatogram = []
    sample_name = Path(filepath).stem
    peaks_raw: list = []
    peak_header: list = []
    peak_mode = False

    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("#") or (not any(c.isdigit() for c in s[:5]) and ":" in s[:60]):
            m = re.match(r"#?\s*([^:]+):\s*(.+)", s.lstrip("#").strip())
            if m:
                k, v = m.group(1).strip(), m.group(2).strip()
                metadata[k] = v
                if "sample" in k.lower():
                    sample_name = v
            continue
        parts = s.split("\t")
        if any(kw in s.lower() for kw in ["peak", "ret.time", "retention"]) and not peak_mode:
            peak_mode = True
            peak_header = [p.lower().strip() for p in parts]
            continue
        if peak_mode and peak_header and len(parts) >= len(peak_header):
            try:
                int(parts[0])
                peaks_raw.append(dict(zip(peak_header, [p.strip() for p in parts])))
                continue
            except ValueError:
                peak_mode = False
        if len(parts) >= 2:
            try:
                chromatogram.append((float(parts[0]), float(parts[1])))
            except ValueError:
                pass

    return {
        "time_list":   [pt[0] for pt in chromatogram],
        "signal_list": [pt[1] for pt in chromatogram],
        "metadata":    metadata,
        "sample_name": sample_name,
        "file_source": str(filepath),
        "_peaks_raw":  peaks_raw,
    }


def _parse_csv_header(lines: list, filepath: str) -> dict:
    metadata = {}
    chromatogram = []
    sample_name = Path(filepath).stem
    peaks_raw: list = []
    peak_header: list = []
    col_time, col_signal = 0, 1
    data_start = 0

    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        parts = re.split(r"[,\t;]", s)
        try:
            float(parts[0])
            float(parts[1])
            data_start = i
            break
        except (ValueError, IndexError):
            lp = [p.lower().strip() for p in parts]
            for j, h in enumerate(lp):
                if h in ("time", "min", "minutes", "rt", "retention time"):
                    col_time = j
                if h in ("signal", "value", "mau", "absorbance", "intensity", "response"):
                    col_signal = j
            m = re.match(r"(.+?)[=:]\s*(.+)", s)
            if m:
                metadata[m.group(1).strip()] = m.group(2).strip()
                if "sample" in m.group(1).lower():
                    sample_name = m.group(2).strip()

    peak_mode = False
    for line in lines[data_start:]:
        s = line.strip()
        if not s:
            continue
        parts = re.split(r"[,\t;]", s)
        if any(kw in s.lower() for kw in ["peak #", "peak no", "ret.time", "area"]) and not peak_mode:
            peak_mode = True
            peak_header = [p.lower().strip() for p in parts]
            continue
        if peak_mode and peak_header and len(parts) >= len(peak_header):
            try:
                int(parts[0])
                peaks_raw.append(dict(zip(peak_header, [p.strip() for p in parts])))
                continue
            except ValueError:
                pass
        if len(parts) >= 2:
            try:
                chromatogram.append((float(parts[col_time]), float(parts[col_signal])))
            except (ValueError, IndexError):
                pass

    return {
        "time_list":   [pt[0] for pt in chromatogram],
        "signal_list": [pt[1] for pt in chromatogram],
        "metadata":    metadata,
        "sample_name": sample_name,
        "file_source": str(filepath),
        "_peaks_raw":  peaks_raw,
    }


# ---------------------------------------------------------------------------
# Peak detection + integration (prominence-based detection + trapezoid integration)
# ---------------------------------------------------------------------------

def _mad_noise(signal: list) -> float:
    """MAD-based noise estimate (from the derivative)."""
    if len(signal) < 2:
        return 1.0
    deriv = [signal[i + 1] - signal[i] for i in range(len(signal) - 1)]
    med_d = sorted(deriv)[len(deriv) // 2]
    abs_dev = sorted(abs(d - med_d) for d in deriv)
    mad = abs_dev[len(abs_dev) // 2]
    return max(mad * 1.4826, 1.0)


def _savgol_smooth(signal: list, window: int = 11) -> list:
    """Weighted moving-average smoothing (no scipy — parabolic kernel approximation)."""
    n = len(signal)
    wl = min(window, (n // 2) * 2 - 1)
    if wl < 5 or wl >= n:
        return list(signal)

    half = wl // 2
    # parabolic (Epanechnikov) kernel weight: 1 - (i/half)^2
    weights = [max(0.0, 1.0 - (abs(i) / (half + 1)) ** 2) for i in range(-half, half + 1)]
    total_w = sum(weights)
    weights = [w / total_w for w in weights]

    result = list(signal)
    for i in range(half, n - half):
        result[i] = sum(signal[i + j] * weights[j + half] for j in range(-half, half + 1))
    return result


def _find_peaks_prominence(signal: list,
                            min_prominence_factor: float = 0.01,
                            height_multiplier: float = 3.0,
                            min_distance: int = 5) -> list:
    """Detect peak indices based on prominence.

    Prominence-based detection logic.
    Returns: list of peak indices (ascending order)
    """
    n = len(signal)
    if n < 3:
        return []

    noise = _mad_noise(signal)
    sig_range = max(signal) - min(signal)
    min_prominence = sig_range * min_prominence_factor
    min_height = noise * height_multiplier

    # local-maximum candidates
    candidates = []
    for i in range(1, n - 1):
        if signal[i] >= signal[i - 1] and signal[i] >= signal[i + 1]:
            if signal[i] >= min_height:
                candidates.append(i)

    # min_distance filter (keeps taller peaks first)
    candidates.sort(key=lambda i: signal[i], reverse=True)
    selected = []
    for c in candidates:
        if all(abs(c - s) >= min_distance for s in selected):
            selected.append(c)
    selected.sort()

    # prominence filter
    result = []
    for idx in selected:
        left_min = signal[idx]
        for i in range(idx - 1, -1, -1):
            if signal[i] > signal[idx]:
                break
            left_min = min(left_min, signal[i])
        right_min = signal[idx]
        for i in range(idx + 1, n):
            if signal[i] > signal[idx]:
                break
            right_min = min(right_min, signal[i])
        prominence = signal[idx] - max(left_min, right_min)
        if prominence >= min_prominence:
            result.append(idx)

    return result


def _find_valley_boundary(signal: list, peak_idx: int,
                           threshold_ratio: float = 0.003) -> tuple:
    """
    Detect peak boundaries based on valley + threshold.
    Boundary search relative to the valley.

    Returns: (left_idx, right_idx)
    """
    n = len(signal)
    peak_max = signal[peak_idx]
    threshold = peak_max * threshold_ratio

    # left scan
    left_idx = peak_idx
    prev_val = peak_max
    for i in range(peak_idx - 1, -1, -1):
        cur_val = signal[i]
        if cur_val > prev_val and prev_val < peak_max * 0.5:
            left_idx = i + 1
            break
        if cur_val <= threshold:
            left_idx = i
            break
        prev_val = cur_val
        left_idx = i

    # right scan
    right_idx = peak_idx
    prev_val = peak_max
    for i in range(peak_idx + 1, n):
        cur_val = signal[i]
        if cur_val > prev_val and prev_val < peak_max * 0.5:
            right_idx = i - 1
            break
        if cur_val <= threshold:
            right_idx = i
            break
        prev_val = cur_val
        right_idx = i

    return left_idx, right_idx


def _trapezoid(y: list, x: list) -> float:
    """Trapezoid-rule integration (no numpy)."""
    if len(y) < 2:
        return 0.0
    return sum(
        0.5 * (y[i] + y[i + 1]) * (x[i + 1] - x[i])
        for i in range(len(y) - 1)
    )


def _detect_and_integrate_peaks(time_list: list, signal_list: list) -> list:
    """
    Automatic peak detection + valley drop-line baseline integration.

    Combines prominence detection with detailed integration.
    Area unit: mAU·s (time: min -> x60 -> converted to s)

    Returns: list of peak dicts
    """
    if len(time_list) < 10:
        return []

    # smoothing (detection only — integration uses the raw signal)
    smoothed = _savgol_smooth(signal_list, window=11)
    corrected = [max(v, 0.0) for v in smoothed]

    peak_indices = _find_peaks_prominence(
        corrected,
        min_prominence_factor=0.01,
        height_multiplier=3.0,
        min_distance=5,
    )

    if not peak_indices:
        return []

    # compute boundaries + correct against the neighboring-peak valley
    boundaries = []
    for k, idx in enumerate(peak_indices):
        left_idx, right_idx = _find_valley_boundary(corrected, idx)

        if k > 0:
            prev_idx = peak_indices[k - 1]
            seg = corrected[prev_idx: idx + 1]
            valley_global = prev_idx + seg.index(min(seg))
            left_idx = max(left_idx, valley_global)

        if k < len(peak_indices) - 1:
            next_idx = peak_indices[k + 1]
            seg = corrected[idx: next_idx + 1]
            valley_global = idx + seg.index(min(seg))
            right_idx = min(right_idx, valley_global)

        boundaries.append((left_idx, right_idx))

    # integration (on the raw signal, valley drop-line baseline)
    peaks = []
    total_area = 0.0
    for k, (idx, (l_idx, r_idx)) in enumerate(zip(peak_indices, boundaries)):
        # time array (min -> s)
        seg_t_s = [time_list[i] * 60.0 for i in range(l_idx, r_idx + 1)]
        seg_s   = [max(signal_list[i], 0.0) for i in range(l_idx, r_idx + 1)]

        if len(seg_t_s) < 2:
            continue

        # valley drop-line baseline: a straight line joining both boundaries
        n_seg = len(seg_t_s)
        baseline = [
            seg_s[0] + (seg_s[-1] - seg_s[0]) * j / (n_seg - 1)
            for j in range(n_seg)
        ]
        corrected_seg = [max(s - b, 0.0) for s, b in zip(seg_s, baseline)]
        area   = _trapezoid(corrected_seg, seg_t_s)
        height = max(corrected_seg) if corrected_seg else 0.0

        rt       = time_list[idx]
        rt_start = time_list[l_idx]
        rt_end   = time_list[r_idx]
        width    = rt_end - rt_start

        # FWHM width (based on the smoothed signal)
        half = height / 2.0
        wl_i, wr_i = idx, idx
        while wl_i > l_idx and corrected[wl_i] > half:
            wl_i -= 1
        while wr_i < r_idx and corrected[wr_i] > half:
            wr_i += 1
        width_fwhm = time_list[wr_i] - time_list[wl_i]

        total_area += area
        peaks.append({
            "peak_number":    k + 1,
            "retention_time": round(rt, 4),
            "rt_start":       round(rt_start, 4),
            "rt_end":         round(rt_end, 4),
            "height":         round(height, 4),
            "area":           round(area, 4),
            "width":          round(width, 4),
            "width_fwhm":     round(width_fwhm, 4),
            "area_percent":   0.0,
        })

    if total_area > 0:
        for p in peaks:
            p["area_percent"] = round(p["area"] / total_area * 100, 2)

    return peaks


# ---------------------------------------------------------------------------
# Normalize the raw peak table from a text file
# ---------------------------------------------------------------------------

def _normalize_raw_peaks(raw_peaks: list) -> list:
    key_map = {
        "peak": "peak_number", "peak #": "peak_number",
        "peak no": "peak_number", "no.": "peak_number",
        "ret.time": "retention_time", "retention time": "retention_time", "rt": "retention_time",
        "area": "area", "height": "height",
        "width": "width", "width at half height": "width_fwhm", "w50": "width_fwhm",
    }
    result = []
    for raw in raw_peaks:
        normalized = {}
        for k, v in raw.items():
            mapped = key_map.get(k.lower().strip(), k.lower().strip())
            normalized[mapped] = v
        result.append(normalized)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_hplc(filepath: str) -> dict:
    """Parse an HPLC data file and return a structured dictionary.

    Supported formats:
      - Agilent .ch binary (ChemStation format 130/131)
      - ChemStation tab export .txt
      - CSV with a header
      - Agilent .arw (text header)

    Args:
        filepath: path to the data file (.ch / .txt / .csv / .arw)

    Returns:
        {
            'chromatogram': [{'time': float, 'signal': float}, ...],
            'peaks': [
                {
                    'peak_number': int,
                    'retention_time': float,   # min
                    'rt_start': float,         # min
                    'rt_end': float,           # min
                    'height': float,           # mAU or nRIU
                    'area': float,             # mAU·s or nRIU·s
                    'width': float,            # min (rt_end - rt_start)
                    'width_fwhm': float,       # min (full width at half maximum)
                    'area_percent': float,
                }, ...
            ],
            'metadata': dict,
            'sample_name': str,
            'file_source': str,
        }

    Notes:
        Peak-handling priority:
          1. .ch file -> auto-detected and integrated by the built-in algorithm
          2. Text file with a peak table -> use that table
          3. Text file without a peak table -> auto-detect and integrate
    """
    path = Path(filepath)
    suffix = path.suffix.lower()

    if suffix == ".ch":
        parsed = _parse_ch_binary(filepath)
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        fmt = _detect_text_format(lines)
        if fmt == "arw":
            parsed = _parse_arw(lines, filepath)
        elif fmt == "chemstation_tab":
            parsed = _parse_chemstation_tab(lines, filepath)
        else:
            parsed = _parse_csv_header(lines, filepath)

    time_list   = parsed["time_list"]
    signal_list = parsed["signal_list"]

    chromatogram = [
        {"time": t, "signal": s}
        for t, s in zip(time_list, signal_list)
    ]

    # peaks: prefer the raw text table, fall back to auto-detection
    raw_peaks = parsed.get("_peaks_raw", [])
    if raw_peaks:
        peaks = _normalize_raw_peaks(raw_peaks)
    else:
        peaks = _detect_and_integrate_peaks(time_list, signal_list)

    return {
        "chromatogram": chromatogram,
        "peaks":        peaks,
        "metadata":     parsed.get("metadata", {}),
        "sample_name":  parsed.get("sample_name", path.stem),
        "file_source":  str(filepath),
    }


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

def _write_chromatogram_csv(results: list, output_path: str) -> None:
    rows = []
    for r in results:
        sample = r.get("sample_name", "unknown")
        source = r.get("file_source", "")
        for pt in r.get("chromatogram", []):
            rows.append({
                "time_min":    pt["time"],
                "signal_mAU":  pt["signal"],
                "sample_name": sample,
                "file_source": source,
            })
    fieldnames = ["time_min", "signal_mAU", "sample_name", "file_source"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_peaks_csv(results: list, output_path: str) -> None:
    rows = []
    for r in results:
        sample = r.get("sample_name", "unknown")
        source = r.get("file_source", "")
        for peak in r.get("peaks", []):
            row = {"sample_name": sample, "file_source": source}
            row.update(peak)
            rows.append(row)
    if not rows:
        print("No peak data — skipping peaks CSV generation.", file=sys.stderr)
        return
    all_keys = list(dict.fromkeys(k for row in rows for k in row))
    base = Path(output_path)
    peaks_path = str(base.parent / (base.stem + "_peaks" + base.suffix))
    with open(peaks_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Peak data: {peaks_path} ({len(rows)} rows)", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Convert an HPLC data file (.ch/.txt/.csv/.arw) to a structured CSV.\n"
            "Peaks are auto-detected by the built-in algorithm (valley boundary + trapezoid integration)."
        )
    )
    parser.add_argument(
        "files", nargs="+",
        help="input file path(s) (multiple files allowed)"
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="output CSV path (default: first_filename_parsed.csv)"
    )
    parser.add_argument(
        "--peaks", action="store_true",
        help="save peak data separately to <name>_peaks.csv"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="output JSON instead of CSV"
    )
    args = parser.parse_args()

    results = []
    for fp in args.files:
        p = Path(fp)
        if not p.exists():
            print(f"Warning: could not find {fp}.", file=sys.stderr)
            continue
        try:
            result = parse_hplc(fp)
            results.append(result)
            n_pts   = len(result["chromatogram"])
            n_peaks = len(result["peaks"])
            print(
                f"{p.name}: {n_pts} points, {n_peaks} peaks "
                f"[{result.get('sample_name', '')}]",
                file=sys.stderr,
            )
        except Exception as e:
            print(f"Error: failed to parse {fp} — {e}", file=sys.stderr)

    if not results:
        print("No files were parsed.", file=sys.stderr)
        sys.exit(1)

    if args.json:
        import json
        output = json.dumps(results, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
            print(f"JSON saved: {args.output}", file=sys.stderr)
        else:
            print(output)
        return

    output_path = args.output
    if not output_path:
        first = Path(args.files[0])
        output_path = str(first.parent / (first.stem + "_parsed.csv"))

    _write_chromatogram_csv(results, output_path)
    total_pts = sum(len(r["chromatogram"]) for r in results)
    print(f"Chromatogram saved: {output_path} ({total_pts} rows)", file=sys.stderr)

    if args.peaks:
        _write_peaks_csv(results, output_path)


if __name__ == "__main__":
    main()
