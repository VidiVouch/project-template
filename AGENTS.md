# AGENTS.md

## Project Maturity

Pre-production, no users. Prefer the best design over backwards compatibility.
Destructive migrations are fine. Don't add compatibility shims.

## Tooling

- **Package manager**: `uv`. Always use `uv run` to execute commands (e.g. `uv run ruff check`).
- **Virtual environment**: the default `.venv/` works on native macOS, Linux,
  and Windows PowerShell — no setup needed.
- **WSL-on-Windows only**: if the same checkout is also accessed from Windows
  PowerShell, `.venv/` can't be shared (WSL expects `bin/python`, PowerShell
  creates `Scripts/python.exe`). Install [direnv](https://direnv.net/) and
  run `direnv allow` in the repo — the committed `.envrc` sets
  `UV_PROJECT_ENVIRONMENT=.venv-wsl` when it detects WSL via `/proc/version`.
  No-op on native macOS/Linux.

## Skills layout

- Workflow skills (`deep-review`, `local-review`, `check-coverage`,
  `html-report`, the `codex-*` skills) are **not bundled in this repo** — they
  ship via the Vidi skills plugin (`vidi-skills@vidi`, see `PLUGINS.md`).
- If a repo-local skill is ever needed: shared (Claude + Codex) skills live in
  `.agents/skills/<name>/` with a per-skill symlink in `.claude/skills/<name>`
  (Codex does not scan `.claude/skills`); Claude-only skills are real
  directories in `.claude/skills/<name>/`. Keep shared skill bodies
  **portable**: no `` !` `` dynamic-context injection, no `@path` imports —
  those are Claude Code runtime features that Codex reads as literal text.

## Commands

- **Tests**: `uv run pytest` (`addopts` defaults to `-n auto --dist worksteal` (pytest-xdist) — pass `-n0` to disable parallelism for single-test debugging.

## Code Standards

- Google-style docstrings
- Linting: `uv run ruff check`
- Formatting: `uv run ruff format .`
- Type checking: `uv run basedpyright`

## Notes & docs

- **Author note docs as HTML, not Markdown.** Plans, reviews, research notes,
  interviews, design docs, and similar deliverables are written *directly* as
  formatted, self-contained HTML (embedded CSS, and `mermaid` for diagrams) —
  not Markdown that is later converted. They are meant to be *used*: layout,
  diagrams, and density matter, and since the agent both writes and edits them,
  Markdown's plain-text editability buys little. The known tradeoff is noisier
  git-diffs; accept it.
- **Stay Markdown** (do not convert): `REVIEW.md` (read by path and parsed by
  `/deep-review` and `/local-review`), the canonical project docs `AGENTS.md` /
  `CLAUDE.md` / `TOOLS.md` / `README.md` / `PLUGINS.md`, and the skill/command
  docs under `.agents/` and `.claude/`. Rule of thumb: human-facing deliverable
  → HTML; machine-parsed config, ledger, or agent instructions → Markdown.
