"""Session transcripts to a bundle of replay runs for demo/replay/index.html.

Reads one run - Claude Code session transcripts (JSONL, the files `strat cost` reads) or a folder
of OpenCode `run --format json` turn logs - and keeps only what a viewer should see: the user's
messages, the agent's messages, tool calls condensed to one line each and grouped between two
messages under a Russian summary, questions the agent asked with their answers, gate stops with
their answer buttons, timestamps, tokens and the model's cost. Thinking, system reminders, hook
output, file bodies and subagent work are dropped; a command's output is kept short. Paths outside
the run folder are hidden and anything that looks like a secret is replaced; the export refuses
to write if a secret pattern survives.

The bundle (version 2) holds several runs, one per model; an export adds a run or replaces the run
with the same id. A version 1 script (one run) is still read and wrapped as one run.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import re
import os
from collections import Counter
from datetime import datetime, timezone
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
    # (lowercase kebab-case slugs and snake_case names of short words are kept)
    re.compile(r"(?<![\w-])(?![a-z0-9]+(?:-[a-z0-9]+){3,}(?![\w-]))"
               r"(?![a-z0-9]{1,12}(?:_[a-z0-9]{1,12}){3,}(?![\w-]))"
               r"(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{40,}(?![\w-])"),
]
ABS_PATH = re.compile(r"(?<![\w.:/~-])(?!/dev/null\b)(?:~|/[A-Za-z0-9._-]+)(?:/[A-Za-z0-9._@-]+)+/?")
TAG_BLOCK = re.compile(r"<([a-z][a-z0-9_-]*)>.*?</\1>", re.S)
ANSWER = re.compile(r'"((?:[^"\\]|\\.)*)"="((?:[^"\\]|\\.)*)"')
GATE_CMD = re.compile(r"strat gate (check|approve) (\d+)")


def _local_users() -> list[str]:
    """The login name of whoever runs the export (shows up in `ls -l` output and the like)."""
    names = set()
    try:
        names.add(getpass.getuser())
    except Exception:  # no login name in this environment
        pass
    return [n for n in names if len(n) >= 3 and n not in ("root", "user", "runner")]


def _user_pattern() -> re.Pattern | None:
    names = _local_users()
    return re.compile(r"(?<![\w.-])(?:" + "|".join(map(re.escape, names)) + r")(?![\w-])") \
        if names else None


def _hide_secrets(text: str) -> str:
    users = _user_pattern()
    if users:
        text = users.sub(HIDDEN, text)
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
    users = _user_pattern()
    patterns = SECRET_PATTERNS + ([users] if users else [])

    def walk(v):
        if isinstance(v, str):
            found.extend(m.group(0) for p in patterns for m in p.finditer(v))
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


# ---------- step groups and their Russian summary ----------

DETAIL_MAX = 400
CATEGORY = {
    "read": "read", "bash": "command", "grep": "search", "glob": "search", "websearch": "net",
    "list": "search", "ls": "search", "edit": "edit", "write": "edit", "multiedit": "edit",
    "notebookedit": "edit", "patch": "edit", "webfetch": "web", "skill": "skill", "error": None,
}
# category -> (verb, singular, few, many); order is the order in the summary
PHRASES = [
    ("read", "прочитал", "файл", "файла", "файлов"),
    ("command", "выполнил", "команду", "команды", "команд"),
    ("search", "искал", "раз", "раза", "раз"),
    ("net", "искал в интернете", "раз", "раза", "раз"),
    ("edit", "изменил", "файл", "файла", "файлов"),
    ("web", "открыл", "страницу", "страницы", "страниц"),
    ("skill", "открыл", "навык", "навыка", "навыков"),
    ("peer", "сверился с другой моделью", "раз", "раза", "раз"),
    ("other", "ещё", "действие", "действия", "действий"),
    ("fail", "", "ошибка", "ошибки", "ошибок"),
]


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def summarize_counts(counts: dict) -> str:
    parts = []
    for key, verb, one, few, many in PHRASES:
        n = counts.get(key, 0)
        if n:
            parts.append(" ".join(x for x in (verb, str(n), plural(n, one, few, many)) if x))
    text = ", ".join(parts)
    return text[:1].upper() + text[1:]


# Web search, saved web pages and second-model checks run through bin/strat inside a shell
# command; they get their own category so the research stage is visible in the summary.
STRAT_CMD = [
    (re.compile(r"\bstrat search\b"), "net"),
    (re.compile(r"\bstrat read https?://"), "web"),
    (re.compile(r"\bstrat (?:consult|judge|review)\b"), "peer"),
]


def category(item: dict) -> str | None:
    tool = item["tool"].lower()
    if tool == "bash":
        for pattern, cat in STRAT_CMD:
            if pattern.search(item.get("line", "")):
                return cat
    return CATEGORY.get(tool, "other")


PROVIDER = {"brave": "Brave", "exa": "Exa", "tavily": "Tavily"}


def summarize(items: list[dict], web: dict | None = None) -> str:
    """Russian summary of a step group. `web` (from the case log) replaces the command count of
    searches and pages with what was really done: a shell loop may run several searches."""
    counts: Counter = Counter()
    for it in items:
        cat = category(it)
        if cat:
            counts[cat] += 1
        if it.get("ok") is False:
            counts["fail"] += 1
    if web:
        counts["net"], counts["web"] = web["searches"], web["pages"]
    text = summarize_counts(counts)
    return text


RESULTS = re.compile(r"^(\w+), (\d+) results")


def web_activity(cdir: Path) -> list[dict]:
    """Searches that answered and web pages saved, from the case log, with their times."""
    out = []
    for row in _jsonl(cdir / "log.jsonl"):
        if row.get("status") != "ok" or not row.get("ts"):
            continue
        if row.get("tool") == "search" and (m := RESULTS.match(row.get("note") or "")):
            out.append({"ts": row["ts"], "kind": "search", "provider": m.group(1),
                        "results": int(m.group(2))})
        elif row.get("tool") == "read" and str(row.get("in", "")).startswith(("http://", "https://")):
            out.append({"ts": row["ts"], "kind": "page"})
    return out


def attach_web(run: dict, cdir: Path) -> None:
    """Count, per step group and per run, the searches made, the provider that answered, the
    results returned and the pages saved, as the case log recorded them. A row belongs to the
    last step group that started before it."""
    acts = web_activity(cdir)
    start = run["meta"].get("start")
    groups = [e for e in run["events"] if e["kind"] == "steps"]
    total = {"searches": 0, "results": 0, "pages": 0, "providers": []}
    if not acts or not start or not groups:
        return
    t0 = datetime.fromisoformat(start)
    for a in acts:
        rel = (datetime.fromisoformat(a["ts"]) - t0).total_seconds()
        g = next((g for g in reversed(groups) if g["t"] <= rel + 2), None)
        if g is None:
            continue
        w = g.setdefault("web", {"searches": 0, "results": 0, "pages": 0, "providers": []})
        for box in (w, total):
            if a["kind"] == "search":
                box["searches"] += 1
                box["results"] += a["results"]
                if a["provider"] not in box["providers"]:
                    box["providers"].append(a["provider"])
            else:
                box["pages"] += 1
    for g in groups:
        if "web" in g:
            g["summary"] = summarize(g["items"], g["web"])
    run["meta"]["web"] = total


def group_steps(flat: list[dict]) -> list[dict]:
    """Consecutive step events become one `steps` event with a summary."""
    out: list[dict] = []
    for ev in flat:
        if ev["kind"] != "step":
            out.append(ev)
            continue
        if not out or out[-1]["kind"] != "steps":
            out.append({"kind": "steps", "summary": "", "items": [], "t": ev["t"]})
        g = out[-1]
        item = {k: ev[k] for k in ("tool", "line", "detail", "ok", "t") if k in ev}
        g["items"].append(item)
        if ev.get("usd"):
            g["usd"] = round(g.get("usd", 0.0) + ev["usd"], 4)
    for g in out:
        if g["kind"] == "steps":
            g["summary"] = summarize(g["items"])
    return out


def _detail(text: str, cwd: str | None) -> str | None:
    text = redact(TAG_BLOCK.sub("", text or ""), cwd).strip()
    return _shorten(text, DETAIL_MAX) if text else None


# ---------- materials named in the first message ----------

PATH_TOKEN = re.compile(r"[\w~./-]*[\w.-]/[\w./-]*\w")


def materials(text: str, cwd: str | None) -> list[dict]:
    """Files inside the repo named in `text`, as links relative to demo/replay/."""
    repo = root().resolve()
    page = repo / "demo" / "replay"
    found: list[dict] = []
    seen: set[str] = set()
    for tok in PATH_TOKEN.findall(text or ""):
        if tok.startswith(("/", "~")):
            base = (cwd or "").rstrip("/")
            if not base or not tok.startswith(base + "/"):
                continue
            tok = tok[len(base) + 1:]
        cand = (repo / tok).resolve()
        if not cand.is_relative_to(repo) or not cand.exists():
            continue
        files = [cand] if cand.is_file() else sorted(
            f for f in cand.rglob("*")
            if f.is_file() and not any(x.startswith(".") for x in f.relative_to(repo).parts))
        for f in files:
            rel = Path(os.path.relpath(f, page)).as_posix()
            if rel not in seen:
                seen.add(rel)
                found.append({"name": f.name, "path": rel})
    return found


# ---------- one run, harness-independent ----------

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


def _out_text(raw) -> str:
    if isinstance(raw, str):
        return raw
    return "\n".join(x.get("text", "") for x in raw or [] if isinstance(x, dict))


SHOW_OUTPUT = {"command", "search"}
CASE_NEW = re.compile(r"strat new ([\w-]+)")
CASE_PATH = re.compile(r"cases/([\w-]+)/")


class Recorder:
    """Collects the flat events of one run and turns them into a v2 run."""

    def __init__(self):
        self.events: list[dict] = []
        self.pending = 0.0
        self.sessions: set[str] = set()
        self.gate: int | None = None
        self.last_agent: int | None = None
        self.first_user: tuple[str, str | None] | None = None
        self.raw: list[str] = []  # raw commands and paths, to find the case

    def add(self, ev: dict, ts: datetime, session: str = "") -> int:
        ev["ts"] = ts
        if ev["kind"] != "user" and self.pending:
            ev["usd"] = self.pending
            self.pending = 0.0
        self.sessions.add(session)
        self.events.append(ev)
        return len(self.events) - 1

    def close_turn(self) -> None:
        if self.gate is not None and self.last_agent is not None:
            self.events[self.last_agent]["gate"] = {"n": self.gate, "buttons": GATE_BUTTONS,
                                                    "typed": True}
        self.gate, self.last_agent = None, None

    def user(self, text: str, ts: datetime, session: str, cwd: str | None) -> None:
        self.close_turn()
        if self.first_user is None:
            self.first_user = (text, cwd)
        text = redact(text, cwd)
        ev = self.events[-1] if self.events else None
        if ev and ev["kind"] == "user" and ev["text"] == text:
            self.events.pop()  # a resend after a failed turn (e.g. a usage limit)
        self.add({"kind": "user", "text": text}, ts, session)

    def agent(self, text: str, ts: datetime, session: str, cwd: str | None) -> None:
        self.last_agent = self.add({"kind": "agent", "text": redact(text.strip(), cwd)}, ts,
                                   session)

    def step(self, tool: str, name: str, inp: dict, ts: datetime, session: str,
             cwd: str | None) -> tuple:
        """`tool` is the harness's own name; `name` the Claude Code name used to condense."""
        self.raw.append(str(inp.get("command") or inp.get("file_path") or inp.get("path") or ""))
        i = self.add({"kind": "step", "tool": tool, "line": condense(name, inp, cwd),
                      "ok": True}, ts, session)
        m = GATE_CMD.search(inp.get("command", "")) if name == "Bash" else None
        if m and m.group(1) == "check":
            return ("check", i, int(m.group(2)), cwd)
        if m and self.gate == int(m.group(2)):
            self.gate = None
        return ("step", i, None, cwd)

    def error(self, message: str, ts: datetime, session: str, cwd: str | None) -> None:
        self.add({"kind": "step", "tool": "error",
                  "line": redact("ошибка модели: " + _shorten(message, 200), cwd), "ok": False},
                 ts, session)

    def result(self, ref: tuple, ok: bool, output: str) -> None:
        kind, i, n, cwd = ref
        ev = self.events[i]
        ev["ok"] = ok
        if CATEGORY.get(ev["tool"].lower(), "other") in SHOW_OUTPUT:
            d = _detail(output, cwd)
            if d:
                ev["detail"] = d
        if kind == "check" and ok:
            self.gate = n

    def question(self, questions: list, ts: datetime, session: str, cwd: str | None) -> int:
        qs = [{"header": redact(q.get("header", ""), cwd),
               "question": redact(q.get("question", ""), cwd),
               "options": [redact(o.get("label", "") if isinstance(o, dict) else str(o), cwd)
                           for o in q.get("options") or []],
               "multi": bool(q.get("multiSelect") or q.get("multiple"))} for q in questions]
        return self.add({"kind": "question", "questions": qs, "answers": []}, ts, session)

    def answer(self, i: int, pairs: list[tuple[str, str]], cwd: str | None) -> None:
        self.events[i]["answers"] = [{"question": redact(q, cwd), "answer": redact(a, cwd)}
                                     for q, a in pairs]

    def case(self) -> str:
        for pat in (CASE_NEW, CASE_PATH):
            for s in self.raw:
                if (m := pat.search(s)):
                    return m.group(1)
        return ""

    def finish(self, prices_known: bool, minutes: float | None = None) -> dict:
        events = self.events
        self.close_turn()
        if not events:
            raise StratError("no conversation in the transcripts", UNAVAILABLE)
        if self.pending:
            last = next((e for e in reversed(events) if e["kind"] != "user"), events[-1])
            last["usd"] = last.get("usd", 0.0) + self.pending
        # gate answers: approved later -> the first button, otherwise the second
        for i, ev in enumerate(events):
            if "gate" in ev:
                n = ev["gate"]["n"]
                approved = any(e["kind"] == "step" and re.search(rf"strat gate approve {n}\b",
                                                                 e["line"]) for e in events[i:])
                replied = any(e["kind"] == "user" or (e["kind"] == "question" and e["answers"])
                              for e in events[i + 1:])
                ev["gate"]["chosen"] = 0 if approved else (1 if replied else None)
        start = events[0]["ts"]
        total = 0.0
        for ev in events:
            ev["t"] = int((ev.pop("ts") - start).total_seconds())
            if "usd" in ev:
                ev["usd"] = round(ev["usd"], 4)
                total += ev["usd"]
        text, cwd = self.first_user or ("", None)
        meta = {
            "date": start.date().isoformat(),
            "start": start.isoformat(),
            "minutes": minutes if minutes is not None else round(events[-1]["t"] / 60, 1),
            "usd": round(total, 4) if prices_known else None,
            "sessions": len(self.sessions),
            "gates": sum("gate" in e for e in events),
            "steps": sum(e["kind"] == "step" for e in events),
            "priced": prices_known,
        }
        return {"case": self.case(), "meta": meta, "materials": materials(text, cwd),
                "events": group_steps(events), "_cwd": cwd}


def _run(rec_run: dict, run_id: str | None, label: str | None, model: str, harness: str,
         case: str | None, tokens: dict | None) -> dict:
    meta = rec_run["meta"]
    if tokens is not None:
        meta["tokens"] = tokens
    return {"id": run_id or _slug(model or harness), "label": label or "Запись реального прогона",
            "model": model, "harness": harness, "case": case or rec_run["case"], "meta": meta,
            "materials": rec_run["materials"], "events": rec_run["events"],
            "_cwd": rec_run.get("_cwd")}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "run"


# ---------- Claude Code ----------

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


def build(folder: Path, label: str | None = None, run_id: str | None = None,
          model: str | None = None, case: str | None = None) -> dict:
    """One run from the Claude Code transcripts in `folder`."""
    from strat.cost import _price

    prices = load_config("prices")
    rec = Recorder()
    seen_msgs: set[str] = set()
    models: Counter = Counter()
    tokens = {"input": 0, "output": 0, "cache_read": 0}
    tools: dict[str, tuple] = {}  # tool id -> ref

    for d in _entries(folder):
        msg = d.get("message") or {}
        cwd = d.get("cwd")
        ts, sid = _ts(d["timestamp"]), d.get("sessionId", "")
        if d["type"] == "assistant":
            m = msg.get("model", "")
            if m == "<synthetic>":
                continue
            mid = msg.get("id") or d.get("uuid") or d["timestamp"]
            if msg.get("usage") and mid not in seen_msgs:
                seen_msgs.add(mid)
                models[m] += 1
                u = msg["usage"]
                tokens["input"] += (u.get("input_tokens") or 0) + (
                    u.get("cache_creation_input_tokens") or 0)
                tokens["output"] += u.get("output_tokens") or 0
                tokens["cache_read"] += u.get("cache_read_input_tokens") or 0
                if m in prices:
                    rec.pending += _price(u, prices[m])
            for b in msg.get("content") or []:
                if b.get("type") == "text" and b.get("text", "").strip():
                    rec.agent(b["text"], ts, sid, cwd)
                elif b.get("type") == "tool_use":
                    name, inp = b.get("name", ""), b.get("input") or {}
                    if name == "AskUserQuestion":
                        tools[b["id"]] = ("ask", rec.question(inp.get("questions") or [], ts,
                                                              sid, cwd), None, cwd)
                    else:
                        tools[b["id"]] = rec.step(name, name, inp, ts, sid, cwd)
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
                    out = _out_text(b.get("content"))
                    if ref[0] == "ask":
                        if not err:
                            rec.answer(ref[1], ANSWER.findall(out), cwd)
                    else:
                        rec.result(ref, not err, out)
            text = _user_text(content)
            if text is not None:
                rec.user(text, ts, sid, cwd)
    run = rec.finish(prices_known=all(m in prices for m in models))
    main = models.most_common(1)[0][0] if models else ""
    return _run(run, run_id, label, model or main, "claude-code", case,
                tokens if models else None)


# ---------- OpenCode ----------

OC_NAMES = {"bash": "Bash", "read": "Read", "write": "Write", "edit": "Edit", "patch": "Edit",
            "multiedit": "Edit", "grep": "Grep", "glob": "Glob", "list": "Glob",
            "webfetch": "WebFetch", "websearch": "WebSearch", "skill": "Skill",
            "todowrite": "TodoWrite", "task": "Task"}
TIMES = re.compile(r"turn (\S+) rc=(-?\d+) secs=(\d+(?:\.\d+)?)")


def turn_key(n: str) -> list:
    return [int(x) if x.isdigit() else x for x in re.findall(r"\d+|\D+", n)]


def _oc_input(tool: str, inp: dict) -> dict:
    out = dict(inp)
    if "filePath" in inp:
        out["file_path"] = inp["filePath"]
    if tool == "skill":
        out["skill"] = inp.get("name", "")
    return out


def _oc_cwd(rows: list[dict]) -> str | None:
    """The run folder, from the absolute paths the agent's tools touched."""
    markers = {"cases"} | {p.name for p in root().iterdir()}
    found: Counter = Counter()
    for d in rows:
        inp = ((d.get("part") or {}).get("state") or {}).get("input") or {}
        for key in ("filePath", "path"):
            p = inp.get(key)
            if isinstance(p, str) and p.startswith("/"):
                parts = p.split("/")
                for i in range(1, len(parts)):
                    if parts[i] in markers:
                        found["/".join(parts[:i])] += 1
                        break
    return found.most_common(1)[0][0] if found else None


IDLE_GAP = 15 * 60  # longer silence inside a turn: the machine slept or the run was paused


def active_minutes(logs: dict[str, list[dict]], secs: dict[str, float]) -> float | None:
    """Working time. Each turn counts its measured wall time (times.txt) or, without it, the span
    of its events; silences longer than IDLE_GAP inside the turn, or after its last event, are
    left out (a run that slept 90 minutes must not show 90 minutes of work)."""
    total = 0.0
    for n, rows in logs.items():
        ts = sorted(d["timestamp"] / 1000 for d in rows if d.get("timestamp") is not None)
        if not ts:
            total += secs.get(n, 0.0)
            continue
        span = ts[-1] - ts[0]
        idle = sum(b - a for a, b in zip(ts, ts[1:]) if b - a > IDLE_GAP)
        wall = secs.get(n, span)
        tail = wall - span
        total += wall - idle - (tail if tail > IDLE_GAP else 0)
    return round(total / 60, 1) if total else None


def build_opencode(folder: Path, label: str | None = None, run_id: str | None = None,
                   model: str | None = None, case: str | None = None) -> dict:
    """One run from a folder of OpenCode `run --format json` turn logs."""
    turns = sorted((f.name[: -len(".jsonl")] for f in folder.glob("*.jsonl")), key=turn_key)
    if not turns:
        raise StratError(f"no OpenCode turn logs in {folder}", UNAVAILABLE)
    logs: dict[str, list[dict]] = {}
    for n in turns:
        rows = []
        for line in (folder / f"{n}.jsonl").read_text(encoding="utf-8",
                                                     errors="replace").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        logs[n] = rows
    cwd = _oc_cwd([d for rows in logs.values() for d in rows])
    secs = {}
    if (folder / "times.txt").is_file():
        for m in TIMES.finditer((folder / "times.txt").read_text(encoding="utf-8")):
            secs[m.group(1)] = float(m.group(3))

    def when(ms) -> datetime:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)

    rec = Recorder()
    tokens = {"input": 0, "output": 0, "cache_read": 0}
    cost = 0.0
    for n in turns:
        rows = logs[n]
        sid = next((d.get("sessionID", "") for d in rows if d.get("sessionID")), "")
        first = next((d["timestamp"] for d in rows if d.get("timestamp")), None)
        prompt = folder / f"{n}.prompt.txt"
        if prompt.is_file() and first is not None:
            text = TAG_BLOCK.sub("", prompt.read_text(encoding="utf-8")).strip()
            if text:
                rec.user(text, when(first), sid, cwd)
        for d in rows:
            kind, part = d.get("type"), d.get("part") or {}
            if not d.get("timestamp"):
                continue
            ts = when(d["timestamp"])
            if kind == "text" and (part.get("text") or "").strip():
                rec.agent(part["text"], ts, sid, cwd)
            elif kind == "tool_use":
                tool = part.get("tool", "")
                state = part.get("state") or {}
                inp = _oc_input(tool, state.get("input") or {})
                ref = rec.step(tool, OC_NAMES.get(tool, tool), inp, ts, sid, cwd)
                rec.result(ref, state.get("status") != "error",
                           _out_text(state.get("output") or state.get("error") or ""))
            elif kind == "step_finish":
                t = part.get("tokens") or {}
                tokens["input"] += (t.get("input") or 0) + ((t.get("cache") or {}).get("write")
                                                             or 0)
                tokens["output"] += (t.get("output") or 0) + (t.get("reasoning") or 0)
                tokens["cache_read"] += (t.get("cache") or {}).get("read") or 0
                c = float(part.get("cost") or 0)
                cost += c
                rec.pending += c
            elif kind == "error":
                err = d.get("error") or {}
                rec.error(str((err.get("data") or {}).get("message") or err.get("name") or
                              "ошибка"), ts, sid, cwd)
    minutes = active_minutes(logs, secs)
    run = rec.finish(prices_known=cost > 0, minutes=minutes)
    return _run(run, run_id, label, model or "", "opencode", case, tokens)


# ---------- claims and sources of the run's case ----------

CLAIM_FIELDS = ("id", "type", "text", "source", "where", "quote")


def find_case_dir(run_folder: str | None, case: str | None) -> Path | None:
    """`<run folder>/cases/<case>` when it holds claims; a case is a plain folder name."""
    if not run_folder or not case or not re.fullmatch(r"[\w-]+", case):
        return None
    cdir = Path(run_folder) / "cases" / case
    return cdir if (cdir / "claims.jsonl").is_file() else None


def _jsonl(path: Path) -> list[dict]:
    rows = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def _sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _source_link(entry: dict, cdir: Path, mats: list[dict]) -> str | None:
    """The original material as a link relative to demo/replay/, only when it is a repo file."""
    if entry.get("kind") != "file" or not entry.get("origin"):
        return None
    repo = root().resolve()
    page = repo / "demo" / "replay"
    orig = (cdir / entry["origin"]).resolve()
    if orig.is_relative_to(repo) and orig.is_file():
        return Path(os.path.relpath(orig, page)).as_posix()
    want = entry.get("sha256") or _sha(orig)
    for m in mats:
        cand = (page / m["path"]).resolve()
        if (cand.name == orig.name and cand.is_relative_to(repo) and want
                and _sha(cand) == want):
            return m["path"]
    return None


def case_evidence(cdir: Path, mats: list[dict]) -> dict:
    """Active and replaced claims and the sources they cite, scrubbed, without absolute paths."""
    cwd = str(cdir.resolve().parent.parent)
    claims = []
    for c in _jsonl(cdir / "claims.jsonl"):
        if c.get("status") not in ("active", "replaced") or not c.get("id"):
            continue
        claims.append({k: (redact(str(c[k]), cwd) if c.get(k) is not None else None)
                       for k in CLAIM_FIELDS})
    sources = [{"id": s["id"], "title": redact(str(s.get("title") or s["id"]), cwd),
                "kind": s.get("kind") or "", "path": _source_link(s, cdir, mats)}
               for s in _jsonl(cdir / "sources" / "index.jsonl") if s.get("id")]
    return {"claims": claims, "sources": sources}


# ---------- the bundle ----------

def from_v1(script: dict, run_id: str) -> dict:
    """A version 1 script (one run, flat steps) as one v2 run."""
    meta = dict(script.get("meta") or {})
    label, model = meta.pop("label", None), meta.pop("model", "")
    flat: list[dict] = []
    for ev in script.get("events") or []:
        ev = dict(ev)
        if ev["kind"] == "question":
            buttons = ev.get("buttons") or []
            chosen = ev.get("chosen")
            ev = {"kind": "question", "t": ev.get("t", 0),
                  "questions": [{"header": "", "question": ev.get("text", ""),
                                 "options": buttons, "multi": False}],
                  "answers": [{"question": ev.get("text", ""), "answer": buttons[chosen]}]
                  if chosen is not None and chosen < len(buttons) else []}
        elif ev["kind"] == "user" and ev.get("via") == "button" and flat \
                and flat[-1]["kind"] == "question":
            continue  # the answer is part of the question event now
        flat.append(ev)
    rec = Recorder()
    rec.raw = [e.get("line", "") for e in flat if e["kind"] == "step"]
    first = next((e["text"] for e in flat if e["kind"] == "user"), "")
    return {"id": run_id, "label": label or "Запись реального прогона", "model": model,
            "harness": "claude-code", "case": rec.case(), "meta": meta,
            "materials": materials(first, None), "events": group_steps(flat)}


def load_bundle(path: Path, legacy_id: str = "legacy") -> dict:
    if not path.is_file():
        return {"version": 2, "runs": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") == 2:
        return data
    return {"version": 2, "runs": [from_v1(data, legacy_id)]}


def put_run(bundle: dict, run: dict) -> dict:
    runs = bundle["runs"]
    for i, r in enumerate(runs):
        if r["id"] == run["id"]:
            runs[i] = run
            break
    else:
        runs.append(run)
    return bundle


def embed(page: Path, script: dict) -> None:
    """Put the bundle into the page, so it plays from file:// without a fetch."""
    html = page.read_text(encoding="utf-8")
    data = json.dumps(script, ensure_ascii=False).replace("</", "<\\/")
    new, n = re.subn(r'(<script id="replay-data" type="application/json">).*?(</script>)',
                     lambda m: m.group(1) + data + m.group(2), html, count=1, flags=re.S)
    if n != 1:
        raise StratError(f"{page}: no replay-data block")
    page.write_text(new, encoding="utf-8")


def write_bundle(target: Path, bundle: dict) -> bool:
    """Refuse on a surviving secret; write script.json and embed it into index.html next to it."""
    bad = leaked(bundle)
    if bad:
        raise StratError(f"refusing to write: {len(bad)} secret-like strings survived redaction",
                         FAILED)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(bundle, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    page = target.parent / "index.html"
    if page.is_file():
        embed(page, bundle)
    return page.is_file()


def export(case: str | None = None, transcripts: str | None = None, out: str | None = None,
           label: str | None = None, as_json: bool = False, opencode: str | None = None,
           run_id: str | None = None, model: str | None = None,
           case_dir: str | None = None) -> int:
    """Add (or replace by id) one run in demo/replay/script.json and embed it into the page."""
    from strat.cost import transcripts_dir

    if transcripts and opencode:
        raise StratError("give either --transcripts or --opencode, not both")
    if opencode:
        folder = Path(opencode)
        if not folder.is_dir() or not any(folder.glob("*.jsonl")):
            raise StratError(f"no OpenCode turn logs in {folder}", UNAVAILABLE)
        run = build_opencode(folder, label, run_id, model, case)
    else:
        folder = Path(transcripts) if transcripts else transcripts_dir()
        if not folder.is_dir() or not any(folder.glob("*.jsonl")):
            raise StratError(f"no session transcripts in {folder}", UNAVAILABLE)
        run = build(folder, label, run_id, model, case)
    run_folder = run.pop("_cwd", None)
    if case_dir and not (Path(case_dir) / "claims.jsonl").is_file():
        raise StratError(f"no claims.jsonl in {case_dir}", UNAVAILABLE)
    cdir = Path(case_dir) if case_dir else find_case_dir(run_folder, run["case"])
    if cdir:
        run.update(case_evidence(cdir, run["materials"]))
        attach_web(run, cdir)
    target = Path(out) if out else root() / "demo" / "replay" / "script.json"
    bundle = put_run(load_bundle(target), run)
    embedded = write_bundle(target, bundle)
    m = run["meta"]
    usd = "no price" if m["usd"] is None else f"{m['usd']} usd (API list prices)"
    emit(f"wrote {target}: run {run['id']} ({run['harness']}, {run['model'] or 'model unknown'}): "
         f"{len(run['events'])} events, {m['steps']} steps, {m['gates']} gates, "
         f"{m['minutes']} min, {usd}, {len(run.get('claims', []))} claims; bundle has {len(bundle['runs'])} runs"
         + ("; embedded into index.html" if embedded else ""),
         {"out": str(target), "id": run["id"], "meta": m, "runs": [r["id"] for r in bundle["runs"]],
          "embedded": embedded}, as_json)
    return 0
