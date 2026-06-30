# Project Template

A language-agnostic project template with an integrated AI agent toolchain
(Claude Code + Codex + plugins), shared IDE settings, and orchestrated code
review. Add a language toolchain layer (Python, Rust, …) on top of this base.

## Table of Contents

- [Getting Started](#getting-started)
- [Pre-commit Hooks](#pre-commit-hooks)
- [IDE Setup](#ide-setup)
- [Code Review](#code-review)

## Getting Started

```bash
# Clone the repository
git clone <repository-url>
cd <project-name>

# Install pre-commit hooks
pre-commit install

# Enable rerere (reuse recorded resolution) — Git caches how you resolve a
# merge conflict and auto-applies the same resolution if it recurs. Useful
# for workflows where the same conflicts recur on cascade rebases.
git config rerere.enabled true
```

Open the project in your IDE — see [IDE Setup](#ide-setup) for configuration.

## Pre-commit Hooks

Pre-commit hooks run automatically on `git commit`.

```bash
# Update hooks to latest versions
pre-commit autoupdate
```

This base sets up:

- **pretty-format-json** — autoformats JSON, scoped via `files:` to
  `.claude/settings.json`, `.codex/*.json`, `.mcp.json`, and `.vscode/*.json`
  only (not every JSON in the tree)

Language-specific hooks (lint, format, type-check, lockfile) are added by the
per-language toolchain layer.

## IDE Setup

### PyCharm / IntelliJ

The `.idea/` directory contains shared project settings. To enable the shared
spell-check dictionary: **Settings → Editor → Natural Languages → Spelling**,
add `project-words.dic` as a custom dictionary.

### VS Code

The `.vscode/` directory contains shared workspace settings. On first open,
install the recommended extensions when prompted.

## Code Review

Orchestrated multi-tool code review via Claude Code commands. Reviews combine
findings from Codex and Claude agents, then synthesize into a
single deduplicated report.

### `/deep-review`

Runs pre-flight CI checks, launches up to 4 parallel reviewers, then
synthesises findings with REVIEW.md-aware false-positive filtering.

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

The pre-flight detects the project's toolchain from its manifest
(`Cargo.toml` → cargo fmt + clippy; `pyproject.toml` → uv + ruff +
basedpyright) and runs that gate before spending review tokens. Tools that
aren't installed are skipped gracefully; Claude agents always run.

### `/local-review`

Lightweight single-pass Claude review using the local git diff. No external
tools, no pre-flight checks. Good for quick feedback during development.

```bash
/local-review                   # review branch vs main (default)
/local-review --base develop    # review branch vs another base
/local-review --uncommitted     # review working tree
/local-review --commit abc123   # review a single commit
/local-review --range abc..def  # review a commit range
```

### REVIEW.md

Project-specific review rules at the repository root:

- **Always check** — rules every review must verify
- **Skip** — known false positives and design decisions to suppress

The skip list encodes learnings from prior review rounds so the same dismissed
findings are never re-flagged.

### Stop Hook

A gate (`.claude/hooks/review-gate.sh`) runs the project's lint/format/type
gate — detected at runtime from `Cargo.toml` or `pyproject.toml` — whenever
Claude finishes work and the working tree has uncommitted or untracked
changes. If any check fails, Claude is blocked from stopping until the issues
are fixed. Configured in `.claude/settings.json` as a `Stop` hook.
