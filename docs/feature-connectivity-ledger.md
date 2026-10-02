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

## 2026-09-02 — Shared HTTP retry policy for the scripts/ tools (sci_http)

**Scope / layer** — sub-feature under the `scripts/` tools: `scripts/sci_http.py`;
callers `ref_fetch.py` (`_http_get_json`, `_http_get_text`), `si_fetch.py`
(`_fetch_archive`), `jcr_batch_verify.py` (`_get`); `doi_verify.py` inherits
through `ref_fetch`.

**Why** — measured 2026-09-02: six private `for attempt … urlopen` loops that
disagreed on what to retry (one retried every non-404 status including
400/401/403; one retried nothing) and none honoured `Retry-After`.

**Contract** — 429/5xx and network errors retried with linear backoff;
other 4xx raised at once; `Retry-After` honoured (capped 30 s); no sleep
after the last attempt; `(value, error)` tuple helpers keep the exact error
strings the existing tests pin (`not_found`, `HTTP 503`, `URLError: …`,
`JSON parse error: …`). `opener`/`sleep` injectable.

**Scope boundary (deliberate)** — skill folders install stand-alone and
cannot import `scripts/sci_http.py`, so `biorxiv-database`, `openalex-database`
and `web-scraping` keep their private loops. The two shared skills are
authored in the runtime tree (skill_drift rule): a change there goes to the
runtime first.

**Evidence** — `tests/test_sci_http.py` 23/23 with a scripted fake opener;
`test_doi_verify.py` 45/45 and `test_si_institutional.py` 19/19 unchanged
through the swap; `test_tool_cli_smoke.py` 28/28 (jcr `--help`).

**Refutation** — 500,500,200 → success with sleeps [1.5, 3.0]; 404 and 403 →
raised at once, no sleep; 429 + `Retry-After: 2` → sleeps 2.0 not 1.5;
`Retry-After: 600` → capped; URLError ×3 → NetworkError with 2 sleeps;
TimeoutError retried; `retries=0` rejected; bad JSON → parse error tuple.

**Deferred risk** — `ref_fetch._download_pdf` still has its own redirect/
content-type handling (it must inspect the response, not just the body);
left as is.

wired-by: scripts/sci_http.py
wired-by: scripts/ref_fetch.py
wired-by: scripts/si_fetch.py
wired-by: scripts/jcr_batch_verify.py
wired-by: tests/test_sci_http.py

## 2026-09-03 — doctor.py split into doctor_lib/ (entry point unchanged)

**Scope / layer** — structural: `doctor.py` 1,305 → 269 lines; new package
`doctor_lib/` (result 80 · sentinel 357 · fswalk 31 · checks_env 188 ·
checks_repo 275 · dead_automation 152 · selftests 99). Every symbol a test
reads (`STATUS_*`, `SELF_TEST_SCRIPTS`, `check_*`, `_run_python`,
`_run_test_script`, `_is_placeholder`, `API_KEY_RE`, `scan_research_markers`,
`_classify_selftest_failure`) is re-exported by name from `doctor.py`.
`SELF_TEST_SCRIPTS` stays in `doctor.py` verbatim because
`tests/test_doc_counts.py` reads it from that file's source.

**Why** — six concerns in one 1,300-line module (sentinel scanner, env
checks, repo checks, dead-automation detector, self-test runner, reporting).

**Deliberately NOT split** — `skills/web-scraping/scripts/fetch_academic.py`
(1,638 lines) and `skills/get-available-resources/scripts/detect_resources.py`
(1,767 lines). Both are shared-skill scripts; the SSOT rule sends structural
changes to the authoring tree first. Measured 2026-09-02: fetch_academic
differs from its runtime copy by 166 lines (translation-level, truly
shared); **detect_resources differs by 2,050 lines — runtime copy 401 lines,
toolkit copy 1,767** — the toolkit has effectively forked it. Which copy is
canonical is the maintainer's call, so the split is deferred with the seam
list in `~/scratch/sci-toolkit-refactor-plan-260902.md` §D.

**Test edits (both widen a scope, neither weakens a check)** —
`tests/test_doctor_selftest_verdicts.py`: "exactly one `subprocess.run`" now
counted over `doctor.py` + `doctor_lib/*.py` (the one call moved into
`result.py`). `tests/test_doc_counts.py`: the "every test is reachable from
doctor" scan now concatenates `doctor_lib/*.py` (the two `_run_test_script`
callers moved there; scanning `doctor.py` alone reported two false "never
runs"). Reproduced on the pre-split tree via `git stash`: passed there, so
the failure was caused by the split, not pre-existing.

**Sentinel self-exemption** — the scanner skipped `doctor.py` by basename
because it carries the detection regexes as literals; `sentinel.py` now
carries them too, so `SENTINEL_DETECTOR_FILES = {"doctor.py", "sentinel.py"}`.
Fixture exemptions (`SENTINEL_SELF_TEST_FILES`) untouched.

**Evidence** — `python doctor.py` → 13 OK / 1 WARN / 0 FAIL (34 self-tests);
`doctor.py --json` → 14 checks; every module < 500 lines; no star imports.

**Deferred risk** — the detector exemption is by basename, so any other file
named `sentinel.py` would be skipped by the secret scan; tighten to the
`doctor_lib/` path if a second one ever appears.

wired-by: doctor.py
wired-by: doctor_lib/selftests.py
wired-by: doctor_lib/sentinel.py
wired-by: tests/test_doctor_selftest_verdicts.py
wired-by: tests/test_doc_counts.py

## 2026-09-03 — Gates that stop regrowth: SKILL.md size ratchet, dual-mode test runner, offline switch

**Scope / layer** — cross-cutting: `tests/test_skill_sizes.py`,
`tests/conftest.py`, `doctor_lib/selftests.py` (`is_pytest_style`,
`_selftest_command`, `OFFLINE_ENV`), `doctor.py --offline`, `pytest.ini`
(`network` marker), the three network probes (`test_si_institutional`,
`test_doi_verify`, `biorxiv-database/tests/test_preprint_search`),
`tests/test_sci_http.py` rewritten pytest-style as the conversion exemplar.

**Why** — (1) avoid-ai-writing/SKILL.md is 93.6 KB with nothing to stop
regrowth after a hand trim; the runtime copies are the same size, so the
trim is runtime-first and this gate only ratchets. (2) Every check in
`tests/` was a script, so `-k`, markers and per-test reporting did not
exist, and a pytest-style file dropped into `tests/` would have been run as
a bare script by doctor — defining its functions and exiting 0 without one
assertion, a silent pass. (3) There was no way to run doctor on a machine
without internet, or during an upstream outage, without red.

**Rules** — SKILL.md ≤ 24 KiB hard, > 16 KiB advisory; three grandfathered
files may only shrink and must be delisted once under the cap. A file that
defines `def test_` runs under pytest in both runners (conftest and doctor);
everything else stays a subprocess script. `SCI_TOOLKIT_OFFLINE=1` (set by
`doctor.py --offline`) makes script probes SKIP with the reason on the line
and deselects `network`-marked pytest tests.

**Evidence** — `doctor.py --offline` → 13 OK / 1 WARN / 0 FAIL; online run
identical; `pytest tests/` collects 66 items (19 native + 47 script items);
`pytest tests/test_sci_http.py` collects exactly 19 (explicit-path double
collection fixed — measured "IndexError: pop from empty list" before).

**Refutation** — `test_doctor_selftest_verdicts.py` (31 cases): a pytest-
style file with a failing assert registered in SELF_TEST_SCRIPTS → FAIL
with the assertion text in details (so it was run under pytest, not as a
script); a `network`-marked test that asserts False → OK under offline, FAIL
online; the env var is visible inside the subprocess. `test_skill_sizes.py`
(48 cases) pins every verdict on synthetic size tables: over cap, exactly
at cap, grandfathered +1 byte, grandfathered under cap ("remove it"),
grandfathered with no file, empty tree.

**Deferred** — the other 34 script-style tests convert one file per commit
using `test_sci_http.py` as the pattern; nothing forces it, both runners
accept either style indefinitely.

wired-by: tests/test_skill_sizes.py
wired-by: tests/conftest.py
wired-by: doctor_lib/selftests.py
wired-by: tests/test_sci_http.py
wired-by: pytest.ini

## 2026-09-03 — GitHub-survey adoptions: spec contract, script-level drift, dependency declaration, gitleaks layer

Source: a 12-repo structure comparison (K-Dense-AI/scientific-agent-skills,
Imbad0202/academic-research-skills, anthropics/claude-plugins-community,
wshobson/agents, alirezarezvani/claude-skills, …); only rules whose gap was
measured here were adopted.

### P1 — Agent Skills structural contract (`tests/test_skill_contract.py`)
**Why** — the upstream contract applied to 37 skills found 8 violations. One
was a live defect: paper-extract kept ten Korean triggers under a top-level
`triggers:` key that no harness reads; the session's skill list showed
paper-extract with no description at all. **Rule** — closed frontmatter key
set, name = folder, description ≤ 1,024 chars, local links resolve, scripts
compile, no tracked bytecode; body > 500 lines advisory for the three
grandfathered files. **Fixes** — paper-extract triggers folded into
description (+ `execution_method` dropped, no consumer); avoid-ai-writing
`version` → `metadata.version`; scientific-validation and
spec-driven-research-dev descriptions condensed to < 1,024 with the full
trigger lists moved into a body section; repo CLAUDE.md no longer names
`triggers:` as a valid place. Shared skills edited in the authoring tree first
(claude-scientific-skills 633af8d). **Evidence** — after the rewrite the
harness re-listed paper-extract WITH its description and Korean triggers
(firing test). 54 cases incl. both directions per rule.

### P2 — skill_drift compares scripts/ and references/
**Why** — detect_resources.py differed by 2,050 lines for 26 days while the
SKILL.md-only compare said SAME. **Now** — per-file drift / toolkit-only /
runtime-only, CRLF-insensitive, `__pycache__`/`downloads/` ignored; SAME only
when prose and files match. `tests/test_skill_drift.py` +9 cases.

### P6 — `config/skill-requirements.toml` (generated) + doctor check 14
**Rule** — every import a skill script needs, module-level or lazy, except
those inside `try: … except ImportError` (the author's optional marker);
import → pip mapping; `--check` fails when the TOML lags the scripts;
`--missing` lists packages that do not import here → doctor WARN (never FAIL).
docs/06 stays hand-written. `tests/test_skill_requirements.py` 12 cases.

### P5 — gitleaks second layer (`.gitleaks.toml`, doctor check 15, CI step)
**Verdicts** — absent binary WARN (SENTINEL still ran), clean OK, findings
FAIL, tool error WARN; allowlist = the same detector/fixture files SENTINEL
exempts (pinned). CI installs a pinned release so doctor runs it there.
🔴 The real binary has NOT run yet (none on laptop or home PC; installing is a
user rail) — `tests/test_gitleaks_layer.py` pins the wrapper with a shim;
first real run happens on the next CI push.

**Deferred / queued** — P3 lockfile (skipped: P2 covers content drift; upstream
commit unknowable for runtime-adopted skills), P4 version-per-merge, P7
scheduled CI run, P8 Codex manifest — proposals in the night-run folder.

wired-by: tests/test_skill_contract.py
wired-by: tests/test_skill_requirements.py
wired-by: tests/test_gitleaks_layer.py
wired-by: scripts/skill_requirements.py
wired-by: scripts/skill_drift.py
wired-by: config/skill-requirements.toml
wired-by: .gitleaks.toml
wired-by: .github/workflows/doctor.yml

### Addendum 2026-09-03 — first CI run after the push found two defects of my own
1. **Sniff too loose.** `is_pytest_style` classified four script-style checks
   (test_body_typo_lint, test_feedback_sanitize, test_dead_automation, biorxiv
   test_preprint_search) as pytest-style because they define `test_*` helpers
   called from a `__main__` guard; CI had no pytest and all four went red with
   no FAIL line. Rule is now `def test_` present AND no `__main__` guard, in
   both `doctor_lib/selftests.py` and `tests/conftest.py`; pinned by a
   verdicts case that runs such a script through doctor.
2. **gitleaks allowlist anchors.** With an absolute `--source`, gitleaks
   reports absolute paths and `^tests/...$` never matched: 13 "findings", all
   in allowlisted files. doctor now passes `--source .`, the regexes are
   `(^|/)…$`, and the test matches both a relative and an absolute sample.
3. CI dependencies: `pytest` and `httpx` added to tests/requirements.txt (the
   runner had neither; the laptop had both, which is why nothing failed here).

---

## 2026-09-23 — journal-presentation-maker → journal-ppt (skills/, sub-feature)

**Scope.** The bundled deck skill was the one its own SKILL.md marks DEPRECATED
(260913). Its successor `journal-ppt` was never added, so the toolkit shipped
only the version documented as defective. Replaced it and removed the two test
exemptions the old file needed.

**Inputs / outputs.** in: runtime copy at
`claude-scientific-skills/scientific-skills/active/journal-ppt`. out:
`skills/journal-ppt/` (5 files), `config/catalog.json` entry,
`config/skill-requirements.toml` (regenerated by the scanner: lxml, pptx), 9
name references across AGENTS/CODEX/PROJECT_STRUCTURE/README and 5 adjacent
skills that list it in their own routing tables.

**Evidence.** pytest 57/57 (baseline 57/57 re-measured before the change);
doctor 14 OK / 2 WARN / 0 FAIL (the 2 WARN — gitleaks absent, connectivity
ratchet — predate this work).

**Refutation.** Two allowlist entries were added to reference checks, so both
were tested against a synthetic miss: an invented skill name
(totally-nonexistent-skill) and an invented script path
(scripts/does_not_exist_xyz.py) were each still reported. Neither exemption is
a blanket one. (Those two probe names are written without backticks on purpose:
the dead-reference check reads a backticked name as a real skill reference, and
this paragraph would otherwise report itself.)

**What the gate caught that the plan missed.**
1. `git rm` left the old directory alive because `__pycache__` is untracked —
   the contract test reads the filesystem, so it saw a skill with no SKILL.md.
   Deleting tracked files is not deleting a skill.
2. `journal-ppt` cites the `pptx` skill's QA conventions in 5 places.
   `test_service_routing` had no notion of `external: true`, which
   `test_skill_references` already had as `EXTERNAL_SKILLS` — the same idea was
   implemented in one test and absent in its sibling. Now read from the catalog
   rather than hardcoded, so a future external skill needs no test edit.
3. `scripts/logo_fetch.py` and `fetch_institution_logo()` are referenced in 3
   places (SKILL.md, pipeline.md, deck_builder docstring) and **exist nowhere**,
   including in the runtime tree. This is an upstream defect that came in with
   the skill, not one the swap created. `authors_slide()` takes finished PNG
   paths, so the code works — only the instructions were wrong. Rewrote them to
   say what the builder actually does rather than allowlisting a phantom file.
4. SENTINEL flagged two unpublished enzyme markers from this lab that the skill
   used as *typography examples* (one in style_spec.md's italic-prefix rule, one
   in a qc_deck.py comment). Replaced with textbook-safe labels of the same
   shape; the rule they illustrate is unchanged. The names are deliberately not
   repeated here -- this ledger ships with the package, so writing them down
   would re-introduce exactly what the scan caught.
5. Python's `write_text` emits CRLF on Windows, so every edit re-broke the LF
   policy pinned in `.gitattributes`. Normalized before each manifest rebuild.

**Deferred risk.** The runtime copy still carries the phantom `logo_fetch.py`
instructions and the unsanitized enzyme/project names; only the toolkit copy was
corrected here, which widens the existing toolkit↔runtime drift by design (the
sanitization delta is intentional; the logo_fetch fix is not, and belongs
upstream). Tracked under the skill_drift backlog card.

wired-by: config/catalog.json
wired-by: config/skill-requirements.toml
wired-by: tests/test_service_routing.py
wired-by: tests/test_skill_references.py

## 2026-09-24 — skill_drift intended-difference declarations (scripts/, sub-feature)

**Why** — the 260924 drift pass classified 27 drifting skills and found only 3
real ports; the rest were license terms, toolkit-ahead edits, environment-bound
paths, or a size ratchet. `skill_drift.py` could not hold that judgment, so the
report never shrank and every session would re-review the same 27.

**Now** — `config/skill-drift-intended.json` (written only by `skill_drift.py
--declare <skill> --reason "..."`). Each entry carries a reason (>= 30 chars) and
the fingerprints of BOTH copies (SKILL.md + scripts/ + references/,
CRLF-insensitive). While both match, the row is INTENDED and does not fail the
run. Either side changing makes it stale (the changed side is named) and the row
falls back to DRIFT / LAGGING. A declaration on identical copies or on a skill
the toolkit does not ship is "unused" and fails the run, so the file cannot
accumulate dead entries. Shape is validated with no runtime tree, so CI checks it.

**Inputs / outputs** — reads both skill trees and the declaration file; writes
the declaration file only on `--declare` (LF, sorted keys). Exit 1 now also
means a malformed or unused declaration.

**Evidence** — `tests/test_skill_drift.py` 36/36 (+22 cases: refusals x3 with
nothing written, INTENDED + reason carried, runtime-side stale, new runtime
script stale, toolkit-side stale, CRLF-only stays current, converged -> unused
-> exit 1, malformed entries caught without a runtime tree, corrupt file -> exit
1, real config well-formed). Mutation check: dropping scripts/ from the
fingerprint, or unpinning the toolkit side, each fails exactly one case.

**Refutation on the real tree** — of the 5 skills the 260924 card recorded as
"do not port", only 3 held up on re-inspection: experiment-hub and primer-design
(runtime Proprietary vs toolkit MIT) and generate-image (runtime names skills
the toolkit does not ship; toolkit script is ahead). paper-extract and
patent-invention-disclosure were NOT declared: besides the environment-bound
lines, each carries a portable runtime change (a literature-review
cross-reference; an avoid-ai-writing section in translation_register.md). A
whole-skill declaration would have hidden those — the fingerprint pins the whole
pair, so a declaration must only be made when the WHOLE diff is intended.
Result on the real tree: LAGGING 14 -> 13, DRIFT 10 -> 8, INTENDED 3.

**Deferred risk** — avoid-ai-writing (size ratchet) and statsmodels /
conda-env-manager (toolkit ahead, to be pushed upstream) are pending actions, not
intended differences, and were deliberately left undeclared.

wired-by: scripts/skill_drift.py
wired-by: tests/test_skill_drift.py

---

## sequence-verification — does the variant exist, and what do reads get compared to (260928)

**Scope / layer** — new skill (sub-feature, `molbio`), plus one function added to
`primer-design`'s SnapGene parser. Answers a question that was previously done
by hand: whether a plasmid variant exists in any saved map, and what a
sequencing read should be aligned against.

**Why it exists** — a filename, a folder name, and an annotated mutagenesis
primer are all consistent with a map holding pure wild-type sequence. SnapGene
stores a primer's *binding site*, which is template sequence, so a map can list
`iPCR_E223A` in its primers and carry `E` at 223; biopython reads it the same
way. In the audit that prompted this, 28 candidate files all belonged to a
variant construction project and all 28 were wild type — the variant map had
never been saved, and nothing in the file names said so.

**Prior art / delta** — kept: `primer-design` owns the SnapGene binary format
(`snapgene_parser`, `snapgene_writer`) and in-silico cloning, and is a hard
dependency rather than being duplicated. Dropped: a ligation simulator of this
skill's own — `write_cloning_construct` already exists and is tested. New: the
primer-sequence reader (the feature table cannot express it), residue scanning
across many files, reference-map construction by codon edit, and Sanger read
coverage. `scientific-validation` was examined and deliberately NOT
cross-linked: it gates whether a measured number is plausible, a different job
from sequence identity, and a link there would be noise.

**Inputs / outputs** — reads `.dna` / `.gb` maps plus a wild-type reference;
writes one GenBank reference map, and only on success. State ownership: none —
every script is a pure function of its inputs except `build_reference_map.py`,
which writes the single `--out` path and unlinks it if the re-read disagrees.

**Two failure modes are enforced, not documented.** Residue numbering comes from
`--reference`, never a CDS annotation, whose bounds are routinely a base or two
off the real frame (the fixture deliberately mis-annotates by one base). And the
map is built by editing a construct that was really built, not by simulating a
ligation: an insert cut for one vector carries that vector's frame, and in the
measured case a pETDuet MCS1 insert dropped into pET-28a's BamHI site shifted
the frame and died at 39 aa, against 352 aa for the lab's own map.

**Evidence** — `tests/test_sequence_verification.py` 20/20 on synthesised
constructs whose answer is known exactly: absence AND presence both asserted;
the annotated-primer trap asserted directly (one file simultaneously yields
`K8R:CGT` from its primer and reads wild type at residue 8); codon recovery
correct despite a deliberately mis-annotated CDS. Refutation: wrong base residue,
codon/residue disagreement, malformed token, missing path, empty directory,
corrupt file, unreachable target — each returns a usage/failure exit code, and
no output file is written on any of them. Verified on real data before the
fixtures existed: 28 files scanned WT, three stored primers independently
recovered (forward and reverse agreeing), reference map reproducing a
hand-built one to the base (2 nt differ, fusion 352 aa unchanged).

**Deferred risk** — `find_variant_maps.py` opens files, so on synced cloud
storage it hydrates placeholders; the docs require a shortlist first, but
nothing enforces it. `read_coverage.py`'s quality bands (600/850) are
conventional Sanger numbers, not measured against this lab's provider.

wired-by: skills/sequence-verification/SKILL.md
wired-by: tests/test_sequence_verification.py
wired-by: config/catalog.json

## sequence-verification / construct_mw.py — what protein does the map express, and how heavy is it (260929)

**Scope / layer** — sub-feature of `sequence-verification` (one new script, no new skill).
Trigger: a task quoted molecular weights that were native-only, while the band on the gel is the
whole vector-encoded fusion (pET-28a leader, 34 aa, about 3.5 kDa).

**Prior art** — `primer-design/src/primer_design/expression_analyzer.py` also reports a MW, but
from a protein string the caller supplies: no map, no leader, no mutation handling, and a
hand-rolled residue table. Kept as is. Its `REFERENCE.md` table now points to `construct_mw.py`
for the mass of what a plasmid really expresses. Not duplicated: translation and feature lookup
reuse `_seqcommon`; the masses come from Biopython ProtParam.

**Inputs / outputs** — reads one `.dna` / `.gb` map, prints fusion / native / thrombin-cleaved
MW, pI and e280 (text or `--json`); with `--mutate` also the mutant and wild-type pairs. State
ownership: none, writes nothing. Exit 0 computed, 1 unresolved, 2 usage.

**Failure modes enforced, not documented** — the ORF is anchored at the T7 promoter and takes the
first downstream ATG, because the longest ORF in a pET-28a map is `lacI` (360 aa), not the insert.
With no anchor and no `--start-pos` the script refuses. Mutation numbering is checked against the
residue actually present, so an off-by-two numbering (Met1-based vs a numbering offset by two) fails
loudly instead of mutating the wrong residue. SnapGene labels carry their description appended
("T7 promoter promoter for bacteriophage T7 RNA p"): exact match first, then a unique prefix, and
an ambiguous prefix raises.

**Evidence** — `tests/test_sequence_verification.py` 38/38 (18 new checks) on synthetic constructs
with exactly known answers. Independent cross-check: the ProtParam mass equals a residue sum
(`IUPACData.protein_weights` minus 18.0153 Da per peptide bond). On real maps it reproduced the
old native-only records (35.923 and 29.047 kDa) and gave the fusion figures 3.5 kDa higher.
Refutation: no anchor, no ATG, no stop, ambiguous base, motif absent or ambiguous, wrong base
residue, residue out of range, malformed token, missing file. One test failed at first (1 Da
resolution from rounding kDa to 3 decimals); fixed by exposing `mw_da` at 2 decimals, the
tolerance was not loosened.

**Deferred risk** — masses are computed, not measured, and the initiator Met is always kept; Met
removal, signal peptides, cofactors and PTMs are not modelled. A map with a C-terminal tag read
through a missing stop is reported as an unresolved construct, not guessed. In the motivating case the
mutant plasmid file was never located, so its figures rest on the wild-type map plus the
substitutions.

wired-by: skills/sequence-verification/SKILL.md
wired-by: AGENTS.md
wired-by: tests/test_sequence_verification.py
wired-by: config/catalog.json

## Refactor batch 1 (2026-10-02) — four units on one branch

Branch `scitoolkit/fix/refactor-batch1-261002`. Each unit went through implement,
prove, refute, connect, regress. Baseline before any change: `pytest -q` = 60
passed (testpaths `tests/`; skill-local suites run through doctor, not through
that command).

### Unit 1 — PROJECT_STRUCTURE.md skills list is checked against `skills/`

**Scope** — the layout table's `skills/` row named 26 of the 42 skill folders.
Sixteen had no entry (the 13 reported at the start plus `analysis-code-testing`,
`data-quality-checks`, `debugging-loop`, with `research-lookup`/`research-search`
only present in an abbreviated "research-ideation/-lookup/-search" spelling no
tool could match).

**Layer** — doc-vs-reality gate (same family as the count checks).

| | |
|---|---|
| Input | `PROJECT_STRUCTURE.md` layout row, folder names under `skills/` |
| Output | list of defects; any entry makes `tests/test_doc_counts.py` exit 1 |
| SSOT | the `skills/` folders (already pinned to `config/catalog.json` by check 0 of the same test) |

**Evidence** — the row now lists every folder as a backticked name;
`test_doc_counts.py` passes. Run against the pre-change document, the new check
names the folders it was missing.

**Refutation** — a fake folder (fake-skill) added to the disk set fails; a
documented name with no folder fails; a table with no `skills/` row fails;
removing one backticked name (`web-scraping`) fails. Three of these run on every
execution as negative controls inside the test, so a parser that stops matching
cannot leave the gate silently green.

**Deferred risk** — only the `skills/` row is parsed; other prose that lists
skills (README tables, catalog roles) is not cross-checked here.

wired-by: tests/test_doc_counts.py
wired-by: PROJECT_STRUCTURE.md
wired-by: doctor.py

### Unit 2 — `paramguard` skill redirected to `fiducial`

**Scope** — the paramguard repo was deleted on 2026-09-30 and replaced by
`fiducial` (public GitHub repo, PyPI fiducial-check 0.1.0).
`skills/paramguard/SKILL.md` still said "not published yet" and pointed at the
dead repo.

**Layer** — skill documentation + catalog entry (no code in the folder).

**Decision** — same tool, so the folder was renamed (`git mv`) to
`skills/fiducial`. Install is `pip install fiducial-check` (command and import
name `fiducial`); the pre-commit block points at the `fiducial` repo `v0.1.0`
hooks (fiducial-names, fiducial-literals, both defined in the upstream
`.pre-commit-hooks.yaml`). The fifth rule (`pointers`), `--conflicts`,
`fiducial check` and `--format=json` were added from the upstream README. A
"Formerly paramguard" line stays for people searching the old name. The
`PARAMGUARD_SKIP` bypass was dropped because upstream has no such switch.
`catalog.json` carries `fiducial` (`pip_package: fiducial-check`) instead of
`paramguard`.

**Evidence** — `gh repo view` (public, default branch main), PyPI JSON
(fiducial-check 0.1.0, Python >=3.10), upstream README read in full, every
flag used in the skill found in the upstream `cli.py`. `test_skill_contract`
(name = folder, description <= 1024 chars), `test_skill_requirements`,
`test_skill_references`, `test_doc_counts` pass. `git grep paramguard` outside
CHANGELOG history now finds only the deliberate "formerly" mentions and the
catalog role text.

**Refutation** — the first rewrite left the description at 1123 characters and
`test_skill_contract` failed it; it was shortened without touching the Korean
triggers. Nothing was written into the skill that the upstream CLI does not
define.

**Deferred risk** — the skill has no runtime counterpart under the maintainer's
skills tree (TOOLKIT-ONLY in `skill_drift.py`), so there is nothing to port
back. It describes upstream behaviour at v0.1.0 and will drift if upstream
changes; no automated check compares it to the PyPI release.

wired-by: config/catalog.json
wired-by: skills/fiducial/SKILL.md
wired-by: tests/test_skill_contract.py

### Unit 3 — primer-design inline `_run_tests()` moved to a pytest suite

**Scope** — seven modules under `skills/primer-design/src/primer_design/` each
carried an inline `_run_tests()` plus an `if __name__ == "__main__"` hook. None
of it ran under doctor or CI.

**Layer** — test infrastructure for a skill (a skill-local suite registered as a
directory entry in `SELF_TEST_SCRIPTS`, like lab-record, experiment-hub and
web-scraping).

| | |
|---|---|
| Input | the seven modules; `skills/primer-design/tests/` (`conftest.py` puts `../src` on `sys.path`) |
| Output | 72 pytest tests across seven `test_<module>.py` files |
| Removed | 1,328 lines: the seven `_run_tests` bodies and hooks, plus the `Path` import only the test used |

**Evidence** — assertion count by AST (assert statements and `check()` calls)
plus the dynamic cases an AST cannot see (a 12-name loop and two
expected-exception cases): colony 19, del 6, expression 24, order_sheet 58,
restriction 25, subst 3, vector 40 = 175 before, 175 after. All seven inline
suites passed before the move, so no `xfail` was needed. No document,
`SKILL.md` or script invoked `python module.py` as a self-test (grep over docs,
scripts, tests, doctor_lib), so no reference needed updating. The suite also
passes with `primer3` blocked, so CI needs no extra package; `xlwt` and `xlrd`
were added to `tests/requirements.txt` for the Macrogen `.xls` case.

**Refutation** — in a scratch copy, changing the frame rule in
`vector_registry` (`in_frame_5prime = (frame_at_insert_start == 1)`) fails 8
tests across vector_registry and restriction_cloning, and corrupting a primer-map
key fails 5 colony tests. Limits found and carried over unchanged from the inline
version: raising the 5,000 KRW minimum primer cost is NOT caught (every test
primer is long enough that the minimum never binds), and altering the first
`AGG` literal in the expression analyzer is not caught either.

**Behaviour changes in the tests** — the subst test's optional load of a private
SnapGene template from a hard-coded home path is dropped (environment-dependent,
and a personal path in a public repo); the fixed built-in template is always
used. `register_primer_pair` mutates module state, so the colony tests restore it
through a fixture. The subst "validation error" case used to print FAILED
without failing when no exception came; it is now `pytest.raises`.

**Deferred risk** — `_frame()` in the vector test adds one assertion the
original did not have (the report renders). `tests/stress_test_genes.py` is
untouched and still network-bound.

wired-by: doctor.py
wired-by: skills/primer-design/tests/conftest.py
wired-by: tests/requirements.txt

### Unit 4 — one sha256 helper for the manifest writer and verifier

**Scope** — five places hash bytes: `scripts/make_checksums.py`,
`doctor_lib/checks_repo.py`, `skills/manuscript-pipeline/scripts/figure_provenance.py`,
`skills/scientific-validation/scripts/check_raw.py`, and `scripts/skill_drift.py`
(the last hashes the normalized text of a whole skill, a different job).

**Layer** — repo-root tooling (doctor and the checksum script ship together with
the repo, and `install.py` already imports from `scripts/` the same way).

**Decision** — consolidate only the two root-level copies into
`doctor_lib/filehash.py` (`sha256_file`); `make_checksums.py` and
`checks_repo.py` import it. The skill-local hashers stay duplicated on purpose:
skills are installed individually (`install.py --skills <name>`), so a skill
script importing from the repo root would break as soon as the root is absent,
and a shared module inside one skill would add a hard `requires` edge between
skills for a four-line loop. They differ anyway (a 12-character prefix with an
"ERR" sentinel; a 16-character display form). The ~95 stdout-setup blocks were
not touched.

**Evidence** — `tests/test_checksums_manifest.py` has a fourth check: identity
of both callers with the shared function, and digests equal to `hashlib` for an
empty file, `abc` (published SHA-256 test vector), exactly one chunk, one chunk
plus one byte, and two chunks. `doctor.py --offline`: 14 OK, 2 WARN (gitleaks
absent; 47 untested tools, pre-existing), 0 FAIL.

**Refutation** — a hasher that drops the last byte of every full chunk fails
three digest cases; a local copy of the loop put back into `make_checksums.py`
fails the identity check; a one-bit flip on the chunk boundary must change the
digest; a missing path must raise `OSError`.

**Deferred risk** — stdout setup (`reconfigure(encoding="utf-8")` blocks):
recommendation is not to mass-edit. Skill scripts duplicate the block for the
same reason as the hashers (standalone copy), and a root-level helper cannot be
imported from them. If it is ever reduced, collapse only the copies under
`scripts/`, `doctor_lib/` and `tests/`, which all live at the repo root, and
leave the skill scripts alone.

wired-by: doctor_lib/filehash.py
wired-by: scripts/make_checksums.py
wired-by: tests/test_checksums_manifest.py


## Refactor batch 2 (2026-10-02) — stdout helper, HTTP consolidation, primer-design decomposition

Same constraint as batch 1: skills install individually, so nothing under
`skills/` may import from the repo root. Units 1 and 2 touch repo-root code only;
unit 3 stays inside one skill package.

### Unit 1 — one UTF-8 stdout helper for root-level code

**Scope** — about 60 files (`doctor.py`, `scripts/`, `scripts/connectors/`, `install/`,
`evals/`, `tests/`) each carried a private `reconfigure(encoding="utf-8")` block,
in four spellings with different exception lists; four connectors even reconfigured
twice, the second time without `errors="replace"` (which silently reset it to strict).

**Decision** — `scripts/_stdio.py::force_utf8(streams=None)`, next to `sci_http.py`.
Every consumer adds the scripts folder to `sys.path` (append, never insert, so it
cannot shadow anything) and calls it. `skills/**` is untouched on purpose: a skill
script cannot import it once installed alone.

**Behaviour changes** — the helper reconfigures on every platform (nine files were
`win32`-only; on Linux the call is a no-op in practice) and always uses
`errors="replace"`. `install.py` also reconfigures stdin, as before, now with
`errors="replace"`.

**Evidence** — `tests/test_stdio.py` (7 tests): idempotent on `io.StringIO`, `None`
and a stream whose `reconfigure` raises; the control (`PYTHONIOENCODING=cp949`, a
print of an emoji + em dash + Hangul) dies with `UnicodeEncodeError` without the
helper and prints valid UTF-8 with it; a converted entry point survives the same
environment; a ratchet fails if any root file grows its own `.reconfigure(` call.
Every script, connector and probe was run with `--help` under
`PYTHONIOENCODING=cp949`; the only two that fail do so identically on the base commit (an argparse `%` in a help string,
and a script with no `--help`).

**Refutation** — the cp949 control proves the test can fail; removing the helper
call from a converted script makes the ratchet and the cp949 run fail.

wired-by: scripts/_stdio.py
wired-by: tests/test_stdio.py
wired-by: doctor.py

### Unit 2 — connectors, `_google_auth` and `ref_fetch` go through `sci_http`

**Scope** — re-measured: the only root-level callers of `urllib.request` outside
`sci_http` were the four REST connectors (asana, github, notion, notion_db),
`connectors/_google_auth.py` (three call sites) and `scripts/ref_fetch.py`
(`_download_pdf`, `fetch_bibtex`). The other files named in the diagnosis do not
exist at root level. Skills were not touched.

**Decision** — `sci_http.request` gained `method=` and `data=`, `HttpError.body`
(the error response, for the connectors' "detail" excerpt), `NetworkError.detail`
(the raw reason, so the connectors' "Check your network connection: ..." text is
unchanged), `Response.header()` (case-insensitive, for the PDF content-type test)
and `http.client.HTTPException` in the retried network errors (truncated bodies).
`retries=None` means 3 for GET/HEAD and exactly **1 for every other method**, and
the connectors pass `retries=1` explicitly: a write is never replayed.

**Behaviour changes** — `ref_fetch` no longer retries a 4xx other than 404/429
(a blocked publisher answered 403 three times before); 5xx and network errors keep
the full retry budget; error strings are unchanged. A read timeout in a connector
is now a clean `[Error] Check your network connection: ...` exit instead of a
traceback. `SCI_TOOLKIT_OFFLINE` was never read by any of these callers (it only
gates the tests' network probes), so there is no offline behaviour to preserve or
change; `test_offline_env_does_not_change_caller_behaviour` pins that.

**Evidence** — `tests/test_http_callers.py` (29 tests) runs every caller against a
throw-away server on 127.0.0.1: success and empty body, 401/403/404/400 messages
with the token masked, a 503 on POST/PATCH/DELETE hits the server exactly once,
refused connection and timeout end in the caller's own message, `ref_fetch` hits a
5xx three times and a 403 once, 404 stays `not_found` / `HTTP 404`, a mixed-case
`Application/PDF` header is accepted, an HTML landing page is rejected. `tests/
test_sci_http.py` gained 11 tests for the new surface. A test fails if any root file
calls `urlopen(` outside `sci_http.py`.

**Deferred risk** — the connectors now import `sci_http.py` and `_stdio.py` from the
parent folder. `config/catalog.json` and `scripts/connectors/README.md` say so
("copy `scripts/connectors/` together with those two files"), but nothing enforces
it; a user who copies only the folder gets an `ImportError`.

wired-by: scripts/sci_http.py
wired-by: scripts/connectors/_google_auth.py
wired-by: scripts/ref_fetch.py
wired-by: tests/test_http_callers.py
wired-by: tests/test_sci_http.py

### Unit 3 — primer-design: three oversized units split behind golden tests

**Scope** — `PrimerOrderSheet` (628-line class), `generate_vector_construct_map`
(286 lines) and `RestrictionCloningDesigner.design` (320 lines), all inside
`skills/primer-design/src/primer_design/`. Pure extraction, no signature change;
`order_sheet.PrimerOrderSheet.to_*`, `cloning_report.generate_vector_construct_map`
and `design()` keep their import paths and results.

**Before the split** — the 72 existing tests did not pin any output cell, drawn
artist or design field, so `tests/characterization.py` + `tests/golden/*.json`
(generated from the pre-split code, deterministic across two runs, LF line endings)
snapshot: every sheet of the order workbooks (values, bold/fill/font, alignment,
column widths; hashes for the 1000 numbered blank rows), the xls via xlrd, CSV,
Markdown, the circular map's lines/patches/texts for seven maps, and 19 design
scenarios plus 8 error cases. Scenarios were chosen by coverage: `design()` was
92% covered after them, the only unreachable line being the "> 60 nt" warning
(primer3 rejects a longer primer first — recorded as a scenario that raises).

**Sizes** — `PrimerOrderSheet` 628 -> 328 lines (`order_sheet.py` 705 -> 404, the
writers moved to `order_sheet_writers.py`, largest function 54); `to_xlsx` 117 -> 8,
`to_macrogen_seq` 112 -> 35. `generate_vector_construct_map` 286 -> 77 in the new
`vector_construct_map.py` (largest helper 40; `cloning_report.py` 1045 -> 681,
re-exporting the function and the two data tables; shared fonts in
`_plot_style.py`). `design` 320 -> 171 (about 70 of those are the docstring and the
result dict); new helpers `_validate_design_inputs`, `_enzyme_pair_warnings`,
`_design_end_annealing` (the forward/reverse fallback ladder was written twice),
`_retry_for_hairpin`, `_primer_level_warnings`, `_check_frame`.

**Evidence / refutation** — golden tests pass unchanged after each split; the
rendered PNGs of the circular map and of `generate_cloning_report` are
byte-identical to the pre-split ones. Three mutations were each caught (a column
width, a warning string, a label offset). One dead assignment (`c5`/`c3` colours in
the frame-status block, never used) was dropped.

**Deferred** — `design()` is still the longest function in the package;
`recommend_re_pair` (130 lines), `generate_cloning_report` and
`mcp_server.py` (1073 lines) were out of scope.

wired-by: skills/primer-design/src/primer_design/order_sheet_writers.py
wired-by: skills/primer-design/src/primer_design/vector_construct_map.py
wired-by: skills/primer-design/tests/test_characterization.py

### Unit 4 — docs

`PROJECT_STRUCTURE.md` (scripts row), `scripts/connectors/README.md`,
`config/catalog.json` (connector install note), `skills/primer-design/REFERENCE.md`
(file list) and the README test count (42 -> 44) name the new helpers and files.

---

## Refactor batch 3 (2026-10-02)

### Unit 1 — connector bundle enforcement

**Scope** — `scripts/connectors/*` imports `scripts/sci_http.py` and
`scripts/_stdio.py` from the parent folder. The helper list was only prose
(README, catalog `_note`); nothing shipped or checked it.

**Change** — `config/catalog.json` gains `connectors._shared_files` (the single
list). `install/install.py` gains `connector_bundle()`, `install_connectors()` and
`--connectors-dest <folder>` (copies `scripts/connectors/` plus both helpers into
`<folder>/scripts/`; preview without `--apply`). New `tests/test_connector_bundle.py`
(15 checks, registered in `doctor.py SELF_TEST_SCRIPTS`).

**Evidence** — every connector module is imported in a fresh `python -I` process
from a temp copy produced by the real installer function, and its `__file__` must
resolve inside the temp copy (no silent fallback to the repo). A static check
fails when a connector imports any `scripts/*.py` module that the catalog does
not list.

**Refutation** — negative controls: deleting `sci_http.py` from the copy breaks
exactly the seven importers that need it (asana, github, notion, notion_db,
_google_auth, calendar, sheets); deleting `_stdio.py` breaks all of them; a plain
`copytree` of `scripts/connectors/` alone fails to import `github_connector`.

wired-by: install/install.py
wired-by: tests/test_connector_bundle.py
wired-by: config/catalog.json

### Unit 2 — primer-design `mcp_server.py` split

**Scope** — `skills/primer-design/src/primer_design/mcp_server.py` (1073 lines,
`_check_expression_viability` 241 lines, `design_re_cloning_primers` 140,
`_fetch_cds_from_gene_id` 135, `fetch_gene_sequence` 113).

**Change** — `mcp_server.py` (1073 -> 86 lines) keeps the FastMCP instance, the
tool registry (names and order) and the entry point; tool bodies moved to plain
functions in `mcp_cloning_tools.py` (277), `mcp_analysis_tools.py` (132),
`mcp_gene_tools.py` (340), `expression_viability.py` (361, pure logic) and
`_mcp_common.py` (logging + designer singletons). Every old name is re-exported from
`mcp_server`, so `tests/stress_test_genes.py` and
`python -m src.primer_design.mcp_server` are untouched. Longest functions after the
split: `fetch_gene_sequence` 88 (docstring ~25), `design_re_cloning_primers` 64
(docstring ~37), `generate_macrogen_order` 49; `_check_expression_viability` 241 -> 99 (docstring and the 35-line result dict included)
via `_translate_insert`, `_fusion_protein`, `_fusion_mw_kda`, `_start_codon_source`,
`_reading_frame_warnings`, `_active_tags`, `_internal_re_sites`, `_premature_stops`,
`_verdict`; `_fetch_cds_from_gene_id` 135 -> 73 via `_fetch_gene_summary`,
`_link_gene_to_nucleotides`, `_cds_info_from_feature`. A no-op condition
(`check_site == re_site or check_site != re_site`) was dropped.

**Evidence** — `tests/characterization_mcp.py` + `tests/golden/mcp_server.json`
(produced from the unsplit module, regenerated twice byte-identical) pin: the
registered tool list with every JSON schema and description, the registration order,
and the output of every tool for fixed inputs: 7 design scenarios (files written to
a temp dir, paths normalised), 56 viability combinations covering PASS/WARNING/FAIL,
frame mismatches, blocked C-tags and internal sites, vector-context fuzzy matching,
RE-pair / colony-PCR / frame / expression tools including unknown-vector errors, the
Macrogen order cells, and `fetch_gene_sequence` against a scripted fake Entrez (8
branches incl. not found, no links, no name match, fetch failure, codon
optimisation). A real stdio client (`mcp.client.stdio`) lists the same 9 tools and
calls one against the split server. 15 new tests; suite 78 -> 93.

**Refutation** — four mutations were each caught: a warning string in
`expression_viability.py`, a swapped registration order, a dropped Entrez link
type, and a changed default in a tool signature (schema).

wired-by: skills/primer-design/src/primer_design/mcp_cloning_tools.py
wired-by: skills/primer-design/src/primer_design/mcp_analysis_tools.py
wired-by: skills/primer-design/src/primer_design/mcp_gene_tools.py
wired-by: skills/primer-design/src/primer_design/expression_viability.py
wired-by: skills/primer-design/tests/test_mcp_characterization.py

### Unit 3 — get-available-resources `detect_resources.py` split

**Scope** — `skills/get-available-resources/scripts/detect_resources.py`
(1767 lines, no tests of its own). The refactor-batch-1 note said the toolkit copy
had forked from the runtime copy; the split stays inside the skill folder and keeps
the CLI path, flags and JSON schema.

**Change** — `detect_resources.py` is now the CLI entry (135 lines: argparse, `main`,
and re-exports of every name the old script defined, private helpers included). The
probes moved to the `scripts/resource_probes/` package (relative imports; `_common`
stays the shared top-level helper): `core.py` (82), `commands.py` (119), `cpu.py`
(266), `cgroup.py` (171), `scheduler.py` (184), `memory.py` (231), `disk.py` (70),
`accelerator_parsers.py` (289), `accelerators.py` (270), `snapshot.py` (221). Longest
function: `_detect_memory` 154 -> 68 (new `_psutil_memory`,
`_platform_memory_fallbacks`, `_effective_memory`), `collect_snapshot` 151 -> 125,
`_detect_accelerators` 151 -> 55 (`_probe_nvidia`, `_probe_amd`, `_probe_apple`,
`_apple_silicon_inferred_device`), `detect_cgroup_v2` 120 -> 52 (`_cgroup_chain`,
`_chain_limits`, `_limit_or_none`, `_cgroup_not_detected`), `detect_scheduler` 105 -> 75
(`_no_scheduler`, `_slurm_memory`).

**Evidence** — new `skills/get-available-resources/tests/` (8 tests, registered in
`doctor.py SELF_TEST_SCRIPTS`): `host_probe_snapshots.py` builds fake hosts (psutil, /proc
and cgroup files, nvidia-smi / amd-smi / rocm-smi / system_profiler output, patched
`platform` / `os` / `shutil`; the container marker default is patched too) and dumps 19
`collect_snapshot` scenarios (Linux container + Slurm + 2 GPUs, bare Linux via /proc,
Apple silicon and Intel Mac with failing probes, Windows with AMD fallbacks, skipped
accelerators, nvidia fallback, garbage and truncated output, 300 GPUs hitting the device
bound, sysconf fallback, three cgroup edge cases, empty platform / bad disk values), every
pure parser, `detect_scheduler` records for 11 environments, the real bounded command
runner (python as the fixed argv: ok, non-zero, timeout, truncation, not found, bad argv),
and the CLI as a subprocess (help flags, exit codes, `--output` / `--force`, key shape of
the live JSON). `tests/golden/detect_resources.json` was generated from the unsplit
script (twice, byte-identical) and the split passes it unchanged.

**Refutation** — five mutations over the split modules; the first round exposed three
gaps in the scenarios themselves (amd-smi `start_error` fallback, Slurm
`tasks_per_node` boundary, psutil total of 0), so those cases were added and the golden
regenerated from the ORIGINAL script before re-running. All five (cgroup memory-limit
skip, scope inversion, `or` vs `is not None` on host memory, amd fallback status set,
the Slurm shared-memory threshold) were then caught.

**Deferred** — `collect_snapshot` is still the longest function (125 lines, mostly the
sequential assembly and the result dict).

wired-by: skills/get-available-resources/scripts/resource_probes/snapshot.py
wired-by: skills/get-available-resources/scripts/resource_probes/cgroup.py
wired-by: skills/get-available-resources/tests/test_detect_resources_characterization.py

### Unit 4 — web-scraping `fetch_academic.py` split

**Scope** — `skills/web-scraping/scripts/fetch_academic.py` (1638 lines). The skill's
shared `_common.py` is reused as is (HTTP client, URL safety, JSON output); no new helper
copy was made.

**Change** — `fetch_academic.py` is now the CLI entry (106 lines: docstring and re-exports
of every name the old script exposed, including the stdlib modules it imported). One module
per source or backend in `scripts/academic_sources/`: `crossref_provider.py` (71),
`arxiv_provider.py` (47), `biorxiv_provider.py` (58), `open_access.py` (138, Unpaywall +
PMC), `libkey.py` (53), `library_auth.py` (316), `ezproxy.py` (438), `pdf_identity.py` (173),
`pdf_downloader.py` (211), `cli.py` (190). Longest functions
now: `_selenium_login` 137 -> 41 (`_chrome_user_data_dir`, `_chromedriver_service`,
`_launch_chrome`, `_login_and_collect_cookies`), `EZproxyPdfDownloader.download` 113 -> 72
(`_stream_pdf`) and `get_pdf_url` 77 -> 47 (`_resolve_pdf_url`), `PdfDownloader.download`
97 -> 43 (one method per source), `verify_pdf_identity` 91 -> 20 (`_read_pdf_text`,
`_identity_score`), `main` 30 -> 12 (`_dispatch`), `_build_parser` 46 -> 12. The quarantine /
size-and-identity result block that `_try_download` and the EZproxy path each carried is now
one `check_downloaded_pdf`. `verify_pdf_identity` closes the file handle it used to leak.

**Evidence** — `tests/academic_snapshots.py` + `tests/golden/fetch_academic.json` (generated
from the unsplit script, twice byte-identical; PDFs built with pypdf, DNS disabled) pin:
the Crossref / Unpaywall / PMC / arXiv / bioRxiv providers against fake modules and a
scripted client, 22 identity-gate cases including the exact score-4 and score-5 boundaries,
the Netscape cookie loader, cookie scope and link host gating, `get_pdf_url` and `download`
over an httpx MockTransport (headers, cookies, rate-limiter calls, quarantine files), the
cookie cache and `_selenium_login` against fake selenium / webdriver-manager modules (profile
fallback, every failure branch), the whole download waterfall with 19 scenarios (+5 record variants) and hostile
filename parts, 16 CLI invocations (outputs, exit codes, stderr, flags and defaults) and
the public surface (every old name and method signature must remain). 15 new tests; suite
129 -> 144 passed (4 skipped as before). `tests/test_ezproxy_scope.py` kept both of its AST
checks but they now scan the entry file and every `academic_sources` module (a widened scope;
scanning only the entry file would have made them fail or pass vacuously).

**Refutation** — mutations caught: dropping `expected=` at the EZproxy call site, an unsanitized
f-string filename, the Default/Profile-1 fallback, identity threshold 5 -> 4, the EZproxy and
the PdfDownloader 1 KB size floors, and an eager (non-lazy) evaluation of the download
sources. Writing the split initially introduced exactly that eager evaluation; the golden
(which records every source call) failed on it. Four of the scenarios (score boundary, 700 B
payload, single-link size case) were added only after a mutation survived, and the golden was
regenerated from the ORIGINAL script each time. One mutation (cookie domain without the leading
dot) is behaviourally equivalent in httpx and cannot be caught.

**Deferred** — `EZproxyPdfDownloader.download` (72 lines) and `InstitutionalLibraryAuth`
(Selenium path) remain the longest units; nothing else beyond the four requested units.

wired-by: skills/web-scraping/scripts/academic_sources/cli.py
wired-by: skills/web-scraping/scripts/academic_sources/pdf_identity.py
wired-by: skills/web-scraping/scripts/academic_sources/pdf_downloader.py
wired-by: skills/web-scraping/tests/test_academic_characterization.py
