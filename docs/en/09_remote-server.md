> English translation of [09_원격서버에서_쓰기.md](../09_원격서버에서_쓰기.md). The Korean original is canonical; if they differ, the Korean version wins.

# 09. Using It on a Remote Server: Lab Shared Server · HPC · Cloud

Read this document when you want to run Claude Code on a computer other than your laptop.

These are the cases it covers.

- The data is on a lab shared compute server and you want to analyze it on that server
- You need to run work that requires a GPU (structure prediction, large-scale fitting) on a server
- You connect to and use the university HPC (cluster)
- The work needs to keep running even when you turn off your laptop

> The connection details for the lab shared server and HPC (address, account, key) are not included in this distribution.
> Use the information you received from your lab or IT office. Do not store connection details inside this folder.

---

## 0. First check: do you really need remote?

Remote brings hassle before it brings convenience. In the cases below, do it on your laptop.

| Situation | Recommendation |
|---|---|
| The data is on my laptop and it finishes in a few minutes | Local |
| Excel, Word, and figure work | Local (remote is awkward for GUIs) |
| The data is only on the server / it is large | Remote |
| A GPU is needed | Remote |
| It takes hours to days | Remote (keeps running even if the laptop is off) |

---

## 1. Method A: VS Code Remote-SSH (most recommended)

This approach lets you open and use the remote server's files right on your own VS Code screen.
It is much more comfortable than using a terminal alone, and the Claude Code extension also runs on the remote side as is.

1. Install `Remote - SSH` (made by Microsoft) from the VS Code extensions.
2. `F1` → `Remote-SSH: Connect to Host...` → enter the server address
   (format: `username@server-address`, for example user `hong` on server `server.example.ac.kr`)
3. Log in with a password or an SSH key.
4. Once connected, a new window is attached to the remote server.
   Open a folder here, install and log in to the Claude Code extension, and you're done.

> You may need to install the extension separately on the remote side.
> If VS Code shows an "Install in SSH: server-name" button, press it.

File browsing, editing, the terminal, and Claude are all on one screen.
You can check result figures in a preview right on the spot.

---

## 2. Method B: SSH in from a terminal and use the CLI

For when you don't use VS Code, or are only doing light work.

```bash
ssh username@server-address     # connect to the server
cd /path/to/my/project          # move to the folder to work in
claude                          # run Claude Code
```

If the server doesn't have Claude Code, install it first.

```bash
npm install -g @anthropic-ai/claude-code
```

If `npm` is missing and you have no administrator rights, ask your IT person to install Node.js, or follow the
instructions at [nodejs.org](https://nodejs.org) to install it in your user home directory.

### Putting this toolkit on the server too

Copy the folder from your laptop to the server (run this in your laptop's terminal).

```bash
scp -r sci-toolkit username@server-address:~/
```

When the copy finishes, open the `~/sci-toolkit` folder on the server and use it.
To install only selected skills, on the server:

```bash
cd ~/sci-toolkit
python install/install.py --preset data-figures --apply
```

---

## 3. Long jobs: keep them running even if the connection drops

With SSH, when the connection drops, whatever was running dies with it. If you close your laptop or
the Wi-Fi drops, a calculation that had been running for hours is lost.

### tmux (recommended)

```bash
tmux new -s work        # start a session named 'work'
# ... run claude here and do your work ...
# Press Ctrl+b, then d  → detach from the session (the work keeps running)

tmux attach -t work     # reconnect later and pick up where you left off
tmux ls                 # list of running sessions
```

It keeps running on the server even if you turn off your laptop. If you reconnect the next day and run `tmux attach`,
the output from in the meantime is still there.

### nohup (simple one-off jobs)

```bash
nohup python my_analysis.py > run.log 2>&1 &
tail -f run.log         # watch progress (Ctrl+C stops only the watching)
```

---

## 4. Getting results back

To bring figures, tables, and reports made on the server back to your laptop (run in your laptop's terminal).

```bash
scp username@server-address:~/project/figure.png .        # one file
scp -r username@server-address:~/project/results ./       # a whole folder
```

If you use VS Code Remote-SSH, you can just drag them over in the file explorer.

---

## 5. Cautions on HPC (clusters)

A university HPC is usually split into login nodes and compute nodes.

- **Do not run heavy computation on the login node.** It harms other users,
  and administrators may forcibly kill the process.
- Heavy jobs must be submitted to the job scheduler (SLURM, etc.).

```bash
sbatch my_job.sh        # submit a job to SLURM
squeue -u $USER         # check the status of my jobs
```

If you tell Claude Code "turn this analysis into a SLURM job script," it will write
one in the form of `my_job.sh`. However, partition names, time limits, and resource request amounts
differ by university, so also give it the IT office's guide documents.

If you want to check the compute resources first, use the `get-available-resources` skill, which surveys
CPU, GPU, memory, and disk and tells you which strategy fits.

---

## 6. Security: things you must follow

- Do not store connection details (address, account, password, SSH key) inside this toolkit folder.
  This folder gets copied around between people.
- Keep SSH keys in `~/.ssh/`, and using a key instead of a password is safer.
- **Do not leave personal API keys in plain text on a shared server.** Other users can see them.
  Use environment variables or a file with restricted permissions (`chmod 600`).
- The shared folders on a shared server may have other people's data mixed in.
  Before having the AI read a whole folder, check what is inside it first.
- Check whether there is any data that must not leave the lab under lab policy.
  If you cannot tell, ask your advisor or a senior first.

---

## 7. Common problems

| Symptom | Cause / fix |
|---|---|
| `claude: command not found` | Not installed on the server, or not on the PATH. Run `npm install -g @anthropic-ai/claude-code` and log in again |
| The connection keeps dropping | Use tmux (section 3). Adding `ServerAliveInterval 60` to your SSH config also helps |
| The login is lost every time | Once you log in on the server, it persists. If your home directory is reset every time, ask the IT office |
| Korean text is garbled | Add `export LANG=ko_KR.UTF-8` or `LC_ALL=C.UTF-8` to `~/.bashrc` |
| Figures don't get drawn | Because the server has no display. Use `matplotlib.use("Agg")` in matplotlib and save to a file |
| It is slow | You may be transferring large files every time. Keep the working folder on the server side |

---

## Next documents

- Which features need preparation → [06_requirements-by-feature](06_requirements-by-feature.md)
- A sense of tokens and cost → [03_tokens-and-cost](03_tokens-and-cost.md)
