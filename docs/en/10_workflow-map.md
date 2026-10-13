> English translation of [10_전체_워크플로우_지도.md](../10_전체_워크플로우_지도.md). The Korean original is canonical; if they differ, the Korean version wins.

# 10. Full Workflow Map — How This Toolkit Actually Runs

The earlier documents were about "how to install and get started." This document is about **"which path does my task take?"**
Once you understand the structure, you can tell right away when the AI heads down the wrong road.

---

## 1. Three layers

This package has three layers. Their roles differ, so don't mix them up.

```
① Rules      AGENTS.md  ─ The operating rules the AI follows. §0 has a "request → path" table.
                CLAUDE.md ─ Summary for Claude Code (a shorter version of the same content)
      ↓  (the AI reads and decides)
② Skills     skills/<name>/SKILL.md ─ A "when X, do Y" guide for each kind of task
                skills/<name>/scripts/  ─ The actual tools that skill uses
      ↓  (runs according to the guide)
③ Checks     doctor.py, tests/, each skill's lint/check scripts
                ─ The gates that must pass before anyone says "it's done"
```

**Key point**: ① decides the path, ② does the work, and **③ must pass before it counts as finished**.
In this toolkit, saying "done" without ③ is not done.

---

## 2. What happens when a request comes in

For example, if you said "이 원고 그림 번호 좀 봐줘" (“check the figure numbers in this manuscript”):

```
User request
    ↓
Find the matching row in the AGENTS.md §0 routing table
    → the "check figure/table numbers and captions" row
    ↓
Run the designated tools
    → docx/scripts/figure_caption_check.py
    → docx/scripts/manuscript_ref_order.py
    ↓
🔒 Gate: read the "kind" of each result
    → An "out-of-order numbering" finding does not automatically mean "move the caption."
      A figure that is never cited, a ghost citation with no caption, and a draft-state
      leftover each call for a different remedy.
    ↓
Report to the user (with evidence)
```

If the AI leaves this path and says "I just read the file and looked at it by eye," it is **going the wrong way**.
In that case, tell it "AGENTS.md §0의 경로대로 해줘" (“follow the path in AGENTS.md §0”).

---

## 3. Paths by task type (summary)

The full table is in `AGENTS.md` §0. Here are the ones you'll use most.

| What you want to do | What to use | What must pass before you finish |
|---|---|---|
| Find papers | `research-search` | 🔒 `scripts/doi_verify.py` — actually catches made-up DOIs and retracted papers |
| Collect references + OA PDFs | `scripts/ref_fetch.py` | 🔒 Report the mismatched and not-found items in the report exactly as they are |
| Write or revise a manuscript | `manuscript-pipeline` | 🔒 Terminology lint + number consistency + `body_typo_lint.py` (units/notation) |
| **Edit a Word file** | `docx` → `incremental_edit.py` | 🔒 `docx_preflight.py` + `word_validate.py` on the output file |
| **Live-edit a Word file that is open** | `docx` → `word_live_edit.py` | Re-read the edited part afterwards to confirm |
| Extract text from Word | 🔒 `manuscript_text.py --count-only` **first** | If tracked changes exist, the ordinary method silently drops text |
| Insert citations | `endnote-citation-injection` | 🔒 `doi_verify.py --bibtex` + `endnote_biblio_check.py` |
| Make a figure | `publication-figures` | 🔒 `figure_lint.py` + recompute the numbers from the raw data |
| Analyze data | `lab-data-analysis` → `stats-workflow` | 🔒 `assumption_check.py` — checks normality and equal variance and names the test to use |
| Model fitting / optimization | the relevant skill → `scientific-validation` | 🔒 `sci_validate.py` (mass balance, physical plausibility) |
| **Put a number into a document** | — | 🔒 Recompute from the original script/raw data |
| Send mail, issues, tasks | `scripts/connectors/` | 🔒 **Drafts only.** A human does the sending |
| Installation isn't working | `doctor.py` | 🔒 Until it shows `PASS` |

🔒 = a gate enforced by a script. Don't judge by eye; run it and look at the exit code.

---

## 4. Why some things are scripts and others are documents

The criterion is **"can it be written down as a rule?"** Even for an easily reversible mistake,
if a check can be built reliably, we build it as a script.

| | Enforced by a script | Guided by a document (guide) |
|---|---|---|
| **Criterion** | The pass/fail rule is clear, so a machine can check it for you | It needs situational judgment and can't be reduced to a rule |
| **Examples** | Manuscript numbers, Word file corruption, secrets, whether a DOI really exists, statistical assumptions, terminology notation | Which database to search, what argument to build, how to interpret results |
| **Why** | Both people and AI mistakenly believe "I checked it." A script doesn't get tired | If a machine makes the call for you, it actually gets it wrong |

At first we assumed "if the cost of a mistake is low, a document is enough," but most of the
things we left as documents on that basis **turned out to be machine-checkable.** So the following three
were moved from documents to scripts.

- **Whether a DOI really exists** (`scripts/doi_verify.py`) — a made-up DOI can't be told apart by eye.
  You have to actually ask both CrossRef and OpenAlex, and a machine is far better at that.
- **Statistical assumptions** (`stats-workflow/scripts/assumption_check.py`) — judging
  "it looks normally distributed" is often wrong. Running Shapiro-Wilk and Levene and choosing the test from
  the result is an entirely mechanical procedure.
- **Terminology and unit notation** (`manuscript-pipeline/scripts/body_typo_lint.py`) —
  things like `50ul`, `n=3`, `NAD+` have clear rules. It is more accurate than skimming by eye.

On the other hand, **"how to interpret this result"** stays a document. Reducing it to a rule
would force wrong answers instead.

> When you can't decide: **"Could I write this rule down so someone else could follow it exactly?"**
> If so, it's better to make it a script.

---

## 5. Checking it yourself

```bash
python doctor.py                        # this one command runs everything below automatically
```

What `doctor.py` runs:

| Check | What it looks at |
|---|---|
| SHA256SUMS | Whether files got corrupted while being copied via USB |
| SENTINEL | Whether secrets or personal information got mixed in |
| `test_skill_references.py` | Whether documents point to files or skills that don't exist (594 items) |
| `test_agents_routing.py` | Whether the AGENTS.md §0 table points only to things that really exist |
| `test_doctor_sentinel.py` | Whether the secret check itself works (blocks a real key + lets a placeholder through) |
| `test_body_typo_lint.py` | Whether the typo check catches what it should and lets through what it should |
| `test_doi_verify.py` | Whether DOI verification actually catches fake DOIs |
| `test_assumption_check.py` | Whether the statistics tool names the right test on data where the answer is known |

The important point is that **the checking tools are tested too**. If a gate quietly breaks,
every deliverable that gate was guarding goes out unchecked.

### When you edit this toolkit yourself

If you added a skill or edited a document, **be sure** to run the following again.

```bash
python scripts/make_checksums.py --apply   # refresh the file list and hashes
python doctor.py                           # confirm PASS
```

In particular, **when you write in a document "run `scripts/foo.py`", check that the file actually exists.**
A document pointing to a file that doesn't exist was the most common breakage in this package,
which is why we made `test_skill_references.py` check it automatically.

---

## 6. What to say when the AI gets lost

| Situation | Say this |
|---|---|
| It seems to be using the wrong skill | "AGENTS.md §0 라우팅 표에서 맞는 경로를 찾아서 그대로 해줘" (“find the right path in the AGENTS.md §0 routing table and follow it exactly”) |
| It says "all done" without verifying | "§0의 게이트를 실행하고 결과를 보여줘" (“run the §0 gate and show me the result”) |
| You don't know where a number came from | "이 숫자가 어느 파일 어느 줄에서 나왔는지 보여줘" (“show me which file and line this number came from”) |
| It's trying to run a file that doesn't exist | "그 파일이 실제로 있는지 먼저 확인해줘" (“first check that the file really exists”) |
| The Word file looks wrong | "docx_preflight.py랑 word_validate.py 돌려줘" (“run docx_preflight.py and word_validate.py”) |

---

## Next documents

- Detailed usage of each skill → `skills/<name>/SKILL.md`
- Full AI operating rules → `AGENTS.md`
- Using it on a remote server → [09_remote-server](09_remote-server.md)
