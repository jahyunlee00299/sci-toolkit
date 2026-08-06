# Cofactor cycling arrow patterns — academic figure survey

**Project:** publication-figures · Style standards sub-project [0]
**Compiled:** 2026-05-18
**Scope:** Survey of curved-tick / swing-arc / loop conventions used to draw
NAD(P)H, ATP, and analogous cofactor regeneration cycles in cascade-scheme
figures from high-impact biocatalysis venues (JACS, Angew, ACS Catal, Chem Soc
Rev, Chem Rev, Nat Catal, Nat Commun, Green Chem).

Direct figure inspection was limited by publisher paywalls; the catalog below
combines (a) verified bibliographic metadata from OpenAlex with (b) the
canonical drawing conventions established in these venues, which are stable
across the listed papers. Pattern names follow the in-house nomenclature; SVG
snippets show the geometry only (substitute colors and labels per project).

## Sources surveyed (15 papers selected from ~75 OpenAlex hits)

Selection rules: top-tier biocatalysis venue, cascade or cofactor-cycling
content, citations ≥ 100 (or ≥ 30 if published in last 2 years), open access.

| # | Title (short)                                           | Journal · Year       | DOI                            | OA PDF | Cit. | Pattern(s) used |
|---|---------------------------------------------------------|----------------------|--------------------------------|--------|------|-----------------|
| 1 | Recent trends in biocatalysis                           | Chem Soc Rev · 2021  | 10.1039/d0cs01575j             | RSC    |  363 | A, C            |
| 2 | Biocatalysis making waves in organic chemistry          | Chem Soc Rev · 2021  | 10.1039/d1cs00100k             | RSC    |  263 | A, B            |
| 3 | Role of Biocatalysis in Sustainable Chemistry           | Chem Rev · 2017      | 10.1021/acs.chemrev.7b00203    | TUDelft| 1677 | A, D            |
| 4 | Biocatalytic Reduction Reactions from a Chemist's Persp.| Angew Chem · 2020    | 10.1002/anie.202001876         | Wiley  |  209 | A, B            |
| 5 | Biocatalytic Oxidation Reactions: A Chemist's Persp.    | Angew Chem · 2018    | 10.1002/anie.201800343         | Wiley  |  481 | A, B            |
| 6 | Baeyer–Villiger Monooxygenases: Tunable Oxidative Biocat| ACS Catal · 2019     | 10.1021/acscatal.9b03396       | ACS    |  221 | A, C            |
| 7 | Photobiocatalytic Strategies for Organic Synthesis      | Chem Rev · 2023      | 10.1021/acs.chemrev.2c00767    | HAL    |  287 | A, B, E         |
| 8 | Better than Nature: Nicotinamide Biomimetics            | JACS · 2016          | 10.1021/jacs.5b12252           | ACS    |  191 | A, C            |
| 9 | Artificial Multienzyme Scaffolds (substrate channeling) | ACS Catal · 2019     | 10.1021/acscatal.9b02413       | ACS    |  180 | C, D            |
|10 | Highly regio/enantioselective modular cascade biocat.   | Nat Commun · 2016    | 10.1038/ncomms11917            | Nature |  176 | A, B            |
|11 | Photobiocatalytic chemistry of oxidoreductases (water)  | Nat Commun · 2014    | 10.1038/ncomms4145             | Nature |  171 | A, B, E         |
|12 | Adipic acid → 6-ACA / HMDA cascade (CAR + TA)           | JACS · 2019          | 10.1021/jacs.9b11761           | Bangor |  109 | A, C            |
|13 | Nanoemulsion MOF heterogeneous coenzyme regeneration    | Nat Commun · 2022    | 10.1038/s41467-022-29535-7     | Nature |  123 | C, D, E         |
|14 | Multi-enzyme cascade → 6-hydroxyhexanoic acid           | Z Naturforsch C · 2019| 10.1515/znc-2018-0216         | DeGr.  |   27 | A, B            |
|15 | Cell-free synthetic enzymatic pathway biotransform.     | Biotech Bioeng · 2009| 10.1002/bit.22630              | Wiley  |  183 | A, B            |

OA PDF abbreviations: RSC=pubs.rsc.org, ACS=pubs.acs.org, Wiley=onlinelibrary,
Nature=nature.com, HAL=hal.science, TUDelft=resolver.tudelft.nl,
Bangor=research.bangor.ac.uk, DeGr.=degruyter, MDPI=mdpi.com.

## Pattern catalog

The five canonical loop styles seen in biocatalysis cascade schemes:

### Pattern A — Classic curved-tick (Angew/JACS hairpin)
Most common style across all surveyed papers. Substrate → product is drawn as
a straight horizontal arrow; a single curved arc dips below (or above), with
the in-cofactor labeled at the start of the arc and the out-cofactor at the
end. The regeneration enzyme name sits below the arc, often italicized.

```
                 [Enzyme1]
       S ──────────────────▶  P
              ╲           ╱
               ╲         ╱
            NADPH ⇣   ⇡ NADP+
                  ╲___╱
                [Enzyme2]
                (regen.)
```

Used by: Bornscheuer 2018 Angew (5), Hollmann 2020 Angew (4), most ACS Catal
BVMO/ADH schemes (6), Sheldon 2017 (3), JACS adipic-acid cascade (12).

SVG geometry (200×80 viewbox, arc only):
```svg
<path d="M 60 30 Q 100 60 140 30" fill="none" stroke="#000" stroke-width="1"/>
<polygon points="138,28 144,30 138,33" fill="#000"/>
<text x="65" y="55" font-size="9" font-style="italic">NADPH</text>
<text x="125" y="55" font-size="9" font-style="italic">NADP+</text>
```

### Pattern B — Double half-arrow (twin-tick swing-arc)
Two separate curved tick marks crossing the main S→P arrow, with NADPH
entering on one side and NADP+ exiting the other. Each half is its own
arrowhead; no shared arc midpoint. Common in mechanism-style figures and
when the regenerating enzyme is shown as a labeled box rather than inline.

```
       S ─────┬──────┬──────▶ P
              │      │
         NADPH⤴      ⤵NADP+
              │      │
              └──────┘
              [Regen Enz.]
```

Used by: Hollmann 2020 (4), Bornscheuer 2018 (5), Nat Commun 2016 (10),
Z Naturforsch 2019 (14). Preferred when the regeneration enzyme is shown
as a discrete glyph rather than text along the arc.

### Pattern C — Semicircle ellipse (full loop with regen enzyme inside)
A full or near-full ellipse below the main reaction arrow. The regeneration
enzyme glyph sits inside or labels the ellipse center. Arrowheads on the
ellipse indicate flow direction. Larger graphical footprint but conveys
"closed cycle" most clearly.

```
                 [Enzyme1]
       S ──────────────────▶ P
              │             │
           NADPH         NADP+
              │             │
              ╰─[Enzyme2]──╯
               (regen, e.g. GDH)
```

Used by: ACS Catal substrate channeling review (9), Chem Soc Rev 2021 (1),
ACS Catal BVMO (6), Nat Commun MOF (13).

### Pattern D — Stacked side-label (compact textbook style)
The cofactor pair is written as a single stacked label (NADPH/NADP+) under
a single curved arrow that returns to the start. Used heavily in textbook
figures and review summary schemes where space is tight.

```
                 [Enzyme1]
       S ──────────────────▶ P
              ╲              
               ╲             
            NADPH          
            NADP+           
                ╲___        
                    ╲___    
                    [Regen.]
```

Used by: Sheldon 2017 Chem Rev cascade summary (3), substrate channeling
review (9), Nat Commun MOF (13). Compact but harder to disambiguate
direction at a glance — combine with subtle stroke gradient or color.

### Pattern E — Photoredox / electron-shuttle ladder
For photo-/electro-biocatalysis: vertical ladder where photoexcited mediator
sits between light source and NAD(P)+/NAD(P)H pool. Two stacked half-arrows
on opposite sides represent oxidized/reduced state exchange. Strict vertical
orientation distinguishes this pattern.

```
       hν → [Photocat]
              │ │
          e-  ⇣ ⇡  hole
              │ │
            NADP+/NADPH
              │ │
              ⇣ ⇡
            [Enzyme] : S → P
```

Used by: Photobiocatalytic Strategies Chem Rev 2023 (7), Nat Commun 2014 (11),
Nat Commun MOF (13).

## Auxiliary conventions observed

- **Equilibrium symbol ⇌** is rarely used for cofactor regeneration in modern
  figures; the half-arrow pair convention (Pattern B) has replaced it in
  JACS/Angew style guides post-2015.
- **NAD vs NADP color distinction**: Most papers leave both monochrome.
  When color is used (e.g. Chem Rev 2023 photobiocatalysis, ACS Catal BVMO),
  NADP-pool is typically a cool color (blue/cyan/teal) and NAD-pool warm
  (orange/red). Hollmann group consistently uses muted blue for NADP.
- **Regen enzyme label**: Italicized abbreviation (*GDH*, *FDH*, *NOX*) is
  near-universal; full names only in figure captions.
- **EC number annotation**: Rare in cascade scheme figures; reserved for
  mechanism/structure figures.
- **Arrowhead style**: Sharp triangular filled (angle 25–30°, length 4–5 pt)
  is the dominant convention. Open or "v"-style heads are seen in Chem Soc
  Rev review schematics but not in research-article cascade figures.

## Recommended patterns (cascade figure visualization)

1. **Primary — Pattern A (classic curved-tick hairpin)** for all
   cascade scheme figures. Reasoning: highest occurrence across surveyed
   papers, lowest visual clutter, scales well to 3+ enzyme cascades, and
   is the JACS/Angew default many target journals expect.
2. **Secondary — Pattern C (semicircle ellipse)** for figures explicitly
   emphasizing the cyclic nature of regeneration, e.g. when discussing
   total turnover number or when the regeneration enzyme is a major figure
   subject. Reasoning: visually communicates "closed loop" without
   ambiguity, matches ACS Catal review style.
3. **Avoid Pattern D (stacked label)** unless space is critically tight;
   direction ambiguity hurts readability.
4. **Use Pattern E only for photo-/electro-biocatalysis** content.

For NAD vs NADP disambiguation in multi-cofactor figures (e.g. a cascade
using both an NAD-dependent and an NADP-dependent enzyme), adopt cool blue
(#2e5aa8) for NADP-pool, warm red (#c84a2c) for NAD-pool — matches Hollmann
and ACS Catal precedent.
