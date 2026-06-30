---
description: Review local changes against a base branch
argument-hint: "[--base <branch>] [--uncommitted] [--commit <sha>] [--range <a>..<b>]"
allowed-tools: Bash(git diff *), Bash(git log *), Bash(git ls-files *), Bash(git rev-parse *), Read, Glob, Grep
---

# Local Review

Single-pass Claude review of local changes. Lightweight alternative to
`/deep-review` when you don't need multi-tool orchestration — one
model reads the diff against project conventions and reports.

## Arguments

Parse `$ARGUMENTS` for:

- `--base <branch>` — base branch to compare against (default: `main`)
- `--uncommitted` — review uncommitted changes (staged + unstaged + untracked) instead of branch diff
- `--commit <sha>` — review a single commit
- `--range <from>..<to>` — review a range of commits

The four modes are mutually exclusive. If no mode flag is provided,
default to `--base main`.

**Diff modes** — diff and log commands adapt per mode:

| Mode                    | Diff command                                      | Log command                         |
|-------------------------|---------------------------------------------------|-------------------------------------|
| `--base main` (default) | `git diff main...HEAD`                            | `git log --oneline main..HEAD`      |
| `--uncommitted`         | `git diff HEAD` + `git diff --cached` + untracked | (no commits to log)                 |
| `--commit abc123`       | `git diff abc123^..abc123`                        | `git log --oneline abc123^..abc123` |
| `--range abc..def`      | `git diff abc..def`                               | `git log --oneline abc..def`        |

In `--uncommitted` mode, `git diff HEAD` and `git diff --cached` do not
see untracked files. Run `git ls-files --others --exclude-standard` and
`Read` each untracked file's full contents — without this, a newly
created file is invisible to the review.

In `--commit` mode on a root commit (no parent), `${COMMIT}^` does not
resolve. Detect with `git rev-parse --verify "${COMMIT}^"` and bail
before running the diff.

## Steps

### 1. Gather the diff

For `--commit` mode, verify the parent exists first:

```bash
git rev-parse --verify "${COMMIT}^" >/dev/null 2>&1 || {
    echo "ERROR: ${COMMIT} is a root commit (no parent); use --range or amend onto a parent first." >&2
    exit 2
}
```

Then run the diff and log commands for the selected mode (see Diff modes
table). Also run a stat summary using the same diff scope, e.g. `git
diff <scope> --stat` (`<scope>` is the same range expression used for
the full diff). The stat output anchors the review header counts.

For `--uncommitted` mode, additionally:

```bash
git ls-files --others --exclude-standard
```

Then `Read` each listed untracked file's full contents.

### 2. Read project context

Read `REVIEW.md` (if it exists) for project-specific rules and known
false positives. Read `CLAUDE.md` for general project conventions.

### 3. Review the changes

Analyse the diff and provide a thorough review covering:

- **Correctness** — logic errors, wrong return values, missing error handling
- **Project conventions** — violations of CLAUDE.md or REVIEW.md rules
- **Performance** — unnecessary allocations, O(n^2) patterns, missing indexes
- **Security** — injection, unsafe deserialization, secrets in code

Do NOT flag anything listed in the REVIEW.md "Skip" section.

### 4. Format the output

```markdown
## Review: <scope description>

**Commits:** <count> | **Files changed:** <count>

### Issues

| # | Severity | File:Line | Finding |
|---|----------|-----------|---------|

### Positive

- What's good about these changes
```

`<scope description>` adapts per mode:

- `--base main`: `<current branch> vs main`
- `--uncommitted`: `working tree`
- `--commit abc123`: `commit abc123`
- `--range abc..def`: `abc..def`

If no issues are found, say so clearly. Keep the review concise — focus
on what matters.
