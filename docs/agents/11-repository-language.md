<!-- Moved verbatim from CLAUDE.md on 2026-10-07 so the file Claude Code reads every session stays short. CLAUDE.md keeps a summary; this file is the full text. -->

### Korean is kept — only where it is data, not prose

Five categories carry meaning that English cannot: translating them either
changes behavior or defeats the text's purpose. Leave them in Korean and do
not "clean them up":

1. **Router trigger phrases.** `한국어 트리거 — …` lines, and Korean phrases in
   a `SKILL.md` frontmatter `description:`. These are how a Korean-language
   request matches the skill. Translate them and the skill stops firing.
   🔴 They must live INSIDE `description:` — the router reads only that field.
   A top-level `triggers:` list is not part of the Agent Skills spec and is
   never read (measured 2026-09-03: paper-extract carried ten Korean triggers
   there and none of them could fire); `tests/test_skill_contract.py` rejects
   such keys.
2. **Korean-language detection logic.** Korean literals used as patterns —
   particles, counters, honorifics, josa — e.g. the regexes in
   `scripts/feedback_sanitize.py` that catch Korean PII, and the taxonomy in
   `skills/avoid-ai-writing/korean-tells.md` whose entire subject *is* Korean
   text. The Korean here is the input alphabet, not commentary.
3. **Test fixtures that exercise those detectors.** A Korean sample string in
   a test exists to prove a Korean pattern matches. Keep it, and write its
   surrounding docstring/comment in English.
4. **Quoted evidence.** A user's or reviewer's exact Korean wording, quoted
   because the wording itself is the finding. Quote verbatim; put the
   explanation around it in English.

5. **Beginner onboarding docs — the whole `docs/` folder.** `docs/00_시작하기.md`
   through `docs/14_터미널_읽기좋게.md` are written for lab members who have
   never used an AI agent, in plain Korean with everyday analogies. Their
   reader is a Korean-speaking beginner, so English would defeat the document's
   purpose. Korean filenames included — they are referenced by path from
   `README.md` and from code, so renaming them breaks those links. Reference
   docs *about* the repo's machinery (`docs/feature-connectivity-ledger.md`)
   are not onboarding docs and follow the English rule.

Everything outside those five is prose and gets translated.

### How to translate, and how to prove it

- **Translate meaning, not words.** These docstrings carry measured findings
  ("실측", dated observations, why a naive fix failed). Preserve the finding
  and its date; do not compress it into a generic summary.
- **Never blind find-replace.** Decide per occurrence whether it is prose or
  one of the five exceptions above. A regex sweep cannot tell them apart.
- **Prove it.** `python doctor.py` must end in PASS (it runs every self-test,
  the SHA256SUMS check, and the SENTINEL scan), and
  a translated file's behavior must be unchanged — translation touches
  comments/docstrings/prose only. If a test's expected output was Korean and
  a translation would change it, that literal was category 3 — revert it.
- **Watch for checks that go quiet.** A verifier that finds its target by
  Korean regex stops matching once the text around it is English, and some
  skip silently rather than fail. Measured 260828: translating README/
  QUICKSTART left 5 of the 8 count checks in `tests/test_doc_counts.py`
  matching nothing while the suite still reported pass. After translating a
  file, grep for anything that greps *it*, and confirm the pattern still
  fires — a green test is not proof the check ran.
