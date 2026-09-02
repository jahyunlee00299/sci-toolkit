<!-- Moved verbatim from AGENTS.md §7 on 2026-09-02 so that AGENTS.md stays under the 32 KiB that Codex reads (`project_doc_max_bytes`). AGENTS.md keeps a stub. -->

### Git branch hygiene (safe cleanup)

Repos accumulate stale branches; clean them with a reversibility test, not
intuition. Verified procedure (260809, six-repo cleanup, zero loss):

- **Classify before deleting**, and write every SHA to a backup file first:
  a local branch whose tip is an ancestor of `origin/<default>` (merged), or
  reachable from *any* origin ref (`git branch -r --contains <sha>`, pushed),
  is deletable with zero loss — the origin retains the objects. A branch on
  no origin ref is **irreversible** to delete: judge it per-branch, never in
  bulk. `git branch -d` is not a safety judge — it only compares against the
  default branch and misses "preserved in a different branch".
- **Containment chains**: run `git merge-base --is-ancestor A B` pairwise
  among unmerged branches; in a chain `A ⊂ B ⊂ TIP`, processing the TIP
  resolves the members. `git cherry origin/<default> <branch>` with all `-`
  means the content already lives in default (squash/rebase residue).
- **Hands off live work**: never delete a branch checked out in a worktree,
  and treat a branch with today's commits as belonging to a live session.
- **Oversized/binary-polluted branches**: archive as a verified `git bundle`
  (checksum both ends) on bulk storage instead of pushing to the code host.
- **Before pushing to any public or shared repo**, scan the full diff — not
  just filenames — for private markers (names, home paths, tokens,
  unpublished model/reaction structure). Example code and docs are the
  classic leak: the numbers are absent but the structure of unpublished
  work is not.
- **Merging accumulated branches**: merge only with the repo's test suite
  green on the *merged* tree; otherwise record a verdict (HOLD / SUPERSEDED
  / ARCHIVE) with the exact command as evidence. "Superseded" needs
  file-level diff proof, not "looks replaced".
