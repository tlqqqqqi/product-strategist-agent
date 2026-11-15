import os
import shutil
import sys

import pytest

from conftest import REPO


@pytest.fixture
def root(tmp_path, monkeypatch, cases):
    """A temp project root with .env.example, agents/, skills/ and .claude/settings.json."""
    r = tmp_path / "proj"
    r.mkdir()
    shutil.copy(REPO / ".env.example", r / ".env.example")
    shutil.copytree(REPO / "agents", r / "agents")
    (r / "skills" / "demo").mkdir(parents=True)
    (r / "skills" / "demo" / "SKILL.md").write_text("x", encoding="utf-8")
    (r / ".claude").mkdir()
    (r / ".claude" / "settings.json").write_text('{"keep": 1}', encoding="utf-8")
    shutil.copytree(REPO / "config", r / "config")
    monkeypatch.setenv("STRAT_ROOT", str(r))
    monkeypatch.setenv("STRAT_ENV_FILE", str(r / ".env"))
    return r


def by_name(rows):
    return {row["name"]: row for row in rows}


def test_doctor_lists_capabilities_without_keys(strat, root):
    r = strat("doctor", "--json")
    assert r.code == 0
    rows = by_name(r.data)
    for name in ("core", "ripgrep", "office files", "web search", "challenger", "judge",
                 "speech to text", "video", "browser capture", "skill links",
                 "claude code subagents"):
        assert name in rows, name
        assert set(rows[name]) == {"name", "available", "detail"}
    assert rows["core"]["available"] is True
    assert rows["web search"]["available"] is False
    assert "IDE" in rows["web search"]["detail"]
    assert "same-vendor" in rows["challenger"]["detail"]
    assert rows["claude code subagents"]["available"] is False
    assert "setup --sync" in rows["claude code subagents"]["detail"]


def test_doctor_reads_keys_from_env_file_and_never_prints_values(strat, root):
    (root / ".env").write_text("TAVILY_API_KEY=secret-tav-123\nSTRAT_PEER_API_KEY=secret-peer-9\n",
                               encoding="utf-8")
    text = strat("doctor")
    data = by_name(strat("doctor", "--json").data)
    assert text.code == 0
    assert "secret" not in text.out + text.err
    assert data["web search"]["available"] is True
    assert "TAVILY_API_KEY" in data["web search"]["detail"]
    assert "cx/gpt-6.1-sol" in data["challenger"]["detail"]
    assert data["judge"]["available"] is True
    assert "ds/deepseek-v4-flash" in data["judge"]["detail"]


def test_setup_creates_env_once_and_lists_empty_keys(strat, root):
    r = strat("setup")
    assert r.code == 0
    assert (root / ".env").read_text() == (root / ".env.example").read_text()
    assert "BRAVE_API_KEY" in r.out
    (root / ".env").write_text("BRAVE_API_KEY=mine-secret\n", encoding="utf-8")
    r = strat("setup")
    assert (root / ".env").read_text() == "BRAVE_API_KEY=mine-secret\n"
    assert "mine-secret" not in r.out


def test_setup_sync_generates_claude_files_idempotently(strat, root):
    stale = root / ".claude" / "agents" / "old.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale", encoding="utf-8")
    for _ in range(2):
        assert strat("setup", "--sync").code == 0
    agent = (root / ".claude" / "agents" / "challenger.md").read_text()
    assert agent.startswith("---\nname: challenger\ndescription: ")
    assert (root / ".claude" / "agents" / "persona.md").is_file()
    assert not stale.exists()
    link = root / ".claude" / "skills"
    assert link.is_symlink() and os.readlink(link) == "../skills"
    assert (link / "demo" / "SKILL.md").is_file()
    assert (root / ".claude" / "settings.json").read_text() == '{"keep": 1}'
    rows = by_name(strat("doctor", "--json").data)
    assert rows["claude code subagents"]["available"] is True


def test_setup_browser_uses_running_interpreter(strat, root, monkeypatch):
    calls = []
    monkeypatch.setattr("strat.setup._run", lambda cmd: calls.append(cmd) or 0)
    monkeypatch.setattr("strat.setup._importable", lambda mod: False)
    assert strat("setup", "--browser").code == 0
    assert calls == [[sys.executable, "-m", "pip", "install", "playwright"],
                     [sys.executable, "-m", "playwright", "install", "chromium"]]
