# Restructure / post-processing pass

Generalizes the proven logic of an archived v5→v6 restructuring script, which is real,
tested, worked output — not a hypothetical. That script is python-docx + lxml based and predates
this skill's docx-skill-SSOT rule; do not run it as-is on a new document. Re-implement the same
*logic* via the docx skill's safe-edit mechanics (unpack → edit `document.xml` → selective zip
replacement, never full repack — see docx skill MUST 1–6).

## What this pass does (proven necessary by the v5→v6 diff)

1. **Consolidate all figures into one `【도면】` section** at the end, immediately before
   `[참고문헌]`. Draft-stage figures land inline near their first mention (natural for drafting);
   examiners expect a single figures section. Moving them is mechanical: strip `w:drawing`
   elements from their inline paragraph, re-insert as `[도 N]` + image pairs at the end.
2. **Renumber all `[도 N]` references consistently**, body text and the 도면 list together — a
   single rename pass (old→new number map) applied to every paragraph, not section-by-section
   (the proven script used a placeholder-character trick, see below, to avoid chain-collisions
   when renumbers overlap, e.g. old 도13→new 도2 while old 도2 already exists).
3. **Merge duplicate figures** — when a supplementary/appendix figure duplicates a main-text
   figure (same underlying image, e.g. SDS-PAGE referenced both as a main figure and again in
   a "추가" appendix note), keep one, retarget both references to it.
4. **Integrate scattered "추가 N" (supplementary/addendum) content back into the numbered body**
   at its natural section location (found by anchoring on nearby existing body text — e.g. an
   addendum about an enzyme's kinetic mechanism inserts right after the kinetic-parameter table). Don't
   leave addenda as an undifferentiated tail block; a reader building the final application needs
   it where it belongs structurally.
5. **Delete stray/duplicate sections** left over from iterative drafting (the proven pass deleted a
   redundant "특허 청구범위 (요약)" section that had drifted out of sync with the separate claims
   draft — a reminder that duplicated content between the main disclosure and the separate
   claims/prior-art docx is a drift risk, not just clutter).

## Renumbering collision trick (from the proven v5→v6 script)

When renumbering overlaps (e.g. old-13→new-2 while old-2 also needs to become new-7), a naive
sequential string-replace corrupts already-renamed numbers on a later pass. The proven fix: use
a placeholder character (e.g. `￾`) as an intermediate target for one side of any swap pair,
then do a final pass replacing the placeholder with the real digit. Build the full old→new map
first, then apply in two passes (old→placeholder-tagged-new, then placeholder→plain new) rather
than one naive pass.

## Verification after restructuring

- Every `[도 N]` reference in body text has a matching entry in the `【도면】` section, and vice
  versa (no orphaned reference, no orphaned image) — a simple regex diff of the two number sets.
- Figure count after dedup matches expectation (ask the user for the expected count, or derive
  from the source manuscript's figure count minus known duplicates) — don't silently drop a
  figure during consolidation.
- Run `docx_preflight.py` + `word_validate.py` (per docx skill MUST 3) after any structural
  edit of this scale — restructuring touches many paragraphs and is exactly the kind of edit
  that risks OOXML corruption if done via full-document re-serialization instead of selective
  zip replacement.
