#!/usr/bin/env python3
"""
Primer Order Sheet Generator
==============================
Converts primer design results into Macrogen order-sheet format.

Supported outputs:
  - XLSX (Macrogen Order + Summary + QC sheets)
  - CSV  (UTF-8 BOM, for Korean-Excel compatibility)
  - Markdown
  - pandas DataFrame
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

import pandas as pd

from .order_sheet_writers import (
    PURIFICATION_TO_MACROGEN as _PURIFICATION_TO_MACROGEN,  # noqa: F401 - still importable from here
    SCALE_TO_UMOL as _SCALE_TO_UMOL,  # noqa: F401
    render_markdown,
    write_macrogen_oligo_xls,
    write_macrogen_oligo_xlsx,
    write_macrogen_seq_xlsx,
    write_order_xlsx,
)


# ── Constants ──────────────────────────────────────────────────────────────

COST_PER_BASE_KRW = 400    # 50 nmol scale
MIN_PRIMER_COST_KRW = 5000

# The Macrogen scale/purification mappings live in order_sheet_writers.py
# (imported above under their historical private names).


# ── Enums ──────────────────────────────────────────────────────────────────

class PrimerScale(Enum):
    NMOL_25 = "25 nmol"
    NMOL_50 = "50 nmol"
    NMOL_100 = "100 nmol"
    UMOL_1 = "1 umol"


class Purification(Enum):
    DESALTING = "Desalting"
    PAGE = "PAGE"
    HPLC = "HPLC"


# ── Data class ─────────────────────────────────────────────────────────────

@dataclass
class PrimerEntry:
    name: str
    sequence: str       # 5'->3', uppercase
    length: int
    scale: PrimerScale
    purification: Purification
    tm: float | None
    gc: float | None
    qc_verdict: str | None
    experiment: str
    direction: str      # "F" or "R"
    notes: str


# ── Order Sheet ────────────────────────────────────────────────────────────

class PrimerOrderSheet:
    """Primer order-sheet generator.

    Takes an iPCR design result (dict) and produces Macrogen order-sheet-format output.
    """

    def __init__(
        self,
        project_name: str = "primer_order",
        default_scale: PrimerScale = PrimerScale.NMOL_50,
        default_purification: Purification = Purification.DESALTING,
    ):
        self.project_name = project_name
        self.default_scale = default_scale
        self.default_purification = default_purification
        self.entries: list[PrimerEntry] = []

    # ── Add from design result ─────────────────────────────────────────

    def add_from_design_result(
        self,
        result: dict,
        experiment: str = "",
        name_prefix: str = "iPCR",
        parent: str = "",
        mutation: str = "",
    ) -> tuple[PrimerEntry, PrimerEntry]:
        """Create F/R primer entries from a design-result dict.

        Naming priority:
          1. When parent + mutation are given: iPCR_{parent}_{mutation}_F/R
          2. When result has re_5prime, re_3prime keys:
             {name_prefix}_{re_5prime}_{re_3prime}_F/R
          3. Default: {name_prefix}_{seq_number}_F/R
        """
        # Determine names
        if parent and mutation:
            base_name = f"iPCR_{parent}_{mutation}"
        elif "re_5prime" in result and "re_3prime" in result:
            base_name = f"{name_prefix}_{result['re_5prime']}_{result['re_3prime']}"
        else:
            seq_number = (len(self.entries) // 2) + 1
            base_name = f"{name_prefix}_{seq_number:03d}"

        f_name = f"{base_name}_F"
        r_name = f"{base_name}_R"

        # Extract QC verdicts
        f_qc_verdict = None
        if isinstance(result.get("f_qc"), dict):
            f_qc_verdict = result["f_qc"].get("verdict")
        r_qc_verdict = None
        if isinstance(result.get("r_qc"), dict):
            r_qc_verdict = result["r_qc"].get("verdict")

        f_seq = result["f_full"].upper()
        r_seq = result["r_full"].upper()

        f_entry = PrimerEntry(
            name=f_name,
            sequence=f_seq,
            length=len(f_seq),
            scale=self.default_scale,
            purification=self.default_purification,
            tm=result.get("f_tm"),
            gc=result.get("f_gc"),
            qc_verdict=f_qc_verdict,
            experiment=experiment,
            direction="F",
            notes="",
        )
        r_entry = PrimerEntry(
            name=r_name,
            sequence=r_seq,
            length=len(r_seq),
            scale=self.default_scale,
            purification=self.default_purification,
            tm=result.get("r_tm"),
            gc=result.get("r_gc"),
            qc_verdict=r_qc_verdict,
            experiment=experiment,
            direction="R",
            notes="",
        )

        self.entries.append(f_entry)
        self.entries.append(r_entry)
        return f_entry, r_entry

    # ── Add custom primer ──────────────────────────────────────────────

    def add_custom_primer(
        self,
        name: str,
        sequence: str,
        experiment: str = "",
        direction: str = "",
        scale: PrimerScale | None = None,
        purification: Purification | None = None,
        tm: float | None = None,
        gc: float | None = None,
        notes: str = "",
    ) -> PrimerEntry:
        """Add a user-defined primer."""
        seq_upper = sequence.upper()
        entry = PrimerEntry(
            name=name,
            sequence=seq_upper,
            length=len(seq_upper),
            scale=scale if scale is not None else self.default_scale,
            purification=purification if purification is not None else self.default_purification,
            tm=tm,
            gc=gc,
            qc_verdict=None,
            experiment=experiment,
            direction=direction,
            notes=notes,
        )
        self.entries.append(entry)
        return entry

    # ── Batch add ──────────────────────────────────────────────────────

    def add_batch_from_results(
        self,
        results: list[dict],
        name_prefix: str = "iPCR",
    ) -> list[tuple[PrimerEntry, PrimerEntry]]:
        """Add multiple design results in a batch."""
        pairs = []
        for result in results:
            pair = self.add_from_design_result(result, name_prefix=name_prefix)
            pairs.append(pair)
        return pairs

    # ── Deduplication ──────────────────────────────────────────────────

    def deduplicate(self) -> list[tuple[str, str]]:
        """Remove duplicate sequences, keeping the first entry and dropping the rest.

        Returns
        -------
        list of (removed_name, kept_name)
        """
        seen: dict[str, str] = {}  # sequence -> name of first occurrence
        removed: list[tuple[str, str]] = []
        unique_entries: list[PrimerEntry] = []

        for entry in self.entries:
            seq_key = entry.sequence.upper()
            if seq_key in seen:
                removed.append((entry.name, seen[seq_key]))
            else:
                seen[seq_key] = entry.name
                unique_entries.append(entry)

        self.entries = unique_entries
        return removed

    # ── Summary ────────────────────────────────────────────────────────

    def summary(self) -> dict:
        """Summary statistics for the order sheet."""
        total_primers = len(self.entries)
        total_length_nt = sum(e.length for e in self.entries)

        estimated_cost_krw = 0
        for entry in self.entries:
            cost = entry.length * COST_PER_BASE_KRW
            estimated_cost_krw += max(cost, MIN_PRIMER_COST_KRW)

        unique_experiments = set()
        for entry in self.entries:
            if entry.experiment:
                unique_experiments.add(entry.experiment)

        scale_counts: dict[str, int] = {}
        for entry in self.entries:
            key = entry.scale.value
            scale_counts[key] = scale_counts.get(key, 0) + 1

        purification_counts: dict[str, int] = {}
        for entry in self.entries:
            key = entry.purification.value
            purification_counts[key] = purification_counts.get(key, 0) + 1

        return {
            "total_primers": total_primers,
            "total_length_nt": total_length_nt,
            "estimated_cost_krw": estimated_cost_krw,
            "unique_experiments": sorted(unique_experiments),
            "scale_counts": scale_counts,
            "purification_counts": purification_counts,
        }

    # ── Export: XLSX ───────────────────────────────────────────────────

    def to_xlsx(self, output_path: str | Path | None = None) -> Path:
        """Generate the Macrogen order-sheet XLSX.

        Sheet1 "Macrogen Order": No., Primer Name, Sequence, Scale, etc.
        Sheet2 "Summary": summary statistics
        Sheet3 "QC": Tm, GC%, QC Verdict
        """
        return write_order_xlsx(self.entries, self.summary(), self._resolve_path(output_path, "xlsx"))

    # ── Export: Macrogen Oligo Order ──────────────────────────────────

    def to_macrogen_oligo(self, output_path: str | Path | None = None) -> Path:
        """Generate the Macrogen Oligo order-sheet format (.xls BIFF8).

        Format compatible with upload on the Macrogen homepage (OLE2/BIFF8):
          No. | Oligo Name | 5` - Oligo Seq - 3` | Amount | Purification

        Amount: in umol (0.05 = 50 nmol default, 0.025 = 25 nmol)
        Purification: MOPC (desalting), PAGE, HPLC
        1000 rows total including blank rows (matches the Macrogen template).

        Saved via openpyxl if output_path's extension is .xlsx, via xlwt if .xls (default).
        """
        output_path = self._resolve_path(output_path, "xls")

        if output_path.suffix.lower() == ".xlsx":
            return self._write_macrogen_oligo_xlsx(output_path)
        return self._write_macrogen_oligo_xls(output_path)

    def _write_macrogen_oligo_xls(self, output_path: Path) -> Path:
        """Generate the Macrogen Oligo order sheet (.xls BIFF8) via xlwt."""
        return write_macrogen_oligo_xls(self.entries, output_path)

    def _write_macrogen_oligo_xlsx(self, output_path: Path) -> Path:
        """Generate the Macrogen Oligo order sheet (.xlsx) via openpyxl (fallback)."""
        return write_macrogen_oligo_xlsx(self.entries, output_path)

    # ── Export: Macrogen Sequencing Order ─────────────────────────────

    def to_macrogen_seq(
        self,
        sample_primer_pairs: list[dict],
        output_path: str | Path | None = None,
    ) -> Path:
        """Generate the Macrogen Standard Sequencing order-sheet format (.xlsx).

        Format compatible with upload on the Macrogen homepage:
          # | Sample Name | Primer Name | Sample Concentration (ng/ul) |
          Plate Name | Well Position | Product Size(bp) | Target Size(bp) |
          Primer Sequence(5 to 3) | Primer Concentration (pmol/ul)

        Parameters
        ----------
        sample_primer_pairs : list[dict]
            Each item:
            {
                "sample_name": str,                      # required
                "primer_name": str,                      # required
                "sample_conc": float | None,             # ng/ul — leave blank (filled in with the measured value)
                "plate_name": str,                       # optional
                "well_position": str,                    # optional
                "product_size": int | None,              # bp (fill in only when known, otherwise omit)
                "target_size": int | None,               # bp (optional)
                "primer_seq": str,                       # optional (5'→3')
                "primer_conc": float | None,             # pmol/ul (omit for a universal primer)
            }

        Note
        ----
        Do not put an arbitrary default (e.g. 100) into sample_conc.
        The experimenter fills in the measured concentration after miniprep,
        so this is left as None (blank).
        """
        return write_macrogen_seq_xlsx(sample_primer_pairs, self._resolve_path(output_path, "xlsx"))

    # ── Export: CSV ────────────────────────────────────────────────────

    def to_csv(self, output_path: str | Path | None = None) -> Path:
        """UTF-8 BOM CSV (for Korean-Excel compatibility)."""
        output_path = self._resolve_path(output_path, "csv")

        df = self.to_dataframe()
        df.to_csv(str(output_path), index=False, encoding="utf-8-sig")
        return output_path

    # ── Export: Markdown ───────────────────────────────────────────────

    def to_markdown(self, output_path: str | Path | None = None) -> Path:
        """Generate the Markdown order sheet."""
        output_path = self._resolve_path(output_path, "md")
        output_path.write_text(
            render_markdown(self.project_name, self.entries, self.summary()),
            encoding="utf-8",
        )
        return output_path

    # ── Export: DataFrame ──────────────────────────────────────────────

    def to_dataframe(self) -> pd.DataFrame:
        """Convert to a pandas DataFrame."""
        rows = []
        for i, entry in enumerate(self.entries, 1):
            rows.append({
                "No.": i,
                "Primer Name": entry.name,
                "Sequence (5'->3')": entry.sequence,
                "Scale": entry.scale.value,
                "Purification": entry.purification.value,
                "Length (nt)": entry.length,
                "Tm": entry.tm,
                "GC%": entry.gc,
                "QC Verdict": entry.qc_verdict or "-",
                "Experiment": entry.experiment,
                "Direction": entry.direction,
                "Notes": entry.notes,
            })
        return pd.DataFrame(rows)

    # ── Filename generation ────────────────────────────────────────────

    def _generate_filename(self, output_dir: Path, ext: str) -> Path:
        date_str = datetime.now().strftime("%Y%m%d")
        existing = sorted(output_dir.glob(f"{self.project_name}_{date_str}_*_order.{ext}"))
        seq = len(existing) + 1
        return output_dir / f"{self.project_name}_{date_str}_{seq:03d}_order.{ext}"

    def _resolve_path(self, output_path: str | Path | None, ext: str) -> Path:
        """``output_path`` as a Path, or an auto-numbered name in the cwd."""
        if output_path is None:
            return self._generate_filename(Path.cwd(), ext)
        return Path(output_path)
