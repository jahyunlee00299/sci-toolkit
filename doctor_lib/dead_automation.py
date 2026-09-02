"""Dead-automation detector: an automation that is configured but no longer
producing output, distinguished from a healthy-but-idle one by artifact
freshness rather than log mtime."""

from __future__ import annotations

import json
import time
from pathlib import Path

from doctor_lib.result import CheckResult, STATUS_OK, STATUS_WARN


def _resolve_artifact_paths(pattern: str, root: Path) -> list[Path]:
    """Expand an artifact pattern into existing files.

    Accepts ``~`` (home-relative, the documented form) and ``*`` globs. A
    relative path is resolved against the toolkit root so a lab machine that
    installed elsewhere still works. Returns only existing regular files.
    """
    raw = (pattern or "").strip()
    if not raw:
        return []
    expanded = Path(raw).expanduser()
    if expanded.is_absolute():
        base, rel = Path(expanded.anchor), expanded.relative_to(expanded.anchor)
    else:
        base, rel = root, expanded
    parts = rel.as_posix()
    try:
        if any(ch in parts for ch in "*?["):
            return [p for p in base.glob(parts) if p.is_file()]
        cand = base / parts
        return [cand] if cand.is_file() else []
    except (OSError, ValueError):
        return []


def check_dead_automation(root: Path) -> CheckResult:
    """Detect automations that are configured but no longer producing output.

    The failure this catches is specific and recurrent: an automation breaks,
    keeps running, keeps writing "nothing new" to its log, and nobody notices
    because **zero output looks exactly like a healthy idle state**. Counting
    the log's mtime cannot tell the two apart -- healthy and dead runs both
    touch the log. So this counts the *artifact* instead: the thing the
    automation exists to produce.

    Opt-in by design. With no config/automations.json the check reports OK and
    explains how to enable it -- a user who has declared no automations has
    nothing to be stale, and a distribution must not FAIL on a machine that
    simply does not use the feature. Findings are WARN, never FAIL: staleness
    is a strong signal but the threshold is the user's estimate, not a fact.
    """
    name = "Dead automation (artifact freshness)"
    cfg_path = root / "config" / "automations.json"
    if not cfg_path.is_file():
        return CheckResult(
            name, STATUS_OK,
            "not configured -- copy config/automations.example.json to "
            "config/automations.json to have your automations checked",
        )
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return CheckResult(name, STATUS_WARN, f"config/automations.json failed to parse: {exc}")

    entries = data.get("automations") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        return CheckResult(name, STATUS_WARN, "config/automations.json has no 'automations' entries")

    now = time.time()
    stale: list[str] = []
    empty: list[str] = []
    missing: list[str] = []
    malformed: list[str] = []
    fresh = 0

    for idx, item in enumerate(entries):
        if not isinstance(item, dict):
            malformed.append(f"entry #{idx + 1}: not an object")
            continue
        label = str(item.get("name") or item.get("artifact") or f"entry #{idx + 1}")
        pattern = item.get("artifact")
        if not isinstance(pattern, str) or not pattern.strip():
            malformed.append(f"{label}: missing 'artifact'")
            continue
        try:
            max_age = float(item.get("max_age_days"))
        except (TypeError, ValueError):
            malformed.append(f"{label}: missing or non-numeric 'max_age_days'")
            continue
        if max_age <= 0:
            malformed.append(f"{label}: 'max_age_days' must be > 0")
            continue
        try:
            min_bytes = int(item.get("min_bytes", 1))
        except (TypeError, ValueError):
            min_bytes = 1

        found = _resolve_artifact_paths(pattern, root)
        if not found:
            missing.append(f"{label}: no artifact matches {pattern!r}")
            continue

        # Newest artifact decides: an automation is alive if it produced
        # anything recently, even if older outputs sit beside it.
        newest, newest_mtime, newest_size = None, -1.0, 0
        for p in found:
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_mtime > newest_mtime:
                newest, newest_mtime, newest_size = p, st.st_mtime, st.st_size
        if newest is None:
            missing.append(f"{label}: artifact matched but is unreadable ({pattern})")
            continue

        age_days = max(0.0, (now - newest_mtime) / 86400.0)
        if newest_size < min_bytes:
            # A zero-byte artifact is the "wired but never fired" signature:
            # the file gets created, nothing is ever written into it.
            empty.append(
                f"{label}: newest artifact is {newest_size}B (< {min_bytes}B) -- "
                f"produced a file but no content ({newest.name})"
            )
        elif age_days > max_age:
            stale.append(
                f"{label}: newest artifact is {age_days:.1f}d old "
                f"(threshold {max_age:g}d) -- {newest.name}"
            )
        else:
            fresh += 1

    details = empty + stale + missing + malformed
    if details:
        counts = []
        for n, word in ((len(empty), "empty"), (len(stale), "stale"),
                        (len(missing), "missing"), (len(malformed), "malformed")):
            if n:
                counts.append(f"{n} {word}")
        return CheckResult(
            name, STATUS_WARN,
            f"{', '.join(counts)} of {len(entries)} automation(s) -- "
            f"{fresh} producing normally",
            details,
        )
    return CheckResult(
        name, STATUS_OK,
        f"all {fresh} configured automation(s) produced output within their thresholds",
    )
