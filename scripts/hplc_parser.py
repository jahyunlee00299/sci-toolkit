#!/usr/bin/env python3
"""HPLC 크로마토그래피 데이터 파서.

피크 검출·적분 알고리즘을 stdlib only 로 포팅:
  - .ch 바이너리: Agilent ChemStation format 130/131 delta-compression 디코딩
  - 텍스트 형식: ChemStation 탭 내보내기 .txt, 헤더 CSV, .arw
  - 피크 검출: MAD noise + prominence 기반 자동 검출 (valley 경계)
  - 피크 적분: valley drop-line baseline + trapezoid rule

사용법:
    python hplc_parser.py data.ch [--output parsed.csv] [--peaks]
    python hplc_parser.py *.txt --output combined.csv --peaks
    python hplc_parser.py data.ch --json

임포트:
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
import argparse
import csv
import re
import struct
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# .ch 바이너리 파서 (ChemStation 바이너리 파서 — numpy 없음)
# ---------------------------------------------------------------------------

def _read_pascal_string(raw: bytes, offset: int) -> str:
    """Pascal string (length byte + chars)을 읽는다."""
    length = raw[offset]
    if length == 0 or length > 64:
        return ""
    return raw[offset + 1: offset + 1 + length].decode("ascii", errors="ignore")


def _decompress_segments(raw: bytes, data_start: int) -> list:
    """
    Agilent format-130 delta-compression 디코딩.

    segment 구조: (label:u8, count:u8) 뒤에 count 개의 int16.
      - int16 == -32768 (0x8000): 다음 4바이트 int32가 새 절댓값
      - 그 외: 이전 값에 delta 누적
    label==0, count==0 → 데이터 끝
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
    """Agilent .ch 바이너리 파일 파싱 (format 130/131)."""
    raw = Path(filepath).read_bytes()

    # 버전 확인 (offset 0: Pascal string "130" 또는 "131")
    version = _read_pascal_string(raw, 0)
    if version not in ("130", "131"):
        raise ValueError(
            f"지원하지 않는 ChemStation 버전: '{version}' "
            f"(처음 4바이트: {raw[:4].hex()})"
        )

    # 시간 범위 (offset 0x11A, 0x11E: big-endian uint32 ms)
    start_ms = struct.unpack(">I", raw[0x11A:0x11E])[0]
    end_ms   = struct.unpack(">I", raw[0x11E:0x122])[0]
    start_time = start_ms / 60000.0
    end_time   = end_ms   / 60000.0

    # Y 스케일 인수 (offset 0x127C: big-endian double)
    y_scale = struct.unpack(">d", raw[0x127C:0x1284])[0]
    if y_scale == 0.0:
        y_scale = 1.0

    # 데이터 블록 (offset 0x1800)
    raw_values = _decompress_segments(raw, 0x1800)
    n = len(raw_values)
    if n == 0:
        raise ValueError("데이터 포인트가 없습니다.")

    signal_list = [v * y_scale for v in raw_values]

    if end_time <= start_time:
        end_time = n / 100.0
    step = (end_time - start_time) / (n - 1) if n > 1 else 0.0
    time_list = [start_time + i * step for i in range(n)]

    # 샘플명 (offset 0x18: Pascal string)
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
# 텍스트 형식 파서 (ChemStation 탭, CSV with header, .arw)
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
# 피크 검출 + 적분 (prominence 기반 검출 + trapezoid 적분)
# ---------------------------------------------------------------------------

def _mad_noise(signal: list) -> float:
    """MAD 기반 noise 추정 (derivative 기준). MAD 기반 추정."""
    if len(signal) < 2:
        return 1.0
    deriv = [signal[i + 1] - signal[i] for i in range(len(signal) - 1)]
    med_d = sorted(deriv)[len(deriv) // 2]
    abs_dev = sorted(abs(d - med_d) for d in deriv)
    mad = abs_dev[len(abs_dev) // 2]
    return max(mad * 1.4826, 1.0)


def _savgol_smooth(signal: list, window: int = 11) -> list:
    """가중 이동 평균 스무딩 (scipy 없음 — parabolic kernel 근사)."""
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
    """prominence 기반 피크 인덱스 검출.

    prominence 기반 검출 로직.
    Returns: 피크 인덱스 목록 (오름차순)
    """
    n = len(signal)
    if n < 3:
        return []

    noise = _mad_noise(signal)
    sig_range = max(signal) - min(signal)
    min_prominence = sig_range * min_prominence_factor
    min_height = noise * height_multiplier

    # 로컬 최댓값 후보
    candidates = []
    for i in range(1, n - 1):
        if signal[i] >= signal[i - 1] and signal[i] >= signal[i + 1]:
            if signal[i] >= min_height:
                candidates.append(i)

    # min_distance 필터 (높은 피크 우선 유지)
    candidates.sort(key=lambda i: signal[i], reverse=True)
    selected = []
    for c in candidates:
        if all(abs(c - s) >= min_distance for s in selected):
            selected.append(c)
    selected.sort()

    # prominence 필터
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
    Valley + threshold 기반 피크 경계 검출.
    valley 기준 경계 탐색.

    Returns: (left_idx, right_idx)
    """
    n = len(signal)
    peak_max = signal[peak_idx]
    threshold = peak_max * threshold_ratio

    # 왼쪽 스캔
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

    # 오른쪽 스캔
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
    """trapezoid rule 적분 (numpy 없음)."""
    if len(y) < 2:
        return 0.0
    return sum(
        0.5 * (y[i] + y[i + 1]) * (x[i + 1] - x[i])
        for i in range(len(y) - 1)
    )


def _detect_and_integrate_peaks(time_list: list, signal_list: list) -> list:
    """
    피크 자동 검출 + valley drop-line baseline 적분.

    prominence 검출 + 상세 적분 통합.
    Area 단위: mAU·s (time: min → ×60 → s 변환)

    Returns: list of peak dicts
    """
    if len(time_list) < 10:
        return []

    # 스무딩 (검출 전용, 적분은 원신호 사용)
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

    # 경계 계산 + 인접 피크 valley로 보정
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

    # 적분 (원신호 기준, valley drop-line baseline)
    peaks = []
    total_area = 0.0
    for k, (idx, (l_idx, r_idx)) in enumerate(zip(peak_indices, boundaries)):
        # 시간 배열 (min→s)
        seg_t_s = [time_list[i] * 60.0 for i in range(l_idx, r_idx + 1)]
        seg_s   = [max(signal_list[i], 0.0) for i in range(l_idx, r_idx + 1)]

        if len(seg_t_s) < 2:
            continue

        # valley drop-line baseline: 양 경계 잇는 직선
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

        # FWHM width (스무딩 신호 기준)
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
# 텍스트 파일 raw peak 테이블 정규화
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
# 공개 API
# ---------------------------------------------------------------------------

def parse_hplc(filepath: str) -> dict:
    """HPLC 데이터 파일을 파싱해 구조화된 딕셔너리를 반환한다.

    지원 형식:
      - Agilent .ch 바이너리 (ChemStation format 130/131)
      - ChemStation 탭 내보내기 .txt
      - 헤더가 있는 CSV
      - Agilent .arw (텍스트 헤더)

    Args:
        filepath: 데이터 파일 경로 (.ch / .txt / .csv / .arw)

    Returns:
        {
            'chromatogram': [{'time': float, 'signal': float}, ...],
            'peaks': [
                {
                    'peak_number': int,
                    'retention_time': float,   # min
                    'rt_start': float,         # min
                    'rt_end': float,           # min
                    'height': float,           # mAU 또는 nRIU
                    'area': float,             # mAU·s 또는 nRIU·s
                    'width': float,            # min (rt_end - rt_start)
                    'width_fwhm': float,       # min (반치폭)
                    'area_percent': float,
                }, ...
            ],
            'metadata': dict,
            'sample_name': str,
            'file_source': str,
        }

    Notes:
        피크 처리 우선순위:
          1. .ch 파일 → 내장 알고리즘으로 자동 검출·적분
          2. 텍스트 파일에 피크 테이블 포함 → 테이블 사용
          3. 텍스트 파일에 피크 테이블 없음 → 자동 검출·적분
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

    # 피크: 텍스트 raw 테이블 우선, 없으면 자동 검출
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
# CSV 출력
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
        print("피크 데이터 없음 — peaks CSV 생성 건너뜀.", file=sys.stderr)
        return
    all_keys = list(dict.fromkeys(k for row in rows for k in row))
    base = Path(output_path)
    peaks_path = str(base.parent / (base.stem + "_peaks" + base.suffix))
    with open(peaks_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"피크 데이터: {peaks_path} ({len(rows)}행)", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "HPLC 데이터 파일(.ch/.txt/.csv/.arw)을 정형화된 CSV로 변환한다.\n"
            "피크는 내장 알고리즘(valley 경계 + trapezoid 적분)으로 자동 검출."
        )
    )
    parser.add_argument(
        "files", nargs="+",
        help="입력 파일 경로 (여러 파일 지정 가능)"
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="출력 CSV 경로 (기본: 첫 번째 파일명_parsed.csv)"
    )
    parser.add_argument(
        "--peaks", action="store_true",
        help="피크 데이터를 별도 <name>_peaks.csv로 저장"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="CSV 대신 JSON으로 출력"
    )
    args = parser.parse_args()

    results = []
    for fp in args.files:
        p = Path(fp)
        if not p.exists():
            print(f"경고: {fp} 를 찾을 수 없습니다.", file=sys.stderr)
            continue
        try:
            result = parse_hplc(fp)
            results.append(result)
            n_pts   = len(result["chromatogram"])
            n_peaks = len(result["peaks"])
            print(
                f"{p.name}: {n_pts}개 포인트, {n_peaks}개 피크 "
                f"[{result.get('sample_name', '')}]",
                file=sys.stderr,
            )
        except Exception as e:
            print(f"오류: {fp} 파싱 실패 — {e}", file=sys.stderr)

    if not results:
        print("파싱된 파일이 없습니다.", file=sys.stderr)
        sys.exit(1)

    if args.json:
        import json
        output = json.dumps(results, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
            print(f"JSON 저장: {args.output}", file=sys.stderr)
        else:
            print(output)
        return

    output_path = args.output
    if not output_path:
        first = Path(args.files[0])
        output_path = str(first.parent / (first.stem + "_parsed.csv"))

    _write_chromatogram_csv(results, output_path)
    total_pts = sum(len(r["chromatogram"]) for r in results)
    print(f"크로마토그램 저장: {output_path} ({total_pts}행)", file=sys.stderr)

    if args.peaks:
        _write_peaks_csv(results, output_path)


if __name__ == "__main__":
    main()
