"""Task 1: a new chat receives the bootstrap and 'no active case'."""

import json
import os
import subprocess
import sys

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
