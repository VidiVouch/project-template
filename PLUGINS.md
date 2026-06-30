# Claude Code Plugins

Plugins are managed via `.claude/settings.json` under `enabledPlugins`.

## context7 - Documentation Retrieval

Provides up-to-date, version-specific library documentation. Activates automatically when working with libraries/frameworks.

- **Plugin**: `context7@claude-plugins-official`
- **Docs**: [context7.io](https://context7.io/docs)
- **Usage**: Activates automatically. Can also prompt: "use context7 to look up Django QuerySet API"

## codex - Delegate to OpenAI Codex

Delegate tasks, code reviews, and bug investigations to Codex from within Claude Code.

- **Plugin**: `codex@openai-codex`
- **Marketplace**: `openai/codex-plugin-cc` (GitHub)
- **Requires**: Codex CLI (`npm i -g @openai/codex` or `brew install codex`)
- **Key Commands**

  ```
  /codex:review                         # Code review via Codex
  /codex:adversarial-review             # Challenge-focused review
  /codex:rescue                         # Hand off task to Codex
  /codex:status                         # Check background job status
  /codex:setup                          # Verify Codex readiness
  ```

## astral - Ruff & UV Tools

Ruff and UV integration for linting, formatting, and package management.

- **Plugin**: `astral@astral-sh`
- **Marketplace**: `astral-sh/claude-code-plugins` (GitHub)
- **Key Commands**

  ```
  /astral:ruff                          # Linting and formatting guidance
  /astral:uv                            # Package management guidance
  ```

## vidi-skills - Vidi AI Development Skills

Shared Vidi workflow skills for AI-driven development, reviews, reports, and
attestation-oriented project work.

- **Plugin**: `vidi-skills@vidi`
- **Marketplace**: `VidiVouch/vidi-plugins` (GitHub)
- **Claude Code**: Enabled by default in `.claude/settings.json`
- **Codex**: Enabled by default in `.codex/config.toml` from the Git
  marketplace `https://github.com/VidiVouch/vidi-plugins.git`
