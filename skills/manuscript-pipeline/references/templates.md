# Templates — Cover Letter / Reviewer Response / Revision (manuscript-pipeline reference)

## Cover Letter Template
```
Dear [Editor Name],

We submit [Title] for consideration in [Journal].

[1 paragraph: what we did and the key finding]

[1 paragraph: why this is significant for the field]

[1 paragraph: why this fits the journal scope]

All authors have approved the manuscript.
No conflicts of interest to declare.

Sincerely,
[Corresponding Author]
```

## Reviewer Response (quick)
```
We thank Reviewer X for their constructive comments.

**Comment 1:** [quote reviewer]
**Response:** [explanation]
**Revision:** [what changed, line numbers]
```

---

## Phase 5 — Revision Response Mode (`revise-response`)

Takes reviewer comments and structures a point-by-point response.

### Input
- Reviewer's original text (email/PDF/text) — usually split into reviewer 1, reviewer 2, ...
- Current manuscript version (DOCX or text)

### Workflow
1. **Parse comments**: split by reviewer and by comment. Assign each comment an ID (`R1.1`, `R1.2`, `R2.1`...).
2. **Classify**: each comment → one of `factual` / `clarification` / `additional-experiment` / `literature` / `style` / `structural`
3. **Draft response per comment**:
   ```
   Comment R1.1: [original text]
   Classification: clarification
   Response: [reply — concede / rebut / compromise]
   Manuscript change: [what changed + line numbers, or "no change"]
   ```
4. **Tone policy**: never frame it as "what the original couldn't do" — frame it as "supplement/addition."
5. **Output formats**: JSON (reprocessable) / Markdown table (for humans) / DOCX response letter (for submission)

### Output structure (JSON)
```json
{
  "reviewers": [
    {
      "id": "R1",
      "comments": [
        {
          "id": "R1.1",
          "original": "...",
          "classification": "clarification",
          "response": "...",
          "manuscript_change": "Lines 145-152, added paragraph on...",
          "status": "addressed | partial | rebutted"
        }
      ]
    }
  ]
}
```

### DOCX response letter format (IJBM/Elsevier style — based on 250718_IJBM_Revision_response.docx)

```
Response to Reviewers' Comments

Journal: <Journal Name>
Manuscript Number: <Number>
Manuscript title: <Title>

We sincerely thank the editor and all reviewers for their thorough and
constructive comments. We have addressed each comment in detail below,
and the corresponding changes in the manuscript are highlighted in red.
We respectfully request that our revised manuscript be reconsidered for
publication in <Journal Name>.

<Reviewer #1>

Reviewer #1: <quote the overall summary/assessment>

Comment 1. <quote the original text>
Response: Thank you for this <valuable | constructive | important> comment.
<reply: concede/rebut/compromise. State clearly what was done and how>

[Revision: lines 445-446]
<quote the revised text — wrapped in italics or quotation marks>

Comment 2. <quote the original text>
Response: Thank you for this <suggestion>.
...
```

**Core rules** (from the user's real submission experience):
1. The response always opens with "Thank you for this <adjective> comment/suggestion/feedback."
2. Every manuscript change carries a `[Revision: lines XXX-YYY]` tag + a quote of the actually-revised text.
3. Order: concede → explain → revise → quote.
4. Even when rebutting, lead with a partial concession ("We agree that...") before "However, ...".
5. Red highlighting stays in the manuscript body; the response letter itself is plain text.
6. Closing sentence for submission: "We respectfully request that our revised manuscript be reconsidered for publication"

---

## Discuss Mode — result interpretation + consideration recommendations

Use when the user shows results and asks "how do I interpret this?" / "how should I write the Discussion?" / "does this mean anything?"

### Workflow
1. **Context gathering** (never assume — ask when unsure): experimental conditions (temperature, pH, concentration, time), comparison target (prior experiment, literature, theoretical value), measurement method + error range
2. **Three-tier interpretation**: **Primary** (data-supported) / **Alternative** (cannot be ruled out) / **Excluded** (explicitly ruled out + reason)
3. **Comment categories**:
   - `[MECHANISM]` — molecular/enzyme-level mechanistic hypothesis
   - `[CONFOUND]` — a confounding variable that could obscure the result
   - `[REPLICATION]` — reproducibility, N count, statistics
   - `[COMPARISON]` — position relative to the literature (better/worse/comparable + condition differences)
   - `[FOLLOWUP]` — experiments/analyses to run next
   - `[LIMITATION]` — limitations that must be stated explicitly
4. **Output**: 7-step Discussion outline (key finding → interpretation → literature comparison → contribution/significance → limitations → future work → conclusion) + comment boxes per category
