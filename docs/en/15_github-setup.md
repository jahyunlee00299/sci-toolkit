> English translation of [15_깃허브_설정하기.md](../15_깃허브_설정하기.md). The Korean original is canonical; if they differ, the Korean version wins.

# 15. Setting Up Git and GitHub

You get sci-toolkit from its GitHub repository (https://github.com/jahyunlee00299/sci-toolkit). The repository is public, so you can download it without an account. You only need an account to file an issue or push a change.

The install command (`python install/install.py`) copies files from the repository folder to a place like `~/.claude/skills/`. It makes no difference whether you use Claude Code or Codex. The repository folder just has to be on your computer, and getting that folder is what this document covers.

---

## 1. Choosing how to download

| Situation | Method |
|---|---|
| Git is unfamiliar, and one download is enough | On the repository page, Code → Download ZIP |
| You want to receive updates later | `git clone` (steps 2 to 5) |
| You will file issues or push changes | `git clone` + GitHub login (steps 2 to 5) |

If you downloaded the ZIP, the folder you extract is the `sci-toolkit` folder. A ZIP has no `.git`, so you cannot update it with `git pull`; download it again when a new version comes out. If you used the ZIP, skip to step 6.

## 2. Install Git

- Windows: download the installer from [git-scm.com/download/win](https://git-scm.com/download/win) and accept the defaults. In a terminal, `winget install --id Git.Git -e` also works.
- macOS: type `git --version` in a terminal. If Git is missing, a developer tools install window appears.

When it finishes, check it.

```bash
git --version
```

A version number means it worked. A terminal that was open before the install does not know about the new setup, so if it says it can't find `git`, close the terminal and open a new one.

## 3. Check Python

`install.py` and `doctor.py` run on Python 3.10 or later.

```bash
python --version
```

If it is missing or older, install it from [python.org/downloads](https://www.python.org/downloads/). On the Windows installer's first screen, check "Add python.exe to PATH".

## 4. GitHub account and login (optional)

Skip this if you only want to download. To file an issue or push a change, create an account at [github.com/signup](https://github.com/signup) and log in with one of these.

- GitHub CLI: install it with `winget install --id GitHub.cli` on Windows or `brew install gh` on macOS, then run `gh auth login`. When it asks, choose GitHub.com, HTTPS and Login with a web browser, and type the code shown in the terminal into the browser window. `gh auth status` shows whether you are logged in.
- GitHub Desktop: install it from [desktop.github.com](https://desktop.github.com) and log in from the app. You can download and update the repository without typing commands.

Do not paste passwords or tokens into the chat window or into code. How to handle tokens is in [05_external-services](05_external-services.md).

## 5. Download the repository

```bash
git clone https://github.com/jahyunlee00299/sci-toolkit.git
cd sci-toolkit
```

Do not put it inside a synced folder such as OneDrive. The repository can break while the `.git` folder is being synced. On Windows, directly under your home folder is a safe place, for example `C:\Users\<username>\sci-toolkit`.

## 6. Install skills

Run these from inside the `sci-toolkit` folder you just entered.

```bash
python install/install.py --list
python install/install.py --preset paper-writing --apply
python doctor.py
```

When `doctor.py` prints `PASS`, you are ready. Claude Code reads newly installed skills only in a new session. For help choosing skills, see [QUICKSTART](../../QUICKSTART.md) and [01_install-and-first-command](01_install-and-first-command.md).

Installing is copying. Updating the repository does not change skills that were already copied, so run `install.py` again after every update.

## 7. Updating

```bash
cd sci-toolkit
git pull
python install/install.py --preset paper-writing --apply
python doctor.py
```

`install.py` does not delete files that are already there. It only replaces files of the same name with the new version.

## 8. Common snags

| Symptom | Fix |
|---|---|
| It says it can't find `git` | Close the terminal and open a new one. If that fails, reinstall Git |
| It says it can't find `python` | Run the Python installer again and check "Add python.exe to PATH" |
| `git clone` reports repository not found | Check that you copied the address above exactly |
| `git pull` reports local changes would be overwritten | You edited a file in the folder. Copy your edited file somewhere else, run `git restore <file>`, then `git pull` again |

If you get stuck, show a lab colleague the full error message. With the whole message, the cause is easier to find.
