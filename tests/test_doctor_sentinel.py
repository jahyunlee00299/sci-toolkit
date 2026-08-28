#!/usr/bin/env python3
"""doctor.py SENTINEL check regression test — both must-block AND must-not-block.

Run: python tests/test_doctor_sentinel.py   (exit 0 = pass)

Confirms the check wasn't loosened just to make it pass.
"""
import importlib.util, sys
from pathlib import Path

# The default Windows console is cp949, which crashes on Korean/symbol output.
# Force UTF-8. Use reconfigure rather than TextIOWrapper — a wrapper owns the
# underlying stream, so once this module is imported and then garbage
# collected, it closes the caller's stdout along with it. While this file
# used a wrapper, `pytest tests/` died outright during collection
# (ValueError: I/O operation on closed file — measured 2026-08-08). doctor.py
# runs each test as a subprocess, so this failure never showed up there — it
# only surfaced on the very first command a fresh clone runs. Every other
# test file was already using reconfigure.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

spec = importlib.util.spec_from_file_location(
    "doctor", str(Path(__file__).resolve().parent.parent / "doctor.py"))
doctor = importlib.util.module_from_spec(spec)
sys.modules["doctor"] = doctor   # dataclass needs the module registered
spec.loader.exec_module(doctor)

MUST_BLOCK = [  # real leaks — must be detected
    ('api_key = "sk-or-v1-9f3ab21c77de40b8a1e6c5d4f0928374"', "real openrouter-style key"),
    ('API_KEY="AKIA5FJ39DKS02MXZQ7B"', "AWS-style access key"),
    ("apikey: 'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6'", "32-char literal"),
    ('secret_key="hunter2hunter2hunter2hunter2"', "secret_key literal"),
    ('sk-abcdefghijklmnopqrstuvwxyz012345', "bare sk- token"),
    ('ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', "github PAT"),
    # --- 2026-08-08 mutation testing: deleting the vendor rules below still
    # left the test green. In other words, the rules existed but nobody had
    # pinned them in place, so a future loosening would sail straight through
    # the gate. Worse, AKIA/AIzaSy/github_pat weren't even **present** in
    # this scanner to begin with — hooks/secret_scan_guard.sh already caught
    # them, so looking at just one layer made it look protected. Each case
    # here is a 'bare token', not an assignment. Written as an assignment,
    # the api_key= rule would catch it instead, and deleting the actual
    # vendor rule would still pass.
    ('xoxb-123456789012-1234567890123-AbCdEfGhIjKlMnOpQrSt', "bare Slack bot token"),
    ('gho_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', "bare GitHub OAuth token"),
    ('AKIA5FJ39DKS02MXZQ7B', "bare AWS access key (no assignment)"),
    ('AIzaSyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q', "bare Google API key"),
    ('github_pat_11ABCDEFG0abcdefghijkl_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
     "bare fine-grained GitHub PAT"),
    ('access_token = "ya29.a0ARrdaM_realish_token_value_here123"', "oauth token"),
    # --- The 4 below are bypass inputs that actually got through during
    # adversarial verification (2026-07-23). Back when placeholder markers
    # were checked as a 'substring', a real key value passed as soon as a
    # marker string happened to appear inside it. Never delete these.
    ('api_key="my-real-project1-secret-abcdefghijklmno"', "bypass: value contains 'project1'"),
    ('api_key="THIS-IS-KEY-HERE-BUT-ALSO-REAL-abcd1234"', "bypass: value contains 'key-here'"),
    ('api_key="example-a83f2c9d41b7e6058fa2"', "bypass: value contains 'example'"),
    ('api_key="test_9f3ab21c77de40b8a1e6c5d4"', "bypass: value contains 'test'"),
    # --- Bypass found in the second-round adversarial verification
    # (2026-07-23). A new hole created by the first-round fix itself.
    # (1) A value made up of only digits was unconditionally treated as
    #     filler (`w.isdigit()` had an unbounded exception).
    # (2) SCREAMING_SNAKE_CASE was read as an env-var name even when it had
    #     an opaque token appended after it.
    # This is a case where the defense logic itself created a new bypass
    # path — never delete these.
    ('secret_key = "123456789012345678901234567890"', "bypass: 30-digit pure number"),
    ('api_key="98765432109876543210"', "bypass: 20-digit pure number"),
    ('access_token = "1234567890123456"', "bypass: 16-digit number"),
    ('api_key = "MY_SECRET_KEY_VALUE_ABCD1234"', "bypass: SCREAMING_SNAKE + opaque token"),
    ('api_key="AUTH_TOKEN_9F3AB21C77DE40B8"', "bypass: SCREAMING_SNAKE + hex token"),
    ('api_key="sk-1234567890123456789012"', "bypass: digits after sk- prefix"),
    ('api_key="sk-or-v1-000000000000000000"', "bypass: digits after vendor prefix"),
]
MUST_NOT_BLOCK = [  # false positives that must NOT happen — doc/code idioms
    ('OPENROUTER_API_KEY=your-api-key-here', "placeholder hyphenated"),
    ('api_key="PARALLEL_API_KEY"', "value is env-var NAME"),
    ('api_key = OPENROUTER_API_KEY', "unquoted env-var name"),
    ("if line.startswith('OPENROUTER_API_KEY='):\n    api_key = line.split('=', 1)[1]",
     "regex spanning newline into code"),
    ('api_key="your_api_key_here"', "underscore placeholder"),
    ('api_key = os.environ.get("OPENROUTER_API_KEY")', "os.environ read"),
    ('client = Parallel(api_key="...")', "ellipsis placeholder"),
    ('sk-or-v1-your-api-key-here', ".env.example line"),
    # A placeholder carrying a vendor prefix (sk-or-v1-). Judging "real key"
    # from the prefix alone would turn the entire document into a false
    # positive (measured 2026-07-23).
    ("export OPENROUTER_API_KEY='sk-or-v1-your-key-here'", "vendor prefix + placeholder"),
    ('OPENROUTER_API_KEY=sk-or-v1-your-api-key-here', "vendor prefix (unquoted)"),
    # When the numeric-value rule was narrowed (see MUST_BLOCK above),
    # catching even short index suffixes would false-positive across whole
    # documents. A short number must still be treated as filler.
    ('api_key="your-key-2"', "short numeric suffix (index)"),
    ('api_key = "example_key_1"', "short numeric suffix (underscore)"),
    ('api_key="PARALLEL_API_KEY"', "pure env-var name (no digits)"),
]

def detected(text):
    """True if either of doctor's two checks flags it."""
    import re
    hard = re.compile(r"api_key\s*=\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE)
    a = any(not doctor._is_placeholder(m.group(0))
            for m in doctor.API_KEY_RE.finditer(text))
    b = any(not doctor._is_placeholder(m.group(0)) for m in hard.finditer(text))
    return a or b

fails = 0
print("=== MUST BLOCK (real keys — detection mandatory) ===")
for text, label in MUST_BLOCK:
    ok = detected(text)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        fails += 1
        print(f"        missed: {text[:70]!r}")

print("\n=== MUST NOT BLOCK (placeholders — false positives forbidden) ===")
for text, label in MUST_NOT_BLOCK:
    ok = not detected(text)
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        fails += 1
        print(f"        false positive: {text[:70]!r}")

print(f"\n{'ALL PASS' if fails == 0 else str(fails) + ' FAILURE(S)'}")
sys.exit(1 if fails else 0)
