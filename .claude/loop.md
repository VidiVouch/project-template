Run a maintenance pass over the current branch. Work through the steps in
order and stop when nothing's pending.

**Safety rule (applies to every step):** irreversible or remote-reaching
actions — `git push`, `git push --force`, branch delete, rebase of an
already-pushed branch, resolving PR review threads, merging — only proceed
when they continue something the transcript already authorized. When in
doubt, prepare the fix locally and report what's ready for the human to
push.

### 1. Continue unfinished work
If the transcript shows an in-progress task (failing test, half-written
edit, pending rebase), resume it. Do not start new initiatives beyond what
was already authorized.

### 2. Tend the current branch's PR
If this branch has an open PR:
- Pull the latest CI status (`gh pr checks`). If a check is red, fetch
  the failing job log, diagnose, and prepare a minimal fix as a **local
  commit**. Do not push — report that the fix is ready.
- Enumerate inline review **comments** via
  `gh api repos/{owner}/{repo}/pulls/{n}/comments` (top-level
  `gh pr view --comments` returns only issue-level comments). This
  endpoint returns review comments, not thread objects — that's fine
  because the loop only *addresses* comments, it doesn't resolve
  threads. Address each comment with a local edit. Do **not** resolve
  the thread (that would need a GraphQL `resolveReviewThread` mutation
  against the thread node ID from `pullRequest.reviewThreads`) — leave
  resolution to the human when they push.
- If there's a merge conflict with `main`, report it and stop Step 2.
  Do not rebase the PR branch autonomously (it would require a
  subsequent force-push).

Skip this step if there's no open PR for the branch.

### 3. Run `/deep-review`
Invoke `/deep-review` (defaults to `--base main`). The command has its
own diff-hash dedup cache, so it's cheap to call repeatedly — it will
skip automatically if the diff hasn't changed since the last review.

If it surfaces **critical**, **warning**, or **nit** findings, address them:
- **Finding maps to a local-only commit**: validate the target, confirm
  it's unpublished, then fixup + autosquash. Otherwise fall through to
  the pushed-commit path below. The sequence:
  ```bash
  # 0. Validate <sha> resolves to a real commit. A stale finding pointing
  #    at a rewritten/deleted commit must fail loud, not fall through
  #    and full-branch rebase.
  git rev-parse --verify "<sha>^{commit}" >/dev/null 2>&1 \
      || { echo "<sha> no longer exists; skipping fixup"; exit 0; }

  # 1. Refuse to classify on detached HEAD — no branch context means
  #    we can't reason about what's pushed; treat as pushed to stay safe.
  if ! git symbolic-ref --quiet HEAD >/dev/null; then
      LOCAL_ONLY=0
  # 2. Merge commits flatten under autosquash (<sha>^ = first parent),
  #    silently dropping the second-parent history. Route to the
  #    follow-up-commit path instead.
  elif [ "$(git rev-list --parents -n 1 <sha> | wc -w)" -gt 2 ]; then
      echo "<sha> is a merge commit; autosquash would flatten history"
      LOCAL_ONLY=0
  # 3. Branch has no upstream → trivially local-only.
  elif ! git rev-parse --abbrev-ref --symbolic-full-name @{upstream} >/dev/null 2>&1; then
      LOCAL_ONLY=1
  else
      # 4. Refresh remote-tracking refs before ancestry check. If fetch
      #    fails (offline, auth), treat as pushed — stale refs could
      #    falsely classify a just-pushed commit as local-only.
      if ! git fetch --quiet; then
          echo "fetch failed; treating as pushed"
          LOCAL_ONLY=0
      else
          # Exit 0 = <sha> is ancestor of upstream (pushed).
          # Exit 1 = not ancestor (local-only).
          # Any other exit = error; conservative → pushed.
          git merge-base --is-ancestor <sha> @{upstream}
          case $? in
              0) LOCAL_ONLY=0 ;;
              1) LOCAL_ONLY=1 ;;
              *) LOCAL_ONLY=0 ;;
          esac
      fi
  fi
  ```
  If `LOCAL_ONLY=1`, create the fixup commit with `git commit --fixup <sha>`
  and run a non-interactive autosquash. The `-i` flag is required —
  without it, `--autosquash` has no effect (it only reorders the todo
  list that interactive mode generates). `GIT_SEQUENCE_EDITOR=true`
  accepts that todo list without opening an editor (the loop has no
  TTY). Detect the root commit explicitly (don't rely on `<sha>^`
  failing — that also fails for invalid SHAs, already screened above
  but worth being precise):
  ```bash
  ROOT=$(git rev-list --max-parents=0 HEAD | head -1)
  if [ "$(git rev-parse <sha>)" = "$ROOT" ]; then
      REBASE_TARGET="--root"
  else
      REBASE_TARGET="<sha>^"
  fi
  # Wrap the rebase so a mid-rebase conflict can't leave the tree
  # mid-state. --autostash only pops cleanly on success; on conflict
  # the stash stays stashed and the rebase stays in progress until a
  # human intervenes. Aborting restores the autostash and preserves
  # the fixup commit itself for later human attention.
  if ! GIT_SEQUENCE_EDITOR=true git rebase -i --autosquash --autostash $REBASE_TARGET; then
      git rebase --abort
      echo "autosquash conflicted; fixup commit preserved for human review"
  fi
  ```
  `--autostash` protects any uncommitted scraps. History rewriting is
  safe because the commit hasn't been pushed.
- **Finding maps to an already-pushed commit (LOCAL_ONLY=0)**: create
  a normal follow-up commit. Do not fixup+autosquash — that would
  require a force-push to update the PR.

Do NOT touch **dismissed** findings — those are explicit false positives
recorded in REVIEW.md and re-fixing them wastes cycles. For **nit**
findings that turn out to be genuinely cosmetic (style-only, no
behavioral delta), apply the fix with judgment: if it's a one-line tweak,
just do it; if it materially bloats the diff or touches unrelated code
under the guise of a nit, defer and flag it. Use the same fixup-vs-
follow-up routing as critical/warning findings above.

If pre-flight fails (the project's lint/format/type gate), fix the failures
first and re-run. `/deep-review` auto-fixes lockfile drift and lint/format
issues, but type errors still need manual intervention.

### 4. Run `/check-coverage`
Invoke `/check-coverage` (defaults to `--base main`).

Read the two-phase diagnostic:
- **Phase 1 high, Phase 2 low** — the new tests are testing the wrong
  thing. Re-read the new test files and fix before adding more tests.
- **Both low** — real coverage gap. For each uncovered line, decide:
  bug-catching test, edge case, error path, or legitimately `pragma:
  no cover`. Don't chase 100%; don't write tests that just exercise
  the line.
- **Both high** — nothing to do here.
- **Phase 2 skipped / "no new test files"** — the diff touches code but
  added no tests. Not automatically a problem (may be docs, fixtures,
  refactor). Evaluate whether the changed code warrants new tests; if
  yes, add them, otherwise move on.
- **Phase 1 low, Phase 2 high** — impossible per the command's own
  table (Phase 2 is a strict subset of Phase 1). If you see it, report
  a `/check-coverage` bug and stop — do not try to write tests against
  a broken diagnostic.

### 5. Push findings to the PR

After steps 1-4, if this branch has an open PR and any local commits were
created during this pass (including earlier passes not yet pushed), push
them to the remote so the PR reviewers can pick up the follow-up commits
and re-review. This step **overrides** the default safety rule's "no autopush"
posture for the PR-feedback loop specifically — the whole point of the
loop is to close review-comment rounds autonomously.

```bash
# Only push when there's actually something to ship and the branch is
# tracking a remote. Detached HEAD, branches with no upstream, and
# no-unpushed-commits all fall through to a no-op with a clear log line.
#
# Explicit exit-status check on ``git push`` is load-bearing. A silent
# failure (non-fast-forward rejection, network error, auth glitch) would
# otherwise leave the loop thinking the commits shipped — subsequent
# ticks would see "no unpushed commits" on the local rev list but the
# remote would still be stale, and the user would not find out until
# the next deep-review tried to re-review already-fixed issues. Fail
# loud instead, with the git output preserved for post-mortem.
if ! git symbolic-ref --quiet HEAD >/dev/null; then
    echo "Detached HEAD; nothing to push."
elif ! UPSTREAM=$(git rev-parse --abbrev-ref --symbolic-full-name @{upstream} 2>/dev/null); then
    echo "Branch has no upstream; skipping push."
elif [ "$(git rev-list --count @{upstream}..HEAD)" -eq 0 ]; then
    echo "No unpushed commits; nothing to push."
else
    if ! git push; then
        echo "git push FAILED. Do NOT retry with --force. Investigate:"
        echo "  - non-fast-forward (remote moved): rebase locally before the next tick"
        echo "  - auth/network: resolve and re-run the loop"
        echo "Local commits preserved; the loop will not re-push on the next tick until the issue is fixed."
        exit 1
    fi
fi
```

Constraints that still apply even inside this step:
- **Never force-push.** If `git push` is rejected as non-fast-forward
  (someone else committed to the PR branch), stop and report — do NOT
  retry with `--force` or `--force-with-lease`.
- **Never skip pre-commit / pre-push hooks.** If a hook fails, diagnose
  and fix in a new local commit; do not pass `--no-verify`.
- **Never merge, close, or resolve review threads.** Those are human
  actions.
- If `main` has moved under the branch and a fast-forward push is not
  possible, report the divergence and stop. Autonomous rebase of a
  pushed branch would require a subsequent force-push and is out of
  scope for this loop.

### 6. Quiet exit

If nothing above had anything to do, say so in one line and stop.
Do not invent work. The safety rule at the top of this file governs
every step — re-read it before any remote-reaching action, with the
single documented exception of step 5's fast-forward push.
