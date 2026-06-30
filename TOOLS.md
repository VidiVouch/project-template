# External Tools

Standalone tools installed system-wide that enhance the Claude Code experience.

## ccstatusline - Terminal Status Line

Customizable status line for Claude Code CLI showing model info, git branch, token usage, and other metrics.

- **Repo**: [sirmalloc/ccstatusline](https://github.com/sirmalloc/ccstatusline)
- **Run**: `npx -y ccstatusline@latest`

## peon-ping - Audio Notifications

Audio and visual notifications for AI coding agents. Alerts when tasks complete, need input, or encounter errors.

- **Repo**: [PeonPing/peon-ping](https://github.com/PeonPing/peon-ping)
- **Install**: `brew install PeonPing/tap/peon-ping`

## direnv - Per-directory environment (WSL on Windows)

Used on WSL-on-Windows to point `uv` at `.venv-wsl/` so it doesn't clash with the `.venv/` that Windows PowerShell creates in the same checkout (WSL expects `bin/python`, PowerShell creates `Scripts/python.exe`). The committed `.envrc` does the detection; you just need direnv installed and allowed. No-op on native macOS/Linux and on PowerShell.

- **Repo**: [direnv/direnv](https://github.com/direnv/direnv)
- **Install (inside WSL, e.g. Ubuntu)**: `sudo apt install direnv`
- **Hook into your shell** (add to `~/.bashrc` / `~/.zshrc`):
  - bash: `eval "$(direnv hook bash)"`
  - zsh: `eval "$(direnv hook zsh)"`
- **Activate in the repo**: `cd` into the repo and run `direnv allow` once.
