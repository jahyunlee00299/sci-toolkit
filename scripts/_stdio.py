#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_stdio — the one place root-level code forces UTF-8 on stdout/stderr.

Why this exists
---------------
A Windows console defaults to a legacy codepage (cp949, cp1252, ...) that
cannot encode the dashes, arrows and Korean text these tools print, so a bare
``print`` dies mid-report with ``UnicodeEncodeError``. Sixty-odd files under
``scripts/``, ``tests/``, ``install/``, ``evals/`` and ``doctor.py`` each carried
their own copy of the same ``reconfigure`` block (with four slightly different
exception lists). This module is the single copy.

Why ``reconfigure`` and not a ``TextIOWrapper``
-----------------------------------------------
A wrapper takes ownership of the underlying buffer: once it is garbage
collected after the importing module finishes, it closes the caller's stdout
too (measured: "I/O operation on closed file"). ``reconfigure`` mutates the
same stream object in place.

Scope
-----
Root-level code only (``scripts/``, ``tests/``, ``install/``, ``evals/``,
``doctor.py``). Skills under ``skills/`` install stand-alone and must not
import this module; their scripts keep their own copy of the block.
"""
from __future__ import annotations

import sys
from typing import Iterable, Optional


def force_utf8(streams: Optional[Iterable[object]] = None) -> None:
    """Reconfigure ``streams`` (default: stdout and stderr) to UTF-8, errors='replace'.

    Idempotent. A stream that cannot be reconfigured (``io.StringIO``, a
    pytest capture object, a closed or detached stream, a ``None`` stdout under
    ``pythonw``) is left untouched and never raises.
    """
    if streams is None:
        streams = (sys.stdout, sys.stderr)
    for stream in streams:
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - any failure means "leave it as is"
            pass
