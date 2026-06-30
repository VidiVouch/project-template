"""Test harness for agent hook scripts.

Hooks live in two directories: ``.agents/hooks/`` for scripts shared
with other agent harnesses (Codex) and ``.claude/hooks/`` for Claude
Code-specific ones. Adds both to ``sys.path`` so tests can import each
hook by its module name and exercise its public functions directly. A
small ``invoke`` fixture also drives ``main()`` end-to-end via
monkeypatched stdin/stdout for integration-style checks.
"""

import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIRS = (REPO_ROOT / ".agents" / "hooks", REPO_ROOT / ".claude" / "hooks")

for hooks_dir in HOOKS_DIRS:
    if str(hooks_dir) not in sys.path:
        sys.path.insert(0, str(hooks_dir))


@pytest.fixture
def invoke(monkeypatch: pytest.MonkeyPatch):
    """Return a callable that drives a hook's ``main()`` end-to-end.

    Feeds the JSON payload through stdin, captures stdout, and returns
    ``(exit_code, parsed_decision_or_None)`` where ``None`` means the hook
    allowed the call (empty stdout).
    """

    def _invoke(module: Any, payload: dict[str, Any]) -> tuple[int, dict[str, Any] | None]:
        stdin = io.StringIO(json.dumps(payload))
        stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdin", stdin)
        monkeypatch.setattr(sys, "stdout", stdout)
        code = module.main()
        out = stdout.getvalue().strip()
        parsed = json.loads(out) if out else None
        return code, parsed

    return _invoke
