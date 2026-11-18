"""NEB Tm Calculator lookup — the polymerase-specific Tm/Ta a Q5 cloning run actually needs.

`iPCRDesignerBase.calc_tm` is a generic salt-corrected nearest-neighbor Tm
(Na+ 50 mM, Mg2+ 2 mM, primer 500 nM). Q5 cloning is the default here, and its reaction
buffer is not those conditions, so the built-in value is for RELATIVE comparison only
(which primer is the limiter, how far blocks are apart). Any annealing temperature
that goes to the bench comes from here.

Measured once against 20 real primer pairs from a variant library:
  * built-in calc_tm UNDERESTIMATES NEB Q5 Tm by +1.1 C on average
    (mutant primers +0.7..+1.8; shared primers +1.3 avg, +0.7..+2.5)
  * NEB CAPS the recommended Ta at 72 C for Q5. Every pair whose Tm exceeded 72
    came back with ta == 72.0 exactly. A "Ta 74 C" recommendation is therefore not
    a Q5 setting at all — at that point the run is a 2-step protocol
    (denature, then combined anneal/extend at 72 C).

Endpoint (public, used by tmcalculator.neb.com):
  GET https://tmapi.neb.com/tm?seq1=<S1>&seq2=<S2>&prodcode=<code>&conc=<uM>
  -> {"success": true, "data": {"tm1", "tm1min", "tm1max", "tm2", ..., "ta"}}

Traps found while wiring this up:
  * `prodcode` is mandatory; omitting it returns 400 "missing product type or prodcode".
  * `conc` is mandatory TOO, but omitting it returns a 500 with a Node stack trace
    (`ReferenceError: conc is not defined`), not a 400 — do not read that 500 as
    "the service is down".
  * `/tm/batch` with a `seqpairs` JSON array 404s; there is no working batch form
    at that path. Loop single calls with a small delay.

This sends primer sequences to an external service. Unpublished designs leave the
machine, so `lookup_pair` requires `consent=True` and the caller is responsible for
having asked. Nothing here is cached to disk.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

__all__ = ["NEB_PRODCODES", "NEB_TA_CAP_C", "CALC_TM_OFFSET_C", "lookup_pair", "lookup_pairs"]

API = "https://tmapi.neb.com/tm"

#: Product codes accepted by the endpoint. Q5 is the default product.
NEB_PRODCODES = {
    "q5": "q5-0",
    "q5u": "q5u-0",
    "phusion": "phusion-0",
    "onetaq": "onetaq-0",
    "taq": "taq-0",
    "longamp": "longamp-0",
    "q5-hotstart": "q5hs-0",
}

#: NEB never recommends an annealing temperature above this for Q5 (measured once, 20 pairs).
NEB_TA_CAP_C = 72.0

#: calc_tm minus NEB Q5 Tm, averaged over 20 real pairs (20 pairs). calc_tm reads LOW.
CALC_TM_OFFSET_C = -1.1


class NebTmError(RuntimeError):
    """The endpoint refused or could not be reached."""


def _get(params: dict, timeout: float, retries: int) -> dict:
    url = f"{API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url, headers={"User-Agent": "curl/8", "Accept": "application/json"}
    )
    last = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if not payload.get("success"):
                raise NebTmError(payload.get("error") or "unsuccessful response")
            return payload["data"]
        except NebTmError:
            raise
        except Exception as exc:  # network, 4xx/5xx, malformed JSON
            last = exc
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    raise NebTmError(f"{type(last).__name__}: {last}")


def lookup_pair(
    seq1: str,
    seq2: str,
    *,
    consent: bool,
    product: str = "q5",
    conc_um: float = 0.5,
    timeout: float = 30.0,
    retries: int = 2,
) -> dict:
    """Tm of each primer and NEB's recommended Ta for the pair.

    Parameters
    ----------
    seq1, seq2 : str
        The two primers of one reaction, 5'->3'. Both are required: NEB's Ta is a
        property of the pair, not of one oligo.
    consent : bool
        Must be True. These sequences are sent to NEB. Ask the sequence owner first.
    product : str
        Key of :data:`NEB_PRODCODES`, or a raw prodcode such as ``"q5-0"``.
    conc_um : float
        Primer concentration in micromolar (NEB's default is 0.5).

    Returns
    -------
    dict
        ``{"tm1", "tm2", "ta", "ta_is_capped", ...}`` — the endpoint's own fields plus
        ``ta_is_capped``, True when ``ta`` sits at :data:`NEB_TA_CAP_C` because the
        primers are hotter than NEB will anneal. A capped pair should run as 2-step.

    Raises
    ------
    ValueError  : consent not given, empty sequence, or unknown product
    NebTmError  : the endpoint refused or was unreachable
    """
    if not consent:
        raise ValueError(
            "lookup_pair sends primer sequences to NEB. Ask the owner, then pass consent=True."
        )
    for name, seq in (("seq1", seq1), ("seq2", seq2)):
        if not seq or set(seq.upper()) - set("ACGT"):
            raise ValueError(f"{name} must be a non-empty ACGT string, got {seq!r}")

    prodcode = NEB_PRODCODES.get(product, product)
    if not prodcode or "-" not in prodcode:
        raise ValueError(f"unknown product {product!r}; use one of {sorted(NEB_PRODCODES)} or a raw prodcode")

    data = _get(
        {"seq1": seq1.upper(), "seq2": seq2.upper(), "prodcode": prodcode, "conc": conc_um},
        timeout,
        retries,
    )
    ta = data.get("ta")
    data["ta_is_capped"] = bool(ta is not None and float(ta) >= NEB_TA_CAP_C)
    data["prodcode"] = prodcode
    return data


def lookup_pairs(
    pairs,
    *,
    consent: bool,
    product: str = "q5",
    conc_um: float = 0.5,
    delay_s: float = 0.4,
    on_error: str = "raise",
):
    """Call :func:`lookup_pair` over an iterable of ``(label, seq1, seq2)``.

    There is no working batch endpoint, so this loops with ``delay_s`` between calls.
    ``on_error="collect"`` records ``{"label", "error"}`` instead of raising, so one bad
    pair does not discard the rest of a long run.
    """
    if on_error not in ("raise", "collect"):
        raise ValueError("on_error must be 'raise' or 'collect'")
    results = []
    for label, seq1, seq2 in pairs:
        try:
            row = lookup_pair(
                seq1, seq2, consent=consent, product=product, conc_um=conc_um
            )
            row["label"] = label
        except (NebTmError, ValueError) as exc:
            if on_error == "raise":
                raise
            row = {"label": label, "error": f"{type(exc).__name__}: {exc}"}
        results.append(row)
        if delay_s:
            time.sleep(delay_s)
    return results
