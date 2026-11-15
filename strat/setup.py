"""Setup: create .env, generate Claude Code files, install the optional browser."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from strat.core import UNAVAILABLE, emit, env, root
from strat.doctor import _importable, checks, rg_install_hint, summary


def _run(cmd: list[str]) -> int:
    return subprocess.run(cmd).returncode


def _env_path() -> Path:
    return Path(os.environ.get("STRAT_ENV_FILE") or root() / ".env")


def _keys(example: Path) -> list[str]:
    names = []
    for line in example.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            names.append(line.split("=", 1)[0].strip())
    return names


def _sync(base: Path) -> list[str]:
    """Write .claude/agents/<name>.md from agents/*.md and link .claude/skills -> ../skills."""
    out = base / ".claude" / "agents"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    done = []
    for src in sorted((base / "agents").glob("*.md")):
        # agents/*.md already use Claude Code's subagent frontmatter (name, description, tools)
        (out / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        done.append(f".claude/agents/{src.name}")
    link = base / ".claude" / "skills"
    if link.is_symlink() or link.is_file():
        link.unlink()
    elif link.is_dir():
        shutil.rmtree(link)
    link.symlink_to(Path("..") / "skills", target_is_directory=True)
    done.append(".claude/skills -> ../skills")
    return done


def setup(browser: bool = False, sync: bool = False, as_json: bool = False) -> int:
    """Create .env from .env.example; --sync writes .claude files; --browser installs chromium."""
    base = root()
    lines: list[str] = []
    data: dict = {}
    path = _env_path()
    example = base / ".env.example"
    if not path.exists() and example.is_file():
        shutil.copy(example, path)
        lines.append(f"created {path.name} from .env.example")
    if example.is_file():
        empty = [k for k in _keys(example) if not env(k)]
        data["empty_keys"] = empty
        if empty:
            lines.append("empty in .env: " + ", ".join(empty))
            lines.append("fill keys in .env by hand in an editor; never paste keys into the chat")
    code = 0
    if sync:
        data["synced"] = _sync(base)
        lines.append("generated: " + ", ".join(data["synced"]))
    if browser:
        steps = []
        if not _importable("playwright"):
            steps.append([sys.executable, "-m", "pip", "install", "playwright"])
        steps.append([sys.executable, "-m", "playwright", "install", "chromium"])
        for cmd in steps:
            if _run(cmd) != 0:
                lines.append("failed: " + " ".join(cmd[1:]))
                code = UNAVAILABLE
                break
        else:
            lines.append(f"browser installed into {sys.executable}")
    rows = checks()
    data["doctor"] = rows
    if not shutil.which("rg"):
        lines.append(f"ripgrep missing; install it with: {rg_install_hint()}")
    lines.append(summary(rows))
    emit("\n".join(lines), data, as_json)
    return code
