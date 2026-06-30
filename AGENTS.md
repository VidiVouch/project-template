# AGENTS.md

## Project Maturity

Pre-production, no users. Prefer the best design over backwards compatibility. Destructive migrations are fine. Don't add compatibility shims.

## Code Standards

- Keep changes small and well-scoped; document non-obvious intent.
- Language-specific tooling and standards are layered on top of this base by the per-language toolchain.

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
