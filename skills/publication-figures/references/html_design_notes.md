# HTML Section Design Notes — research_visualization_toolkit_plan.html

**Date:** 2026-05-18
**Target file:** `C:\Users\USER\research_visualization_toolkit_plan.html`
**Purpose:** Improve section spacing, sub-section anatomy, and reading rhythm without removing any existing assets.

---

## Sources Surveyed

1. [Refactoring UI — Layout & Spacing (Jacob Shannon notes)](https://jacobshannon.com/blog/books/refactoring-ui/layout-and-spacing/) — Schoger/Wathan principles on hierarchy through space.
2. [Atlassian Design — Spacing tokens](https://atlassian.design/foundations/spacing) — 0/2/4/6/8/12/16/20/24/32/40/48/64/80 scale, range-by-purpose.
3. [Refactoring UI — Color Palette excerpt](https://www.refactoringui.com/previews/building-your-color-palette) — color discipline (9-tier shades, no procedural lighten).
4. [Tailwind CSS — Padding & spacing scale](https://tailwindcss.com/docs/padding) — section padding patterns (`py-12`/`py-16`/`py-20`/`py-24`/`py-32` = 48/64/80/96/128 px).
5. [Mantlr — How Stripe / Linear / Vercel ship premium UI](https://mantlr.com/blog/stripe-linear-vercel-premium-ui) — hairlines `0.5–1 px` at low alpha; single typeface family at 4-6 sizes; modular scale.
6. [SetProduct — Vercel Geist aesthetic](https://www.setproduct.com/blog/complete-guide-to-blueprint-grid-design) — monospaced eyebrow, minimal palette, subtle grid.
7. Cieden / Ratio Calculator — Modular scale ratios — body-heavy docs benefit from `1.2–1.333` (Perfect Fourth), avoid `>1.5` for dense layouts.
8. Apple HIG defaults (general practice) — 8 pt base unit, 16-20 pt margins on mobile.

---

## Diagnosis (Before)

| Item | Current | Issue |
|---|---|---|
| `.sub-section` top spacing | `margin-top:72px; padding-top:32px` | OK numerically but section heads collide with previous h3/figure. |
| Color stripe | `width:64px; height:3px` flat solid | Reads as a small bullet, not a section accent. |
| Inline h3 | Mixed `h3` (12.5 px regular) + `h3.section-h3` (mono-uppercase eyebrow) — `style="margin-top:18px"` / `36px` inline | Inconsistent mini-section spacing. |
| Body paragraph max-width | `64ch` (lede) / `60–62ch` (inline) | Mixed. |
| Section end | No divider; next section jumps | Hard to perceive section boundary. |
| Card hover only | No section/heading entrance motion | Static feel. |
| Section heading line-height | `1.2` default + tight letter-spacing | Heading top "sits" on stripe with no breath. |

---

## Recommended Values

| Property | Current | Recommended | Source |
|---|---|---|---|
| Section top margin | `72px` | **`96px`** (`py-24`-class break) | Tailwind / Refactoring UI ("section > content") |
| Section top padding | `32px` | **`40px`** | 8 pt scale (Atlassian `space.500`) |
| Color stripe size | `64×3 px` flat | **`88×4 px` gradient fade** to transparent | Vercel/Linear hairline craft |
| H2 line-height | `1.2` | **`1.15`** + `margin-top:14px` after eyebrow | Refactoring UI heading rule |
| H2 letter-spacing | `-0.008em` | **`-0.012em`** (heading optical correction) | Linear "details matter" |
| Mini-section (h3) spacing | mixed `18/24/36 px` inline | **`36px` top, `12px` bottom** (uniform) | Atlassian `space.400` |
| Mini-section h3 style | uppercase mono OR plain regular | **Geist 13 px / 600 / accent-tinted** | Stripe docs h3 convention |
| Inter-paragraph (table/gallery/code) | mixed | **`16-20 px` top, `20-28 px` bottom** | Refactoring UI sub-grouping |
| Section end divider | none | **`hairline 1 px @ 12% alpha`, margin `56px 0 0`** | Vercel/Stripe docs |
| Lede width | `64 ch` | keep `64 ch` (good for 14 px Geist) | Modular scale guidance |
| Heading entrance | none | **fade-in + 6 px slide-up** (respects `prefers-reduced-motion`) | M3 motion guidelines |
| Sub-section background | `transparent` | **subtle gradient halo near stripe** | Refactoring UI "color discipline" (low-alpha tint) |

### Rationale (1-line)

1. **96 px section break** — Tailwind `py-24` is industry default; matches Refactoring UI's 80–96 px rule for distinct sections vs. internal grouping.
2. **Gradient stripe** — flat 64×3 reads as a tag, not a section accent; fade-out reads as a section anchor.
3. **Optical H2 letter-spacing -0.012em** — Instrument Serif at 1.45-1.7 rem needs tighter optical tracking to feel intentional.
4. **Unified h3** — current inline `margin-top` values cause visible asymmetry between [A]/[B]/[C]/[D]; one `.mini-section` class fixes this.
5. **Hairline divider at section end** — explicit termination so reader knows where one sub-project ends; matches Stripe/Vercel docs.
6. **Subtle entrance motion** — `prefers-reduced-motion: reduce` is already gated globally, so a 250 ms heading fade is safe.

---

## Preservation Contract

- All cards, tables, galleries, gantt, flow SVG, validation panels, JS data — **untouched**.
- Color tokens (`--paper`, `--ink`, `--accent`, `--muted`, etc.) **unchanged**.
- Dark-mode toggle behavior **unchanged** (only new tokens derive from existing ones).
- Topbar layout **unchanged**.
- All `<section class="sub-section">` IDs and anchor targets **preserved** for in-page links.
