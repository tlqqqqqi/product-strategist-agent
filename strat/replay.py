"""Session transcripts to a replay script for demo/replay/index.html.

Reads the Claude Code session transcripts (JSONL) of a run - the same files `strat cost` reads -
and keeps only what a viewer should see: the user's messages, the agent's messages, each tool
call condensed to one line, gate stops with their answer buttons, timestamps and the IDE model's
cost per step. Thinking, system reminders, hook output, raw tool output and subagent work are
dropped. Paths outside the run folder are hidden and anything that looks like a secret is
replaced; the export refuses to write if a secret pattern survives.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from strat.core import FAILED, UNAVAILABLE, StratError, emit, load_config, root

HIDDEN = "[скрыто]"
NO_PATH = "[путь скрыт]"
# Default answer buttons at a gate the agent presented as text (the user typed the answer).
GATE_BUTTONS = ["Да, утверждаю", "Нужны правки"]

SECRET_PATTERNS = [
    re.compile(r"sk-(?:ant-)?[A-Za-z0-9_-]{16,}"),
    re.compile(r"tvly-[A-Za-z0-9_-]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_\w{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"(?i)bearer\s+(?!\[скрыто\])[A-Za-z0-9._~+/-]{16,}=*"),
    re.compile(r"(?i)\b(\w*(?:key|token|secret|password)\w*)(\s*[=:]\s*)"
               r"(?!\[скрыто\])(['\"]?)[^\s'\"]{6,}\3"),
    # long mixed letter-digit strings: tokens and keys without a known prefix
    re.compile(r"(?<![\w-])(?![a-z0-9]+(?:-[a-z0-9]+){3,}(?![\w-]))(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{40,}"
               r"(?![\w-])"),
]
ABS_PATH = re.compile(r"(?<![\w.:/~-])(?!/dev/null\b)(?:~|/[A-Za-z0-9._-]+)(?:/[A-Za-z0-9._@-]+)+/?")
TAG_BLOCK = re.compile(r"<([a-z][a-z0-9_-]*)>.*?</\1>", re.S)
ANSWER = re.compile(r'"((?:[^"\\]|\\.)*)"="((?:[^"\\]|\\.)*)"')
GATE_CMD = re.compile(r"strat gate (check|approve) (\d)")


def _hide_secrets(text: str) -> str:
    for pat in SECRET_PATTERNS:
        if pat.groups >= 2:
            text = pat.sub(lambda m: f"{m.group(1)}{m.group(2)}{HIDDEN}", text)
        else:
            text = pat.sub(HIDDEN, text)
    return text


def redact(text: str, cwd: str | None = None) -> str:
    """Hide secrets; make paths in the run folder relative and hide every other absolute path."""
    text = _hide_secrets(text)
    if cwd:
        text = text.replace(cwd.rstrip("/") + "/", "").replace(cwd.rstrip("/"), ".")
    return ABS_PATH.sub(NO_PATH, text)


def leaked(script: dict) -> list[str]:
    """Strings in the script that still match a secret pattern."""
    found: list[str] = []

    def walk(v):
        if isinstance(v, str):
            found.extend(m.group(0) for p in SECRET_PATTERNS for m in p.finditer(v))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(script)
    return found


def _shorten(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _path(p: str, cwd: str | None) -> str:
    if cwd and p.rstrip("/") == cwd.rstrip("/"):
        return "."
    if cwd and p.startswith(cwd.rstrip("/") + "/"):
        rel = p[len(cwd.rstrip("/")) + 1:]
        m = re.match(r"cases/[^/]+/(.+)", rel)
        return m.group(1) if m else rel
    return p if not p.startswith(("/", "~")) else NO_PATH


def _command(cmd: str) -> str:
    lines = [ln.strip() for ln in cmd.splitlines()]
    lines = [ln for ln in lines if ln and ln not in ("set -e", "set -eu", "set -euo pipefail")
             and not ln.startswith("#")]
    if not lines:
        return "команда"
    first = lines[0]
    while (m := re.match(r"cd \S+ && (.+)", first)):
        first = m.group(1)
    first = re.sub(r'"([^"]{41,})"', lambda m: '"' + _shorten(m.group(1), 40) + '"', first)
    first = _shorten(first, 140)
    return first + (f" (и ещё {len(lines) - 1})" if len(lines) > 1 else "")


def condense(name: str, inp: dict, cwd: str | None) -> str:
    """One line in Russian for a tool call."""
    path = inp.get("file_path") or inp.get("notebook_path") or inp.get("path") or ""
    if name == "Bash":
        line = _command(inp.get("command", ""))
    elif name == "Read":
        line = f"прочитал {_path(path, cwd)}"
    elif name == "Write":
        line = f"записал {_path(path, cwd)}"
    elif name in ("Edit", "MultiEdit", "NotebookEdit"):
        line = f"изменил {_path(path, cwd)}"
    elif name == "Grep":
        line = f"искал «{_shorten(inp.get('pattern', ''), 50)}»" + (
            f" в {_path(path, cwd)}" if path and _path(path, cwd) != "." else "")
    elif name == "Glob":
        line = f"искал файлы {_shorten(inp.get('pattern', ''), 60)}"
    elif name == "WebSearch":
        line = f"веб-поиск: «{_shorten(inp.get('query', ''), 80)}»"
    elif name == "WebFetch":
        line = f"открыл страницу {_shorten(inp.get('url', ''), 90)}"
    elif name == "Skill":
        line = f"открыл навык {inp.get('skill', '')}"
    elif name == "ToolSearch":
        line = "подключил инструменты"
    elif name == "TodoWrite":
        line = "обновил список задач"
    elif name in ("Agent", "Task"):
        line = f"поручил подзадачу: {_shorten(inp.get('description', ''), 80)}"
    elif name.startswith("mcp__"):
        line = "вызвал " + name.split("__", 2)[-1]
    else:
        line = name
    return redact(line, cwd)


def _user_text(content) -> str | None:
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        content = "\n".join(b.get("text", "") for b in content
                            if isinstance(b, dict) and b.get("type") == "text")
    if not isinstance(content, str):
        return None
    text = TAG_BLOCK.sub("", content).strip()
    if not text or text.startswith("[Request interrupted"):
        return None
    return text


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _entries(folder: Path) -> list[dict]:
    rows = []
    for f in sorted(folder.glob("*.jsonl")):
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines()):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if (d.get("type") in ("user", "assistant") and d.get("timestamp")
                    and not d.get("isSidechain") and not d.get("isMeta")
                    and not d.get("isCompactSummary")):
                rows.append(d)
    rows.sort(key=lambda d: _ts(d["timestamp"]))  # stable: blocks of one message keep order
    return rows


def build(folder: Path, label: str | None = None) -> dict:
    """The replay script from the transcripts in `folder`."""
    from strat.cost import _price

    prices = load_config("prices")
    events: list[dict] = []
    seen_msgs: set[str] = set()
    models: Counter = Counter()
    sessions: set[str] = set()
    pending = {"usd": 0.0}
    tools: dict[str, tuple[str, int | None]] = {}  # tool id -> (kind, event index)
    turn = {"gate": None, "last_agent": None}

    def add(ev: dict, d: dict) -> None:
        ev["ts"] = d["timestamp"]
        if ev["kind"] != "user" and pending["usd"]:
            ev["usd"] = pending["usd"]
            pending["usd"] = 0.0
        sessions.add(d.get("sessionId", ""))
        events.append(ev)

    def close_turn() -> None:
        if turn["gate"] is not None and turn["last_agent"] is not None:
            events[turn["last_agent"]]["gate"] = {"n": turn["gate"], "buttons": GATE_BUTTONS,
                                                  "typed": True}
        turn["gate"], turn["last_agent"] = None, None

    for d in _entries(folder):
        msg = d.get("message") or {}
        cwd = d.get("cwd")
        if d["type"] == "assistant":
            model = msg.get("model", "")
            if model == "<synthetic>":
                continue
            mid = msg.get("id") or d.get("uuid") or d["timestamp"]
            if msg.get("usage") and mid not in seen_msgs:
                seen_msgs.add(mid)
                models[model] += 1
                if model in prices:
                    pending["usd"] += _price(msg["usage"], prices[model])
            for b in msg.get("content") or []:
                if b.get("type") == "text" and b.get("text", "").strip():
                    add({"kind": "agent", "text": redact(b["text"].strip(), cwd)}, d)
                    turn["last_agent"] = len(events) - 1
                elif b.get("type") == "tool_use":
                    name, inp = b.get("name", ""), b.get("input") or {}
                    if name == "AskUserQuestion":
                        for q in inp.get("questions") or []:
                            add({"kind": "question", "text": redact(q.get("question", ""), cwd),
                                 "buttons": [redact(o.get("label", ""), cwd)
                                             for o in q.get("options") or []]}, d)
                        tools[b["id"]] = ("ask", len(events) - 1)
                        continue
                    add({"kind": "step", "tool": name, "line": condense(name, inp, cwd),
                         "ok": True}, d)
                    tools[b["id"]] = ("step", len(events) - 1)
                    m = GATE_CMD.search(inp.get("command", "")) if name == "Bash" else None
                    if m and m.group(1) == "check":
                        tools[b["id"]] = ("check", len(events) - 1, int(m.group(2)))
                    elif m and turn["gate"] == int(m.group(2)):
                        turn["gate"] = None
        else:
            content = msg.get("content")
            if isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict) or b.get("type") != "tool_result":
                        continue
                    ref = tools.get(b.get("tool_use_id"))
                    if not ref:
                        continue
                    err = bool(b.get("is_error"))
                    if ref[0] in ("step", "check"):
                        events[ref[1]]["ok"] = not err
                        if ref[0] == "check" and not err:
                            turn["gate"] = ref[2]
                    elif ref[0] == "ask" and not err:
                        raw = b.get("content")
                        raw = raw if isinstance(raw, str) else " ".join(
                            x.get("text", "") for x in raw or [] if isinstance(x, dict))
                        answers = [a for _, a in ANSWER.findall(raw)]
                        if answers:
                            q = events[ref[1]]
                            if answers[-1] in q["buttons"]:
                                q["chosen"] = q["buttons"].index(answers[-1])
                            add({"kind": "user", "text": redact(answers[-1], cwd),
                                 "via": "button"}, d)
            text = _user_text(content)
            if text is None:
                continue
            close_turn()
            text = redact(text, cwd)
            if events and events[-1]["kind"] == "user" and events[-1]["text"] == text \
                    and events[-1].get("via") != "button":
                events.pop()  # a resend after a failed turn (e.g. a usage limit)
            add({"kind": "user", "text": text}, d)
    close_turn()
    if not events:
        raise StratError("no conversation in the transcripts", UNAVAILABLE)
    if pending["usd"]:
        last = next(e for e in reversed(events) if e["kind"] != "user")
        last["usd"] = last.get("usd", 0.0) + pending["usd"]

    # gate answers: approved later -> the first button, otherwise the second
    for i, ev in enumerate(events):
        if "gate" in ev:
            n = ev["gate"]["n"]
            approved = any(e["kind"] == "step" and re.search(rf"strat gate approve {n}\b",
                                                             e["line"]) for e in events[i:])
            replied = any(e["kind"] == "user" for e in events[i:])
            ev["gate"]["chosen"] = 0 if approved else (1 if replied else None)

    start = _ts(events[0]["ts"])
    total = 0.0
    for ev in events:
        ev["t"] = int((_ts(ev.pop("ts")) - start).total_seconds())
        if "usd" in ev:
            ev["usd"] = round(ev["usd"], 4)
            total += ev["usd"]
    meta = {
        "label": label or "Запись реального прогона",
        "date": start.date().isoformat(),
        "start": start.isoformat(),
        "model": models.most_common(1)[0][0] if models else "",
        "minutes": round(events[-1]["t"] / 60, 1),
        "usd": round(total, 4),
        "sessions": len(sessions),
        "gates": sum("gate" in e for e in events),
        "steps": sum(e["kind"] == "step" for e in events),
        "priced": all(m in prices for m in models),
    }
    return {"version": 1, "meta": meta, "events": events}


def embed(page: Path, script: dict) -> None:
    """Put the script into the page, so it plays from file:// without a fetch."""
    html = page.read_text(encoding="utf-8")
    data = json.dumps(script, ensure_ascii=False).replace("</", "<\\/")
    new, n = re.subn(r'(<script id="replay-data" type="application/json">).*?(</script>)',
                     lambda m: m.group(1) + data + m.group(2), html, count=1, flags=re.S)
    if n != 1:
        raise StratError(f"{page}: no replay-data block")
    page.write_text(new, encoding="utf-8")


def export(case: str | None = None, transcripts: str | None = None, out: str | None = None,
           label: str | None = None, as_json: bool = False) -> int:
    """Build demo/replay/script.json (and embed it into index.html next to it)."""
    from strat.cost import transcripts_dir

    folder = Path(transcripts) if transcripts else transcripts_dir()
    if not folder.is_dir() or not any(folder.glob("*.jsonl")):
        raise StratError(f"no session transcripts in {folder}", UNAVAILABLE)
    script = build(folder, label)
    bad = leaked(script)
    if bad:
        raise StratError(f"refusing to write: {len(bad)} secret-like strings survived redaction",
                         FAILED)
    target = Path(out) if out else root() / "demo" / "replay" / "script.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(script, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    page = target.parent / "index.html"
    if page.is_file():
        embed(page, script)
    m = script["meta"]
    emit(f"wrote {target}: {len(script['events'])} events, {m['steps']} steps, {m['gates']} gates, "
         f"{m['minutes']} min, {m['usd']} usd (IDE model, API list prices)"
         + (f"; embedded into {page.name}" if page.is_file() else ""),
         {"out": str(target), "meta": m, "embedded": page.is_file()}, as_json)
    return 0
