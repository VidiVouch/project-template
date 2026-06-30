---
description: Orchestrated multi-tool code review with pre-flight CI checks
argument-hint: "[ --base <branch> ] [ --uncommitted ] [ --commit <sha> ] [ --range <a>..<b> ] [ --nofix ] [ --skip-preflight ] [ --focus <text> ] [ --force ]"
allowed-tools: Bash(uv run *), Bash(uv lock *), Bash(cargo *), Bash(git diff *), Bash(git log *), Bash(git ls-files *), Bash(git checkout *), Bash(git symbolic-ref *), Bash(git rev-parse *), Bash(git hash-object *), Bash(shasum *), Bash(mkdir *), Bash(echo *), Bash(ls *), Bash(printf *), Bash(sort *), Bash(tail *), Bash(cut *), Bash(tr *), Bash(command *), Bash(codex *), Bash(cubic *), Bash(node *), Agent, Read, Glob, Grep, TaskCreate, TaskUpdate, TaskList
---

# Deep Review

Multi-tool orchestrated code review that runs pre-flight CI checks, launches parallel reviews from Codex, Cubic, and Claude, then synthesises findings into a single categorised report.

## Arguments

Parse the user's args (`$ARGUMENTS`) for:

- `--base <branch>` — base branch to compare against (default: `main`)
- `--uncommitted` — review uncommitted changes (staged + unstaged) instead of branch diff
- `--commit <sha>` — review a single commit
- `--range <from>..<to>` — review a range of commits (e.g. `abc123..def456`)
- `--nofix` — opt out of auto-fixing pre-flight failures (default is to fix)
- `--skip-preflight` — skip Phase 0 CI checks (use when you know they pass)
- `--focus <text>` — pass focus text to the adversarial review
- `--force` — run even if diff is unchanged since last review

If no args are provided, default to `--base main`.

**Diff modes** — the diff command adapts based on which flag is passed:

| Flag                    | Git diff command            | Codex args             | Cubic args             |
|-------------------------|-----------------------------|------------------------|------------------------|
| `--base main` (default) | `git diff main...HEAD`      | `--base main`          | `--base main`          |
| `--uncommitted`         | `git diff HEAD`             | `--scope working-tree` | (none — default scope) |
| `--commit abc123`       | `git diff abc123^..abc123`  | `--commit abc123`      | `--commit abc123`      |
| `--range abc..def`      | `git diff abc..def`         | `--base abc`           | `--base abc`           |

In `--uncommitted` mode, `git diff HEAD` alone does **not** see untracked files. Phase -1 mixes per-file content hashes (via `git hash-object`) into the dedup hash so both new untracked files AND in-place edits of existing untracked files invalidate the cache, and Agents D/E additionally fetch untracked file contents via `git ls-files --others --exclude-standard` before reviewing. The table entry above captures only the tracked-changes portion of the payload. Cubic's default uncommitted scope DOES include untracked files natively (verified v1.7.0), so Agent F needs no equivalent workaround.

The diff hash, pre-flight checks, and agent prompts all adapt to the selected mode.

## Phase -1: Diff-hash deduplication

Before doing any work, check if the diff has changed since the last review:

```bash
mkdir -p .review-cache
# Compute diff hash using the appropriate diff command for the selected mode
DIFF_PAYLOAD="$(<diff command from table above>)"
# In --uncommitted mode, git diff HEAD does NOT see untracked files, so a
# diff containing only new untracked files would produce the same hash as
# the previous review and incorrectly hit the "no changes" skip path. Mix
# per-file content hashes (via git hash-object) into the payload so both
# new files AND in-place edits of existing untracked files change the hash.
# Filename-only metadata would miss in-place edits entirely.
if [ "$MODE" = "uncommitted" ]; then
    UNTRACKED_META=$(git ls-files --others --exclude-standard | sort | while IFS= read -r f; do
        printf '%s %s\n' "$(git hash-object -- "$f")" "$f"
    done)
    DIFF_PAYLOAD="$DIFF_PAYLOAD"$'\n'"UNTRACKED:"$'\n'"$UNTRACKED_META"
fi
DIFF_HASH=$(printf '%s' "$DIFF_PAYLOAD" | shasum -a 256 | cut -d' ' -f1)
# Sanitise the mode identifier for use as cache filename
CACHE_KEY=$(echo "<mode identifier>" | tr '/' '_' | tr '.' '_')
CACHE_FILE=".review-cache/${CACHE_KEY}.hash"
```

Cache key examples: `main`, `uncommitted`, `commit_abc123`, `range_abc_def`.

If the cache file exists and contains the same hash, and `--force` was not passed:

- Tell the user: "No changes since last review (hash: `<short-hash>`). Use --force to re-review."
- Stop.

Otherwise, continue. At the end of a successful review (Phase 4), write the hash:

```bash
echo "$DIFF_HASH" > "$CACHE_FILE"
```

## Phase 0: Pre-flight CI checks

Before spending tokens on reviews, verify the code passes the same checks as CI.

Detect the project's toolchain from its manifest and run that gate (skip this
phase entirely if neither manifest is present):

- **Rust** — `Cargo.toml` present → `cargo fmt` + `cargo clippy`
- **Python** — `pyproject.toml` present → `uv` + `ruff` + `basedpyright`

**Default (auto-fix) — `--nofix` NOT passed.** Run the fixing variants
sequentially. They're no-ops when there's nothing to fix; when there IS
something to fix, they fix it in place. The lint/type gate (clippy /
basedpyright) has limited or no auto-fix, so it's the gate that can still stop
the run. Stop at the first failure.

```bash
# Rust
cargo fmt --all
cargo clippy --all-targets --all-features -- -D warnings

# Python
uv lock
uv run ruff check --fix
uv run ruff format .
uv run basedpyright
```

If the lint/type gate fails, report the errors and stop — type errors need
manual intervention.

**Working-tree side effects.** These commands write to disk in place. For
Python, `uv lock` may rewrite `uv.lock`, and `ruff check --fix` / `ruff format
.` rewrite any `.py`/`.pyi` files (and configured notebooks) that aren't clean;
for Rust, `cargo fmt` rewrites unformatted sources. The reviewers in Phases 2-3
see the post-fix tree, so any auto-fixes will appear in their diff alongside the
user's own changes. If you want reviewers to see only the user's changes, pass
`--nofix` or commit before running.

**`--nofix` passed.** Run the check-only variants. Stop at the first failure
and tell the user to fix them manually (or drop `--nofix` to let the command
auto-fix next run).

```bash
# Rust
cargo fmt --all -- --check
cargo clippy --all-targets --all-features --locked -- -D warnings

# Python
uv lock --check
uv run ruff check
uv run ruff format --check
uv run basedpyright
```

**If all checks pass**, proceed to Phase 1.

## Phase 1: Read review context

Before launching reviews, gather context:

1. Read `REVIEW.md` from the repository root (if it exists)
2. Run a stat/log summary appropriate to the selected mode:
  - `--base <branch>`: `git diff <base>...HEAD --stat` and `git log --oneline <base>..HEAD`
  - `--uncommitted`: `git diff HEAD --stat` and `git diff --cached --stat` (no log — no commits)
  - `--commit <sha>`: `git diff <sha>^..<sha> --stat` and `git log --oneline <sha>^..<sha>`
  - `--range <a>..<b>`: `git diff <a>..<b> --stat` and `git log --oneline <a>..<b>`

Store this context — you will need it for Phase 3 synthesis.

## Phase 2: Launch parallel reviews

Before launching, check which external tools are available.

* Agent B (Codex standard) uses `codex exec review` with diff targeting via `--base` / `--commit` / `--uncommitted`, so it only needs the `codex` CLI.
* Agent C (Codex adversarial) uses the codex-companion script from the installed Codex plugin because the companion owns the adversarial prompt template — without the companion script, skip Agent C.
* Agent F (Cubic) needs the `cubic` CLI (`npm i -g @cubic-dev-ai/cli`; auth lives in `~/.local/share/cubic/auth.json`).

```bash
command -v codex >/dev/null && echo "CODEX=yes" || echo "CODEX=no"
command -v cubic >/dev/null && echo "CUBIC=yes" || echo "CUBIC=no"
CODEX_COMPANION=$(ls "$HOME/.claude/plugins/cache/openai-codex/codex/"*/scripts/codex-companion.mjs 2>/dev/null | sort -V | tail -1)
if [ -n "$CODEX_COMPANION" ]; then
  echo "CODEX_COMPANION=$CODEX_COMPANION"
  echo "CODEX_ADVERSARIAL=yes"
else
  echo "CODEX_ADVERSARIAL=no"
fi
# Resolve once so each agent can pass --cwd $REPO_ROOT (or -C $REPO_ROOT) to
# codex / codex-companion. The Bash tool spawns a fresh shell per
# call, so `cd` from a previous call doesn't persist — without explicit
# targeting, a worktree-spawned review can silently scan the main repo.
REPO_ROOT=$(git rev-parse --show-toplevel)
echo "REPO_ROOT=$REPO_ROOT"
```

Capture `CODEX_COMPANION` for Agent C; the `sort -V | tail -1` glob picks the highest installed plugin version so this survives plugin updates without hardcoding. Capture `REPO_ROOT` and thread it through every external tool (see per-agent invocations below). Agent B uses `codex exec review` which has the native review prompt baked into the binary — no external prompt file needed.

Launch all **available** tools in parallel as background agents. If a tool is missing, skip it and note which tools were used in the final output. Agents D and E (Claude) always run.

**IMPORTANT**: In non-range modes every reviewer must be a background Agent (`run_in_background: true`) so all 5 run in parallel. Each external-tool agent (Codex, Cubic) runs its command via `Bash` inside the subagent and returns the raw structured output verbatim — do NOT try to invoke `/codex:review` or `/codex:adversarial-review` as Skills. The codex review slash commands are marked `disable-model-invocation: true` in their plugin frontmatter and can't be reached via the Skill tool. Likewise do NOT reach for the `mcp__cubic__*` MCP tools for Agent F — they trigger and read cubic's cloud reviews of GitHub PRs, not local diffs. All three external tools expose structured output via direct CLI flags — use those.

Launch all 5 in a single message with multiple Agent tool calls.

**Exception for `--range <a>..<b>` mode**: Agents B, C, and F each do a `git checkout <b>` as part of their checkout dance before invoking their tool, then restore the original branch. Concurrent `git checkout` operations in the same working tree race against each other — one agent's post-review checkout can flip the tree mid-run for another agent, producing nondeterministic or wrong findings. So in range mode: launch Agents D and E (Claude bug scanner + convention compliance) in parallel as usual, but run Agents B, C, and F **sequentially** — wait for each to complete its full checkout-review-restore cycle before starting the next. For all other modes (`--base`, `--uncommitted`, `--commit`) there's no checkout dance, and all 5 agents should launch in parallel as before.

### Agent B: Codex standard review (skip if `codex` CLI not installed)

Launch a background general-purpose Agent with prompt:

> Run Codex's native reviewer via `codex exec review --json`. This uses the built-in review prompt (embedded in the codex binary at `codex-rs/core/review_prompt.md`) and lets Codex introspect the diff itself — DO NOT embed the diff inline in a prompt, DO NOT use `--output-schema` (that's for `codex exec`, not `codex exec review`, and passing a prompt alongside `--base` is mutually exclusive).
>
> The `--json` flag emits a JSONL event stream on stdout. The actual review payload arrives as one `item.completed` event of type `exitedReviewMode` whose `review` field carries the same prose Codex would have written to `-o <FILE>`. Capturing JSONL (vs. `-o`) lets Phase 3 reliably locate the review payload and ignore surrounding chatter, plus surfaces explicit error events when present.
>
> **Worktree targeting:** always pass `-C "<REPO_ROOT>"` to `codex exec` (positioned BEFORE the `review` subcommand — it's an `exec`-level flag). Without this, `codex` resolves the repo from `process.cwd()`, which is whatever shell context the Bash tool happened to be in and is NOT guaranteed to match the worktree under review.
>
> - `--base main` mode (default): `codex exec -C "<REPO_ROOT>" review --json --base <base>`
> - `--uncommitted` mode: `codex exec -C "<REPO_ROOT>" review --json --uncommitted`
> - `--commit <sha>` mode: `codex exec -C "<REPO_ROOT>" review --json --commit <sha>`
> - `--range <a>..<b>` mode: Codex's `--base` reviews from the given commit up to HEAD. To target the `a..b` window precisely, temporarily check out `b` first, then use `--base <a>`. Chain in one Bash call: `cd "<REPO_ROOT>" && ORIG=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || git rev-parse --verify HEAD) && git checkout <b> && codex exec -C "<REPO_ROOT>" review --json --base <a>; git checkout "$ORIG"`. (Plain `symbolic-ref` exits 1 when HEAD is already detached, which would leave the tree stranded on `<b>`.)
>
> Return the raw JSONL stdout verbatim. Phase 3 will scan for the `exitedReviewMode` event, extract the `review` field, and regex-parse the prose findings out of it.
>
> The review payload itself is prose in this format:
> ```
> - [P1] <Imperative title> — <absolute file path>:<line_start>-<line_end>
>   <One-paragraph explanation of why this is a problem>
> ```
> followed by an "overall correctness" verdict sentence. The `review` subcommand has no schema-constraining option, so the prose shape is what we get.
>
> Note that the native reviewer is non-deterministic — two runs on the same diff may produce different findings.

If the `codex` CLI is not installed, skip this agent entirely.

### Agent C: Codex adversarial review (skip if `CODEX_ADVERSARIAL=no`)

Launch a background general-purpose Agent with prompt:

> Run the codex companion script with the `adversarial-review` subcommand. This path templates the plugin's adversarial prompt from `prompts/adversarial-review.md` (skeptical framing, strict grounding rules, JSON-schema output) and hands it to codex via the app-server with an outputSchema attached, returning a structured payload with `result.parsed.findings`. Use the `CODEX_COMPANION` path resolved in the Phase 2 preamble.
>
> **Worktree targeting:** pass `--cwd "<REPO_ROOT>"` (or `-C "<REPO_ROOT>"`) to the companion on every invocation. Its `resolveCommandCwd` falls back to `process.cwd()` when `--cwd` is absent, and the Bash tool's cwd is unreliable across calls — so a bare invocation from a worktree can silently retarget the MAIN repo and review the wrong diff.
>
> - `--base main` mode (default): `node "$CODEX_COMPANION" adversarial-review --cwd "<REPO_ROOT>" --json --base <base> <focus>`
> - `--uncommitted` mode: `node "$CODEX_COMPANION" adversarial-review --cwd "<REPO_ROOT>" --json --scope working-tree <focus>`
> - `--commit <sha>` mode: `node "$CODEX_COMPANION" adversarial-review --cwd "<REPO_ROOT>" --json --commit <sha> <focus>`
> - `--range <a>..<b>` mode: the companion's `--base` flag reviews from that commit to HEAD, not to a specific upper bound. Perform the checkout dance inside the target worktree in a single chained Bash call: `cd "<REPO_ROOT>" && ORIG=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || git rev-parse --verify HEAD) && git checkout <b> && node "$CODEX_COMPANION" adversarial-review --cwd "<REPO_ROOT>" --json --base <a> <focus>; git checkout "$ORIG"`.
>
> Include `<focus>` text only if `--focus` was provided; omit otherwise. Return the raw JSON stdout verbatim — the companion's envelope with `result.parsed.findings` carrying the structured findings.
>
> **Post-run sanity check:** before returning, verify `.context.repoRoot` in the returned JSON matches `<REPO_ROOT>`. If it does NOT match, the review targeted the wrong repo — re-run with `--cwd` explicitly set (not relying on shell cwd) and flag the mismatch in the returned output so the orchestrator can discard the bogus findings.

Skip this agent entirely if the Phase 2 preamble reported `CODEX_ADVERSARIAL=no` — that covers both "`codex` CLI missing" and "codex CLI present but companion script missing", since Agent C needs both. Do NOT fall back to invoking the companion with an empty `CODEX_COMPANION` — that expands to `node "" adversarial-review ...` and fails noisily.

### Agent D: Claude bug scanner (opus)

Launch a general-purpose Agent with `model: "opus"` for deep reasoning:

> Fetch the diff for the selected mode:
> - `--base <branch>`: `git diff <base>...HEAD`
> - `--uncommitted`: `git diff HEAD` to get tracked uncommitted changes, then `git ls-files --others --exclude-standard` and `Read` each untracked file's full contents (`git diff HEAD` does NOT see untracked files — a newly created file would otherwise be invisible to the review).
> - `--commit <sha>`: `git diff <sha>^..<sha>`
> - `--range <a>..<b>`: `git diff <a>..<b>`
>
> Read REVIEW.md at the repository root for project-specific rules and known false positives.
>
> Review the diff. Focus exclusively on:
> 1. Code that will fail at runtime (missing imports, wrong signatures, type errors)
> 2. Logic errors that produce wrong results regardless of input
> 3. Resource leaks (unclosed files, connections, missing finally blocks)
> 4. Exception handling gaps (bare except, swallowed errors, missing re-raise)
>
> Do NOT flag anything in the REVIEW.md "Skip" section. Do NOT flag style issues, missing docstrings, or potential issues that depend on specific inputs.
>
> Return findings as a JSON array — nothing else. No markdown fence, no prose wrapper, no preamble. Each finding must have these fields:
>
> - `file` (string): path relative to repo root
> - `line_start` (int): first affected line number
> - `line_end` (int): last affected line number (equal to `line_start` for single-line findings)
> - `severity` (one of `"critical"`, `"warning"`, `"nit"`)
> - `description` (string): what's wrong, grounded in the diff
> - `recommendation` (string): the concrete fix
>
> Return `[]` (empty array) if nothing is found. Output ONLY the JSON array — do not add commentary before or after it.

### Agent E: Claude convention compliance (sonnet)

Launch a general-purpose Agent with `model: "sonnet"` for pattern matching:

> Fetch the diff for the selected mode:
> - `--base <branch>`: `git diff <base>...HEAD`
> - `--uncommitted`: `git diff HEAD` to get tracked uncommitted changes, then `git ls-files --others --exclude-standard` and `Read` each untracked file's full contents (`git diff HEAD` does NOT see untracked files — a newly created file would otherwise be invisible to the review).
> - `--commit <sha>`: `git diff <sha>^..<sha>`
> - `--range <a>..<b>`: `git diff <a>..<b>`
>
> Read both CLAUDE.md and REVIEW.md at the repository root.
>
> Review the diff for compliance with CLAUDE.md and REVIEW.md rules. Check:
> 1. New code follows conventions documented in CLAUDE.md
> 2. REVIEW.md "Always check" rules are satisfied
> 3. No REVIEW.md "Skip" items are being violated
> 4. Dependencies are properly declared in the project manifest (pyproject.toml / Cargo.toml)
> 5. Lint suppressions (ruff per-file-ignores / clippy allows) are justified
>
> Return violations as a JSON array — nothing else. No markdown fence, no prose wrapper, no preamble. Each violation must have these fields:
>
> - `file` (string): path relative to repo root
> - `line_start` (int): first affected line number
> - `line_end` (int): last affected line number
> - `severity` (one of `"critical"`, `"warning"`, `"nit"`)
> - `rule` (string): the specific CLAUDE.md or REVIEW.md rule violated, quoted verbatim
> - `description` (string): why the code violates the rule
>
> Return `[]` (empty array) if nothing is found. Output ONLY the JSON array — do not add commentary before or after it.

### Agent F: Cubic review (skip if not installed)

Launch a background general-purpose Agent with prompt:

> Run `cubic review --json` with the appropriate diff scope. The `--json` flag emits a single JSON object `{"issues": [...]}` on stdout instead of the interactive TUI.
>
> **Worktree targeting:** cubic has no review-scoped directory flag — the top-level `--dir` belongs to the TUI server command, and `cubic review --dir` just prints the help text and exits 1 (observed v1.7.0). Always chain `cd "<REPO_ROOT>" && ...` in a single Bash call (the Bash tool spawns a fresh shell per call, so a prior `cd` doesn't persist). Prefix every invocation with `CUBIC_DISABLE_AUTOUPDATE=1` so the CLI can't self-update mid-run (cubic's own CI guidance).
>
> **Bad-ref guard:** cubic silently returns `{"issues": []}` with exit 0 when given an unresolvable `--base`/`--commit` ref (observed v1.7.0) — indistinguishable from a clean pass. In `--base`/`--commit`/`--range` modes, validate each ref first with `git rev-parse --verify "<ref>^{commit}"`; if validation fails, return an error note instead of running cubic, so a typo'd ref can't masquerade as a clean review.
>
> - `--base main` mode (default): `cd "<REPO_ROOT>" && CUBIC_DISABLE_AUTOUPDATE=1 cubic review --json --base <base>`
> - `--uncommitted` mode: `cd "<REPO_ROOT>" && CUBIC_DISABLE_AUTOUPDATE=1 cubic review --json` — uncommitted changes are cubic's default scope when no targeting flag is passed, and that scope includes untracked files natively (no extra fetch needed).
> - `--commit <sha>` mode: `cd "<REPO_ROOT>" && CUBIC_DISABLE_AUTOUPDATE=1 cubic review --json --commit <sha>`
> - `--range <a>..<b>` mode: cubic's `--base` reviews from the given ref up to the current tree, so use the same checkout dance as Agents B/C in one chained Bash call: `cd "<REPO_ROOT>" && ORIG=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || git rev-parse --verify HEAD) && git checkout <b> && CUBIC_DISABLE_AUTOUPDATE=1 cubic review --json --base <a>; git checkout "$ORIG"`.
>
> If `--focus` was provided, append `--prompt "<focus text>"` in `--base`, `--uncommitted`, and `--range` modes — per `cubic review --help` (v1.7.0), `--prompt` can be used alone or combined with `--base`. Omit it in `--commit` mode; the help text does not promise `--prompt` combines with `--commit`.
>
> Return the raw JSON stdout verbatim plus the command's exit code — do not parse, summarise, or reformat. **Exit 1 with valid JSON on stdout means "issues found", not failure** — cubic uses CI-gate exit semantics (0 = clean, 1 = findings; verified v1.7.0). Phase 3 extracts the structured fields.

If the `cubic` CLI is not installed, skip this agent entirely.

## Phase 3: Synthesise findings

Once all agents complete, you (the orchestrator) synthesise the results. This is the most important phase — it is where human-level judgment is applied.

All five agents now return structured data. Normalise every finding into a common shape before doing anything else:

```
{
  "source":         str,   # "codex-review" | "codex-adversarial"
                           # | "cubic" | "claude-bugs" | "claude-conventions"
  "file":           str,   # path relative to repo root, normalised
  "line_start":     int,
  "line_end":       int,
  "severity":       str,   # original severity from the tool
  "description":    str,   # what's wrong
  "recommendation": str,   # concrete fix
  "raw":            obj,   # original tool output, kept for reference
}
```

### Step 3a: Parse each agent's structured output

Each agent returns a different shape. Parse them all into the common form.

**Codex native review (Agent B, via `codex exec review --json`)**: the agent returns the raw JSONL stdout from `codex exec`. Scan line-by-line for an `item.completed` event whose nested item type is `exitedReviewMode` and extract the `review` field — that string is the actual review payload (the same prose the old `-o <FILE>` path would have written). The review payload is prose in a specific format. Each finding is a bullet:

```
- [P1] <Imperative title> — <absolute file path>:<line_start>-<line_end>
  <One paragraph explaining why this is a problem, possibly multi-line>
```

After the bullets, there's an "overall correctness" verdict sentence like "The patch is correct" or "The patch introduces at least two regressions: ..." — keep this aside as the ship/no-ship narrative for Phase 4.

Parse each bullet with this regex (multi-line; DOTALL on the body):

```
^-\s+\[P([0-3])\]\s+(.+?)\s+—\s+(\S+?):(\d+)(?:-(\d+))?\s*$\n((?:\s{2,}.+(?:\n|$))+)
```

Capture groups:

- `priority` (int, from P0-P3)
- `title` (imperative sentence)
- `file` (absolute path — strip the repo root prefix to normalise)
- `line_start` (int)
- `line_end` (int; may equal line_start if only one line is cited)
- `body` (the indented paragraph below the bullet)

Normalise each finding as:

- `file` ← absolute path with repo root stripped
- `line_start`, `line_end` ← parsed ints
- `severity` ← map from `priority`: `0` → `"critical"`, `1` → `"warning"`, `2` → `"nit"`, `3` → `"nit"` (Phase 4 only has critical/warning/nit/dismissed buckets — collapse P3 into nit so these findings still render)
- `description` ← `title`
- `recommendation` ← the body paragraph (the fix is embedded in the explanation — the native prompt doesn't have a dedicated recommendation field)

**Important caveat**: the native reviewer is non-deterministic. Two runs on the same diff can produce very different findings (one run zero, the next run three). Don't dismiss single-tool Agent B findings just because they didn't show up on a previous run — verify against the actual code.

**Parser validation**: after regex parsing, if 0 findings were extracted but the verdict or body text contains keywords like "regression", "issue", "broken", "must", "incorrect", or "fails", the regex likely failed to parse a format drift. Emit a warning and fall back to treating the full captured text as a single synthetic finding with severity `"warning"` so the output isn't silently empty.

**Rate-limit / degradation detection (Agent B)**: codex's `--json` stream emits discrete error envelopes, so use a structural check before falling back to keywords. Check four signals in order, stopping at the first match:

- **Top-level error event** (preferred): if any line is `{"type":"error", ...}`, the codex stream itself reported a fatal error. Mark Agent B as `degraded` and surface the event's `message` field in the Phase 4 note.
- **Failed turn event**: if any line is `{"type":"turn.failed", ...}`, the turn aborted. Mark `degraded` and surface `error.message`.
- **Missing `exitedReviewMode` event** (structural fallback): if neither of the above fired but no `item.completed` event of nested type `exitedReviewMode` is present, the review didn't produce a payload — mark `degraded` (no review data).
- **Exit code + keyword fallback**: codex exits 1 on terminal failure (vs. 0 for a clean run with 0 findings). If exit was non-zero, mark `degraded`. As a last resort, lowercase the captured stream and check for: "usage limit", "hit your usage limit", "upgrade to Pro", "try again at", "rate limit", "rate limited", "quota", "quota exceeded", "over quota", "insufficient quota", "too many requests", "429".

Note that codex flattens the underlying reason (quota / rate-limit / auth / workspace credit depleted / etc.) to a free-text `message` field — the structured-event tiers (top-level `error` and `turn.failed`) reliably detect *that* a failure happened, but classifying *why* requires reading the message text. Mark Agent B as `degraded` (not "0 findings") and exclude it from the tool-count in Phase 4. Do NOT treat this as a clean pass — the absence of findings is an absence of data, not an absence of problems.

**Codex adversarial review (Agent C, via `codex-companion.mjs adversarial-review --json`)**: the companion script wraps the raw codex output in an envelope. The schema-conformant findings live at `.result.parsed.findings`. Different schema than native! Each finding:

```
{
  "severity": "critical" | "high" | "medium" | "low",
  "title": str,
  "body": str,
  "file": str,
  "line_start": int,
  "line_end": int,
  "confidence": float,
  "recommendation": str
}
```

Normalise each finding as:

- `file` ← `file` (already relative in practice)
- `line_start` / `line_end` ← (already flat ints)
- `severity` ← `severity` (already categorical — use directly, map `"high"` → `"warning"` and `"medium"`/`"low"` → `"nit"` for the final report if you want to match native severity levels)
- `description` ← `title` + `body`
- `recommendation` ← `recommendation`
- Also pull `.result.parsed.summary` aside as the adversarial ship/no-ship narrative for Phase 4 commentary.
- If `.parseError` is non-null **and** case-insensitively matches the same quota/rate-limit indicator set used for Agent B above (including "rate limit", "quota", "too many requests", and "429"): this is a quota/rate-limit error, not a parse failure. Match with a case-insensitive regex or lowercase before comparing — observed casings vary. Mark Agent C as `degraded` (same as Agent B above). Do NOT synthesise a warning finding from it — no review data exists to act on.
- If `.parseError` is non-null but does NOT match the quota pattern: fall back to treating `.rawOutput` as a single opaque finding with severity `"warning"` and note the parse error text verbatim in the Phase 4 output.

**Cubic (Agent F, via `cubic review --json`) — single JSON object**: the agent returns `{"issues": [...]}` plus the exit code. Each issue (exact shape verified v1.7.0):

```
{
  "priority": "P0" | "P1" | "P2" | "P3",
  "file": str,        # already repo-relative
  "line": int,        # single line — cubic does not emit ranges
  "title": str,
  "description": str
}
```

Normalise each issue as:

- `file` ← `file` (already relative — no stripping needed)
- `line_start` / `line_end` ← `line` (set both to the same value; default `0` if absent)
- `severity` ← map `priority`: `P0` → `"critical"`, `P1` → `"warning"`, `P2`/`P3` → `"nit"` (same collapse as Agent B). Default unknown values to `"warning"`.
- `description` ← `title`
- `recommendation` ← `description` (the explanation embeds the fix — the `--json` output has no dedicated fix field; the TUI's fix prompts are not exposed here)
- Tag with `source: "cubic"`.

**Rate-limit / degradation detection (Agent F)**: check these signals in order, stopping at the first match:

- **Valid JSON with an `issues` array** → Agent F succeeded, REGARDLESS of exit code. cubic exits 1 when issues were found and 0 when clean (CI-gate semantics, verified v1.7.0) — exit 1 with parseable findings is a successful review, NOT a degraded one.
- **Non-JSON stdout or missing `issues` key** → mark `degraded`. Observed failure shape: unrecognised flags make yargs print the help text to stdout and exit 1. Surface the first lines of stdout/stderr in the Phase 4 note.
- **Keyword fallback** on stderr (case-insensitive): `rate limit`, `quota`, `429`, `too many requests`, `sign in`, `unauthorized`, `forbidden`. Usage is unlimited during cubic's alpha but rate caps are planned; credentials live in `~/.local/share/cubic/auth.json` — surface the message so the user can tell billing/auth failures from infra glitches.
- **Silent bad-ref trap**: an unresolvable `--base`/`--commit` ref does NOT error — cubic returns `{"issues": []}` with exit 0. An empty result is only trustworthy when the Agent F prompt's `git rev-parse --verify` guard passed; if the agent reports the guard failed, mark `degraded` (bad ref), never a clean pass.

Same rule as the other external reviewers: a degraded Cubic is NOT a clean pass — absence of findings from a failed reviewer is absence of data.

**Claude bugs (Agent D) — JSON array**: already in the target shape. Tag each element with `source: "claude-bugs"` and merge.

**Claude conventions (Agent E) — JSON array**: each element has `{file, line_start, line_end, severity, rule, description}`. The `rule` field is unique to Agent E (the specific CLAUDE.md/REVIEW.md rule quoted verbatim). Map it into the normalised shape as:

- `file`, `line_start`, `line_end`, `severity`, `description` ← pass through
- `recommendation` ← `rule` (the rule itself IS the fix guidance)
- Tag with `source: "claude-conventions"` and preserve the original `rule` field in `raw` for the final report.

### Step 3b: Check against REVIEW.md skip list

For each normalised finding, check if it matches any entry in the REVIEW.md "Skip" section. Structural matching is preferred: compare on `file` path prefix or regex against `description`/`rule` rather than substring. If it matches, mark it **dismissed** with the reason from REVIEW.md.

### Step 3c: Cross-reference and deduplicate

Group findings by `(normalised_file, overlapping_line_range)`. Two findings overlap if:

- Same `file` (after path normalisation), AND
- Line ranges overlap: `a.line_start <= b.line_end AND b.line_start <= a.line_end`

When multiple tools flag the same location:

- This is a **high-confidence** finding — record all sources that agreed.
- Merge descriptions; prefer the most specific recommendation.
- Use the highest severity from any agreeing tool as the cluster severity.

Single-tool findings are NOT dismissed — they just don't get the high-confidence marker.

### Step 3d: Validate remaining findings

For each non-dismissed finding cluster, verify it against the actual code:

- Read the relevant file and lines (structured fields make this precise)
- Confirm the issue actually exists in the current code
- Dismiss if it's a false positive (explain why in the output)

Pay particular attention to findings confidently flagged by a single tool as **critical** — the Codex adversarial pass occasionally emits high-severity false positives. Cross-reference against the actual code before including them in the final report.

### Step 3e: Assign final severity

- **Critical** — will break at runtime or produce wrong results. Fix before merge.
- **Warning** — real issue but won't crash. Should fix.
- **Nit** — minor improvement, not blocking.
- **Dismissed** — false positive, known skip, or not applicable.

## Phase 4: Output

Present the synthesised review in this format:

```markdown
## Deep Review: <branch> → <base>

**Commits:** <count> | **Files changed:** <count> | **Pre-flight:** passed
**Tools used:** <list which tools actually ran, e.g. "Codex, Cubic, Claude (bugs + conventions)">
**Degraded:** <comma-separated list — format `ToolName (reason)`; e.g. `Codex native (quota, resets 5:02 PM), Cubic (not installed)`>

### Critical (fix before merge)

| # | File:Line | Finding | Sources |
|---|-----------|---------|---------|

### Warning (should fix)

| # | File:Line | Finding | Sources |
|---|-----------|---------|---------|

### Nit (minor)

| # | File:Line | Finding | Sources |
|---|-----------|---------|---------|

### Dismissed (<count>)

<collapsed list of dismissed findings with reasons>
```

The **Degraded** line is important for auditability — a review that says "0 findings" means different things depending on how many reviewers actually ran. Count `ATTEMPTED` as the number of reviewers the current invocation was supposed to launch (typically 5, lowered only when a reviewer's CLI tool is not installed and Agent B/C/F is skipped outright). Count `DEGRADED` as the attempted reviewers that did not return usable findings — both `skipped (not installed)` and `runtime-degraded (quota / crash / timeout)` count. Include the **Degraded** line and the trailing note whenever `DEGRADED > 0`; omit them only when every attempted reviewer completed.

When `DEGRADED > 0`, append a one-line note after the tables:

> **Note:** `<DEGRADED>` of `<ATTEMPTED>` reviewer(s) were degraded (`<S>` skipped, `<R>` runtime-degraded). Re-run after the quota resets / missing tools are installed for full cross-tool coverage. When `DEGRADED == 1`, use "reviewer was" for grammatical correctness.

If there are no critical or warning findings, say:

> No issues found. Checked with `<list of tools that ran>`. `<count>` findings dismissed per REVIEW.md.

After outputting the review, write the diff hash to the cache so the next run can skip if nothing changed:

```bash
echo "$DIFF_HASH" > "$CACHE_FILE"
```

## Important rules

- **Never skip Phase 0** unless `--skip-preflight` is passed. Broken code wastes review tokens.
- **Always read REVIEW.md** before synthesising. It contains hard-won knowledge from prior reviews.
- **Cross-tool agreement is the strongest signal.** A finding flagged by 2+ tools is almost certainly real.
- **Single-tool findings need verification.** Read the code before including them.
- **Do not repeat dismissed findings in future reviews.** That is the whole point of REVIEW.md.
