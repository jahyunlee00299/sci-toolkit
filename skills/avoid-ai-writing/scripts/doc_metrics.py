"""Prose metrics for markdown guides: em dash, bold, bullets, sentence length per doc.

usage: python doc_metrics.py FILE [FILE ...]   (prints one TSV row per file)
Code blocks, tables, link targets and blockquote markers are stripped first.
"""
import re
import sys
from pathlib import Path

DASH = "—"


def strip_md(text):
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", " ", text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("|")]
    return "\n".join(lines)


def metrics(path):
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    body = strip_md(raw)
    words = len(body.split())
    kw = max(words, 1) / 1000
    lines = [ln for ln in body.splitlines() if ln.strip()]
    bullets = sum(1 for ln in lines if re.match(r"\s*([-*+]|\d+\.)\s", ln))
    quotes = sum(1 for ln in lines if ln.lstrip().startswith(">"))
    heads = [ln for ln in lines if ln.startswith("#")]
    head_dash = sum(1 for h in heads if DASH in h or " -- " in h)
    prose = re.sub(r"^\s*(#+|>|[-*+]|\d+\.)\s*", "", body, flags=re.M)
    sents = [s for s in re.split(r"(?<=[.!?。])\s+|\n+", prose) if len(s.split()) > 2]
    lens = [len(s.split()) for s in sents] or [0]
    mean = sum(lens) / len(lens)
    sd = (sum((x - mean) ** 2 for x in lens) / len(lens)) ** 0.5
    return {
        "file": Path(path).name,
        "words": words,
        "emdash_per_1k": round((raw.count(DASH) + raw.count(" -- ")) / kw, 1),
        "bold_per_1k": round(len(re.findall(r"\*\*[^*\n]+\*\*", raw)) / kw, 1),
        "bullet_share": round(bullets / max(len(lines), 1), 2),
        "quote_share": round(quotes / max(len(lines), 1), 2),
        "heading_dash": head_dash,
        "sent_mean": round(mean, 1),
        "sent_sd": round(sd, 1),
    }


if __name__ == "__main__":
    rows = [metrics(p) for p in sys.argv[1:]]
    if rows:
        print("\t".join(rows[0].keys()))
        for r in rows:
            print("\t".join(str(v) for v in r.values()))
