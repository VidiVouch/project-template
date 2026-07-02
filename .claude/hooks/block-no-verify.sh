#!/usr/bin/env bash
# PreToolUse guard (Bash matcher): deny git commit/push/merge invocations that
# skip hooks. Hooks and tests are the review gate: a failure gets fixed, not
# bypassed. Applies user-wide so no agent in any repo can slip past it.
#
# Two bypass families are blocked:
#   1. --no-verify / the -n commit shorthand (skips the hook explicitly).
#   2. `git -c core.hooksPath=<dir>` (or `--config-env=core.hooksPath=<var>`),
#      which redirects hook lookup away from .git/hooks so the pre-commit/
#      pre-push/pre-merge hook never fires: a silent equivalent of --no-verify.
#
# Deliberately NOT covered (documented, not oversights):
#   - Environment-assignment bypasses: `HUSKY=0 git commit`, a preset
#     `GIT_CONFIG_GLOBAL=/dev/null`, or `GIT_CONFIG_COUNT/GIT_CONFIG_KEY_n=
#     core.hooksPath` config injection. Blocking arbitrary env prefixes on a
#     single command line sanely isn't feasible here (they cross tokens and
#     have legitimate uses); env-assignment bypasses are out of scope.
#   - `--git-dir`/`GIT_DIR` retargeting: too broad to distinguish from
#     legitimate use, and it does not itself disable hooks.
#   - Stateful setup done in a PRIOR command (`git config core.hooksPath …`
#     then a later plain `commit`, editing .git/config, chmod -x .git/hooks/*).
#     This guard sees one command at a time; multi-step state is out of reach.
set -euo pipefail

cmd=$(jq -r '.tool_input.command // empty' 2>/dev/null) || exit 0
[ -z "$cmd" ] && exit 0

# Strip quoted strings so a commit MESSAGE mentioning --no-verify can't
# false-positive; the flags we care about are never quoted when effective.
# Newlines are folded first: sed is line-oriented, and a multi-line quoted
# message would otherwise leave its quotes unpaired per-line and unstripped.
cmd=$(printf '%s' "$cmd" | tr '\n' ' ' | sed -E "s/'[^']*'//g; s/\"[^\"]*\"//g")

deny() {
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Blocked: %s skips the git hooks (pre-commit checks/tests). Fix the failing check and commit normally. Never bypass verification."}}\n' "$1"
  exit 0
}

# The flag cluster that can sit between `git` and the subcommand. It matches a
# run of global options, INCLUDING the value-taking `-c <name>=<value>` / `-C
# <path>` in BOTH forms: space-separated (`-c core.x=y`) and attached
# (`-ccore.x=y`). Matching that value word is what stops an attacker from
# anchoring past the subcommand check by inserting a harmless `-c foo=bar`;
# without it, `git -c x=y commit --no-verify` (or the attached `git -cx=y
# commit …`, whose `.`/`=` chars the plain flag-word alt can't span) would sail
# through because the value is neither a flag nor the `commit` token. The
# attached alt can't over-consume the subcommand: it requires a leading `-`,
# which `commit`/`push`/`merge` never have.
CLUSTER='([[:space:]]+(-[cC][[:space:]]+[^[:space:]|;&]+|-[cC][^[:space:]|;&]+|-[-[:alnum:]=]+))*'

# core.hooksPath override on a hook-firing op: redirects hook lookup so the
# hook never runs. Git config names are case-insensitive (hence -i and the
# lowercase pattern). No legitimate commit/push/merge redirects its own hooks,
# so any `core.hooksPath=` assignment alongside those ops is denied. The `=`
# anchor also catches `--config-env=core.hooksPath=<var>` (env-indirected form).
if printf '%s' "$cmd" | grep -Eq '(^|[^[:alnum:]])git([[:space:]]|$)' \
   && printf '%s' "$cmd" | grep -Eqi 'core\.hookspath[[:space:]]*=' \
   && printf '%s' "$cmd" | grep -Eq '[[:space:]](commit|push|merge)([[:space:]]|$)'; then
  deny "core.hooksPath override (disables git hooks) on git commit/push/merge"
fi

# `git ... commit ...` with --no-verify or the -n shorthand (clustered or bare).
if printf '%s' "$cmd" | grep -Eq "git${CLUSTER}[[:space:]]+commit[^|;&]*[[:space:]](--no-verify|-[a-zA-Z]*n[a-zA-Z]*)([[:space:]]|\$)"; then
  # Allow -n-ish flags that are NOT no-verify shorthands (e.g. none for commit;
  # every -n cluster on commit means no-verify, so deny outright).
  deny "--no-verify/-n on git commit"
fi

# `git push/merge ... --no-verify` (push -n is dry-run, allowed).
if printf '%s' "$cmd" | grep -Eq "git${CLUSTER}[[:space:]]+(push|merge)[^|;&]*[[:space:]]--no-verify([[:space:]]|\$)"; then
  deny "--no-verify on git push/merge"
fi

exit 0
