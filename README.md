# Vidi Template

## Table of Contents

- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Development](#development)
  - [Package Management](#package-management)
  - [Code Quality](#code-quality)
  - [Pre-commit Hooks](#pre-commit-hooks)
  - [Testing](#testing)
- [IDE Setup](#ide-setup)
  - [PyCharm](#pycharm)
  - [VS Code](#vs-code)
- [Code Review](#code-review)

## Prerequisites

- **Python 3.14+**
- **[uv](https://github.com/astral-sh/uv)** package manager — install via the
  [standalone installer](https://docs.astral.sh/uv/getting-started/installation/#standalone-installer)
  (not brew/pip/pipx) so `uv self update` works

## Getting Started

```bash
# Clone the repository
git clone <repository-url>
cd <project-name>

# Install dependencies
uv sync

# Install pre-commit hooks
uv run pre-commit install

# Enable rerere (reuse recorded resolution) — caches how you resolve
# merge conflicts so Git auto-applies the same fix next time. Essential
# for this project's stacked branch workflow where the same conflicts
# recur on every cascade rebase.
git config rerere.enabled true
```

Open the project in your IDE — see [IDE Setup](#ide-setup) for configuration.

## Development

### Package Management

This project uses `uv` for dependency management:

```bash
# Add a new package
uv add package-name

# Add a dev dependency
uv add --dev package-name

# Update a single package
uv lock --upgrade-package package-name

# Update all packages
uv lock --upgrade

# Install with all extras
uv sync --all-extras

# Install without dev dependencies
uv sync --no-dev
```

### Code Quality

```bash
# Linting
uv run ruff check .
uv run ruff check --fix . # Auto-fix issues

# Formatting
uv run ruff format .
```

```bash
# Type checking
uv run basedpyright
```

### Pre-commit Hooks

Pre-commit hooks run automatically on `git commit`. They are installed during [Getting Started](#getting-started).

```bash
# Update hooks to latest versions
uv run pre-commit autoupdate
```

`.pre-commit-config.yaml` declares `default_install_hook_types` for
**pre-commit**, **post-checkout**, **post-merge**, and **post-rewrite**,
so `pre-commit install` wires hooks into all four — branch switches,
merges, and rebases trigger the relevant hooks automatically.

This sets up:

- **uv-lock** — validates the lockfile via `uv lock --locked`. Runs on
  pre-commit and **post-rewrite**, so any rebase or amend that leaves
  `uv.lock` out of sync with `pyproject.toml` surfaces a warning right
  after the rewrite (the hook can't fix the drift in-flight — re-rebase
  with an `--exec` regen step to fix — but it makes silent drift loud)
- **uv-sync** — syncs `.venv` to the lockfile; also runs on
  post-checkout / post-merge / post-rewrite so switching branches and
  rebasing auto-update your dependencies without a manual `uv sync`
- **uv-sort** — keeps `pyproject.toml` dependency arrays alphabetised
  (`project.dependencies`, `dependency-groups`, etc.) so `uv add`'s
  append-only insertion doesn't drift the file out of order
- **pretty-format-json** — autoformats JSON, scoped via `files:` to
  `.claude/settings.json`, `.codex/*.json`, `.mcp.json`, and
  `.vscode/*.json` only (not every JSON in the tree)
- **ruff-check** — linting with `--fix`
- **ruff-format** — formatting
- **basedpyright** — type-checks the **whole project** on every commit
  (`pass_filenames: false`). Slower than a per-file hook but catches
  cross-file regressions a per-file check would miss (a signature
  change in file A breaking callers in file B). CI runs the same
  check, so this is belt-and-braces.

### Testing

Tests use `pytest` with `pytest-cov` and `diff-cover`. Config in
`pyproject.toml` under `[tool.pytest.ini_options]` and `[tool.coverage.*]`.

```bash
uv run pytest                                  # run the suite
uv run pytest --cov --cov-report=term-missing  # + coverage with missing lines
```

For "did my recent changes get tested?" — both the whole-suite check and
the stricter "did the tests I just wrote cover the code I just wrote?"
check — use the `/check-coverage` slash command.

## IDE Setup

### PyCharm

The `.idea/` directory contains shared project settings. Native Pyright and Ruff integrations are pre-enabled via `misc.xml`, and PyCharm's built-in `PyTypeChecker` inspection is disabled in `inspectionProfiles/Project_Default.xml` to avoid running it alongside basedpyright.

These settings should be pre-set: in **Settings → Languages & Frameworks → Python → Tools → Pyright**, keep execution mode to **Interpreter** so it picks up `basedpyright` from the project venv. **Reformat code** and **Optimize imports** in **Settings → Tools → Actions on Save** should be enabled.

To enable the shared spell-check dictionary: **Settings → Editor → Natural Languages → Spelling**, add `project-words.dic` as a custom dictionary.

The **uv run configurations** in `.idea/runConfigurations/` invoke `/usr/bin/env sh` and only work on macOS/Linux. On Windows, run the equivalent `uv` commands in the terminal or use the VS Code tasks instead — those are shell-agnostic.

### VS Code

The `.vscode/` directory contains shared workspace settings. On first open:

1. Install the recommended extensions when prompted
2. VS Code auto-detects the `.venv` interpreter

Ruff formats on save and organizes imports automatically via `codeActionsOnSave`.

## Code Review

Orchestrated multi-tool code review via Claude Code commands. Reviews combine findings from Codex and Claude agents, then synthesize into a single deduplicated report.

### `/deep-review`

Runs pre-flight CI checks, launches up to 4 parallel reviewers, then synthesises findings with REVIEW.md-aware false positive filtering.

```bash
/deep-review --base main                    # review branch vs main
/deep-review --uncommitted                  # review working tree changes
/deep-review --commit abc123                # review a single commit
/deep-review --range abc123..def456         # review a commit range
/deep-review --base main --nofix            # skip auto-fix (default is to fix)
/deep-review --base main --skip-preflight   # skip CI checks
/deep-review --base main --focus "security" # focus adversarial review
/deep-review --base main --force            # re-review even if diff unchanged
```

**Pipeline:**

1. **Diff-hash dedup** — skips if diff unchanged since last review
2. **Pre-flight CI** — by default runs `uv lock`, `uv run ruff check --fix`, `uv run ruff format .`, `uv run basedpyright` (auto-fixing in place). With `--nofix`, runs the check-only variants and stops at the first failure.
3. **Parallel reviews** (all as background agents):
   - Codex standard (via `codex exec review --json`)
   - Codex adversarial (via the Codex plugin's `codex-companion.mjs adversarial-review`)
   - Claude opus bug scanner
   - Claude sonnet convention compliance
4. **Synthesis** — collect, deduplicate, validate against REVIEW.md skip list
5. **Output** — categorized table (critical/warning/nit/dismissed)

Tools that aren't installed are skipped gracefully. Claude agents always run.

### `/local-review`

Lightweight single-pass Claude review using local git diff. No external tools, no pre-flight checks. Good for quick feedback during development.

```bash
/local-review                   # review branch vs main (default)
/local-review --base develop    # review branch vs another base
/local-review --uncommitted     # review working tree
/local-review --commit abc123   # review a single commit
/local-review --range abc..def  # review a commit range
```

### REVIEW.md

Project-specific review rules at the repository root. Contains:

- **Always check** — rules every review must verify
- **Project-specific rules** — Python version and conventions
- **Skip** — known false positives and design decisions to suppress

The skip list encodes learnings from prior review rounds so the same dismissed findings are never re-flagged.

### Stop Hook

A pre-commit-style gate (`.claude/hooks/review-gate.sh`) runs `uv run ruff check`, `uv run ruff format --check`, and `uv run basedpyright` whenever Claude finishes work and the working tree has uncommitted or untracked changes. If any check fails, Claude is blocked from stopping until the issues are fixed. Configured in `.claude/settings.json` as a `Stop` hook.
