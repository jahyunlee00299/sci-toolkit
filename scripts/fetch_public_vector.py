#!/usr/bin/env python3
"""
fetch_public_vector.py - Thin, generic helper to fetch PUBLIC vector/plasmid
sequences by accession number from NCBI.

Why this exists
----------------
The primer-design skill only *lists* the vectors it already knows about
(a fixed, curated set). It has no retrieval step. This script is the
retrieval step: given any public NCBI accession (e.g. a plasmid/vector
GenBank record), it downloads the record via Biopython's Bio.Entrez and
writes it locally as GenBank or FASTA. It is intentionally generic -
no lab-specific vector list, no hardcoded accessions, no PII.

NCBI Entrez policy
-------------------
NCBI's E-utilities require an identifying email address on every request
(so NCBI can contact you if a script is misbehaving / hitting rate limits).
This script does NOT hardcode a real email. You must supply one yourself,
either via --email or the NCBI_EMAIL environment variable. See the
--email placeholder below.

Addgene note (IMPORTANT - read before assuming this script covers it)
-----------------------------------------------------------------------
Addgene is a very common source of plasmid/vector sequences, but Addgene
has NO clean public programmatic API for bulk/scripted sequence retrieval.
Their plasmid pages are backed by a web UI (and SnapGene/GenBank file
downloads gated behind a session/click-through, sometimes requiring you
to select "depositor full sequence" vs "Addgene full sequence"). There is
no documented, stable REST endpoint you can hit like Entrez efetch.

  -> If your vector is an Addgene plasmid: go to
     https://www.addgene.org/<plasmid-id>/  in a browser, and manually
     download the GenBank (.gb) file from the "Sequences" tab. This
     script will happily accept that file for downstream steps once you
     have it locally - it just can't fetch it for you automatically.

  -> If your vector also has an NCBI accession (some Addgene plasmids
     cross-reference one, e.g. in the plasmid's "Sequences" or
     publication), use this script with that accession instead.

Usage
-----
    python fetch_public_vector.py <accession> [--format genbank|fasta]
                                   [--email <YOUR_EMAIL placeholder>]
                                   [--api-key NCBI_API_KEY]
                                   [--out OUTPUT_PATH]
                                   [--db nuccore]

Examples
--------
    # GenBank record for a common cloning vector (pUC19), written as .gb
    python fetch_public_vector.py L09137 --format genbank \\
        --email your_name@your_institution.edu

    # Same, but read the email from an environment variable instead
    set NCBI_EMAIL=your_name@your_institution.edu   (Windows cmd)
    $env:NCBI_EMAIL="your_name@your_institution.edu" (PowerShell)
    export NCBI_EMAIL=your_name@your_institution.edu (bash)
    python fetch_public_vector.py L09137 --format fasta

Notes for beginners
------------------------------------------
- "Accession" = the short ID NCBI assigns to a sequence record
  (e.g. "L09137", "NC_001416.1"). You can find it on the NCBI page
  for the vector/plasmid you're looking for.
- This script only reads PUBLIC records. It cannot fetch private,
  unpublished, or restricted sequences.
- Always double check the fetched sequence (length, features, source
  organism) against the vector's known map before using it in
  downstream primer design - public records occasionally have
  submitter annotation errors.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# --- Placeholder shown in --help / error messages. Never a real address. ---
EMAIL_PLACEHOLDER = "YOUR_EMAIL@YOUR_INSTITUTION.EDU"

# Recognized output formats -> (Entrez rettype, rettmode, file extension)
_FORMATS = {
    "genbank": ("gb", "text", ".gb"),
    "fasta": ("fasta", "text", ".fasta"),
}


def _fail(msg: str, code: int = 1) -> "None":
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(code)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fetch_public_vector.py",
        description=(
            "Fetch a PUBLIC vector/plasmid sequence record from NCBI by "
            "accession, using Biopython's Bio.Entrez. Addgene has no clean "
            "public API - see the module docstring for the manual-download "
            "workaround."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "accession",
        help="NCBI accession number of the vector/plasmid record, "
        "e.g. L09137 or NC_001416.1",
    )
    parser.add_argument(
        "--format",
        choices=sorted(_FORMATS.keys()),
        default="genbank",
        help="Output format (default: genbank)",
    )
    parser.add_argument(
        "--email",
        default=None,
        metavar="YOUR_EMAIL",
        help=(
            "Email address required by NCBI Entrez for every request "
            f"(placeholder: {EMAIL_PLACEHOLDER}). Do NOT hardcode a real "
            "email into scripts/version control - pass it here or set the "
            "NCBI_EMAIL environment variable instead. Required."
        ),
    )
    parser.add_argument(
        "--api-key",
        default=None,
        metavar="NCBI_API_KEY",
        help=(
            "Optional NCBI API key (raises the rate limit from 3 to 10 "
            "requests/sec). Falls back to the NCBI_API_KEY environment "
            "variable if not given. Not required for occasional single "
            "fetches like this."
        ),
    )
    parser.add_argument(
        "--db",
        default="nuccore",
        help=(
            "Entrez database to query (default: nuccore, the standard "
            "nucleotide database that holds GenBank plasmid/vector "
            "records). Rarely needs to change."
        ),
    )
    parser.add_argument(
        "--out",
        default=None,
        metavar="PATH",
        help=(
            "Output file path. Default: '<accession>.<ext>' in the "
            "current directory, extension chosen from --format."
        ),
    )
    return parser


def resolve_email(cli_email: str | None) -> str:
    """Resolve the Entrez contact email from --email, else NCBI_EMAIL env var.

    Refuses to run with the literal placeholder or no email at all - Entrez
    requires a real, working contact address per NCBI usage policy.
    """
    email = cli_email or os.environ.get("NCBI_EMAIL")
    if not email:
        _fail(
            "an email address is required by NCBI Entrez.\n"
            f"  Pass --email your_name@your_institution.edu\n"
            f"  or set the NCBI_EMAIL environment variable.\n"
            f"  (placeholder shown in --help: {EMAIL_PLACEHOLDER} - "
            "do not use this literally, it is not a real address.)"
        )
    if email.strip().upper() == EMAIL_PLACEHOLDER.upper():
        _fail(
            f"'{EMAIL_PLACEHOLDER}' is a placeholder, not a real email. "
            "Replace it with your actual address."
        )
    return email


def fetch_record(
    accession: str,
    db: str,
    rettype: str,
    retmode: str,
    email: str,
    api_key: str | None,
) -> str:
    """Fetch a record from NCBI Entrez and return the raw text content."""
    try:
        from Bio import Entrez
    except ImportError:
        _fail(
            "Biopython is not installed. Install it with:\n"
            "  pip install biopython"
        )
        raise  # unreachable, keeps type checkers happy

    Entrez.email = email
    if api_key:
        Entrez.api_key = api_key

    try:
        with Entrez.efetch(
            db=db, id=accession, rettype=rettype, retmode=retmode
        ) as handle:
            data = handle.read()
    except Exception as exc:  # noqa: BLE001 - surface NCBI/network errors plainly
        _fail(
            f"failed to fetch accession '{accession}' from NCBI ({db}): {exc}\n"
            "  Check that the accession exists and is public, and that "
            "your email/network are valid.\n"
            "  If this is an Addgene-only plasmid (no NCBI accession), "
            "see the Addgene note in this script's docstring - download "
            "it manually from the Addgene plasmid page instead."
        )
        raise  # unreachable

    if not data or not data.strip():
        _fail(
            f"NCBI returned an empty record for accession '{accession}'. "
            "Double-check the accession is correct and public."
        )

    return data


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    fmt = args.format
    rettype, retmode, ext = _FORMATS[fmt]

    email = resolve_email(args.email)
    api_key = args.api_key or os.environ.get("NCBI_API_KEY")

    out_path = Path(args.out) if args.out else Path(f"{args.accession}{ext}")

    print(
        f"Fetching accession '{args.accession}' from NCBI "
        f"(db={args.db}, format={fmt}) ...",
        file=sys.stderr,
    )

    data = fetch_record(
        accession=args.accession,
        db=args.db,
        rettype=rettype,
        retmode=retmode,
        email=email,
        api_key=api_key,
    )

    out_path.write_text(data, encoding="utf-8")
    print(f"Saved -> {out_path.resolve()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
