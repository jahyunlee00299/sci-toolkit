> English translation of [11_불편한점_남기기.md](../11_불편한점_남기기.md). The Korean original is canonical; if they differ, the Korean version wins.

# 11. Filing Feedback

How to leave a record on the spot when you get stuck or notice something odd while using the toolkit.

## Why file it

When people get stuck, most find some workaround and move on. But that workaround stays
only in your head, and the next person gets stuck in exactly the same place. Only recorded annoyances get fixed.

Please file the ones that make you think "I probably just used it wrong," too. If several people
misuse something at the same spot, the tool is at fault, not the users.

## The easiest way: just say it

Talk to Claude Code as you normally would.

> "docx 표 편집이 자꾸 실패하는데 이거 좀 불편해요" (“Table editing in docx keeps failing, and it's a real hassle”)
> "이런 기능이 있으면 좋겠는데 없네요" (“I wish there were a feature like this, but there isn't”)
> "이거 왜 안 되는지 모르겠어요" (“I don't understand why this doesn't work”)

Claude will then ask a follow-up question once (usually "그래서 원래는 어떻게 되길 기대하셨어요?" (“So what were you expecting to happen?”))
to fill in what's missing, and record it for you. It won't grill you: if you get interrogated while you're
already annoyed, nobody will report anything.

Once recorded, you'll see a one-line message like "기록했습니다 — <ID>" (“Recorded — <ID>”).

## If you want to file it yourself

```bash
python scripts/feedback_log.py add "표 안에서 find-replace 가 계속 실패합니다"
```

With more detail (all optional; leave out what you don't know):

```bash
python scripts/feedback_log.py add "표 안에서 find-replace 가 계속 실패합니다" \
    --kind bug \
    --skill docx \
    --expected "표 셀 값이 바뀜" \
    --actual "51 matches 라는 메시지만 반복"
```

(The example texts above, in Korean, mean: “find-replace keeps failing inside tables”; expected “the table cell value changes”; actual “only the message '51 matches' repeats.”)

`--kind` is one of five values.

| Value | When |
|---|---|
| `bug` | It clearly behaves wrongly |
| `friction` | It works, but it's inconvenient (the default) |
| `missing` | A feature that should exist is missing |
| `docs` | The documentation is wrong or lacking |
| `idea` | "It would be even better if..." |

## Checking what you filed

```bash
python scripts/feedback_log.py list
```

Items marked with `*` haven't been passed on to the maintainer yet.

## Where it's stored

`out/feedback.jsonl` is a single file on your computer.

Recording needs no GitHub account, no token, and no internet connection. This is
deliberate. You should be able to file feedback right away, even on the first day you get the toolkit by USB.

## How it reaches the maintainer

`out/feedback.jsonl` is not committed to git (it is blocked by `.gitignore`).
So if you leave it alone, that file never leaves your computer. To pass it on,
you have to run one command yourself.

```bash
python scripts/feedback_log.py export --github --repo <the repository the maintainer told you> --write
```

Only at this step do you need a GitHub account (permission to write issues is enough; write access to
the repository is not needed). If you don't want to create an account, run it without `--github` to print
just the body text, then hand that text to the maintainer directly.

## What you must not include (the code enforces this)

This record is passed on to other people. So if any of the following is in it,
`export` **refuses to run.** This is an actual check, not just a notice.

- Passwords, API keys, tokens
- Other people's personal information (names, emails, phone numbers)
- Unpublished research content (enzyme names, strains, numbers, unpublished sequences, etc.)
- Absolute paths that reveal a user name (a path under the Windows `Users` folder or a Linux home folder)

Write "what failed," and leave out "what data it failed on."
For example: instead of `"D-갈락토스 12.4 g/L 데이터에서 실패"` (“failed on D-galactose 12.4 g/L data”), write `"HPLC csv 파일에서 실패"` (“failed on an HPLC csv file”).

The check catches not only numbers with units (`12.4 g/L`) but also bare numbers.
`"수율이 92 였습니다"` (“the yield was 92”) is blocked, while `"수율 파일 3개가 안 열립니다"` (“3 yield files won't open”) passes.
That's because counting numbers such as quantities, order, time, and page numbers are not treated as values.

When you record (`add`), it doesn't block; it only warns, so that you can fix it on the spot.
What actually blocks is the `export` step, where the record goes outside.

```
⚠ 밖으로 내보낼 수 없는 내용이 들어 있습니다:
  · [what] 연구 수치: 12.4 g/L
  · [actual] 절대경로: C:\Users\...
```

(The message above, in Korean, reads: “Content that cannot be exported is included: [what] research number: 12.4 g/L; [actual] absolute path: (a path under the Windows Users folder)”.)

If you decide the check is wrong, you can pass it through with `--approve`. But that
ignores the check results entirely, so use it only after you have verified the content yourself.

If you want to see in advance what gets flagged, you can check a single sentence on its own.

```bash
python scripts/feedback_sanitize.py "여기에 쓸 내용을 넣어보세요"
```

(The Korean sample text means “put the text you want to write here.”)

## Who gets assigned: by default, the person who found it

Issues aren't dumped on the maintainer. When you actually post with `--github --write`, if you give no
options, it is automatically assigned to the account that ran the command (the owner of the GitHub token = in most cases the person who found it).
You can also assign someone else, or leave it unassigned.

```bash
python scripts/feedback_log.py export --github --repo owner/name --write
# Default: assigned to the person who ran it

python scripts/feedback_log.py export --github --repo owner/name --assignee other-login --write
# Assign someone else

python scripts/feedback_log.py export --github --repo owner/name --no-assignee --write
# Assign no one
```

Even if the automatic assignee lookup (`/user`) fails (for example, offline), creating the issue is not blocked;
it is posted without an assignee.

## For maintainers

```bash
python scripts/feedback_log.py list --pending          # not yet posted
python scripts/feedback_log.py export                  # preview the issue body
python scripts/feedback_log.py export --github --repo owner/name --write
```

Without `--write` it only previews (AGENTS.md §9 draft-first).
Each issue automatically gets the record ID, timestamp, OS, and Python/Claude Code versions attached,
so you can start reproducing without asking again. File paths, user names, and
host names are not collected.

The sanitizing gate also applies to the preview. If only the preview were let through, there would be a
workaround of copying that output and posting it by hand, and that path has no checks at all.

What the gate catches and what it lets through is pinned down as a contract by `tests/test_feedback_sanitize.py`.
The blocking cases in it are leaks that actually happened, so if false positives are annoying,
fix the gate instead of deleting the cases.
