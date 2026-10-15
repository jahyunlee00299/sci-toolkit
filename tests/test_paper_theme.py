#!/usr/bin/env python3
"""Regression test for skills/publication-figures/scripts/paper_theme.py.

Run: python tests/test_paper_theme.py   (exit 0 = pass)

Cases:
  1. apply() sets the Prism look (inward ticks, 1.8 pt axes, 600 dpi, frameless legend).
  2. muted() keeps hue and lightness and lowers saturation by the stated factor.
  3. An unregistered entity raises instead of silently getting a colour; a registered one keeps colour and style.
  4. plot_series + legend + panel + style_axis + save write a PNG and an SVG without a legend/marker error.
"""
import colorsys
import sys
import tempfile
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.append(str(_Path(__file__).resolve().parents[1] / "scripts"))  # shared helper: scripts/_stdio.py
from _stdio import force_utf8  # noqa: E402
force_utf8()  # UTF-8 stdout/stderr on legacy Windows codepages

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "publication-figures" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import to_rgb  # noqa: E402

import paper_theme as pt  # noqa: E402

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


# 1. rcParams
pt.apply()
rc = matplotlib.rcParams
check(rc["xtick.direction"] == "in" and rc["ytick.direction"] == "in", "ticks must point inward")
check(rc["axes.linewidth"] == 1.8, "axes line width must be 1.8 pt")
check(rc["savefig.dpi"] == 600, "savefig dpi must be 600")
check(rc["legend.frameon"] is False, "legend must be frameless")
check(not rc["axes.spines.top"] and not rc["axes.spines.right"], "top and right spines must be off")

# 2. muted colour keeps hue and lightness, scales saturation
h0, l0, s0 = colorsys.rgb_to_hls(*to_rgb("#0072B2"))
h1, l1, s1 = colorsys.rgb_to_hls(*to_rgb(pt.muted("#0072B2")))
check(abs(h0 - h1) < 0.01 and abs(l0 - l1) < 0.01, "muting must keep hue and lightness")
check(abs(s1 / s0 - pt.MUTE_KEEP) < 0.02, f"saturation ratio {s1 / s0:.3f} != {pt.MUTE_KEEP}")

# 3. registry
try:
    pt.series_style("never registered")
    check(False, "an unregistered entity must raise KeyError")
except KeyError:
    pass
pt.register_series("MBP-AgMdh", pt.OKABE_ITO["orange"], "-")
check(pt.series_style("MBP-AgMdh") == (pt.OKABE_ITO["orange"], "-"), "registered colour/style must round-trip")
check(pt.series_style("no enzyme")[1] == ":", "the blank trace must be dotted")

# 4. a whole figure renders and saves both formats
fig, ax = plt.subplots(figsize=(3.2, 2.4))
xs = list(range(0, 91))
line, = pt.plot_series(ax, xs, [0.5 - 0.003 * x for x in xs], "WT", label="WT", markevery=5)
pt.plot_series(ax, xs, [0.5] * len(xs), "no enzyme", label="No enzyme", markevery=5, zorder=2)
ax.set_xlim(0, 90)
ax.set_ylim(0, 0.75)
pt.legend(ax)
pt.panel(ax, "a")
pt.style_axis(ax)
check(line.get_linestyle() == "-" and line.get_markevery() == 5, "plot_series must pass style and markevery")
with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "t.png"
    pt.save(fig, out)
    check(out.stat().st_size > 5000, "PNG was not written")
    check(out.with_suffix(".svg").stat().st_size > 1000, "SVG was not written")
plt.close(fig)

# 5. figure_lint accepts the module itself (theme exemption) and dpi above 300 in a render script
import subprocess  # noqa: E402

lint = SCRIPTS / "figure_lint.py"
r = subprocess.run([sys.executable, str(lint), str(SCRIPTS / "paper_theme.py")], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
check(r.returncode == 0, "figure_lint must pass paper_theme.py itself: " + r.stdout[-300:])
with tempfile.TemporaryDirectory() as tmp:
    demo = Path(tmp) / "render_demo.py"
    demo.write_text("import matplotlib.pyplot as plt\nfig, ax = plt.subplots(constrained_layout=True)\n"
                    "fig.savefig('a.png', dpi=600, bbox_inches='tight')\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(lint), str(demo)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    check("savefig missing" not in r.stdout, "dpi=600 must satisfy the savefig check: " + r.stdout[-300:])

if failures:
    print("FAIL")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("PASS: paper_theme (rcParams, muted colours, registry, full render)")
