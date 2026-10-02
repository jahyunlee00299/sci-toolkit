"""Regression tests for scripts/_stdio.py (the one UTF-8 stdout/stderr helper).

  1. Idempotent and safe on streams that cannot be reconfigured (io.StringIO,
     None, an object whose reconfigure raises).
  2. Refutation under a legacy codepage: with PYTHONIOENCODING=cp949 a bare
     print of a character cp949 cannot encode dies with UnicodeEncodeError
     (control), and the same print after force_utf8() succeeds and emits UTF-8.
  3. Converted entry points survive the same cp949 environment end to end.
  4. Ratchet: no root-level file (scripts/, tests/, install/, evals/, doctor.py)
     carries its own `.reconfigure(` call any more.
"""
import io
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import _stdio  # noqa: E402

NON_CP949 = "emoji \U0001F600 em-dash — hangul 한글"


def _run(code, env_extra=None):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "cp949"
    env.pop("PYTHONUTF8", None)
    env.update(env_extra or {})
    return subprocess.run([sys.executable, "-c", code], capture_output=True,
                          env=env, timeout=60)


def test_stringio_untouched_and_idempotent():
    buf = io.StringIO()
    _stdio.force_utf8([buf])
    _stdio.force_utf8([buf])
    buf.write(NON_CP949)
    assert buf.getvalue() == NON_CP949


def test_none_and_raising_streams_do_not_raise():
    class Raises:
        def reconfigure(self, **kw):
            raise ValueError("cannot")

    _stdio.force_utf8([None, Raises(), object()])


def test_idempotent_on_real_text_stream():
    raw = io.BytesIO()
    s = io.TextIOWrapper(raw, encoding="cp949", errors="strict")
    _stdio.force_utf8([s])
    _stdio.force_utf8([s])
    s.write(NON_CP949)
    s.flush()
    assert raw.getvalue().decode("utf-8") == NON_CP949


def test_control_cp949_print_fails_without_helper():
    r = _run(f"print({NON_CP949!r})")
    assert r.returncode != 0 and b"UnicodeEncodeError" in r.stderr


def test_cp949_print_succeeds_with_helper():
    code = (f"import sys; sys.path.insert(0, {str(SCRIPTS)!r}); import _stdio; "
            f"_stdio.force_utf8(); print({NON_CP949!r})")
    r = _run(code)
    assert r.returncode == 0, r.stderr
    assert r.stdout.decode("utf-8").strip() == NON_CP949


def test_converted_script_survives_cp949():
    # connectivity_check prints a report containing non-cp949 punctuation paths-free;
    # use a tiny converted script with deterministic output instead.
    r = subprocess.run([sys.executable, str(SCRIPTS / "env_detect.py"), "--json"],
                       capture_output=True, timeout=60,
                       env={**os.environ, "PYTHONIOENCODING": "cp949"})
    assert b"UnicodeEncodeError" not in r.stderr
    assert r.stdout.decode("utf-8")  # valid UTF-8 JSON line


def test_no_private_reconfigure_blocks_left():
    offenders = []
    files = [ROOT / "doctor.py"]
    for d in ("scripts", "tests", "install", "evals", "doctor_lib"):
        files += (ROOT / d).rglob("*.py")
    for p in files:
        if p.name in ("_stdio.py", "test_stdio.py"):
            continue
        if ".reconfigure(" in p.read_text(encoding="utf-8", errors="replace"):
            offenders.append(str(p.relative_to(ROOT)))
    assert not offenders, f"use scripts/_stdio.force_utf8 instead: {offenders}"
