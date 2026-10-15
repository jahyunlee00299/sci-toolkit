"""Layout registry for journal-ppt.

A *layout* is a slide composition (pipeline rail, KPI tiles, giant number, ...) built from Deck primitives
and the active theme's roles/palette. Themes decide colors; layouts decide structure. Layouts live in
sibling modules and register themselves with @register; Deck.layout(name, **content) dispatches.

Contract for a layout function ``fn(deck, **content) -> slide``:
  * build the slide with Deck primitives (add_textbox / bullets / content_slide / ...) so autofit,
    line spacing, Arial, closed type scale and theme colors stay enforced;
  * use only the shared closed lists; the one extra size a layout may need is stat_big (54 pt), declared
    with ``extra_sizes=(STAT_BIG_PT,)`` so Deck.save() records it and qc_deck allows it for that deck;
  * name shapes that must not trip QC: decoration -> 'deco:<what>', logos -> 'logo:<x>';
  * never place anything below Y_FLOOR or inside the margins (qc_deck/qc_layout enforce this);
  * every slide gets Korean speaker notes from the caller via Deck.notes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

LAYOUTS: dict[str, "LayoutSpec"] = {}


@dataclass(frozen=True)
class LayoutSpec:
    name: str
    fn: Callable
    kind: str                       # title | divider | content | figure | data | agenda | closing
    summary: str
    extra_sizes: frozenset = field(default_factory=frozenset)
    source: str = ""                # where the design language was seen (grammar file / template)


def register(name: str, *, kind: str, summary: str, extra_sizes=(), source: str = ""):
    """Decorator: register a layout function under ``name`` (names are unique)."""
    def deco(fn):
        if name in LAYOUTS:
            raise ValueError(f"layout {name!r} already registered")
        LAYOUTS[name] = LayoutSpec(name, fn, kind, summary, frozenset(extra_sizes), source)
        return fn
    return deco


def list_layouts() -> list[dict]:
    return [dict(name=s.name, kind=s.kind, summary=s.summary,
                 extra_sizes=sorted(s.extra_sizes), source=s.source) for s in LAYOUTS.values()]


def load_all() -> None:
    """Import every sibling layout module so their @register calls run."""
    import importlib
    import pkgutil
    for m in pkgutil.iter_modules(__path__):
        importlib.import_module(f"{__name__}.{m.name}")
