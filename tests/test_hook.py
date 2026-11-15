"""Task 1: a new chat receives the bootstrap and 'no active case'."""

import json
import os
import subprocess
import sys

import pytest

from conftest import REPO


def run_hook(cases_dir, **env):
    full = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "CURSOR"))}
    full.update(STRAT_CASES=str(cases_dir), **env)
    proc = subprocess.run([sys.executable, str(REPO / "hooks" / "session-start")],
                          capture_output=True, text=True, env=full, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_claude_code_gets_bootstrap_and_no_active_case(tmp_path):
    out = run_hook(tmp_path, CLAUDE_PROJECT_DIR=str(REPO))
    ctx = json.loads(out)["hookSpecificOutput"]
    assert ctx["hookEventName"] == "SessionStart"
    assert "name: using-strategist" in ctx["additionalContext"]
    assert "no active case" in ctx["additionalContext"]


def test_plain_environment_gets_text(tmp_path):
    out = run_hook(tmp_path)
    assert "using-strategist" in out and "no active case" in out


def test_settings_register_the_hook():
    settings = json.loads((REPO / ".claude" / "settings.json").read_text())
    command = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "hooks/session-start" in command


def run_hook_args(cases_dir, *args, **env):
    full = {k: v for k, v in os.environ.items()
            if not k.startswith(("CLAUDE", "CURSOR", "QWEN", "GEMINI", "COPILOT"))}
    full.update(STRAT_CASES=str(cases_dir), **env)
    proc = subprocess.run([sys.executable, str(REPO / "hooks" / "session-start"), *args],
                          capture_output=True, text=True, env=full, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def nested(out):
    data = json.loads(out)
    assert list(data) == ["hookSpecificOutput"]
    assert data["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    return data["hookSpecificOutput"]["additionalContext"]


FORMATS = {
    "claude": nested,
    "qwen": nested,
    "gigacode": nested,
    "gemini": nested,
    "cursor": lambda out: json.loads(out)["additional_context"],
    "copilot": lambda out: json.loads(out)["additionalContext"],
    "text": lambda out: out,
}


@pytest.mark.parametrize("fmt", sorted(FORMATS))
def test_format_flag_picks_the_output_key(tmp_path, fmt):
    # the flag wins over whatever the environment variables suggest
    out = run_hook_args(tmp_path, "--format", fmt, CLAUDE_PROJECT_DIR=str(REPO))
    text = FORMATS[fmt](out)
    assert "name: using-strategist" in text and "no active case" in text
    if fmt in ("cursor", "copilot"):
        assert len(json.loads(out)) == 1


def test_copilot_detected_by_env(tmp_path):
    out = run_hook_args(tmp_path, COPILOT_CLI="1", CLAUDE_PROJECT_DIR=str(REPO))
    assert list(json.loads(out)) == ["additionalContext"]


def test_unknown_format_still_never_breaks_the_session(tmp_path):
    out = run_hook_args(tmp_path, "--format", "nonsense")
    assert "using-strategist" in out
