---
title: "Git repo initialized at home dir instead of project root — fresh re-init recovery"
date: 2026-05-14
category: infrastructure
tags: [git, github, github-actions, force-push, repo-structure, sveltekit, ci-cd, history-rewrite]
components:
  - ~/.git
  - ~/Documents/claude/csfd/.gitignore
  - ~/Documents/claude/csfd/streamfinder/
  - .github/workflows/deploy-streamfinder.yml
  - ~/.svelte-kit/
  - ~/src/
symptoms:
  - "`git rev-parse --show-toplevel` returned `/Users/radozoo` instead of the project directory"
  - "All tracked file paths in commits carried a stray `Documents/claude/csfd/` prefix"
  - "`git status` from the project dir listed 90+ untracked files from unrelated home subdirs (`~/Downloads/`, `~/Library/`, `~/Pictures/`)"
  - "Deploy workflow required a `working-directory: Documents/claude/csfd/streamfinder` workaround to find the SvelteKit app"
  - "A routine `git reset --hard origin/main` destructively wiped uncommitted work across the entire home tree"
root_causes:
  - "`git init` (likely via `npx sv create`) was executed in `~` instead of `~/Documents/claude/csfd`, placing `.git` at the home root"
  - "Git silently walks up the directory tree to find any `.git`, so the misplaced repo produced no error — the mistake stayed invisible for weeks"
  - "The deploy workflow was patched with a `working-directory` hack that masked the underlying structural problem and made the broken setup appear functional"
---

# Git repo initialized at home dir instead of project root — fresh re-init recovery

## Problem Statement

A git repository was accidentally initialized at the **home directory** (`~/.git`) instead of at the **project root** (`~/Documents/claude/csfd/.git`). This is a deceptively dangerous misconfiguration: most git commands still appear to work, but every operation silently treats your entire home folder as the working tree. The symptoms are subtle at first and catastrophic at the end:

- `git status` from inside the project shows tracked files with a long relative prefix:
  ```
  modified:   Documents/claude/csfd/streamfinder/src/routes/+page.svelte
  ```
  instead of the expected:
  ```
  modified:   streamfinder/src/routes/+page.svelte
  ```
- `git status` also shows hundreds of untracked files that have **nothing to do with the project** — `Desktop/`, `Downloads/`, `Library/`, screenshots in `~/Pictures/`, other repositories nested under `~/Documents/`, dotfiles, browser caches, etc.
- `git rev-parse --show-toplevel` returns `/Users/radozoo` (your home), not the project directory you `cd`'d into.
- `git rev-parse --git-dir` returns `/Users/radozoo/.git`.
- Pushes to the project's remote include the wrong directory layout — the repo on GitHub ends up with a `Documents/claude/csfd/` prefix that nobody wants.
- CI workflows that use path-based triggers (`paths: streamfinder/**`) silently never fire, because in the misplaced repo the paths look like `Documents/claude/csfd/streamfinder/**`.

The **catastrophic** failure mode that finally forced this cleanup: a routine `git reset --hard origin/main`, intended to discard a few uncommitted experimental edits in the project, instead **wiped uncommitted work across the entire home directory tree** because the working tree extended all the way to `~/`. Anything that was modified-but-not-committed under `~/` — including small in-flight changes in sibling projects, dotfile edits, scratch notes — was reverted to whatever state `origin/main` reflected, or deleted outright if it didn't exist in `origin/main`.

This is the classic "working tree is way bigger than you think" footgun. Once `~/.git` exists, git considers your **entire home directory** to be a single repository, and every destructive command (`reset --hard`, `clean -fd`, `checkout .`, `restore .`) operates over that entire tree.

### How to diagnose this quickly

Before doing **anything** destructive, run these two commands from inside your project:

```bash
git rev-parse --show-toplevel    # expected: your project root
git rev-parse --git-dir          # expected: <project-root>/.git
```

If either points outside your project, **stop**. Do not run `git reset`, `git clean`, `git checkout .`, or anything else destructive until you fix the location.

Also useful:

```bash
git config --show-origin --get core.bare       # see which config file is in play
git config --show-origin --get remote.origin.url
ls -la ~/.git 2>/dev/null && echo "WARNING: ~/.git exists"
```

If `~/.git` exists and you didn't deliberately put it there, you have this problem.

## Why this happened

The most common way `~/.git` gets created accidentally:

1. **A `git init` was run from the home directory.** Most often this happens because a terminal session opened in `~/` (the default working directory for a fresh shell), and a copy-pasted onboarding command — `git init`, `npm create svelte@latest`, a scaffolding tool, or a `git clone ... .` with a stray `.` — ran without first `cd`ing into the project. SvelteKit, Vite, Next, and similar scaffolds often suggest `git init` as part of their post-install instructions, and if you run them in the wrong directory the init lands in `~/`.
2. **A nested directory was added later.** You then `mkdir Documents/claude/csfd`, scaffold the project there, edit files, and run `git status` — git happily walks up the directory tree, finds `~/.git`, and treats your project as a subdirectory of that repo. Nothing complains. There is no warning.
3. **The remote was added to the wrong repo.** When you eventually run `git remote add origin <project-remote>`, you're adding it to `~/.git`. From that point on the home-rooted repo is wearing the project's identity. Every `git push` confirms this misconfiguration is "working."

Why git doesn't catch this: git is intentionally permissive about where repos live. `git init` succeeds in any directory; `git status` walks **upward** to find the nearest `.git`; and there is no built-in check that warns "you have a git directory at `~/.git` containing 10,000 untracked files, are you sure?" The design assumes the developer knows where they are.

### Contributing factors in this specific case

- The project root already had a `.gitignore` (Python-only), which made the project **look** like it had its own repo to a quick visual scan. There was no obvious "missing repo" signal.
- The `.github/workflows/` directory existed inside the project with correct relative paths, but there was **also** a `~/.github/workflows/` directory created by the home-rooted repo with absolute-from-home paths (`working-directory: Documents/claude/csfd/streamfinder`). Two parallel CI configurations existed simultaneously and nobody noticed.
- VS Code's git integration showed file changes without complaining, because it just calls `git status` under the hood and accepts whatever toplevel git reports.

## Solution

The fix is **Option A: fresh re-init at the correct location**, then force-push to overwrite the remote with the corrected history. This is the cleanest path when:

- The remote history is short or unimportant (early-stage project, solo developer).
- Untangling historical commits to "shift" their paths would be more work than starting over.
- Nobody else has cloned the misplaced version.

If any of those don't hold (long history you want to preserve, multiple collaborators, protected branches), the alternative is `git filter-repo --subdirectory-filter Documents/claude/csfd/` to extract just the project subtree as a new history — more complex, covered briefly at the end of this section.

### Step 1: Mirror backup of the remote

Before touching anything, create a **clone of the remote in mirror mode** so that even if you destroy both local and remote, you have a recoverable copy.

```bash
git clone --mirror https://github.com/radozoo/streamfinder.git /tmp/streamfinder-backup-mirror.git
# Cloning into bare repository '/tmp/streamfinder-backup-mirror.git'...
# remote: Total 521 (delta ...), reused 521
# Receiving objects: 100% (521/521), 8.37 MiB | ... done.
```

Why mirror and not regular clone: `--mirror` copies **all refs** (branches, tags, notes, remote-tracking refs) in their original layout, so if you need to restore you can `git push --mirror /tmp/streamfinder-backup-mirror.git https://github.com/radozoo/streamfinder.git` and get back exactly what was on GitHub before your force-push.

### Step 2: Local `.git` backup

The misplaced `~/.git` directory contains the only local copy of any commits that weren't pushed yet, plus reflog data that can recover "lost" commits. Copy it before deleting.

```bash
cp -R ~/.git /tmp/dotgit-backup-2026-05-14
ls /tmp/dotgit-backup-2026-05-14/HEAD    # sanity check — file should exist
```

If you discover later that you needed something from the old history (a stash, a dropped branch, a commit you forgot to push), you can `cd /tmp/dotgit-backup-2026-05-14` and run git commands against it directly using `--git-dir`:

```bash
git --git-dir=/tmp/dotgit-backup-2026-05-14 reflog
git --git-dir=/tmp/dotgit-backup-2026-05-14 log --all --oneline
```

### Step 3: Verify the diagnosis one more time

Confirm the problem exists before destroying anything:

```bash
cd ~/Documents/claude/csfd
git rev-parse --show-toplevel    # returns /Users/radozoo  ← WRONG
git rev-parse --git-dir          # returns /Users/radozoo/.git  ← WRONG
```

If those return your project root instead, **stop** — this solution doesn't apply to you and following it will destroy a working repo.

### Step 4: Reconcile any divergent project files

In this case there were two copies of the deploy workflow:

- `~/.github/workflows/deploy-streamfinder.yml` — used `working-directory: Documents/claude/csfd/streamfinder` (created by the misplaced repo's perspective).
- `~/Documents/claude/csfd/.github/workflows/deploy-streamfinder.yml` — used `working-directory: streamfinder` (correct relative path).

Before re-init'ing, **read both** and confirm which is canonical. Here the project-dir copy was already correct, so no merge was needed — but if you find divergence, manually reconcile before you proceed. The home-rooted copies will be deleted in step 8, so anything you need must be in the project tree first.

```bash
diff ~/.github/workflows/deploy-streamfinder.yml \
     ~/Documents/claude/csfd/.github/workflows/deploy-streamfinder.yml
```

### Step 5: Initialize a fresh repo at the project root

```bash
cd ~/Documents/claude/csfd
git init -b main
# Initialized empty Git repository in /Users/radozoo/Documents/claude/csfd/.git/
git rev-parse --show-toplevel    # /Users/radozoo/Documents/claude/csfd  ← CORRECT
```

The `-b main` ensures the initial branch is named `main` (matching the remote default). On older git versions without `-b`, set it after init:

```bash
git symbolic-ref HEAD refs/heads/main
```

Note: at this point your project directory has **two** git directories competing for attention — the new `~/Documents/claude/csfd/.git` (correct) and the still-existing `~/.git` (wrong). Because git walks upward and stops at the **first** `.git` it finds, the new one wins for any command run from inside the project. That's why we can safely init the new one before deleting the old one. Just don't run git commands from `~/` until cleanup is done.

### Step 6: Set up `.gitignore` for the new repo

The existing `.gitignore` was Python-only (left over from an earlier version of the project). The current stack is SvelteKit, so it needs Node ecosystem entries plus project-local exclusions for artifacts and personal notes that shouldn't be tracked.

```gitignore
# Node / SvelteKit
node_modules/
.svelte-kit/
.output/
.vercel/
.netlify/

# IDE / workspace
.claude/

# Project-local artifacts and personal notes
logs/
ideas and notes/
old/
dashboard/
```

Why each entry:
- `node_modules/`, `.svelte-kit/`, `.output/` — generated, large, reproducible from `package.json`. Never commit.
- `.vercel/`, `.netlify/` — deploy-platform local state; contains tokens.
- `.claude/` — local agent configuration (settings, transcripts, allowlists); machine-specific and may contain personal data.
- `logs/`, `ideas and notes/`, `old/`, `dashboard/` — directories the user keeps in the project tree for scratch work, prior iterations, and personal notes; not meant for the public repo.

Verify the ignore is working **before** staging:

```bash
git status --ignored | head -50
git check-ignore -v node_modules    # should print the rule that matched
```

### Step 7: First-time stage and commit

```bash
git add .
git status                          # review — should be project source only
git commit -m "chore: re-initialize repository at project root"
# [main (root-commit) 03c18d7] chore: re-initialize repository at project root
#  112 files changed, 17144 insertions(+)

git rev-parse HEAD                  # 03c18d79d151e0c47baa225ae148f5a8e7ca86a2
```

Critical sanity checks before committing:

- `git status` should show **only project files**, no `../../../...` paths, no `Desktop/`, no `Library/`.
- The file count should match the project's actual size. If `git status` reports 10,000 staged files, you re-init'd in the wrong place — abort.

### Step 8: Connect to GitHub and force-push

This is the irreversible step. Anyone who has cloned the previous (misplaced-history) version of the repo will need to re-clone after this.

```bash
git remote add origin https://github.com/radozoo/streamfinder.git
git push --force origin main
# + 525aa75...03c18d7 main -> main (forced update)
git branch --set-upstream-to=origin/main main
```

Why `--force` (not `--force-with-lease`): we **want** to discard the remote history entirely. `--force-with-lease` would refuse if the remote had moved since our last fetch, which is the right default for collaborative work but unnecessary here — we've already taken a mirror backup in step 1, and the whole point is to replace remote history.

For projects with multiple collaborators or protected branches, `--force-with-lease` is the safer choice and you should coordinate with the team first.

### Step 9: Clean up the misplaced repo files

Once the new repo is connected and pushed, the home-rooted git artifacts are dead weight. They're not tracked by any active repo anymore (the new repo at the project root doesn't know about them). Safe to delete:

```bash
rm -rf ~/.git ~/.github ~/.gitignore ~/.npmrc ~/.svelte-kit ~/src
```

Per-path rationale:
- `~/.git` — the misplaced repo metadata. The root cause. Delete.
- `~/.github/` — workflows from the misplaced repo's perspective. Already reconciled into the project tree in step 4.
- `~/.gitignore` — ignore rules for the misplaced repo; meaningless now.
- `~/.npmrc` — only delete if it was created by the misplaced project; **check first** in case it contains real user-level npm config (registry tokens, scope mappings).
- `~/.svelte-kit/` — generated by a stray SvelteKit run from `~/`.
- `~/src/` — scaffolded source dir from a SvelteKit init in the wrong directory.

Do **not** blindly delete `~/.vscode/`. In this case it contained legitimate VS Code data (`argv.json` from 2024, an actively-maintained `extensions/` directory) and only the `~/.vscode/extensions.json` file was a SvelteKit init artifact — harmless to leave in place. Verify with `ls -la ~/.vscode/` and `stat ~/.vscode/<file>` before deciding.

### Alternative: history-preserving fix with `git filter-repo`

If you cannot force-push (protected branch, collaborators, valuable history), the alternative is to rewrite the misplaced repo's history so that the `Documents/claude/csfd/` prefix is stripped from every commit:

```bash
cd ~/.misplaced-repo-checkout    # clone of the misplaced repo
git filter-repo --subdirectory-filter Documents/claude/csfd/
# After this, paths like 'Documents/claude/csfd/streamfinder/src/...'
# become 'streamfinder/src/...' across all commits.
```

Then move the resulting `.git` to the project root and force-push. This preserves commit hashes' relative relationships and per-commit history, at the cost of being more complex and still requiring a force-push. Use only if step 8's force-push is genuinely unacceptable.

## CI gotcha

The force-push triggered the GitHub Actions deploy workflow, which immediately failed:

```
npm error code EUSAGE
npm error
npm error `npm ci` can only install packages when your package.json and
npm error package-lock.json or npm-shrinkwrap.json are in sync. Please update
npm error your lock file with `npm install` before continuing.
npm error
npm error Missing: @emnapi/core@1.10.0 from lock file
npm error Missing: @emnapi/runtime@1.10.0 from lock file
npm error Missing: @tybys/wasm-util@0.10.1 from lock file
```

### Root cause

`npm ci` is strict: it refuses to run if `package-lock.json` doesn't perfectly match `package.json`. The `@emnapi/*` packages are Node's N-API emulator for WebAssembly — they're **optional transitive dependencies** of some platform-specific packages (notably `@rollup/rollup-*` and `@swc/core-*`). On macOS, npm omits them from the lock file because they're not needed. On Linux CI runners, npm wants them, finds they're absent, and `npm ci` refuses to install them (since adding to the lock file would be a "modification").

This is a well-known npm-on-Linux-vs-macOS lock-file drift problem. It has nothing to do with the repo migration — it would have hit eventually anyway — but the migration was the first time the workflow ran end-to-end after the lock file was regenerated locally.

### Fix

Switch `npm ci` → `npm install` in the deploy workflow:

```yaml
- name: Install dependencies
  # Use 'npm install' instead of 'npm ci' to tolerate minor lock-file drift
  # across platforms (CI runner vs developer machines). npm ci is strict
  # about package-lock.json matching package.json exactly, which breaks
  # when optional transitive dependencies (e.g. @emnapi/*) differ between
  # macOS and Linux.
  run: npm install
```

Commit and push, and the deploy succeeds.

### Trade-offs of `npm install` vs `npm ci`

| Aspect | `npm ci` | `npm install` |
|---|---|---|
| Strictness | Refuses on any drift | Reconciles drift silently |
| Speed | Faster (no resolution) | Slower (does resolution) |
| Reproducibility | Exact lock file | May add/update entries |
| Cross-platform | Brittle | Tolerant |

`npm ci` is the right default for production CI where reproducibility is critical and the dev/CI environments match. For a small SvelteKit project deploying to GitHub Pages where the package set is simple, `npm install` is fine and avoids the cross-platform headache.

### Better long-term fixes (if you need `npm ci` strictness)

- **Generate the lock file on Linux:** run `npm install` once in a Linux container (or a CI job that commits its output) so the lock file includes the `@emnapi/*` entries that Linux needs. Then `npm ci` works everywhere.
- **Pin the Node version:** ensure `package.json` `engines.node` matches the CI runner's Node version, since npm's lock-file format has subtly changed across Node majors.
- **Delete and regenerate the lock file:** `rm package-lock.json && npm install` on the platform that CI will run on, then commit.

For this project, `npm install` was the pragmatic choice — documented in a code comment so the next person doesn't "fix" it back to `npm ci`.

## Verification

After completing the migration and the CI fix, verify across four layers: filesystem, git, remote, and runtime.

### Filesystem layer

```bash
ls -la ~/.git 2>/dev/null && echo "FAIL: ~/.git still exists" || echo "OK: ~/.git is gone"
ls -la ~/.github 2>/dev/null && echo "FAIL: ~/.github still exists" || echo "OK"
ls -la ~/Documents/claude/csfd/.git    # should exist and be a real directory
```

Expected: `~/.git` absent, project `.git` present.

### Git layer

```bash
cd ~/Documents/claude/csfd
git rev-parse --show-toplevel
# /Users/radozoo/Documents/claude/csfd

git rev-parse --git-dir
# /Users/radozoo/Documents/claude/csfd/.git

git status
# On branch main
# Your branch is up to date with 'origin/main'.
# nothing to commit, working tree clean

git log --oneline -5
# 031fe4c ci: use 'npm install' to tolerate package-lock drift on CI runner
# 03c18d7 chore: re-initialize repository at project root

git remote -v
# origin  https://github.com/radozoo/streamfinder.git (fetch)
# origin  https://github.com/radozoo/streamfinder.git (push)
```

Critical things to check:

- `git status` shows **no** files from outside the project. No `Desktop/`, no `Library/`, no other repo dirs.
- Tracked paths have **no** `Documents/claude/csfd/` prefix. They start with `streamfinder/`, `src/`, etc.
- The branch is tracking `origin/main` and they're in sync.

### Remote layer

```bash
# Verify GitHub has the new history
git ls-remote origin main
# 031fe4c...  refs/heads/main  (the latest commit after CI fix)

# Verify the deploy workflow ran and succeeded
gh run list --workflow=deploy-streamfinder.yml --limit 3
# completed  success  ...  main  push  ...
```

Browse the repo on GitHub and confirm:
- The file tree at the root looks like the project (no `Documents/claude/csfd/` wrapper directory).
- The Actions tab shows a green check on the most recent run.
- `paths:` filters in workflow YAMLs reference `streamfinder/**`, not `Documents/claude/csfd/streamfinder/**`.

### Runtime layer

The whole point of fixing the repo was to ship the app. Verify deployment:

```bash
curl -sI https://radozoo.github.io/streamfinder/ | head -1
# HTTP/2 200
```

Open the live site in a browser and click through key flows:

- **Katalog page**: posters render, filter pills work, clicking a title opens its modal.
- **Kalendár page**: date grid loads, day cells show titles, modals open.
- **Navigation**: links between pages work, URLs match expected paths.

In this case, manual verification at `https://radozoo.github.io/streamfinder/` confirmed both pages working: filter pills, modals, posters all rendered correctly.

### Recovery rehearsal (optional but recommended)

Before deleting the `/tmp` backups, rehearse a restore to confirm the backups are intact:

```bash
# Verify mirror backup is readable
git --git-dir=/tmp/streamfinder-backup-mirror.git log --all --oneline | head -5

# Verify dotgit backup is readable
git --git-dir=/tmp/dotgit-backup-2026-05-14 log --all --oneline | head -5
```

If both produce sane output, you have a working safety net. Keep the backups for at least a week, then delete:

```bash
rm -rf /tmp/streamfinder-backup-mirror.git /tmp/dotgit-backup-2026-05-14
```

(On macOS, `/tmp` is cleared on reboot anyway, so this often happens for you.)

## Trade-off

The chosen solution (fresh re-init + force-push) is fast and clean but **discards remote history**. Here's what was traded and why each trade was acceptable in this case:

### What was lost

- **Remote commit history.** The previous 525aa75-tip history on GitHub is gone (archived in `/tmp/streamfinder-backup-mirror.git` for now, but no longer reachable from the live remote). Anyone who had cloned the old version sees their fork diverge.
- **Issue and PR linkage to commit SHAs.** GitHub issues that reference old commit SHAs (`Fixed in abc1234`) now point to commits that don't exist on the default branch. The commits still exist as orphaned objects on GitHub's side for some time, but they'll be garbage-collected eventually.
- **Per-file blame continuity.** `git blame` on the new repo starts from the migration commit. Lines that were last touched in the old history all show the migration commit as their author. Useful blame data is lost.
- **Branch and tag history.** Any feature branches or tags on the old remote were not migrated. Only `main` was force-pushed. If there were valuable feature branches, they would have needed separate handling.

### Why it was acceptable here

- **Solo developer, early stage.** Nobody else has cloned the repo. There are no open PRs from collaborators to break.
- **History was short and partly garbage.** The misplaced-repo history included commits that touched files outside the project (every commit was potentially polluted with home-directory churn). The history wasn't worth saving.
- **The catastrophic `reset --hard` had already destroyed local state.** The cost of "lose history" was already partially paid; finishing the migration was strictly better than living with the misplacement.
- **Decision rationale already captured elsewhere.** Major design decisions had been documented in `docs/brainstorms/` and `docs/solutions/` from prior `/cde:compound` passes. Commit history was redundant with that.

### When this trade-off is NOT acceptable

Use the history-preserving alternative (`git filter-repo --subdirectory-filter`) instead if any of these apply:

- **Multiple contributors.** Force-pushing main on a shared repo creates chaos. Coordinate or use filter-repo.
- **Long, meaningful history.** If commits tell a story (bisectable bugs, careful refactors), preserve them.
- **External references to commits.** If issues, deploys, changelogs, or downstream tooling reference specific commit SHAs, breaking those references has real cost.
- **Protected branches with required signatures or reviews.** You may not even be allowed to force-push.

### Other options considered and rejected

| Option | Why rejected |
|---|---|
| Move `~/.git` to `~/Documents/claude/csfd/.git` and rewrite paths | `git mv` of every file at every commit is what `filter-repo` does cleanly; doing it manually is error-prone. |
| Use `git filter-repo --subdirectory-filter` | Valid but more complex. Solo project + short history made re-init the better cost/benefit. |
| Leave the misplacement in place, just be careful | Already proven dangerous (the `reset --hard` incident). Not viable. |
| Initialize the new repo and cherry-pick commits across | Requires reconstructing the migration commit-by-commit. High effort, low marginal benefit over re-init. |

### Lessons that generalize

- **Backups before destruction are non-negotiable.** Mirror clone + local `.git` copy took 30 seconds and made every later step risk-free.
- **Diagnose with `git rev-parse --show-toplevel` and `--git-dir` before any destructive command.** These two commands would have prevented the original `reset --hard` disaster.
- **Force-pushing is fine when the trade-off is conscious.** It's the unconscious or "I didn't realize this would discard X" force-pushes that cause harm.
- **CI failures after a migration are normal.** Expect at least one round of "the workflow ran for the first time on the new repo and surfaced a latent issue." Budget time for it.

## Prevention & Best Practices

The most expensive part of this incident was not the time spent on the fix — it was the lost in-progress work from a `git reset --hard` operating on a worktree that secretly extended across the entire home directory. None of that was necessary. The mistake is trivial to detect within seconds of scaffolding, and trivial to avoid if you build the right reflex. This section is the playbook.

### Recognize the symptoms early

If any of the following signals appear, **stop committing and investigate** before doing anything else. Each one is a near-certain indicator that your git worktree root is not where you think it is.

- [ ] **`git rev-parse --show-toplevel` returns a path that is not your project directory.**
  This is the single most authoritative check. The toplevel is the actual root of the worktree — i.e., the directory containing `.git`. If you are inside `~/Documents/claude/csfd/streamfinder` but this command prints `/Users/you`, every other piece of git tooling will operate on your entire home directory.

- [ ] **`git status` shows files from outside your project as untracked.**
  Lines like `?? ../../../Downloads/`, `?? ../../../Library/`, `?? ../../Music/` are not normal. A correctly-rooted repo cannot see files above its own toplevel. Seeing them means the toplevel is too high.

- [ ] **Tracked paths in `git ls-tree -r HEAD --name-only` have an unexpected prefix.**
  In a healthy repo, paths look like `src/lib/foo.ts` or `package.json`. If they look like `Documents/claude/csfd/streamfinder/src/lib/foo.ts`, git is recording the project as a *subdirectory* of the repo, not the repo itself. Every CI workflow, every editor's "open repo" command, and every relative-path script will now be subtly wrong.

- [ ] **Deploy workflows need a `working-directory:` workaround pointing deep into a path.**
  ```yaml
  - run: npm install
    working-directory: Documents/claude/csfd/streamfinder
  ```
  If your CI yaml has a `working-directory` that *looks like your home folder structure*, that is a smell. CI checks out the repo into a clean directory — there is no legitimate reason the path inside it should mirror your laptop's folder hierarchy.

- [ ] **Mysterious dotfiles appear at unexpected directory levels.**
  Finding `.svelte-kit/`, `.npmrc`, `node_modules/`, or a project-specific `.gitignore` directly inside `~` (your home dir) is a giveaway that a scaffolder ran from the wrong place. These should live inside the project, never at `$HOME`.

- [ ] **Two `.gitignore` files exist at different parent dirs of the same project.**
  One at `~/.gitignore` and one at `~/Documents/claude/csfd/streamfinder/.gitignore` is almost never intentional. The home-level one was likely created by a scaffolder that thought `~` *was* the project.

- [ ] **`git log` shows commits with file paths that include the directory structure of your laptop.**
  `git log --stat` or `git show <commit>` revealing paths like `Documents/claude/csfd/streamfinder/package.json` confirms the project was committed as a *subtree*, not as the root.

- [ ] **VS Code / your editor's source-control panel shows wildly more changed files than you edited.**
  Editors usually pick up the toplevel via `git rev-parse`. If the panel lists hundreds of files you've never touched, the worktree is too wide.

Any *one* of these is enough to act on. Do not rationalize away a strange path or an extra prefix — they compound, and the longer you wait the more painful the cleanup.

### The rule

> **Always run `git rev-parse --show-toplevel` immediately after scaffolding any new project, and after the first `git init` in any new directory. If the output is anything other than the project directory you are currently `cd`'d into, abort, delete the `.git` folder, and re-initialize at the correct location before committing a single file.**

Memorize this. Make it the *first* thing you do after `npx sv create`, `npm create vite`, `cargo new`, `rails new`, `django-admin startproject`, or `git init`. Five seconds of paranoia at scaffolding time saves hours of force-pushing later.

### Pre-flight checklist for new projects

Run through this every time you start a new project — *especially* when a scaffolder is involved. Do not skip steps because "I know what I'm doing." This bug bites precisely the people who think that.

1. **Decide on the project directory before doing anything else.**
   ```bash
   mkdir -p ~/Documents/claude/my-new-project
   ```

2. **`cd` into the intended project directory and verify with `pwd`.**
   ```bash
   cd ~/Documents/claude/my-new-project
   pwd
   # /Users/you/Documents/claude/my-new-project   <-- confirm this is correct
   ```

3. **Run the scaffolder with an *explicit* target.**
   Prefer named targets over `.` whenever the tool supports it:
   ```bash
   # Good — unambiguous, scaffolder creates and enters the dir
   npx sv create streamfinder
   cd streamfinder

   # Acceptable — but only after verifying pwd in step 2
   npx sv create .
   ```
   The `.` form is a footgun: if you are even one directory off, the scaffolder will happily explode files into the wrong place.

4. **Immediately verify the worktree root.**
   ```bash
   git rev-parse --show-toplevel
   # Should print: /Users/you/Documents/claude/my-new-project
   ```
   If it does not match `pwd` (or `pwd`/subdir if you `cd`'d into the scaffold), STOP.

5. **Check `git status` for surprises.**
   ```bash
   git status
   ```
   You should see only files the scaffolder created. *Any* `??` line referencing `../` or a path outside the project is a red flag.

6. **Skim `.gitignore` and confirm it lives inside the project.**
   ```bash
   ls -la .gitignore
   # .gitignore should be at the project root, not at ~/.gitignore
   ```

7. **Make the initial commit only after the above pass.**
   ```bash
   git add -A
   git commit -m "Initial scaffold"
   ```
   Now your safety net (reflog, commit history) exists.

8. **Push to a remote early.**
   A pushed `main` is a backup. Do this before any significant work.

### Defensive habits

Even with the best intentions, mistakes happen. These habits *contain* damage when they do:

- **Commit early, commit often.**
  Anything committed locally — even on a throwaway branch — survives `git reset --hard` because the reflog keeps it for 90 days by default. Uncommitted work has no such protection. If you find yourself thinking "I'll just commit this when it's done," you are one stray command away from losing it.

- **Take a `git clone --mirror` backup BEFORE any history-rewriting operation.**
  Before `git reset --hard`, `git filter-repo`, `git rebase -i`, force-push, or re-init:
  ```bash
  git clone --mirror . /tmp/backup-$(date +%Y%m%d-%H%M%S).git
  ```
  A mirror clone captures *all* refs and the full reflog. If the rewrite goes wrong, you have a recoverable copy. This takes ten seconds. Always do it.

- **Never run `git reset --hard` on uncommitted work unless you have explicitly accepted losing it.**
  `git reset --hard` is destructive and silent. Prefer `git stash`, `git switch -c rescue-branch`, or `git commit -m "wip"` first. If you must reset, run `git status` *and* `git diff` *and* `git stash list` immediately before, and ask: "If everything in those outputs vanishes, am I OK?"

- **Make `git rev-parse --show-toplevel` muscle memory.**
  At the start of any new shell session in an unfamiliar repo, type it. It is the git equivalent of looking both ways before crossing a street. It costs nothing and prevents catastrophe.

- **Set up a shell prompt that shows the git root or branch.**
  Tools like starship, oh-my-zsh's git plugin, or a custom `PS1` can surface the current branch and warn when you are in a repo. A prompt that says `(main)` while you are inside `~` is a five-alarm fire.

- **Never run `git init` in `$HOME`.**
  Consider adding a defensive `pre-init` shell wrapper or a personal habit of *always* `cd`'ing into a project dir before `git init`. Some teams even add a guard:
  ```bash
  # ~/.zshrc snippet
  git() {
      if [[ "$1" == "init" && "$PWD" == "$HOME" ]]; then
          echo "REFUSED: never 'git init' in \$HOME. cd into a project dir first."
          return 1
      fi
      command git "$@"
  }
  ```

- **Push to a remote often.**
  A remote is a backup you cannot accidentally delete locally. The earlier and more often you push, the less you can lose to a bad `reset`.

- **Periodically audit your home directory.**
  ```bash
  ls -la ~ | grep -E '^\.(git|svelte-kit|npmrc|env)'
  ```
  Catching a stray `.git` in `~` early lets you fix it before it has tangled with months of work.

### If you find yourself in this state — decision matrix

You discovered the bug. Now what? The right answer depends on history length, collaborators, and stakes.

| Option | Steps | When to choose | Drawbacks |
|---|---|---|---|
| **A: Fresh start (re-init)** | 1. `git clone --mirror` backup. 2. Copy project files out to a safe temp dir. 3. Delete the stray `.git`. 4. `cd` into correct project dir. 5. `git init`. 6. Update `.gitignore`. 7. `git add -A && git commit -m "Initial commit"`. 8. `git remote add origin <url>`. 9. `git push --force origin main`. 10. Clean up junk files from home. | Solo project, short history, no external collaborators, low stakes on git log. | Loses commit history, authorship, blame. Anyone with an old clone is broken. |
| **B: `git filter-repo` to strip the prefix** | 1. `git clone --mirror` backup. 2. Install `git-filter-repo`. 3. Run `git filter-repo --subdirectory-filter Documents/claude/csfd/streamfinder` to lift the subdirectory to the repo root. 4. Verify with `git log --stat` that paths look correct. 5. Force-push. 6. Coordinate clone-resets with collaborators. | Team project, long meaningful history, blame/authorship matters, you want to preserve commit metadata. | `filter-repo` is powerful but unforgiving — one wrong flag rewrites history in surprising ways. Force-push still breaks every existing clone; collaborators must re-clone. Requires understanding of git internals. |
| **C: Live with it** | Keep `working-directory:` workarounds in CI. Document the quirk in a `README` so future-you isn't confused. Avoid running `git reset --hard` ever (because the worktree extends across `$HOME`). | Archived project, dead code, not worth the disruption, no active work. | Permanent low-grade friction. Every new tool, CI step, and editor integration will hit the weird structure. `git reset --hard` remains a loaded gun — anyone who runs it wipes uncommitted files across your home dir. Not recommended for any active project. |

**Default recommendation:** For solo / hobby / small projects, **Option A** is almost always right — the friction of losing log is less than the friction of `filter-repo`. For team or production projects, **Option B** is worth the care. **Option C** is a trap; the `reset --hard` hazard alone makes it dangerous.

Whichever option you pick, **take the mirror backup first**. It is the single cheapest insurance policy in git.

### Specific to SvelteKit / Node project scaffolders

This is the exact category of tool that caused this incident. Read carefully.

**Most modern JS/TS scaffolders run `git init` for you automatically.** This includes:

- `npx sv create` (SvelteKit)
- `npm create vite@latest`
- `npm create svelte@latest` (legacy)
- `npx create-next-app`
- `npx create-remix`
- `npx create-react-app` (deprecated but still in use)
- `npx nuxi init`
- Many `npm create <something>` scripts

If you run any of these from the wrong directory — especially from your home dir — they will silently `git init` *there*, and every file the scaffolder creates becomes a tracked file in a repo rooted at `~`. This is precisely how the incident happened.

**Always pass an explicit target directory.** Compare:

```bash
# DANGER — if you are in $HOME, this initializes git in $HOME
cd ~
npx sv create .

# SAFE — scaffolder creates ./streamfinder and inits git inside it
cd ~/Documents/claude/csfd
npx sv create streamfinder
cd streamfinder
git rev-parse --show-toplevel   # confirm before doing anything else
```

**If a scaffolder offers a `--no-git` flag, consider using it** and running `git init` yourself afterward. This forces you to be the one who decides where the repo lives:

```bash
npx sv create streamfinder --no-git    # check the tool's docs for exact flag
cd streamfinder
git init
git rev-parse --show-toplevel
```

**Watch the scaffolder's output.** Most of them print a line like:

```
Initialized empty Git repository in /Users/you/.git/
```

If that path is your home directory, **stop immediately**. Do not run the suggested `npm install` or `npm run dev`. Delete the stray `.git` (`rm -rf ~/.git`), `cd` to the correct location, and start over. The longer you wait, the more files get tracked at the wrong root.

**Specific gotcha for `npm ci` in CI:** A misrooted project often does not have a `package-lock.json` committed at the apparent repo root (the lock is inside the subdirectory). `npm ci` will fail because it requires a lock at the working directory. Switching to `npm install` is a workaround, but the real fix is to put the repo root and `package-lock.json` in the same directory by re-rooting the repo (Option A or B above).

**Final reminder:** SvelteKit's `npx sv create` is a *great* tool — this incident was not its fault. The tool did what it was told. The lesson is to be explicit about *where* you tell it to work, and to verify with `git rev-parse --show-toplevel` *every single time* before committing anything.

## Related

- [Streamfinder data pipeline / frontend field mismatches](../integration-issues/streamfinder-data-pipeline-frontend-mismatches.md) — Same April 15 era as the wiped work; documents the static-site/SvelteKit pipeline that gets deployed via the CI workflow this doc fixes.
- [SvelteKit URL state sync via `$effect` + `history.replaceState`](../integration-issues/sveltekit-url-state-sync-effect.md) — Part of the April 16 kalendar work era that was lost during the same period of repo dysfunction; touches the kalendar files referenced in this doc's context.
- [Svelte 5 `$derived.by` over-invalidation — split slow and fast dependencies](../performance-issues/svelte5-derived-invalidation-splitting.md) — April 16 kalendar work that was lost/restored alongside the repo-init fix; same time window of broken repo state.
- [FilterDropdown: panels clipped by overflow + simultaneous multi-panel opening](../ui-bugs/svelte-dropdown-overflow-clip-and-singleton-state.md) — The original FilterDropdown work explicitly called out as lost during the era of repo dysfunction.
- [Kalendár filter bar brainstorm](../../brainstorms/2026-04-16-kalendar-filter-bar-brainstorm.md) — April 16 kalendar FilterBar plan wiped during the same repo-init era.
- [Kalendár load-more days brainstorm](../../brainstorms/2026-04-16-kalendar-load-more-days-brainstorm.md) — Companion April 16 kalendar brainstorm from the same lost-work window.
- [Streamfinder dashboard brainstorm](../../brainstorms/2026-04-12-streamfinder-dashboard-brainstorm.md) — Establishes the static-site/GitHub Pages deployment target that the broken CI workflow (`npm ci` lock drift) was meant to publish.

### Future cross-references to add (when relevant docs land)

- A future doc on `package-lock.json` cross-platform drift / `npm ci` vs `npm install` reproducibility should link back here as the precipitating incident.
- A future doc on GitHub Actions deploy-to-Pages workflow hardening (Node version pinning, cache keys, `actions/configure-pages`) should reference the deploy-streamfinder fix.
- A future doc on `.gitignore` hygiene for accidentally-tracked home-root files (`.zsh_history`, `.ssh/`, `.config/`) should cite this as the cleanup precedent.
