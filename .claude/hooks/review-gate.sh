#!/usr/bin/env bash
# Stop hook: lightweight, toolchain-detecting review gate.
#
# When the working tree has uncommitted or untracked changes, runs the
# project's pre-flight CI gate and blocks the stop if it fails. Committed work
# is assumed to have already passed the pre-commit hooks and is not re-checked.
#
# The toolchain is detected at runtime from the project manifest, so a single
# copy of this hook works on every project regardless of language:
#
#   Cargo.toml     -> cargo fmt --check + cargo clippy
#   pyproject.toml -> uv run ruff check + ruff format --check + basedpyright
#   neither        -> no-op (exit 0)
#
# This is NOT the full /deep-review — it just ensures basic CI passes before
# Claude finishes. Run /deep-review manually for the full multi-tool review.

set -euo pipefail

# Drain stdin (the hook payload) so the writer never blocks. Everything this
# gate needs comes from the repo state and $CLAUDE_PROJECT_DIR, so no JSON
# parser (and thus no language runtime) is required here.
cat >/dev/null 2>&1 || true

ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
cd "$ROOT" 2>/dev/null || exit 0

# Only run inside a git repo.
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

# Gate only when there is something uncommitted/untracked to check. Untracked
# files matter: a fresh source file with errors would otherwise slip past,
# because `git diff HEAD` doesn't see it.
DIRTY=$(git diff --name-only HEAD 2>/dev/null || true)
STAGED=$(git diff --cached --name-only 2>/dev/null || true)
UNTRACKED=$(git ls-files --others --exclude-standard 2>/dev/null || true)
if [[ -z "$DIRTY" && -z "$STAGED" && -z "$UNTRACKED" ]]; then
    exit 0
fi

ERRORS=""
gate() { # gate "<label>" cmd...
    local label="$1"
    shift
    local out
    if ! out=$("$@" 2>&1); then
        ERRORS+="[$label]"$'\n'"$out"$'\n\n'
    fi
}

if [[ -f "$ROOT/Cargo.toml" ]]; then
    gate "cargo fmt" cargo fmt --all -- --check
    [[ -z "$ERRORS" ]] && gate "cargo clippy" cargo clippy --all-targets --all-features -- -D warnings
elif [[ -f "$ROOT/pyproject.toml" ]]; then
    gate "ruff check" uv run ruff check
    gate "ruff format" uv run ruff format --check
    # basedpyright is slow: only run if the fast checks passed.
    [[ -z "$ERRORS" ]] && gate "basedpyright" uv run basedpyright
else
    # No recognised toolchain: nothing to gate on.
    exit 0
fi

if [[ -n "$ERRORS" ]]; then
    REASON_TEXT="Pre-flight checks failed:"$'\n\n'"${ERRORS}"$'\n'"Fix before finishing."
    # JSON-escape the payload without a language runtime. jq is the common
    # path; fall back to a minimal static payload if jq isn't installed.
    if command -v jq >/dev/null 2>&1; then
        printf '{"decision":"block","reason":%s}\n' "$(printf '%s' "$REASON_TEXT" | jq -Rs .)"
    else
        printf '{"decision":"block","reason":"Pre-flight checks failed. Fix before finishing."}\n'
    fi
    exit 0
fi

# All checks passed.
exit 0
