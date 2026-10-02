"""Source and backend modules behind `scripts/fetch_academic.py`.

One module per source or backend; `cli.py` wires them to the command line:

    crossref_provider.py   Crossref metadata (habanero)
    arxiv_provider.py      arXiv search (arxiv package)
    biorxiv_provider.py    bioRxiv / medRxiv REST API
    open_access.py         Unpaywall OA lookup and PubMed Central PDF locator
    libkey.py              LibKey Nomad placeholder (Chrome MCP only)
    library_auth.py        institutional library login (Selenium, cookie cache)
    ezproxy.py             EZproxy PDF downloader and Netscape cookie loading
    pdf_identity.py        "is this the requested paper" gate and quarantine
    pdf_downloader.py      the Crossref -> Unpaywall -> PMC -> LibKey -> EZproxy waterfall
    cli.py                 argparse flags and `main`

HTTP helpers (client, rate limiter, URL safety, JSON output) stay in the skill's
shared `_common.py`. The CLI entry point stays `scripts/fetch_academic.py`, which
re-exports every name the single-file script had.
"""
