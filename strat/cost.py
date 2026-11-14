"""Time and money by stage, from log.jsonl.

Money counts every logged call, failed ones included. Time per stage is wall-clock: from the
first line of a stage to the first line of the next one (the last stage ends at its last line).
The IDE model's own usage is not in the log. In Claude Code it is read from the session
transcripts of this folder (~/.claude/projects/<folder>/*.jsonl), priced with
config/prices.yaml, and assigned to the stage that was current when each model call was made.
Elsewhere it is not available and the output says so.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

from strat.core import case_path, emit, load_config, read_jsonl, root


def by_stage(rows: list[dict]) -> list[dict]:
    stages: dict[str, dict] = {}
    order: list[str] = []
    for i, row in enumerate(rows):
        name = row.get("stage", "?")
        if name not in stages:
            stages[name] = {"stage": name, "steps": 0, "errors": 0, "usd": 0.0,
                            "tokens_in": 0, "tokens_out": 0, "seconds": 0.0}
            order.append(name)
        s = stages[name]
        s["steps"] += 1
        s["errors"] += row.get("status") != "ok"
        s["usd"] += float(row.get("usd") or 0)
        s["tokens_in"] += int(row.get("tokens_in") or 0)
        s["tokens_out"] += int(row.get("tokens_out") or 0)
        start = datetime.fromisoformat(row["ts"])
        end = datetime.fromisoformat(rows[i + 1]["ts"]) if i + 1 < len(rows) else start
        s["seconds"] += max((end - start).total_seconds(), 0.0)
    out = []
    for name in order:
        s = stages[name]
        s["usd"] = round(s["usd"], 6)
        s["minutes"] = round(s.pop("seconds") / 60, 1)
        out.append(s)
    return out


def transcripts_dir() -> Path:
    env = os.environ.get("STRAT_TRANSCRIPTS")
    if env:
        return Path(env)
    return Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(root()))


def _price(usage: dict, p: dict) -> float:
    cc = usage.get("cache_creation") or {}
    w5 = cc.get("ephemeral_5m_input_tokens")
    w1 = cc.get("ephemeral_1h_input_tokens")
    if w5 is None and w1 is None:  # older format: all writes at the 5 minute price
        w5, w1 = usage.get("cache_creation_input_tokens", 0), 0
    return (usage.get("input_tokens", 0) * p["input"] + usage.get("output_tokens", 0) * p["output"]
            + (w5 or 0) * p["cache_write_5m"] + (w1 or 0) * p["cache_write_1h"]
            + usage.get("cache_read_input_tokens", 0) * p["cache_read"]) / 1_000_000


def ide_usage(rows: list[dict], created: str | None) -> dict:
    """The IDE model's usage by stage, from Claude Code transcripts of this folder."""
    folder = transcripts_dir()
    if not folder.is_dir():
        return {"source": "unavailable", "stages": [], "total": {"usd": 0.0, "calls": 0},
                "note": "no Claude Code transcripts for this folder; the IDE model's usage is "
                        "not known to the CLI"}
    prices = load_config("prices")
    since = (datetime.fromisoformat(created) - timedelta(minutes=15)) if created else None
    marks = [(datetime.fromisoformat(r["ts"]), r["stage"]) for r in rows]
    calls: dict[str, tuple[datetime, str, dict]] = {}
    for f in folder.glob("*.jsonl"):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            msg = d.get("message") or {}
            if (d.get("type") != "assistant" or not msg.get("usage") or not d.get("timestamp")
                    or msg.get("model") == "<synthetic>"):  # local placeholders, no API call
                continue
            if d.get("cwd") and Path(d["cwd"]).resolve() != root():
                continue
            ts = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00"))
            if since and ts < since:
                continue
            calls[msg.get("id") or f"{f.name}:{d['timestamp']}"] = (ts, msg.get("model", ""),
                                                                     msg["usage"])
    stages: dict[str, dict] = {}
    unpriced: set[str] = set()
    for ts, model, usage in sorted(calls.values(), key=lambda c: c[0]):
        stage = marks[0][1] if marks else "intake"
        for when, name in marks:
            if when <= ts:
                stage = name
        s = stages.setdefault(stage, {"stage": stage, "calls": 0, "tokens_in": 0,
                                      "tokens_out": 0, "usd": 0.0})
        s["calls"] += 1
        s["tokens_in"] += (usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
                           + usage.get("cache_creation_input_tokens", 0))
        s["tokens_out"] += usage.get("output_tokens", 0)
        if model in prices:
            s["usd"] += _price(usage, prices[model])
        else:
            unpriced.add(model)
    out = [dict(v, usd=round(v["usd"], 4)) for v in stages.values()]
    return {"source": "claude-code transcripts", "stages": out,
            "total": {"usd": round(sum(v["usd"] for v in out), 4),
                      "calls": sum(v["calls"] for v in out)},
            "note": ("models without a price: " + ", ".join(sorted(unpriced))) if unpriced
            else "API list prices; on a subscription this is the equivalent value, not a bill"}


def cost(case: str | None = None, as_json: bool = False) -> int:
    """Print time and money by stage."""
    cdir = case_path(case)
    rows = read_jsonl(cdir / "log.jsonl")
    stages = by_stage(rows)
    total = {k: round(sum(s[k] for s in stages), 6)
             for k in ("steps", "errors", "usd", "tokens_in", "tokens_out", "minutes")}
    lines = [f"{'stage':12} {'steps':>5} {'errors':>6} {'minutes':>8} {'usd':>9}"]
    for s in stages:
        lines.append(f"{s['stage']:12} {s['steps']:>5} {s['errors']:>6} {s['minutes']:>8} "
                     f"{s['usd']:>9}")
    lines.append(f"{'total':12} {total['steps']:>5} {total['errors']:>6} {total['minutes']:>8} "
                 f"{total['usd']:>9}")
    lines.append("(CLI calls: search, read, source add and the agent's logged steps)")
    from strat.state import load as load_state

    ide = ide_usage(rows, load_state(cdir).get("created"))
    lines.append("")
    lines.append(f"IDE model ({ide['source']}):")
    for s in ide["stages"]:
        lines.append(f"  {s['stage']:12} {s['calls']:>5} calls {s['tokens_in']:>10} in "
                     f"{s['tokens_out']:>8} out {s['usd']:>9} usd")
    lines.append(f"  {'total':12} {ide['total']['calls']:>5} calls {'':>10}    {'':>8}     "
                 f"{ide['total']['usd']:>9} usd")
    lines.append(f"  note: {ide['note']}")
    emit("\n".join(lines), {"stages": stages, "total": total, "ide": ide}, as_json)
    return 0
