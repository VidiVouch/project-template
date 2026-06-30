#!/usr/bin/env python3
"""PreToolUse hook: deny bare ``python``/``pip``/``pytest`` invocations.

This project standardises on ``uv`` (see CLAUDE.md). The hook intercepts
Bash tool calls and replaces them with a deny + a hint at the right uv
equivalent. The command is split into top-level segments so a bare binary
anywhere in a chain (``ls && pytest``) is still caught; each segment is then
classified by its *leading* command word, so ``uv run python`` passes.

Before a segment's head is read, leading noise is normalised away so it can
not hide the real binary: ``NAME=value`` env-assignments (``FOO=bar pytest``)
are stripped, and a small allowlist of transparent wrappers — ``env``,
``command``, ``time``, ``xargs``, ``nohup``, ``exec`` — is unwrapped
repeatedly (``time xargs python`` → ``python``). ``env``'s own inline
``NAME=value`` arguments are skipped too.

Splitting is quote-aware: separators (``;``, ``&``, ``|``, newlines) inside
single- or double-quoted strings do not start a new segment. This matters
for remote commands — ``ssh host 'a; python b'`` is a single ``ssh`` segment,
not a local ``python`` call — and segments whose leading command is ``ssh``
are exempt entirely, since their payload runs on the remote host where this
project's uv convention does not apply.

Accepted limitations (documented, not fixed — they need real tokenisation
rather than a whitespace/quote split, and are asserted as-is by the tests):
command substitution ``$(python ...)``, subshells ``(python ...)``, and brace
groups ``{ python ...; }`` are *not* classified, so a bare binary nested only
inside one of those constructs is allowed through.

The ``__future__`` import is load-bearing: hooks run under whatever
``python3`` is on PATH (macOS system 3.9 here), where PEP 604 ``X | Y``
annotations raise TypeError at definition time unless kept lazy.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

# Leading commands that run their arguments on a remote host, outside this
# project's environment — uv enforcement does not apply to their payload.
REMOTE_COMMANDS = frozenset({"ssh"})

# Quote characters that suppress segment splitting until they are closed.
_QUOTES = ("'", '"')

# Characters that separate top-level command segments (single ``&``/``|``
# cover ``&&``/``||`` too — the empty piece between them classifies to None).
_SEPARATORS = ";&|\n"

# Matches a leading ``NAME=value`` shell env-assignment token so it can be
# stripped before the real head command is read (``FOO=bar pytest`` → ``pytest``).
_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# Transparent wrappers whose first non-option argument is the command that
# actually runs. Unwrapped repeatedly so ``time xargs python`` resolves to
# ``python``. ``env`` additionally takes inline ``NAME=value`` arguments, which
# are skipped by the same env-assignment strip that runs each iteration.
_WRAPPERS = frozenset({"env", "command", "time", "xargs", "nohup", "exec"})

# Leading command word → uv hint, for binaries with no sub-command nuance.
# ``pip`` is handled separately because its first argument selects the hint.
_SIMPLE_HINTS = {"python": "uv run python", "python3": "uv run python", "pytest": "uv run pytest"}

# ``pip``/``pip3`` first argument → the more actionable uv hint; anything else
# (``list``, ``show``, ``freeze``, …) falls back to the generic ``uv pip``.
_PIP_SUBCOMMAND_HINTS = {"install": "uv add", "uninstall": "uv remove"}


def split_segments(command: str) -> list[str]:
    """Split a command into top-level segments, respecting shell quoting.

    Separators (``;``, ``&``, ``|``, newline) split the command, but only when
    they appear outside single- or double-quoted strings. Quote tracking is
    deliberately simple — it does not model backslash escapes or ``$()`` —
    which is enough to classify the leading command of each segment.
    """
    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    for ch in command:
        if quote is not None:
            current.append(ch)
            if ch == quote:
                quote = None
        elif ch in _QUOTES:
            quote = ch
            current.append(ch)
        elif ch in _SEPARATORS:
            segments.append("".join(current))
            current = []
        else:
            current.append(ch)
    segments.append("".join(current))
    return segments


def _normalize_head(tokens: list[str]) -> list[str]:
    """Drop leading env-assignments and transparent wrappers from ``tokens``.

    Returns the tokens starting at the real head command, so a bare binary can
    not be hidden behind ``PYTHONPATH=. python`` or ``time xargs python``. The
    two rules are applied in a loop until the head stabilises: a leading
    ``NAME=value`` token is stripped, and a leading wrapper word (``env``,
    ``command``, ``time``, ``xargs``, ``nohup``, ``exec``) is unwrapped.
    """
    remaining = list(tokens)
    while remaining:
        if _ENV_ASSIGNMENT.match(remaining[0]):
            remaining.pop(0)
            continue
        if remaining[0] in _WRAPPERS:
            remaining.pop(0)
            continue
        break
    return remaining


def classify_segment(segment: str) -> str | None:
    """Return the uv hint for a single segment, or None if it is allowed.

    Only the leading command word is classified, so ``uv run python`` passes
    (leading word ``uv``) and an ``ssh`` segment is exempt because its
    arguments execute remotely. Leading env-assignments and transparent
    wrappers are normalised away first (see :func:`_normalize_head`).
    ``pip install``/``pip uninstall`` get the more actionable
    ``uv add``/``uv remove`` hint before the generic ``uv pip``.
    """
    tokens = _normalize_head(segment.split())
    if not tokens:
        return None
    head = tokens[0]
    if head in REMOTE_COMMANDS:
        return None
    if head in ("pip", "pip3"):
        sub = tokens[1] if len(tokens) > 1 else ""
        return _PIP_SUBCOMMAND_HINTS.get(sub, "uv pip")
    return _SIMPLE_HINTS.get(head)


def evaluate(command: str) -> str | None:
    """Return the uv replacement hint if the command should be denied, else None."""
    for segment in split_segments(command):
        hint = classify_segment(segment)
        if hint is not None:
            return hint
    return None


def build_deny_decision(hint: str, command: str) -> dict[str, Any]:
    """Build the PreToolUse JSON payload that denies the tool call."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"Use `{hint}` instead. Blocked: {command}",
        }
    }


def main() -> int:
    """Read the Bash tool_use payload from stdin and emit a decision on stdout."""
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0

    command = (payload.get("tool_input") or {}).get("command") or ""
    hint = evaluate(command)
    if hint is not None:
        json.dump(build_deny_decision(hint, command), sys.stdout)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
