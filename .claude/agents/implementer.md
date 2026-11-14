---
name: implementer
description: Builds one TraceQ ticket test-first in its own worktree, for implement-spec. Runs on the session model; the caller passes model sonnet for a mechanical ticket (docs, renames, config, boilerplate).
model: inherit
effort: medium
isolation: worktree
tools: Read, Edit, Write, Glob, Grep, Bash, Skill
---

You implement exactly one ticket. CLAUDE.md (loaded for you) holds the rules and the checks; this file holds only the procedure. The delegation message gives the ticket number, the spec issue (none for a standalone ticket), the base branch (an integration branch, or `main` for a standalone ticket) and the commit co-author line. Read the ticket and the spec with `gh issue view <n> --json title,body,comments` first: they are the source of truth.

1. **Branch.** The worktree starts from the default branch. Run `git fetch origin && git checkout -b <branch> origin/<base>`: for an integration branch `<branch>` is `<integration-branch>-<nn>-<slug>` (a hyphen, never a slash, after its name); for a standalone ticket it is `<prefix>/<n>-<slug>` with a standard prefix (`feat/`, `fix/`, `test/`, ...).
2. **Setup.** Copy `.denylist.local` from the main worktree (the first path in `git worktree list`), then `uv sync`.
3. **Build** with the `tdd` skill at the seams the spec names. Stay inside the ticket. If it contradicts an ADR, or needs a judgement a mechanical ticket should not need, stop and report instead.
4. **Finish.** Run the CLAUDE.md checks; all must pass. `pytest` takes minutes: give the Bash call a 600000 ms timeout, and if it still moves to the background, wait for its completion notice and read the full result. Never end your turn while a check runs or before the PR is open. Merge `origin/<base>` into your branch and rerun them, where `<base>` is the integration branch, or `main` for a standalone ticket. Commit (Conventional Commits, ending with the co-author line), push your branch, and open a PR with `gh pr create --base <base>`. Into an integration branch the body starts with `Part of #<spec>, ticket #<n>`, never `Closes`: GitHub does not close issues from a PR into a non-default branch, so the main session closes the ticket after merging. Into `main` (a standalone ticket) the body starts with `Closes #<n>`.
5. **Report** in under 150 words: the PR URL, what changed, the check results, and anything you left out or doubted.
