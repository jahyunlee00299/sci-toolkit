# QUICKSTART — get started from a USB drive in 5 minutes (for beginners)

This guide's goal is for a **complete beginner** who just got sci-toolkit to pull it
off a USB drive (or a shared folder) and get something working in Claude Code within
5 minutes. Don't start by installing — the order here is
**read the docs first, pick only the modules you need, and install last.**

---

## Step 0 — check the prerequisites (30 seconds)

- Claude Code must already be installed, and **you must be logged into a subscription
  (Claude Pro/Max, etc.)**. This distribution is designed with **subscription-based use
  as the default (base)** — most skills work immediately with no separate API key.
- A few skills that do require an API key (direct external DB lookups, etc.) are not
  needed for the core functionality (paper search, figures, statistics, primer design,
  etc.). Prepare that only when you actually need it, by reading that skill's own doc.

---

## Step 1 — read the docs before installing anything (2 minutes)

Don't copy/install the moment you plug in the USB drive. Skim through in this order first:

1. `README.md` — the overall picture and module list (the file next to this one)
2. Find which module covers the task you want to do right now, in the table below
3. Open that module's `skills/<name>/SKILL.md` once (check the trigger phrases and usage examples)

| What you want to do | Module (skill folder) |
|---|---|
| Find/summarize/review papers | `research-search`, `literature-review` |
| Write/polish a manuscript | `manuscript-pipeline`, `academic-term-rules` |
| Design primers/sequences | `primer-design` |
| Make figures for a paper/presentation | `publication-figures` |
| Not sure what statistical test to use | `stats-workflow` |
| Read a PDF/document as text | `markitdown` |
| Check whether a result makes sense | `scientific-validation` |

> Nothing gets installed at this step. This step is only for confirming
> "what should I pick".

---

## Step 2 — install only the modules you need (1-2 minutes)

**Don't install everything at once — pick only what you'll use right now** and install
that. This toolkit ships a **pick-and-choose installer** (`install/install.py`), so
saying "I'm only doing manuscript writing" installs only the related skills. Any other
skill it depends on (e.g. `academic-term-rules`, which `manuscript-pipeline` needs) gets
installed **automatically alongside it**, so there's nothing to worry about missing.

> `docx`, `pdf`, `pptx`, and `xlsx` are Anthropic-owned, so they're not in this
> repository. The installer tells you that, and document work itself still works fine
> through Claude Code's own built-in capability.

### The easiest way — interactive (recommended for beginners)

Run the following from the `sci-toolkit` folder and a menu comes up. Answer "what do
you want to do?" with a number.

```
python install/install.py
```

- It shows only a **preview** first (nothing changes yet). Once you've confirmed what
  will be installed, run it again with `--apply` to actually install:
  ```
  python install/install.py --apply
  ```

### If you want to see what's available first

```
python install/install.py --list
```
This lists 41 skills and the presets, grouped by category. Four of them
(docx · xlsx · pdf · pptx) are owned by Anthropic, so they are not bundled in
this repository and only a pointer is shown — 37 are actually installable.

### If you already know what you want to install (one-liner)

```
# by preset: the manuscript-writing set (manuscript-pipeline + dependencies automatically)
python install/install.py --preset paper-writing --apply

# or pick individual skills
python install/install.py --skills primer-design,literature-review --apply
```

**Preset list**: `paper-writing` (manuscript writing) · `literature` (literature search) ·
`molbio` (molecular biology) · `data-figures` (data/figures) · `documents` (document work) ·
`all` (everything — 37 bundled, plus a pointer for the 4 external ones)

- The install target folder defaults to `~/.claude/skills/`. If you need a different one,
  specify it with `--dest <path>`.
- "Install" here doesn't mean a build/compile step — **copying the folder is the
  install.** The installer does that copy for you, and makes sure it doesn't miss any
  needed dependency along the way.

---

## Step 3 — try it right away in a new session (1 minute)

1. Restart Claude Code, or open a new conversation.
2. Ask for something in natural language, as usual. For example:
   - "Summarize this paper's abstract"
   - "Design primers to introduce a K123A substitution into this gene"
   - "Make a figure from this HPLC data"
3. Claude Code finds and loads the relevant skill on its own. You don't need to name the
   skill directly (though you can, if you want, by saying something like "use the
   primer-design skill").

That's it — this is the minimum path a beginner can complete in 5 minutes.

---

## Step 4 (optional) — install everything, or copy files by hand without the installer

**If you genuinely need everything** (e.g. setting up a shared lab PC), use the
installer's `all` preset. Pulling all 37 at once makes it hard to tell what
got loaded and why, so the two-step approach — pick only what you need — is
the better starting point. But if you really do need everything:

```
python install/install.py --preset all --apply
```

**If you're on an environment where the Python installer can't run**, you can copy files
by hand instead, since copying the folder is the install. In that case, though, **you
have to track dependencies yourself** (e.g. `manuscript-pipeline` needs
`academic-term-rules` to work correctly).

```powershell
# a single skill (Windows) — check its dependencies yourself
Copy-Item -Recurse "E:\sci-toolkit\skills\primer-design" "$env:USERPROFILE\.claude\skills\primer-design"
```

```bash
# a single skill (macOS/Linux)
cp -r /Volumes/USB/sci-toolkit/skills/publication-figures ~/.claude/skills/publication-figures
```

After installing, confirm in a new session that it shows up correctly in the skill
list; any skill you don't use can later just be deleted, folder and all (this doesn't
affect other skills — skills are independent of each other).
What each skill needs is listed under `config/catalog.json`'s `requires` field.

---

## If you get stuck (Troubleshooting)

- If a skill isn't being recognized: check that the copied path matches the
  `~/.claude/skills/<skill-name>/SKILL.md` structure (make sure there isn't an extra
  wrapping subfolder).
- If a particular skill asks for an API key: that skill's own `SKILL.md` states the key
  it needs and any free alternative. Try skills that don't need one first.
- If it still doesn't work: ask your lab admin (whoever maintains the distribution).
  This distribution is a shared, PII-free public version, so a personal-configuration
  problem is usually faster to fix by checking your own Claude Code environment
  settings first, rather than the shared lab docs.
