"""Check that a prose edit changed no code, link, inline code, table row or digit token.

usage: python preserve_check.py REPO_ROOT FILE [FILE ...]   (FILE relative to REPO_ROOT)
Compares the working-tree file against `git show HEAD:FILE`. Exit 1 on any difference.
Also checks that every '#anchor' link in the file still matches a heading slug.
"""
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path


def slug(h):
    h = re.sub(r"[`*_\[\]()!:.,/&?'\"+<>=%]", "", h.strip().lower())
    return re.sub(r"\s", "-", h)


def parts(text):
    fences = re.findall(r"```.*?```", text, flags=re.S)
    no_fence = re.sub(r"```.*?```", " ", text, flags=re.S)
    return {
        "code fences": Counter(fences),
        "inline code": Counter(re.findall(r"`[^`\n]+`", no_fence)),
        "link targets": Counter(re.findall(r"\]\(([^)]+)\)", no_fence)),
        "bare urls": Counter(re.findall(r"https?://[^\s)>\]]+", no_fence)),
        "table rows": Counter(ln.strip() for ln in no_fence.splitlines() if ln.lstrip().startswith("|")),
        "digit tokens": Counter(re.findall(r"\d+(?:\.\d+)?", no_fence)),
    }


def main(root, files):
    bad = 0
    for f in files:
        new = (Path(root) / f).read_text(encoding="utf-8")
        old = subprocess.run(
            ["git", "-C", root, "show", f"HEAD:{f}"],
            capture_output=True, encoding="utf-8", errors="replace",
        ).stdout
        po, pn = parts(old), parts(new)
        for k in po:
            if po[k] != pn[k]:
                lost, gained = po[k] - pn[k], pn[k] - po[k]
                print(f"DIFF {f} [{k}] lost={dict(list(lost.items())[:4])} gained={dict(list(gained.items())[:4])}")
                bad += 1
        heads = {slug(m) for m in re.findall(r"^#+\s+(.*)$", new, flags=re.M)}
        for a in re.findall(r"\]\(#([^)]+)\)", new):
            if a not in heads:
                print(f"ANCHOR {f}: #{a} matches no heading")
                bad += 1
        print(f"{'OK  ' if not bad else 'CHECK'} {f}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2:]))
