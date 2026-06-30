# AGENTS.md

## Project Maturity

Pre-production, no users. Prefer the best design over backwards compatibility. Destructive migrations are fine. Don't add compatibility shims.

## Tooling

- **Toolchain**: Rust **stable** (via rustup). Components `rustfmt` + `clippy` are required.
- **Build/run**: `cargo build`, `cargo run`.

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

- **Build**: `cargo build` (release: `cargo build --release`)
- **Tests**: `cargo test` (single test: `cargo test <name> -- --nocapture`)
- **Lint**: `cargo clippy --all-targets --all-features` (must be clean)
- **Format**: `cargo fmt` (check-only: `cargo fmt --check`)

## Code Standards

- Rustdoc doc comments (`///`) on public items; `#![forbid(unsafe_code)]` — any `unsafe` needs a `// SAFETY:` justification and a lint-allow.
- Lints live in `Cargo.toml` `[lints]` (strict: clippy pedantic/nursery on).
- Errors: prefer `?` and typed errors over `unwrap`/`panic` outside tests.

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
