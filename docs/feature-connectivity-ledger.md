# Feature connectivity ledger

One entry per feature unit. Not **what was built**, but **what it is wired
to and whether it actually fires**. The most common failure mode in this
workspace is building the right artifact and having nothing call it.

---

## Feedback sanitization gate (2026-08-07)

**Scope** — blocks unpublished research content, credentials, and PII from
reaching GitHub issues before a record left by `feedback_log.py` goes out.

**Layer** — cross-cutting (spans the entire logging path)

**Why it was needed** — `to_issue()` drops `what`/`expected`/`actual`/`note`
verbatim into the issue body. The doc's §"What must not leak" section
existed, but **it was guidance for a human, not code that actually runs.**
The same shape of failure has happened three times in this workspace (260628
plaintext key exposure · 260706 unpublished figures and a real name pushed ·
260807 something logged as "removed" while still present in the payload).

### Input/output

| | |
|---|---|
| Input | a record dict from `feedback.jsonl` (`what`/`expected`/`actual`/`note`) |
| Output | a list of risk-item strings (empty list = pass) |
| State ownership | none — pure function. Does **not modify** the original text |
| External effects | none (blocking only; upload uses the existing path) |

### Wiring (where it's actually called)

| Site | Behavior | Firing confirmed |
|---|---|---|
| `feedback_log.cmd_add` | warns only, record still saved | Yes — E2E: `⚠` printed on a contaminated record |
| `feedback_log.cmd_export` | **hard block** (exit 2), includes a preview | Yes — E2E: confirmed exit 2 |
| `--approve` | proceeds, ignoring the check | Yes — E2E: confirmed exit 0 + warning printed |
| `doctor.py SELF_TEST_SCRIPTS` | runs the test automatically | Yes — item appears in doctor output |
| `doctor.py SENTINEL_SELF_TEST_FILES` | test file exempted from the scan | Yes — confirmed SENTINEL OK |

Why the design is asymmetric: blocking at `add` would just make a tired
person give up on reporting at all, which erases the whole reason this
feature exists. The real risk appears when data leaves, so the block sits
at `export`.

### Evidence

- `tests/test_feedback_sanitize.py` — **50/50 passing**.
  Every blocked case is a measured leak type from real incidents
  (260628 · 260706 · 260807). The allowed cases are ordinary friction
  reports — if those got blocked, the feature would be dead on arrival.
- Existing `tests/test_research_marker_scan.py` — **41/41 intact** (no
  regression).
- `doctor.py` — SENTINEL OK, 11 self-tests passing.

### Refute

Ran 24 separate adversarial cases and found **one real gap**:
`E-factor comes out to 0.71` passed through. The check only looked at
numbers attached to `$`/`%` and missed a **bare unitless decimal** — and the
E-factor that leaked in 260706 was exactly that shape. → Added bare decimals
to `MONEY_PCT_RE` and pinned that case as a regression test.

**Mutation check** — deliberately broke the real-name detection label and
the test immediately FAILed (48/50). Evidence that the test is actually
guarding something. Confirmed, then restored.

Also, the SENTINEL scan **caught two real names I had left in a comment
myself** — a case of the tool catching the author's own mistake, worth
recording as-is. Replaced with pseudonyms.

### Integer detection — a first-pass judgment overturned by measurement (added same day)

The first draft wrote "integers are skipped because they explode false
positives" as an **intentional limitation**. The user pushed back, and
re-measuring against 24 cases showed that judgment was wrong:

| Approach | Leaks missed | False positives |
|---|---|---|
| bare decimals only (first draft) | **4/7** — `yield came out to 92` passed through | 1/13 |
| all bare integers | 0/7 | **13/13 — every normal report flagged** |
| integers, excluding counter words | 0/9 | 0/15 ← adopted |

What separates them is **not the shape of the number but the word after
it**. `92 였습니다` ("came out to 92") is a value; `line 3`, `2 items`,
`5 minutes` are counts. The intuition "false positives will explode" was
right, but it didn't mean "give up on integers entirely."

Re-running adversarial cases against the adopted approach turned up **4 more
findings**:
- `MPSP 120 dollars` **missed** — the Korean unit word for "month" (달)
  matched as a prefix of "dollars" (달러). When a short Korean unit word is
  matched as a prefix, every word starting with that syllable gets exempted.
- Boundary tightened to `(?![가-힣])` and it immediately flagged `2개로`
  ("with 2 items"), `3행에서` ("at row 3"), `7개가` ("7 items") as 10 false
  positives. The boundary had to **allow trailing particles and sentence
  endings** — the same root cause already hit once before in the real-name
  detector.
- `issue #42`, `axis starts at 0` — false positives, because identifiers
  and boundary values are not measurements.

### Remaining risk / intentional limitations

- **The counter-word list is itself the false-positive defense line.**
  Shrinking `COUNTER_WORD_RE` blocks normal reports. The back half of the
  test's MUST_NOT_FLAG cases pins that defense line in place.
- **A sentence with no research-context word around its number is not
  inspected.** A bare value with no context word, like `그 값은 92 입니다`
  ("that value is 92"), passes through — catching bare integers without a
  context word makes false positives uncontrollable.
- **English names are not checked.** They're indistinguishable from
  ordinary English words.
- **`--approve` disables the check entirely.** It is not per-item approval.
  If it gets overused the gate is effectively gone, so if usage becomes
  frequent, recalibrate the gate itself.
- `out/feedback.jsonl` is blocked from commits by `.gitignore`. Keep it that
  way — sanitization protects the export path, not the commit path.

---

## Feedback issue assignee = the reporter themselves (2026-08-10)

**Scope** — the default assignee on a GitHub issue filed via
`feedback_log.py export --github --write`.

**Layer** — sub-feature (a shallow addition on top of the existing feedback
sanitization gate)

**Why it was needed** — issues were created but never assigned to anyone,
so they piled up ownerless. Unless the code enforces "whoever found it owns
it," things either pile onto a single maintainer (burnout) or nobody looks
at them (neglect).

### Input/output

| | |
|---|---|
| Input | `--assignee <login>` (optional) / `--no-assignee` (optional) |
| Output | the `assignees` field on the GitHub issue-creation request |
| State ownership | none |
| External effects | `GET /user` (assignee lookup, only when no option given) + `POST .../issues` |

### Behavior

- No option (default) → auto-assigns to the GitHub account running this
  command (`GET /user`). In other words, **the person who found it** is the
  default assignee — nothing auto-piles onto a maintainer.
- `--assignee <login>` → assigns to that person. Skips the `/user` lookup
  (avoids an unnecessary call).
- `--no-assignee` → assigns to nobody.
- Even if the `/user` lookup fails (e.g. offline), issue creation itself is
  not blocked — it just prints a warning and proceeds with no assignee.

### Wiring

| Site | Behavior | Firing confirmed |
|---|---|---|
| `feedback_log.cmd_export` | self-assigns by default, only calls the real API under `--write` | Yes — mock E2E |
| `--no-assignee` | skips the `/user` call entirely | Yes — mock E2E |
| `--assignee` | uses the given value, skips the `/user` call | Yes — mock E2E |
| `doctor.py SELF_TEST_SCRIPTS` | already registered under the existing `test_feedback_log.py` entry — the new test rides along automatically, no separate wiring needed | Yes — confirmed |

### Evidence / refute

- `tests/test_feedback_log.py` §7 — verified 4 cases with a mock GitHub API
  (default self-assign · `--no-assignee` · explicit `--assignee` · crash-free
  fallback when the `/user` lookup fails). **23/23 total passing**, no
  regression in the existing 16.
- One refute found and fixed: the first version of the test monkeypatched
  `_mod.FEEDBACK_PATH`, but the actual constant name is `LOG_PATH` — so the
  real `out/feedback.jsonl` (accumulated real records on disk locally) got
  swept into the mock export too. This was an isolation failure, not a logic
  defect, but the assertion was rewritten from a value list to "are they all
  the same assignee" so it wouldn't break even with real records mixed in.
- Regress: `tests/test_feedback_sanitize.py` 73/73, `test_doc_counts.py` +
  `test_skill_references.py` 2/2 — confirmed intact.

### Remaining risk / intentional limitations

- In a repo owned by a team (organization), if `assignees` is given a login
  that isn't a collaborator on the repo, the GitHub API silently ignores it
  (no error) — this feature does not verify the premise that "the reporter
  is a collaborator on this repo."

---

## 260816 — REST connector regression safety net + unifying the dry-run token contract

### Scope / layer

Cross-cutting layer. The user's request was "make skills/workflows reach
services via REST API instead of MCP," but **prior-art research found zero
policy violations** — `AGENTS.md §9`, `docs/05`, and
`scripts/connectors/README.md` already mandate REST-first, and five
connectors already exist. All 4 MCP mentions found in skills were legitimate
(primer-design = its own local engine, journal-presentation-maker's 2 = paywall
rendering and visual slide inspection, markitdown = an upstream project's own
footnote). So the task was reframed from **establishing new policy** to
**closing the remaining gap**.

### Input/output / state ownership

| Site | Behavior | Firing confirmed |
|---|---|---|
| `github/notion/notion_db main()` | write command with no `--write` → does not require a token (same rule as asana) | Yes — test [4] |
| `github cmd_open_pr` | with no token, **skips** the fork check but says so explicitly in the preview | Yes — test [2] |
| `notion_db cmd_add_row` | deliberate exception — requires a token because schema comparison is the whole point of the preview | Yes — test [4] |
| `doctor.py SELF_TEST_SCRIPTS` | newly registered `tests/test_connectors.py` | Yes — 20→21 kinds, shown in PASS output |
| `AGENTS.md §0` | new "reading external services" row (previously only an outward row existed) | Yes — `test_agents_routing.py` |
| `AGENTS.md §9` | new `--write` contract section (dry-run needs no token / is not a rehearsal) | — doc only |

### Evidence / refute

- New `tests/test_connectors.py` — **31/31 passing, zero credentials, zero
  network**. Covers 5 argparse variants · dry-run isolation · the `--write`
  gate · token gating · mail draft-first.
  `http()` is monkeypatched into a bomb so that if dry-run ever touches the
  network, that itself is caught as a failure.
- **Refute 1 (gate defeated)**: changed `notion append`'s `if not
  args.write:` to `if False:` so it always sends → 2 cases FAIL, exit 1,
  pinpointed as "the dry-run path called the network." Restore confirmed.
- **Refute 2 (token gate weakened)**: made `github` stop requiring a token
  even under `--write` → "`--write` requires a token" FAILs, exit 1.
  Restore confirmed.
- The first draft of the test assumed `--project`, but the actual flag was
  `--workspace` — **the test was fixed, not the code** (never bend code to
  make a test pass).
- Regress: `doctor.py` 12 OK / 0 WARN / 0 FAIL, self-test 21/21.
  `test_doc_counts.py` caught the README count not being updated 21→22, and
  the doc was fixed to resolve it.
  `make_checksums.py` rejected untracked files, forcing the correct commit
  order (the gate working as intended).

### Remaining risk / intentional limitations

- `mail_connector send` requires a TTY plus typed confirmation, so an
  automated test can't drive the send path end to end. Instead it asserts,
  at the source level, "no SMTP trace in the draft/reply path" and "isatty
  exists" — a structural test, not a behavioral one.
- `github open-pr` can't run the fork check in a token-less dry-run. It
  prints a warning in the preview, but there is still room for a **user who
  doesn't read that line** to mistakenly believe upstream safety was
  confirmed. The check itself is always performed at the `--write` step.
- Google Calendar / shared Sheets still have no REST connector (a
  pre-existing, documented exception). Out of scope for this work — writing
  new connectors is a separate task.

---

## 260816b — Adversarial-verification follow-up: removing connector-silence steering + a routing gate

### Scope / layer

Cross-cutting layer. The 260816 audit concluded "zero MCP-steering
violations," but an independent adversarial verification **refuted that
conclusion**. This entry is the handling of that refutation.

### What went wrong

- **Audit scope error**: the earlier audit only swept `skills/**/SKILL.md`
  and reported it as if it were the whole thing. The actual MCP mentions
  span 21 files, 114 occurrences (mostly anti-MCP policy text, so the safety
  conclusion itself still holds) — the problem was narrowing the scope and
  then speaking as if it were universal.
- **Self-confirmation structure**: the audit was run on top of its own
  fix commit (HEAD = `merge: rest-over-mcp-260816`). A textbook
  self-confirmation setup, so the blind spot stayed exactly where it was.
- **One actual violation**: `skills/academic-term-rules/.prompt.md:162` §11
  "Notion Page Writing Rules" instructs writing to a Notion page and never
  once mentions `notion_connector.py`. Silence about the connector is
  itself steering — an agent falls back to whatever tool it already has
  (= MCP). It fell into a double blind spot: no string search caught it
  because the word "MCP" never appears, and no SKILL.md glob caught it
  because it's a dotfile.

### Fix

| Site | Action | Firing confirmed |
|---|---|---|
| deleted `.prompt.md` | an orphaned older version (12 sections) of `SKILL.md` (17 sections). Zero references, its only unique content was the §11 Notion section, which is the offender itself. The current §11 had already been replaced with superscript-formatting rules | Yes — `git rm`, history preserved |
| `scientific-validation/SKILL.md:75` | replaced a pointer to an undistributed skill (kinetic-bo-pipeline) as the first-choice option with the distributed `scripts/sci_validate.py` `PHYSICAL_RANGES` | Yes — check B |
| `tests/test_service_routing.py` | new — check A (connector silence) + check B (dead skill reference) | Yes — 2/2 |
| `doctor.py SELF_TEST_SCRIPTS` | newly registered | Yes — 21→22 kinds |

A side effect of deleting `.prompt.md`: §11 had also recommended uploading
research images to `catbox.moe` (anonymous public hosting) — advice that
has no place in a lab distribution, and it disappeared along with the rest.

### Evidence / refute

- **Refute 1 failed → design fixed**: restoring the deleted `.prompt.md`
  and check A **still didn't catch it** (EXIT=0). The cause was looking for
  action verbs only in the body — the title says "Notion Page **Writing**
  Rules" but the body only says "use `<br>`", "must use public URLs," so
  "write"/"작성" never matched. Directive intent lives in the title. Fixed
  to look at title and body together and switched to stem matching
  (`writ`).
- **Refute 1 retried, passed**: restoring the same file → detected
  `FAIL … .prompt.md:162`, EXIT=1.
- **Refute 2 passed**: inserted a one-line reference naming a nonexistent
  skill as if it were real → check B detected it with file:line, EXIT=1.
  Restore confirmed.
- Removed false positives: the first version of check B picked up every
  kebab-case token — x-axis, margin-top, load-bearing — as 11 false
  positives. Instead of growing an allowlist, **the grammar of detection
  was changed** — it now looks only at places where the author explicitly
  marked "this is a skill": `` `foo` skill ``, `` skill `foo` ``,
  `Skill("foo")`. False positives 11 → 0.
  Check A also dropped one false positive, "GitHub auto-detects theme" (a
  rendering explanation), from being judged as directive.
- Regress: `doctor.py` 12 OK / 0 WARN / 0 FAIL, self-test 22/22.
  `test_doc_counts.py` caught the README count not updated 22→23 and it was
  resolved.

### Remaining risk / intentional limitations

- Both checks are **lexical**. The adversarial verifier pointed out the same
  limit — phrasing outside the listed patterns still steers undetected.
  This is a conservative design that judges by "where the author explicitly
  marked it" rather than by meaning, so it fails toward missing things
  (false negatives over false positives).
- Check A only looks at the 3 services with connectors (notion · asana ·
  github). Mail was excluded because the service name is also an ordinary
  noun, which produces too many title-matching false positives — mail
  steering is instead blocked by the `AGENTS.md §9` draft-first gate and
  `test_connectors.py`'s assertion that no SMTP code path exists.
- Calendar and shared sheets still have no connector (a documented
  exception). MCP guidance toward those two services is not in scope for
  this check, and that is intentional.

---

## 260816c — Google Calendar / Sheets connectors (removing the last MCP exception)

### Scope / layer

Core. `docs/05` and `connectors/README.md` had long stated that "Calendar
and shared Sheets have no connector, so MCP is the **only legitimate
exception**." As long as that exception stood, the REST-first policy had one
hole left open. This entry closes it.

### Two design decisions

**stdlib only.** The README's existing TODO assumed installing
google-api-python-client, but the other 5 connectors use nothing but
urllib — "just copy the folder and it works" is this package's core
principle, and making Google the one exception would break it. So the
refresh-token exchange was implemented directly in `_google_auth.py`
(roughly 150 lines). Only the first-time browser consent needs a human; every
renewal after that runs without a library.

**Reuse existing tokens.** Since the token file is read in Google's standard
format (`access_token`/`refresh_token`/`expiry_date`), anyone who already has
a Google token from another tool only needs to point `token_cache_path` at
that file. No personal path was hardcoded anywhere in the docs or code — this
is a lab-wide distribution, so only the generic form ships.

### Input/output / state ownership

| Site | Behavior | Firing confirmed |
|---|---|---|
| `_google_auth.access_token()` | refreshes 60s before expiry, rewrites to the file. A save failure only warns (the current call still proceeds) | Yes — manual run |
| `calendar_connector` reads | calendars / list / agenda — no flag needed | Yes — argparse check |
| `calendar add-event` | requires `--write`. If `--attendee` is given, prints the outward warning first | Yes — test [2b] |
| `sheets` reads | info / read | Yes — argparse check |
| `sheets append` | requires `--write`, uses `INSERT_ROWS` so existing rows are untouched | Yes — test [2b] |
| `tests/test_connectors.py` | 5 kinds → 7 kinds, 31 → 41 checks | Yes — 41/41 |
| `config/catalog.json` connectors | calendar · sheets registered | Yes |
| `docs/05` · `docs/06` · `AGENTS.md §9` · `connectors/README.md` | removed the "no-connector exception" wording, MCP is now a last resort limited to browser exploration | Yes — 0 remaining hits by grep |

### Deliberately not built

- **No calendar edit/delete.** This tool should be structurally incapable of
  the mistake of deleting someone else's event.
- **No sheet update/delete.** Overwriting an existing cell in a shared sheet
  effectively destroys whatever value someone else entered (recoverable only
  by a human digging through Google's version history). Same reasoning as
  the Notion connector being additive-only. Editing an existing value is a
  human's job, done in the browser.

### Evidence / refute

- Offline tests 41/41. Network-blocking alone wasn't enough for the two
  Google connectors, so **the `access_token()` call itself is spied on** —
  if dry-run ever looks up a token, the preview would break for anyone
  without a token file.
- **Refute 1**: planted an `update` subcommand on `sheets` → the
  additive-only check FAILs, exit 1. Restore confirmed.
- **Refute 2**: pinned `calendar`'s `is_outward` to False → the outward
  warning check FAILs, exit 1. Restore confirmed.
- CSV parsing confirmed: `--row 'a,"b,c",d'` → 3 cells (a naive split would
  push it to 4).
- Run confirmed: dry-run succeeds with no token configured; `--write`
  exits 1 with issuance instructions.
- Regress: `doctor.py` 12 OK / 0 WARN / 0 FAIL, self-test 22/22.

### Remaining risk / intentional limitations

- **Initial OAuth consent is not automated.** A script clicking through the
  consent screen on someone's behalf is the kind of automation that should
  not exist. So this connector assumes "a token already exists," and if not,
  it prints the issuance path and exits.
- `_google_auth` detects a revoked refresh token (`invalid_grant`) and
  directs the user to reissue it, but reissuing itself is still a human's
  job.
- Scope lives in the token and this code does not check it. If it was
  issued with a read-only scope, `--write` will get a 403 from the API, and
  that message is shown as-is.

## 2026-08-27 — Dead-automation detection (doctor.py)

**Scope / layer** — cross-cutting verification check in `doctor.py`; opt-in via
`config/automations.json`.

**Why** — an automation that breaks but keeps running is invisible. Logs are
written by healthy and dead runs alike, so log mtime cannot separate them, and
zero output looks exactly like a healthy idle state. Two local cases had run
that way unnoticed for months (a conversation indexer stopped in May; an OTel
sink left a 0-byte log since August) — both fully implemented, neither
producing. The check counts the produced **artifact** instead of the log.

**Inputs / outputs** — reads `config/automations.json` (name, artifact glob,
`max_age_days`, optional `min_bytes`); emits a `CheckResult` (OK / WARN, never
FAIL). Newest matching artifact decides freshness.

**Evidence** — `tests/test_dead_automation.py`, 14 cases, all passing;
registered in `SELF_TEST_SCRIPTS` so `doctor.py` runs it. Full `doctor.py`
run: 11 OK, 1 WARN, 0 new FAIL.

**Refutation** — 11 adverse cases executed: stale (30d > 7d), zero-byte,
below-`min_bytes`, missing artifact, four malformed-entry shapes, empty list,
unparseable JSON, `~` home-relative miss. Both directions pinned — the
must-NOT-warn cases (fresh output, old sibling beside a new file, no config)
guard against false alarms, which would train users to ignore doctor.

**Deferred risk** — thresholds are the user's estimate, not a measured fact,
so findings stay advisory (WARN). The check verifies that output *appears*,
not that its content is correct.

**Pre-existing, untouched** — `tests/test_assumption_check.py` fails on this
machine for a missing `scipy`; unrelated to this branch and present on
`origin/main`.


## 2026-09-02 — Tool connectivity check (orphan / untested ratchet)

**Scope / layer** — cross-cutting verification: `scripts/connectivity_check.py`,
doctor check 13, `tests/test_connectivity.py`, `tests/test_tool_cli_smoke.py`.

**Why** — measured 2026-09-02: nine tools (`hplc_parser`, `jcr_batch_verify`,
`excel_formula_check`, `fetch_public_vector`, `primer_structure_check`,
`variant_filter`, `convert_literature`, `manuscript_packet`, `fetch_github`)
had no doc naming them, no importer and no test, while doctor reported 12 OK.
This ledger itself was read by nothing. The failure the ledger describes
("build the right artifact and nothing calls it") had happened to the ledger.

**Rule** — every non-underscore `.py` under `scripts/`, `scripts/connectors/`
and `skills/*/scripts/` is classified on two axes. *Reachable*: a doc an
agent/user reads names it, or a module imports it, or a hook/installer/doctor
runs it. *Exercised*: `tests/**`, `skills/*/tests/**`, `doctor.py` or `evals/`
names it. ORPHAN (unreachable) = FAIL. UNTESTED (reachable, no test) = WARN
in doctor, with a ratchet in the test (`MAX_UNTESTED`) so the count can only
fall. Prose that says "hplc parser" without `.py` does not count — the stem
alone matched unrelated sentences.

**Ledger contract** — an entry may carry `wired-by: <path>` lines; every path
must exist. This is the only mechanically checked part of the ledger.

**Resolution of the nine** — routed (README package-layout table +
`docs/agents/08-verification-routes.md` + smoke test): the six `scripts/`
tools, `convert_literature.py`, `fetch_github.py`. Retired (deleted; git
history keeps them): `skills/research-lookup/scripts/manuscript_packet.py`
(pure helpers with no importer in the toolkit *or* the authoring tree) and
`skills/primer-design/tests/test_md_vs_direct.py` (depends on a task-builder
skill that does not ship in this toolkit, printed FAIL and exited 0 — a test
that can never pass and never fails). The authoring tree should drop the same two files.

**Also wired** — `skills/web-scraping/tests` (129 pytest cases: EZproxy scope,
PDF pipeline, target safety, GitHub failure surfacing) now runs under doctor;
`SELF_TEST_SCRIPTS` accepts a directory entry and runs it with pytest.

**Evidence** — `python scripts/connectivity_check.py` → 0 orphan; doctor 13 OK;
`tests/test_tool_cli_smoke.py` re-parses real output (2 peaks at 3.0/7.5 min
from a synthetic chromatogram; hairpin primer FAILs, clean primer PASSes;
3-row PASS/FAIL matrix).

**Refutation** — synthetic trees: nothing-points-here → ORPHAN exit 1;
doc-only → UNTESTED exit 0 and exit 1 under `--max-untested 0`; import+test →
OK; `_helper.py` not a tool; stem-only prose does not count; dangling
`wired-by:` → exit 1; empty tree → PASS; adverse tool inputs (non-chromatogram
file, no primer sequences, missing CSV) never yield a silent PASS.

**Deferred risk** — 52 reachable skill scripts have no test in this toolkit
(they are downstream copies of skills authored elsewhere). The ratchet stops
growth; it does not shrink the number.

wired-by: doctor.py
wired-by: scripts/connectivity_check.py
wired-by: tests/test_connectivity.py
wired-by: tests/test_tool_cli_smoke.py
wired-by: skills/web-scraping/tests

## 2026-09-02 — Doctor verdict quality: upstream outage ≠ broken tool

**Scope / layer** — cross-cutting: `doctor.py` (`_run_python`,
`_classify_selftest_failure`, `check_toolkit_selftests`, `_run_test_script`),
`tests/test_si_institutional.py`, `tests/test_doi_verify.py`,
`tests/test_doctor_selftest_verdicts.py`, `PROJECT_STRUCTURE.md`.

**Why** — measured 2026-09-02: Europe PMC answered HTTP 500 in the morning
and 404-for-every-PMCID in the evening; the fixture record's `hasSuppl`
flipped to N. Only `[network]` cases failed, yet doctor said "a verification
tool is broken". The tests' availability probe was a TCP handshake, which
succeeds while the REST service is down. Separately, `_run_test_script`
chose its summary line by matching two Korean words that no test has printed
since the 2026-08-28 translation — the summary silently fell back to the
generic message on every run.

**Change** — (1) one `_run_python` helper replaces four `subprocess.run`
copies; (2) a self-test whose failing lines are all `[network]`-tagged and
whose output carries an outage marker (HTTP 5xx/429, URLError, timed out…)
is reported as *blocked by an upstream outage* → WARN, never FAIL; a mixed
failure stays FAIL; (3) the two network tests probe the endpoint/record they
actually use and SKIP with the reason on the line; (4) the summary is the
script's own last stdout line; (5) `PROJECT_STRUCTURE.md` table rows that had
drifted below a prose section are back in the table.

**Evidence** — doctor 13 OK / 1 WARN / 0 FAIL; the "Skill reference
integrity" row now prints the script's real verdict ("ALL PASS — every
reference exists") instead of the fallback; `test_si_institutional.py` prints
`[SKIP] Europe PMC upstream reports hasSuppl='N' …` and exits 0.

**Refutation** — `tests/test_doctor_selftest_verdicts.py`, 23 cases:
outage-only → WARN; broken → FAIL; outage + broken → FAIL (an outage never
hides a real break); `[network]` FAIL *without* an outage marker → broken (a
wrong answer from a live API is a real bug); crash with no FAIL line →
broken; timeout raises; exactly one `subprocess.run` in doctor.py; the Korean
matcher is gone.

**Deferred risk** — the SI fixture (PMC4456712, "3 SI files on 2026-08-07")
may be stale rather than the service degraded; when Europe PMC recovers and
still says hasSuppl=N, replace the fixture PMCID.

wired-by: doctor.py
wired-by: tests/test_doctor_selftest_verdicts.py
wired-by: tests/test_si_institutional.py
wired-by: tests/test_doi_verify.py
