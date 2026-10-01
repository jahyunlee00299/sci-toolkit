"""One streaming SHA-256 of a file, shared by the manifest writer and the manifest verifier.

`scripts/make_checksums.py` writes SHA256SUMS and `doctor_lib.checks_repo`
verifies it. They used to carry a byte-identical copy of this loop each; if one
ever changed chunking or digest form the manifest would be written one way and
checked another. Both now import this function.

Deliberately NOT shared with the skill-local hashers
(`skills/manuscript-pipeline/scripts/figure_provenance.py`,
`skills/scientific-validation/scripts/check_raw.py`): skills are installed
individually (`install.py --skills <name>`), so a skill script importing from
here would break the moment the repo root is absent. Those two differ anyway
(a 12-char prefix with an "ERR" sentinel; a 16-char display form).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 1 << 20  # 1 MiB: bounded memory for large raw-data files


def sha256_file(path: Path | str) -> str:
    """Hex SHA-256 of the file's bytes (streamed; raises OSError if unreadable)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()
