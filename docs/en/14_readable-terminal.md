> English translation of [14_터미널_읽기좋게.md](../14_터미널_읽기좋게.md). The Korean original is canonical; if they differ, the Korean version wins.

# 14. Making Your Terminal Readable

If the logs look smeared together, Korean tables don't line up with ASCII headers, and the tabs you opened at the same time
all look identical so you can't tell which one failed, this document fixes those three.

Whether you notice a wrong number or let it slip by is decided here, so this is more than a matter of taste.

```bash
python scripts/terminal_setup.py            # preview (writes nothing)
python scripts/terminal_setup.py --apply    # apply after backing up
python scripts/terminal_setup.py --verify   # confirm it actually took effect
python scripts/terminal_setup.py --revert   # undo
```

Without `--apply` it writes nothing. Every file it touches is first copied to a timestamped
`.bak`, and `--revert` restores it.

---

## What changes

| | Details |
|---|---|
| Color scheme | [Catppuccin Mocha](https://github.com/catppuccin/windows-terminal): defined in `schemes` and applied to profiles |
| Font | The best one installed ([D2Coding](https://github.com/naver/d2-coding-font) → [Cascadia](https://github.com/microsoft/cascadia-code) → Consolas) |
| Tab color | A different color per profile type (PowerShell, cmd, WSL, SSH, ...) |
| Readability | Automatic contrast adjustment, bold text distinction, cursor shape |
| History | PowerShell = [PSReadLine](https://github.com/PowerShell/PSReadLine) prediction / bash = `.inputrc` prefix search |

If a value already exists, it is not overwritten. Profiles whose colors you picked yourself are left alone.

---

## If you use WSL: half of it is already done

What draws the [WSL](https://learn.microsoft.com/en-us/windows/wsl/) window is not Linux but [Windows Terminal](https://learn.microsoft.com/en-us/windows/terminal/).

So the color scheme, font, and tab color are inherited as-is from the Windows-side settings.
You don't need to install a font on Linux or create a separate scheme. Apply it once on Windows and
the WSL tabs look better too.

The only thing bash lacks is history prediction, so on the Linux side the only thing
this script creates is a single `~/.inputrc`.

```
# What .inputrc does
Type the first part of a command and press ↑ → it scans only the history entries that start with that prefix
```

bash has no gray preview text like PSReadLine. Prefix search is the closest
substitute.

---

## Two things that fail silently (what this script prevents)

### 1. Using a name that doesn't exist produces no complaint

Windows Terminal accepts things like this without a word.

```jsonc
"colorScheme": "Dark+"                    // OK even if Dark+ isn't in schemes
"font": { "face": "D2Coding Nerd Font" }  // OK even if no such font exists
```

No warning, no log. It draws with the defaults, and to the user it looks like
"the setting didn't take effect." We ran into both of these while writing this repository.

So this script

- does not use a scheme name that isn't defined,
- uses a font only after asking the OS "do you have that name?",
- and `--verify` re-checks both.

> **Font-name trap**: the name you download and the name the OS calls it are different.
> It is not `D2Coding Nerd Font` but `D2Coding ligature`.
> To check: `python scripts/terminal_setup.py --verify`

### 2. PowerShell 5.1 only half works

| | 5.1 | 7.1+ |
|---|---|---|
| History prediction | Works | Works |
| Plugin prediction (AI-style suggestions) | **Doesn't work** | Works |
| ListView | Needs PSReadLine 2.2.6+ | Same |

5.1 ships with PSReadLine 2.0.0 and doesn't update itself. To use ListView,
you have to upgrade the module.

```powershell
# You must install NuGet first — otherwise Install-Module stops with no output
# at the "install the provider?" prompt
Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Scope CurrentUser -Force
Install-Module PSReadLine -Scope CurrentUser -Force -SkipPublisherCheck
```

The profile block this script inserts turns ListView off by itself if the version is too low and
applies only the rest. It doesn't raise an error.

---

## If your profile throws errors

If red text appears every time you run a script, the prediction settings are the cause.

A shell run through a pipe (= every script and hook) has no console buffer, so
both `PredictionSource` and `PredictionViewStyle` throw exceptions.

The block this script inserts first checks that it's a real console before proceeding.

```powershell
try {
    $null = $Host.UI.RawUI.KeyAvailable   # throws here if redirected
    Set-PSReadLineOption -PredictionSource History
    Set-PSReadLineOption -PredictionViewStyle ListView
} catch { }
```

If you edited your profile by hand, use the same guard.

---

## Telling tabs apart when you have many

A per-profile color tells you which shell it is. To tell apart several sessions launched with the same shell,
add a color at launch time.

```powershell
wt -w 0 new-tab -p "Windows PowerShell" --tabColor "#89B4FA" --title "run-3"
```

`--tabColor` overrides the profile value. If an automation script hands out a palette in rotation, one per session,
you can take in both axes, which shell × which run, at a glance.

> In PowerShell, a `;` in a `wt` argument is taken as a command separator. Escape it with a
> backtick. If you split the window, you also need to give `--tabColor` separately to the splitting subcommand
> (wt's split-pane) for the color to apply beyond the first pane.

---

## If Korean is garbled or tables don't line up

- Widths are off → Use a D2Coding-family font. Korean is designed to be exactly
  twice the width of Latin, so tables line up. Cascadia and JetBrains Mono have no Korean at all, so they fall back to a
  system font, and the widths break at that point.
  Install: https://github.com/naver/d2-coding-font
- Still garbled → Windows Terminal has an unresolved Korean rendering issue
  ([microsoft/terminal#16778](https://github.com/microsoft/terminal/issues/16778)).
  It's a width-calculation problem, so it is hard to avoid entirely with a font alone.
- Korean inside a `.ps1` is garbled → PowerShell 5.1 reads a `.ps1` without a BOM using the ANSI code page. Save
  it as UTF-8 with BOM.

---

## Undoing

```bash
python scripts/terminal_setup.py --revert
```

It restores from the most recent backup. Backups sit next to the original in the form
`<original name>.sci-toolkit.bak_<timestamp>`, so you can also copy them back by hand.
