"""excel_formula_check.py — Generic, Windows-native Excel formula-error scanner.

WHY THIS EXISTS
----------------
The previous checker (recalc.py) depends on LibreOffice's headless recalculation
to force formulas to re-evaluate before scanning, but LibreOffice is not
installed on this machine. The only other working checker was hardcoded to a
single private billing dashboard's sheet/column layout. This script replaces
both: it works on ANY .xlsx workbook, uses openpyxl (pure Python, no external
app required) to read cached formula results, and optionally uses xlwings
(if a local Excel install is available) to force a real recalculation first
so the values it scans are fresh rather than stale cached values.

WHAT IT DOES
------------
1. (Optional) Recalculate the workbook via xlwings + installed Excel (COM),
   so cached formula-result values reflect the current formulas/inputs.
   If Excel/xlwings is not available, it skips this step and warns that
   the scanned values may be stale (openpyxl only ever reads the last
   cached result written by whatever last saved the file — it cannot
   evaluate formulas itself).
2. Scan every sheet/cell (via openpyxl, data_only=True) for the 7 standard
   Excel error strings: #REF!, #DIV/0!, #VALUE!, #NAME?, #NULL!, #NUM!, #N/A
   and report the sheet name, cell coordinate, formula (if available), and
   cached value for each hit.
3. Run two generic structural heuristics that often precede real errors:
     a. Suspicious unit-multiplier patterns — a formula containing a bare
        "*1000" (or *100, *10, *1e3, etc.) directly adjacent to a "-" or "/"
        operator, e.g. "=A1*1000-B1" or "=A1/1000*C2". This pattern shows up
        when someone mixes unit conversion into an arithmetic chain and a
        sign/precedence slip silently produces a wrong-order-of-magnitude
        result instead of an Excel error string.
     b. Self-referencing-row drift — a formula in row N that references its
        own row's other columns is normal (e.g. row totals), but a formula
        that references a DIFFERENT row than the row it lives in for what
        looks like the same column pattern as neighboring rows (e.g. row 12's
        formula references row 11 while every other row in that column
        references its own row) suggests a copy-paste/fill-down error where
        a relative reference didn't shift as expected.
   These are heuristics, not certainties — they are reported as "suspicious"
   findings, separate from hard error-string findings.

This script is intentionally generic: no hardcoded sheet names, column
layouts, or billing/domain-specific logic. It contains no PII.

CLI USAGE
---------
    python excel_formula_check.py <file.xlsx> [--json] [--no-recalc]

    <file.xlsx>   Path to the workbook to check.
    --json        Emit machine-readable JSON instead of human-readable text.
    --no-recalc   Skip the xlwings/Excel recalculation step even if available.

EXIT CODES
----------
    0   No hard Excel errors found (suspicious heuristic findings do not
        affect exit code).
    1   One or more hard Excel error strings were found.
    2   The file could not be opened / processed at all.
"""

from __future__ import annotations

# Windows' default console is cp949 and dies on non-ASCII/symbol output. Force UTF-8.
# Use reconfigure: wrapping in a TextIOWrapper takes ownership of the underlying
# stream, so once this module is imported, GC'ing the wrapper closes the
# caller's stdout too (measured).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import argparse
import io
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# Windows consoles often default to a legacy codepage (e.g. cp949/cp1252)
# that cannot encode characters like the em-dash (—) used in messages
# below. Force UTF-8 stdout/stderr so this script is safe to run from any
# Windows terminal regardless of the active codepage.
if sys.platform == "win32":
    for _stream_name in ("stdout", "stderr"):
        _stream = getattr(sys, _stream_name)
        if hasattr(_stream, "buffer"):
            setattr(
                sys,
                _stream_name,
                io.TextIOWrapper(_stream.buffer, encoding="utf-8", errors="replace"),
            )

# The 7 standard Excel error strings.
EXCEL_ERROR_STRINGS = (
    "#REF!",
    "#DIV/0!",
    "#VALUE!",
    "#NAME?",
    "#NULL!",
    "#NUM!",
    "#N/A",
)

# Matches a numeric multiplier like *1000, *100, *1e3, *1E4, with optional
# surrounding whitespace, immediately followed (within a short lookahead) by
# a "-" or "/" operator — a common symptom of a unit-conversion-plus-arithmetic
# slip (e.g. "=A1*1000-B1" meant to be "=(A1-B1)*1000").
UNIT_MULTIPLIER_PATTERN = re.compile(
    r"\*\s*(?:\d+(?:\.\d+)?(?:[eE]\d+)?)\s*[-/]",
)

# A cell reference like A1, $A$1, Sheet1!A1, 'Sheet 1'!$B$12 etc.
CELL_REF_PATTERN = re.compile(
    r"(?:'[^']+'!|[A-Za-z_][A-Za-z0-9_]*!)?\$?([A-Za-z]{1,3})\$?(\d+)"
)


@dataclass
class ErrorFinding:
    """A hard Excel error string found in a cell."""

    sheet: str
    cell: str
    error: str
    formula: str | None
    kind: str = "error"


@dataclass
class SuspiciousFinding:
    """A heuristic (soft) finding — not a hard error, worth a human look."""

    sheet: str
    cell: str
    reason: str
    formula: str | None
    kind: str = "suspicious"


@dataclass
class ScanReport:
    file: str
    recalculated: bool
    recalc_note: str
    sheets_scanned: int
    cells_scanned: int
    errors: list[ErrorFinding] = field(default_factory=list)
    suspicious: list[SuspiciousFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


def try_recalculate_with_excel(file_path: Path) -> tuple[bool, str]:
    """Attempt to recalculate the workbook in place using xlwings + a local
    Excel install (COM automation, Windows only).

    Returns (recalculated: bool, note: str). Never raises — any failure
    (xlwings not installed, Excel not installed, COM error, etc.) is caught
    and reported back as a note so the caller can decide whether to proceed
    with (potentially stale) cached values.
    """
    try:
        import xlwings as xw
    except ImportError:
        return False, "xlwings not installed — values may be stale (cached, not recalculated)."

    app = None
    try:
        app = xw.App(visible=False, add_book=False)
        app.display_alerts = False
        app.screen_updating = False
        book = app.books.open(str(file_path))
        try:
            book.app.calculate()
            book.save()
        finally:
            book.close()
        return True, "Recalculated via xlwings + Excel COM before scanning."
    except Exception as exc:  # noqa: BLE001 - deliberately broad: any COM/Excel failure just downgrades to a warning
        return False, (
            f"xlwings/Excel recalculation failed ({exc!r}) — "
            "values may be stale (cached, not recalculated)."
        )
    finally:
        if app is not None:
            try:
                app.quit()
            except Exception:  # noqa: BLE001
                pass


def _cell_value_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _find_error_in_value(value: Any) -> str | None:
    """Return the Excel error string contained in a cell value, if any."""
    if value is None:
        return None
    text = str(value)
    for err in EXCEL_ERROR_STRINGS:
        if err in text:
            return err
    return None


def _row_of_coordinate(coordinate: str) -> int | None:
    m = re.match(r"^\$?[A-Za-z]{1,3}\$?(\d+)$", coordinate)
    if not m:
        return None
    return int(m.group(1))


def scan_workbook(file_path: Path) -> tuple[list[ErrorFinding], list[SuspiciousFinding], int, int]:
    """Scan every sheet/cell of the workbook for hard errors and heuristic
    suspicious patterns.

    Two openpyxl loads are used:
      - data_only=True  -> cached formula RESULT values (to detect error strings)
      - data_only=False -> the FORMULA TEXT itself (to run heuristics and to
                            annotate error findings with the offending formula)
    """
    import openpyxl

    wb_values = openpyxl.load_workbook(str(file_path), data_only=True)
    wb_formulas = openpyxl.load_workbook(str(file_path), data_only=False)

    errors: list[ErrorFinding] = []
    suspicious: list[SuspiciousFinding] = []
    cells_scanned = 0

    for sheet_name in wb_values.sheetnames:
        ws_values = wb_values[sheet_name]
        ws_formulas = wb_formulas[sheet_name] if sheet_name in wb_formulas.sheetnames else None

        # Track, per "column signature" (column letter + set of columns the
        # formula references relative to its own row), which row offset is
        # used — to spot a row whose fill-down pattern deviates from its
        # neighbors (self-referencing-row drift heuristic).
        column_row_offsets: dict[str, dict[int, int]] = {}

        max_row = ws_values.max_row or 0
        max_col = ws_values.max_column or 0

        for row in ws_values.iter_rows(min_row=1, max_row=max_row, max_col=max_col):
            for cell in row:
                cells_scanned += 1
                err = _find_error_in_value(cell.value)
                formula_text = None
                if ws_formulas is not None:
                    f_cell = ws_formulas[cell.coordinate]
                    if isinstance(f_cell.value, str) and f_cell.value.startswith("="):
                        formula_text = f_cell.value

                if err is not None:
                    errors.append(
                        ErrorFinding(
                            sheet=sheet_name,
                            cell=cell.coordinate,
                            error=err,
                            formula=formula_text,
                        )
                    )

                if formula_text is None:
                    continue

                # Heuristic A: suspicious unit-multiplier pattern.
                if UNIT_MULTIPLIER_PATTERN.search(formula_text):
                    suspicious.append(
                        SuspiciousFinding(
                            sheet=sheet_name,
                            cell=cell.coordinate,
                            reason=(
                                "Unit-multiplier pattern (e.g. *1000 next to - or /) — "
                                "check operator precedence; a conversion factor may be "
                                "applied to only part of an expression."
                            ),
                            formula=formula_text,
                        )
                    )

                # Heuristic B: self-referencing-row drift.
                own_row = _row_of_coordinate(cell.coordinate)
                if own_row is None:
                    continue
                refs = CELL_REF_PATTERN.findall(formula_text)
                if not refs:
                    continue
                col_letter = re.match(r"^\$?([A-Za-z]{1,3})", cell.coordinate).group(1)
                # Build the set of row-offsets this formula uses relative to
                # its own row (0 = same-row reference, -1 = references the
                # row above, etc.). A same-row reference (offset 0) is a
                # perfectly normal, common "signature" — e.g. every row in a
                # totals column referencing its own row's inputs — so it must
                # NOT be discarded here; discarding it would blind this
                # heuristic to exactly the drift case it exists to catch
                # (one row referencing a different row than all its
                # neighbors, most commonly the row above, offset -1).
                offsets = sorted({int(r) - own_row for (_c, r) in refs})
                if not offsets:
                    continue
                # Use the smallest-magnitude offset actually present as this
                # row's "signature" offset for the column it lives in.
                sig_offset = min(offsets, key=abs)
                seen = column_row_offsets.setdefault(col_letter, {})
                seen[own_row] = sig_offset

        # After collecting all offsets for a column, flag rows whose offset
        # deviates from the majority pattern in that column (drift).
        for col_letter, row_offsets in column_row_offsets.items():
            if len(row_offsets) < 3:
                continue  # not enough rows to establish a "normal" pattern
            from collections import Counter

            counts = Counter(row_offsets.values())
            majority_offset, majority_count = counts.most_common(1)[0]
            if majority_count < 2:
                continue  # no clear majority pattern to compare against
            for row_num, offset in row_offsets.items():
                if offset != majority_offset:
                    coord = f"{col_letter}{row_num}"
                    f_cell = ws_formulas[coord] if ws_formulas is not None else None
                    formula_text = f_cell.value if f_cell is not None else None
                    suspicious.append(
                        SuspiciousFinding(
                            sheet=sheet_name,
                            cell=coord,
                            reason=(
                                f"Self-referencing-row drift — other rows in column "
                                f"{col_letter} reference row offset {majority_offset:+d}, "
                                f"but this row references offset {offset:+d}. Possible "
                                f"copy-paste/fill-down error."
                            ),
                            formula=formula_text,
                        )
                    )

    wb_values.close()
    wb_formulas.close()

    return errors, suspicious, len(wb_values.sheetnames), cells_scanned


def check_file(file_path: Path, allow_recalc: bool = True) -> ScanReport:
    recalculated = False
    recalc_note = "Recalculation skipped (--no-recalc)."

    if allow_recalc:
        recalculated, recalc_note = try_recalculate_with_excel(file_path)

    errors, suspicious, sheets_scanned, cells_scanned = scan_workbook(file_path)

    return ScanReport(
        file=str(file_path),
        recalculated=recalculated,
        recalc_note=recalc_note,
        sheets_scanned=sheets_scanned,
        cells_scanned=cells_scanned,
        errors=errors,
        suspicious=suspicious,
    )


def print_human_report(report: ScanReport) -> None:
    print(f"File: {report.file}")
    if report.recalculated:
        print(f"Recalc: OK — {report.recalc_note}")
    else:
        print(f"Recalc: SKIPPED — {report.recalc_note}")
    print(f"Sheets scanned: {report.sheets_scanned}, cells scanned: {report.cells_scanned}")
    print()

    if report.errors:
        print(f"HARD ERRORS FOUND: {len(report.errors)}")
        for e in report.errors:
            loc = f"[{e.sheet}!{e.cell}]"
            if e.formula:
                print(f"  {loc} {e.error}  formula: {e.formula}")
            else:
                print(f"  {loc} {e.error}")
    else:
        print("HARD ERRORS FOUND: 0")

    print()

    if report.suspicious:
        print(f"SUSPICIOUS PATTERNS (heuristic, not confirmed errors): {len(report.suspicious)}")
        for s in report.suspicious:
            loc = f"[{s.sheet}!{s.cell}]"
            print(f"  {loc} {s.reason}")
            if s.formula:
                print(f"      formula: {s.formula}")
    else:
        print("SUSPICIOUS PATTERNS (heuristic, not confirmed errors): 0")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generic Windows-native Excel formula-error scanner. Scans any "
            ".xlsx workbook for Excel error strings (#REF!, #DIV/0!, #VALUE!, "
            "#NAME?, #NULL!, #NUM!, #N/A) plus heuristic checks for suspicious "
            "unit-multiplier patterns and self-referencing-row drift. "
            "For beginners: just pass a file path — recalculation via "
            "Excel is attempted automatically if Excel is installed."
        )
    )
    parser.add_argument("file", help="Path to the .xlsx file to check.")
    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON instead of text."
    )
    parser.add_argument(
        "--no-recalc",
        action="store_true",
        help="Skip the xlwings/Excel recalculation step even if Excel is available.",
    )
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"ERROR: file not found: {file_path}", file=sys.stderr)
        return 2
    if file_path.suffix.lower() not in (".xlsx", ".xlsm"):
        print(
            f"WARNING: expected a .xlsx/.xlsm file, got '{file_path.suffix}'. Attempting anyway.",
            file=sys.stderr,
        )

    try:
        report = check_file(file_path, allow_recalc=not args.no_recalc)
    except Exception as exc:  # noqa: BLE001 - top-level CLI guard
        if args.json:
            print(json.dumps({"error": f"Failed to process file: {exc!r}"}, ensure_ascii=False, indent=2))
        else:
            print(f"ERROR: failed to process file: {exc!r}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print_human_report(report)

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
