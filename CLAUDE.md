<!--
This file is intentionally NOT a symlink to AGENTS.md.

Claude Code reads CLAUDE.md (not AGENTS.md), so we import AGENTS.md with @-syntax:
every agent reads the one shared instruction file, and Claude-specific guidance can
be appended below the import without forking the content. Edit shared rules in
AGENTS.md; add any Claude-only notes below the import (e.g. under a "## Claude Code"
heading). A symlink also works but needs Administrator/Developer Mode on Windows.
Docs: https://code.claude.com/docs/en/memory#agents-md
-->

@AGENTS.md

- Mechanics: gpt-5.5 is only reachable through the Codex CLI - `codex exec` / `codex review` (my ~/.codex/config.toml defaults to gpt-5.5). The codex-cli skill holds the shared invocation mechanics (targeting, JSONL parsing, timeouts, failure detection); the codex-review and codex-computer-use skills build on it. For work they don't cover (investigation, data analysis), run `codex exec -s read-only` directly with a self-contained prompt.
- Claude models (sonnet-5, opus-4.8, fable-5) run via the Agent/Workflow model parameter.

Using gpt-5.5 inside workflows and subagents (the model parameter only takes Claude models, so use a wrapper):
- Spawn a thin Claude wrapper agent with `model: 'sonnet', effort: 'Low'` whose prompt instructs it to write a self-contained codex prompt, run `codex exec` via Bash, and return the report (use `schema` on the wrapper to get structured output back).
- Always label these agents with a `gpt-5.5:` prefix, e.g. `{label: 'gpt-5.5:review-auth'}` - the workflow UI shows the wrapper's Claude model, so the label is the only indication the real worker is gpt-5.5.
- Codex runs can exceed Bash's 10-minute timeout: pass an explicit timeout, or run in the background and poll for the report file.
- Parallel gpt-5.5 implementation agents must use `isolation: 'worktree'` so codex edits don't collide in the shared checkout.
- Workflow token budgets only count Claude tokens; codex work is free and invisible to `budget. spent ()`.
