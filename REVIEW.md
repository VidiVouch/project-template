# Code Review Guidelines

Review-specific rules read during code reviews. For general project instructions, see CLAUDE.md.

## Always check

- `TYPE_CHECKING` imports are not used at runtime (safe with PEP 649 in 3.14)
- New dependencies are declared in `pyproject.toml` and explicitly bounded (minor or tighter)
- Exception handling is specific — no bare `except Exception` without justification

## Project-specific rules

- **Python 3.14 target**: PEP 758 allows `except A, B:` without parentheses *when there is no `as` binding*. If you bind the exception with `as e`, parentheses are still required: `except (A, B) as e:` is legal, `except A, B as e:` is a `SyntaxError`. Ruff format enforces the unparenthesized style for `target-version = "py314"`. This is not Python 2 syntax.
- **PEP 649 deferred annotations**: imports used only in type annotations can safely live inside `TYPE_CHECKING` blocks without `from __future__ import annotations`.

## Skip

These are known design decisions or false positives. Do not flag them:

- `except ImportError, SyntaxError:` without parentheses — valid PEP 758 Python 3.14
- **Coverage below 100% on changed lines is not automatically a finding.** Run `/check-coverage` to see gaps, but evaluate each missing line on whether covering it would catch a real bug vs. just exercise the line. Trivial lines (logging, debug prints, unreachable defensive guards) should be marked `# pragma: no cover`, not forced into a test.



