---
name: statusline-usage
description: Show the model, context-window use, 5-hour and weekly rate-limit use (with reset times) in the Claude Code status line, from a dependency-free bash script (or a PowerShell twin on Windows). Use when the user wants to see how much context or plan quota is left without running a command. 한국어 트리거 — "상태줄", "상태창", "컨텍스트 표시", "주간 사용량", "사용량 표시", "statusline", "남은 한도 보이게".
license: MIT license
metadata:
    skill-author: Lab Researcher
---

# statusline-usage

## Overview

Claude Code runs the `statusLine` command on every render and pipes a JSON
object to its stdin. This skill ships a script that turns that JSON into one
line:

```
Opus 5.5 | ctx 96k/1M 10% | 5h 1% ~21:30 | 7d 53% ~Sat 07:00
```

| Segment | Meaning |
|---|---|
| `Opus 5.5` | model display name |
| `ctx 96k/1M 10%` | tokens in the context window (input + cache creation + cache read), window size, percent used |
| `5h 1% ~21:30` | 5-hour rate-limit window: percent used and local reset time (24 h) |
| `7d 53% ~Sat 07:00` | weekly window: percent used and reset weekday and time (English day names) |

A segment whose percent is at or above the warning threshold (default 80) gets a
`!` prefix, for example `!7d 85% ~Sat 07:00`. A segment whose data is missing is
left out. Empty or unparseable input prints `claude`. The script always exits 0,
so a bad render never breaks the session.

## Install

Add to `~/.claude/settings.json` (user-wide) or a project's `.claude/settings.json`.
Bash, or Git Bash on Windows (recommended: fastest start-up, no `jq` or Python needed):

```json
{
  "statusLine": {
    "type": "command",
    "command": "bash ~/.claude/skills/statusline-usage/scripts/statusline.sh"
  }
}
```

PowerShell alternative on Windows (start-up is slower than bash because every
render launches a new PowerShell process):

```json
{
  "statusLine": {
    "type": "command",
    "command": "powershell -NoProfile -ExecutionPolicy Bypass -File <skills-dir>/statusline-usage/scripts/statusline.ps1"
  }
}
```

Replace `<skills-dir>` with the folder this skill is installed in.

## Environment knobs

| Variable | Default | Effect |
|---|---|---|
| `STATUSLINE_WARN_PCT` | `80` | percent at or above which a segment gets the `!` prefix |
| `STATUSLINE_TZ_OFFSET_MIN` | unset | integer minutes east of UTC, used for reset times instead of the system timezone (for example `540` for Korea, `-300` for US Eastern standard time) |

Without `STATUSLINE_TZ_OFFSET_MIN` the reset times use the system local time
(`TZ` is honoured by the bash script).

## When the rate-limit segments are missing

`rate_limits` is only sent for Claude subscription logins (Pro or Max), and only
after the first API response of a session. With an API key, or right after
start-up, the `5h` and `7d` segments are absent by design; that is not a bug.

## How the bash script reads the JSON

There is no `jq` on a stock Git Bash and a Python start-up on every render is
wasteful, so `scripts/statusline.sh` uses bash regular expressions. Each value is
read from inside its own parent object (`used_percentage` appears under
`context_window` and under both rate-limit windows), so key order, pretty or
compact layout and spaces after colons do not matter. Floats are floored to
integers. Values nested deeper than the one `current_usage` object, or numbers in
exponent notation, are not supported.

## Verification

`tests/test_statusline_usage.py` feeds every fixture in `tests/fixtures/` to the
bash script (and to the PowerShell script when it exists and PowerShell is on
`PATH`) and compares the exact output line, with `STATUSLINE_TZ_OFFSET_MIN=540`
so the result does not depend on the machine's timezone. To try it by hand:

```bash
STATUSLINE_TZ_OFFSET_MIN=540 bash scripts/statusline.sh < tests/fixtures/stdin_full.json
```
