#!/usr/bin/env python3
"""PreToolUse hook: nudge bare rustc/rustfmt/clippy-driver toward cargo.

This project standardises on cargo as the single entry point. The hook
intercepts Bash tool calls and denies direct compiler/tool invocations,
hinting the cargo equivalent. The command is split into top-level segments
so a bare binary anywhere in a chain (``ls && rustc x.rs``) is still caught;
each segment is classified by its *leading* command word, so
``cargo build`` passes.

Splitting is quote-aware: separators (``;``, ``&``, ``|``, newlines) inside
single- or double-quoted strings do not start a new segment. Segments whose
leading command is ``ssh`` are exempt entirely; their payload runs on a
remote host where this project's cargo convention does not apply.
"""

import json
import sys
from typing import Any

# Leading commands that run their arguments on a remote host, outside this
# project's environment. Cargo enforcement does not apply to their payload.
REMOTE_COMMANDS = frozenset({"ssh"})

# Quote characters that suppress segment splitting until they are closed.
_QUOTES = ("'", '"')

# Characters that separate top-level command segments (single ``&``/``|``
# cover ``&&``/``||`` too, the empty piece between them classifies to None).
_SEPARATORS = ";&|\n"

# Leading command word -> cargo hint. These are the direct compiler/formatter/
# linter binaries that should go through their cargo front-ends instead.
_SIMPLE_HINTS = {
    "rustc": "cargo build (or cargo check)",
    "rustfmt": "cargo fmt",
    "clippy-driver": "cargo clippy",
}


def split_segments(command: str) -> list[str]:
    """Split a command into top-level segments, respecting shell quoting."""
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


def classify_segment(segment: str) -> str | None:
    """Return the cargo hint for a single segment, or None if it is allowed.

    Only the leading command word is classified, so ``cargo build`` passes
    (leading word ``cargo``) and an ``ssh`` segment is exempt because its
    arguments execute remotely.
    """
    tokens = segment.split()
    if not tokens:
        return None
    head = tokens[0]
    if head in REMOTE_COMMANDS:
        return None
    return _SIMPLE_HINTS.get(head)


def evaluate(command: str) -> str | None:
    """Return the cargo replacement hint if the command should be denied, else None."""
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
