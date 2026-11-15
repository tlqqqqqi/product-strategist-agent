"""Doctor: report each capability as available or missing, with the reason."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys

from strat.core import emit, env, load_config, root

SEARCH_KEYS = ("BRAVE_API_KEY", "TAVILY_API_KEY", "EXA_API_KEY")


def _importable(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def _conf(name: str) -> dict:
    try:
        return load_config(name)
    except Exception:
        return {}


def _chromium_installed() -> bool:
    """Ask playwright for its chromium path in a child process (no browser start)."""
    code = ("from playwright.sync_api import sync_playwright\n"
            "import os,sys\n"
            "with sync_playwright() as p:\n"
            "    sys.exit(0 if os.path.exists(p.chromium.executable_path) else 1)\n")
    try:
        return subprocess.run([sys.executable, "-c", code], capture_output=True,
                              timeout=60).returncode == 0
    except Exception:
        return False


def rg_install_hint() -> str:
    system = platform.system()
    if system == "Darwin":
        return "brew install ripgrep"
    if system == "Windows":
        return "winget install BurntSushi.ripgrep.MSVC"
    return "sudo apt install ripgrep"


def checks() -> list[dict]:
    rows: list[dict] = []

    def add(name: str, available: bool, detail: str) -> None:
        rows.append({"name": name, "available": available, "detail": detail})

    v = sys.version_info
    add("core", True, f"Python {v.major}.{v.minor}.{v.micro} at {sys.executable}")

    add("ripgrep", bool(shutil.which("rg")),
        "rg on PATH" if shutil.which("rg") else
        f"rg not found; knowledge search falls back to plain search. Install: {rg_install_hint()}")

    office = {"openpyxl": "openpyxl", "docx": "python-docx", "pptx": "python-pptx",
              "pypdf": "pypdf"}
    missing = [pkg for mod, pkg in office.items() if not _importable(mod)]
    add("office files", not missing,
        "xlsx, docx, pptx, pdf readers importable" if not missing else
        f"missing: {', '.join(missing)}; install with .venv/bin/pip install -r requirements.txt")

    keys = [k for k in SEARCH_KEYS if env(k)]
    add("web search", bool(keys),
        f"strat search via {', '.join(keys)}" if keys else
        "no BRAVE_API_KEY, TAVILY_API_KEY or EXA_API_KEY in .env; the agent uses the IDE's "
        "own web search")

    peer = bool(env("STRAT_PEER_API_KEY"))
    peer_model = env("STRAT_PEER_MODEL") or _conf("routes").get("consult", {}).get("model", "")
    add("challenger", True,
        f"peer model {peer_model} (STRAT_PEER_API_KEY set)" if peer else
        "no STRAT_PEER_API_KEY; the challenger runs as a native subagent, marked same-vendor")

    if env("STRAT_JEV_API_KEY"):
        add("judge", True, f"jev ({env('STRAT_JEV_MODEL') or 'jev'}, STRAT_JEV_API_KEY set)")
    elif peer:
        chat = _conf("routes").get("judge", {}).get("chat_model") or peer_model
        add("judge", True, f"chat model {chat} on the peer endpoint (STRAT_PEER_API_KEY set)")
    else:
        add("judge", True, "no STRAT_JEV_API_KEY or STRAT_PEER_API_KEY; the IDE agent answers")

    if env("STRAT_STT_API_KEY"):
        add("speech to text", True,
            f"{env('STRAT_STT_BASE_URL') or 'STT service'} (STRAT_STT_API_KEY set)")
    elif _importable("faster_whisper"):
        add("speech to text", True, "local Whisper (faster-whisper)")
    else:
        add("speech to text", False,
            "no STRAT_STT_API_KEY and no local Whisper; set the key in .env or "
            ".venv/bin/pip install faster-whisper")

    add("video", bool(shutil.which("ffmpeg")),
        "ffmpeg on PATH" if shutil.which("ffmpeg") else
        "ffmpeg not found; video and long audio need it")

    if not _importable("playwright"):
        add("browser capture", False, "playwright not installed; run bin/strat setup --browser")
    elif not _chromium_installed():
        add("browser capture", False, "chromium not installed; run bin/strat setup --browser")
    else:
        add("browser capture", True, "playwright and chromium installed")

    base = root()
    link = base / ".agents" / "skills"
    ok = link.is_dir() and link.resolve() == (base / "skills").resolve()
    add("skill links", ok,
        ".agents/skills -> skills/" if ok else
        ".agents/skills does not resolve to skills/ (on Windows clone with "
        "git config core.symlinks true)")

    sub = (base / ".claude" / "agents" / "challenger.md").is_file()
    add("claude code subagents", sub,
        ".claude/agents/challenger.md present" if sub else
        "no .claude/agents/challenger.md; run bin/strat setup --sync")
    return rows


def summary(rows: list[dict]) -> str:
    return "\n".join(f"[{'ok' if r['available'] else 'missing'}] {r['name']}: {r['detail']}"
                     for r in rows)


def doctor(as_json: bool = False) -> int:
    """List capabilities and why each is missing."""
    rows = checks()
    emit(summary(rows), rows, as_json)
    return 0
