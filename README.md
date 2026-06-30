# Project Template (Rust)

A Rust project template with an integrated AI agent toolchain (Claude Code +
Codex + plugins), shared IDE settings, and orchestrated code review.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Development](#development)
  - [Building](#building)
  - [Code Quality](#code-quality)
  - [Testing](#testing)
- [Pre-commit Hooks](#pre-commit-hooks)
- [IDE Setup](#ide-setup)
- [Code Review](#code-review)

## Prerequisites

- **Rust** (stable) via [rustup](https://rustup.rs/), with the `rustfmt` and
  `clippy` components: `rustup component add rustfmt clippy`.

## Getting Started

```bash
# Clone the repository
git clone <repository-url>
cd <project-name>

# Build
cargo build

# Install pre-commit hooks
pre-commit install

# Enable rerere (reuse recorded resolution) — Git caches how you resolve a
# merge conflict and auto-applies the same resolution if it recurs.
git config rerere.enabled true
```

Open the project in your IDE — see [IDE Setup](#ide-setup) for configuration.

## Development

### Building

```bash
cargo build            # debug build
cargo build --release  # optimized build
cargo run              # build and run
```

### Code Quality

```bash
# Formatting
cargo fmt              # format in place
cargo fmt --check      # check only (CI/pre-commit)

# Linting
cargo clippy --all-targets --all-features -- -D warnings
```

Strict lints are configured in `Cargo.toml` under `[lints]` (clippy
pedantic/nursery enabled; `unsafe_code` forbidden).

### Testing

```bash
cargo test                          # run the suite
cargo test <name> -- --nocapture    # a single test, with output
```

## Pre-commit Hooks

Pre-commit hooks run automatically on `git commit`.

```bash
# Update hooks to latest versions
pre-commit autoupdate
```

This sets up:

- **pretty-format-json** — autoformats JSON, scoped via `files:` to
  `.claude/settings.json`, `.codex/*.json`, `.mcp.json`, and `.vscode/*.json`
- **cargo fmt** — `cargo fmt --all -- --check` (fails on unformatted code)
- **cargo clippy** — `cargo clippy --all-targets --all-features --locked -- -D warnings`

## IDE Setup

### RustRover / IntelliJ

The `.idea/` directory contains shared project settings. RustRover loads the
Cargo project automatically. To enable the shared spell-check dictionary:
**Settings → Editor → Natural Languages → Spelling**, add `project-words.dic`.

### VS Code

The `.vscode/` directory contains shared workspace settings. On first open,
install the recommended extensions when prompted (including
`rust-lang.rust-analyzer`). rust-analyzer is configured to run `clippy` on
check.

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
```

The pre-flight detects the project's toolchain from its manifest; for this
Rust project (`Cargo.toml`) it runs `cargo fmt` + `cargo clippy` before
spending review tokens. Tools that aren't installed are skipped gracefully;
Claude agents always run.

### `/local-review`

Lightweight single-pass Claude review using the local git diff. No external
tools, no pre-flight checks.

### REVIEW.md

Project-specific review rules at the repository root:

- **Always check** — rules every review must verify
- **Skip** — known false positives and design decisions to suppress

### Stop Hook

A gate (`.claude/hooks/review-gate.sh`) runs the project's lint/format gate —
detected at runtime from `Cargo.toml` (here: `cargo fmt --check` +
`cargo clippy`) — whenever Claude finishes work and the working tree has
uncommitted or untracked changes. If any check fails, Claude is blocked from
stopping until the issues are fixed.
