#!/usr/bin/env python3
"""Regression test for caption_style.py and figure_lint.py's caption-sidecar lint.

Run: python tests/test_caption_style.py   (exit 0 = pass)

Cases:
  1. S-prefixed labels (Fig. S3., Table S3., Fig. S9b.) are recognised.
  2. A caption with a question-word + colon title and interpretive sentences is flagged
     (two HIGH title findings, at least three MED interpretive hits); the corrected
     caption is clean.
  3. False-positive guards: "1:1" ratio, "vs." abbreviation, bare "rather than".
  4. figure_lint reads the `*.caption.txt` sidecar a render script writes: HIGH for the bad
     caption (script FAILs), nothing for the good one.
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.append(str(_Path(__file__).resolve().parents[1] / "scripts"))  # shared helper: scripts/_stdio.py
from _stdio import force_utf8  # noqa: E402
force_utf8()  # UTF-8 stdout/stderr on legacy Windows codepages

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "publication-figures" / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cs = _load("caption_style")
fl = _load("figure_lint")
fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


# 1. labels
m = cs.LABEL_RE.match("Fig. S3. Foo")
check("label Fig. S3", bool(m) and m.group(2).upper() == "S" and m.group(3) == "3")
check("label Table S3", bool(cs.LABEL_RE.match("Table S3. Foo")))
m = cs.LABEL_RE.match("Fig. S9b. Foo")
check("label Fig. S9b keeps suffix", bool(m) and m.group(4) == "b")
m = cs.LABEL_RE.match("Figure 2. Foo")
check("label Figure 2 has no S", bool(m) and m.group(2) == "")

# 2. bad vs good
bad = cs.analyze(cs.EXAMPLE_BAD)
check("bad: HIGH question title", any(f["sev"] == "HIGH" and f["code"] == "TITLE_QUESTION" for f in bad))
check("bad: HIGH colon title", any(f["sev"] == "HIGH" and f["code"] == "TITLE_COLON" for f in bad))
check("bad: >=3 interpretive hits", sum(f["code"] == "INTERPRETIVE" for f in bad) >= 3)
check("good: clean", not cs.analyze(cs.EXAMPLE_GOOD))

# 3. false-positive guards
check("ratio 1:1 is not a colon title", not cs.check_title_form("Fig. 2. Yield at a 1:1 substrate ratio."))
check("'vs.' does not end the title",
      cs.split_caption("Fig. 5. Titer vs. yield of the front. More text.")[1] == "Titer vs. yield of the front.")
check("bare 'rather than' is not an interpretive flag", not cs.scan_interpretive("A was tested rather than B."))

# 4. figure_lint sidecar wiring
tmp = Path(tempfile.mkdtemp(prefix="capstyle_"))
(tmp / ".git").mkdir()
(tmp / "out").mkdir()
script = tmp / "render_x.py"
script.write_text(
    "import matplotlib.pyplot as plt\n"
    "fig, ax = plt.subplots(constrained_layout=True)\n"
    "open('out/SI_X.caption.txt', 'w').write('cap')\n"
    "fig.savefig('out/x.png', dpi=300, bbox_inches='tight')\n", encoding="utf-8")
(tmp / "out" / "SI_X.caption.txt").write_text(cs.EXAMPLE_BAD, encoding="utf-8")
res = fl.lint_script(script)
sev = [f["sev"] for f in res["findings"]["caption_style"]]
check("figure_lint: bad sidecar -> HIGH, script FAILs", "HIGH" in sev and not res["pass"], str(res["counts"]))
check("figure_lint: interpretive hits are MED", sev.count("MED") >= 3)
(tmp / "out" / "SI_X.caption.txt").write_text(cs.EXAMPLE_GOOD, encoding="utf-8")
res = fl.lint_script(script)
check("figure_lint: good sidecar -> clean", res["pass"] and not res["findings"]["caption_style"], str(res["counts"]))

print("ALL PASS" if not fails else f"FAILED ({len(fails)})")
sys.exit(0 if not fails else 1)
