#!/usr/bin/env bash
# Test suite for block-no-verify.sh. Feeds each case as a PreToolUse payload on
# stdin (exactly as Claude Code invokes the hook) and asserts the guard's
# decision: DENY cases must emit permissionDecision "deny"; ALLOW cases must
# emit nothing. Run:  bash block-no-verify.test.sh
set -uo pipefail

DIR=$(cd "$(dirname "$0")" && pwd)
GUARD="$DIR/block-no-verify.sh"
[ -x "$GUARD" ] || { echo "guard not executable: $GUARD" >&2; exit 2; }

pass=0 fail=0

# run <expect: deny|allow> <command>
run() {
  local expect=$1 cmd=$2 out got
  out=$(jq -n --arg c "$cmd" '{tool_input:{command:$c}}' | "$GUARD" 2>/dev/null)
  if printf '%s' "$out" | grep -q '"permissionDecision":"deny"'; then got=deny; else got=allow; fi
  if [ "$got" = "$expect" ]; then
    pass=$((pass+1))
  else
    fail=$((fail+1))
    printf 'FAIL [expected %s, got %s]: %s\n' "$expect" "$got" "$cmd" >&2
  fi
}

# ---- DENY: explicit --no-verify / -n bypass -------------------------------
run deny 'git commit -m "msg" --no-verify'
run deny 'git commit --no-verify -m "msg"'
run deny 'git commit -nm "msg"'                       # clustered -n
run deny 'git commit -am "msg" --no-verify'
run deny 'git push --no-verify'
run deny 'git push origin main --no-verify'
run deny 'git merge --no-verify feature'
run deny 'git -c user.name=x commit -m "y" --no-verify'  # -c inserted to slip the anchor (spaced)
run deny 'git -cuser.name=x commit --no-verify -m hi'    # attached -c form slips the anchor
run deny 'git -cuser.name=x push --no-verify'            # attached -c form on push
run deny 'git -cuser.name=x merge --no-verify feature'   # attached -c form on merge

# ---- DENY: core.hooksPath override (disables hooks) -----------------------
run deny 'git -c core.hooksPath=/dev/null commit -m "x"'
run deny 'git -c core.hooksPath= commit -m "x"'          # empty path
run deny 'git -c core.hookspath=/dev/null commit'        # lowercase key
run deny 'git -c CORE.HOOKSPATH=/dev/null commit'        # uppercase key
run deny 'git -c core.hooksPath="/dev/null" commit -m "x"'  # quoted value
run deny 'git --config-env=core.hooksPath=NOHOOKS commit -m "x"'  # env-indirected
run deny 'git -c core.hooksPath=/tmp/empty push'         # override on push
run deny 'git -c core.hooksPath=/tmp/empty merge feature'

# ---- ALLOW: normal, hook-respecting git ops -------------------------------
run allow 'git commit -m "msg"'
run allow 'git commit -am "fix the thing"'               # -am has no n
run allow 'git push origin main'
run allow 'git merge feature'
run allow 'git push -n'                                  # push -n is dry-run, allowed

# ---- ALLOW: false-positive guards ------------------------------------------
run allow 'git commit -m "do not use --no-verify here"'  # flag only in message
run allow 'git commit -m "disable core.hooksPath trick"' # hooksPath only in message
run allow 'echo "git commit --no-verify"'                # not a git commit at all
run allow 'git -c color.ui=always commit -m "x"'         # benign -c, not hooksPath/-n
run allow 'git -cuser.name=x commit -m hi'               # attached -c, no bypass flag
run allow 'git -c core.hooksPath=/dev/null log'          # hooksPath but non-hook op
run allow 'git -c core.hooksPath=x config --get merge.tool'  # merge.tool is not the merge op

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
