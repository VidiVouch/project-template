"""Tests for `.agents/hooks/enforce_uv.py`."""

import enforce_uv as hook
import pytest


@pytest.mark.parametrize(
    "command",
    [
        "python foo.py",
        "python3 foo.py",
        "python",
        "python3",
        "python -c 'print(1)'",
        "python3 -m http.server",
        "  python -V",
    ],
)
def test_bare_python_is_blocked(command: str):
    assert hook.evaluate(command) == "uv run python"


@pytest.mark.parametrize(
    "command",
    [
        "uv run python foo.py",
        "uv run python3 foo.py",
        "echo python is great",
        "grep python requirements.txt",
        "cat pythonic_code.py",
    ],
)
def test_python_in_arg_or_uv_passes(command: str):
    assert hook.evaluate(command) is None


@pytest.mark.parametrize(
    "command",
    [
        "pip install requests",
        "pip3 install django",
        "pip install -r requirements.txt",
        "pip install --upgrade pip",
        "pip3 install -e .",
    ],
)
def test_pip_install_routes_to_uv_add(command: str):
    assert hook.evaluate(command) == "uv add"


@pytest.mark.parametrize("command", ["pip uninstall requests", "pip3 uninstall django", "pip uninstall -y requests"])
def test_pip_uninstall_routes_to_uv_remove(command: str):
    assert hook.evaluate(command) == "uv remove"


@pytest.mark.parametrize("command", ["pip show django", "pip list", "pip3 freeze", "pip check", "pip3 list --outdated"])
def test_other_pip_subcommands_route_to_uv_pip(command: str):
    assert hook.evaluate(command) == "uv pip"


@pytest.mark.parametrize(
    "command", ["uv add requests", "uv remove requests", "uv pip show django", "uv pip list", "echo pip is deprecated"]
)
def test_uv_prefixed_pip_passes(command: str):
    assert hook.evaluate(command) is None


@pytest.mark.parametrize("command", ["pytest", "pytest -v", "pytest --tb=short -x", "pytest tests/", "  pytest -q"])
def test_bare_pytest_is_blocked(command: str):
    assert hook.evaluate(command) == "uv run pytest"


@pytest.mark.parametrize("command", ["uv run pytest", "uv run pytest -v", "echo pytest is installed", "uv add pytest"])
def test_uv_pytest_passes(command: str):
    assert hook.evaluate(command) is None


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("python foo.py && pytest", "uv run python"),
        ("uv run python foo.py; pytest", "uv run pytest"),
        ("uv run python foo.py && pytest -v", "uv run pytest"),
        ("python foo.py || echo failed", "uv run python"),
        ("echo ok && pip install requests", "uv add"),
        ("echo ok; pip show django", "uv pip"),
        ("false||python3 -V", "uv run python"),
        ("true && pip freeze", "uv pip"),
        # Newline-separated commands — `grep` evaluated per-line, so the
        # bash hook caught these; `re.search` does not unless `\n` is in
        # the segment-delimiter class.
        ("echo hello\npip install requests", "uv add"),
        ("uv run ruff check\npytest", "uv run pytest"),
        ("ls\npython foo.py", "uv run python"),
    ],
)
def test_compound_commands_are_blocked_per_segment(command: str, expected: str):
    assert hook.evaluate(command) == expected


@pytest.mark.parametrize(
    "command",
    [
        "uv run python foo.py && uv run pytest",
        "echo hello && ls",
        "uv run ruff check && uv run basedpyright",
        "ls",
        "git status",
        "uv sync",
        "uv run ruff check",
        "echo hello",
    ],
)
def test_unrelated_commands_pass(command: str):
    assert hook.evaluate(command) is None


# === env-prefix and wrapper bypasses ===


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        # Leading NAME=value env-assignments must not hide the real binary.
        ("PYTHONPATH=. python -m foo", "uv run python"),
        ("FOO=bar pytest", "uv run pytest"),
        ("FOO=bar BAZ=qux python3 x.py", "uv run python"),
        ("PIP_NO_CACHE_DIR=1 pip install requests", "uv add"),
        # Transparent wrappers unwrap to the command that actually runs.
        ("env python foo.py", "uv run python"),
        ("env FOO=bar python foo.py", "uv run python"),
        ("command python x", "uv run python"),
        ("time pytest", "uv run pytest"),
        ("xargs python < list", "uv run python"),
        ("nohup python foo.py &", "uv run python"),
        ("exec python x", "uv run python"),
        # Wrappers stack and combine with env-assignments.
        ("time xargs python", "uv run python"),
        ("FOO=bar env python x", "uv run python"),
    ],
)
def test_env_prefix_and_wrappers_are_normalized(command: str, expected: str):
    assert hook.evaluate(command) == expected


@pytest.mark.parametrize(
    "command",
    [
        # Wrapping a uv-prefixed command must still pass — normalisation only
        # strips the wrapper, it does not re-block the head that follows.
        "env uv run python foo.py",
        "time uv run pytest",
        # A wrapper word used as an ordinary argument (not the head) is fine.
        "uv run python -m timeit",
        "echo time to test",
    ],
)
def test_normalization_does_not_over_block(command: str):
    assert hook.evaluate(command) is None


@pytest.mark.parametrize(
    "command",
    [
        # Accepted limitations: command substitution, subshells, and brace
        # groups need real tokenisation, so a bare binary nested only inside
        # one of these is NOT caught. These assert the current (accepted)
        # behaviour so the gap is explicit rather than silent — see the module
        # docstring. Fixing them is out of scope for the whitespace/quote split.
        "x=$(python foo.py)",
        "(python foo.py)",
        "{ python foo.py; }",
    ],
)
def test_documented_substitution_gaps_are_not_caught(command: str):
    assert hook.evaluate(command) is None


# === ssh / remote commands ===


@pytest.mark.parametrize(
    "command",
    [
        # Unquoted remote command — python is an argument to ssh, not local.
        "ssh deploy@portal.onrender.com python manage.py migrate",
        # Quoted remote command — the leading word of the segment is ssh.
        "ssh deploy@portal.onrender.com 'python manage.py migrate'",
        # Separators *inside* the quoted remote command must not leak out and
        # be read as local segments (this is the case that motivated the fix).
        "ssh deploy@portal.onrender.com 'echo up; python --version'",
        "ssh -o BatchMode=yes srv@ssh.oregon.render.com 'printenv X | python -c \"pass\"'",
        # Remote pip/pytest are exempt for the same reason.
        "ssh deploy@portal.onrender.com 'pip install requests'",
        'ssh deploy@portal.onrender.com "pytest -q"',
    ],
)
def test_python_over_ssh_is_allowed(command: str):
    assert hook.evaluate(command) is None


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        # A real top-level separator after the ssh segment starts a new local
        # segment, which is still enforced.
        ("ssh host 'python remote.py'; python local.py", "uv run python"),
        ("ssh host 'deploy' && pytest", "uv run pytest"),
        ("python local.py; ssh host 'python remote.py'", "uv run python"),
    ],
)
def test_local_binary_after_ssh_segment_still_blocked(command: str, expected: str):
    assert hook.evaluate(command) == expected


@pytest.mark.parametrize(
    "command",
    [
        # Separators inside quotes no longer split, so the binary token they
        # precede is never read as a local segment head.
        "echo 'all done; pytest later'",
        'git commit -m "remember to pip install requests"',
        'echo "pipe then python: a | python b"',
    ],
)
def test_separators_inside_quotes_do_not_split(command: str):
    assert hook.evaluate(command) is None


# === main() integration ===


def test_main_stays_silent_for_ssh_python(invoke):
    code, parsed = invoke(
        hook,
        {"tool_name": "Bash", "tool_input": {"command": "ssh deploy@portal.onrender.com 'python manage.py migrate'"}},
    )
    assert code == 0
    assert parsed is None


def test_main_emits_deny_for_bare_pytest(invoke):
    code, parsed = invoke(hook, {"tool_name": "Bash", "tool_input": {"command": "pytest -v"}})
    assert code == 0
    assert parsed is not None
    out = parsed["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert "uv run pytest" in out["permissionDecisionReason"]
    assert "pytest -v" in out["permissionDecisionReason"]


def test_main_stays_silent_for_uv_command(invoke):
    code, parsed = invoke(hook, {"tool_name": "Bash", "tool_input": {"command": "uv run pytest"}})
    assert code == 0
    assert parsed is None
