"""Time and money by stage, from log.jsonl.

Money counts every logged call, failed ones included. Time per stage is wall-clock: from the
first line of a stage to the first line of the next one (the last stage ends at its last line).
The IDE model's own usage is not in the log; it is reported separately.
"""

from __future__ import annotations

from datetime import datetime

from strat.core import case_path, emit, read_jsonl


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


def cost(case: str | None = None, as_json: bool = False) -> int:
    """Print time and money by stage."""
    cdir = case_path(case)
    stages = by_stage(read_jsonl(cdir / "log.jsonl"))
    total = {k: round(sum(s[k] for s in stages), 6)
             for k in ("steps", "errors", "usd", "tokens_in", "tokens_out", "minutes")}
    lines = [f"{'stage':12} {'steps':>5} {'errors':>6} {'minutes':>8} {'usd':>9}"]
    for s in stages:
        lines.append(f"{s['stage']:12} {s['steps']:>5} {s['errors']:>6} {s['minutes']:>8} "
                     f"{s['usd']:>9}")
    lines.append(f"{'total':12} {total['steps']:>5} {total['errors']:>6} {total['minutes']:>8} "
                 f"{total['usd']:>9}")
    lines.append("CLI calls only; the IDE model's own usage is not included.")
    emit("\n".join(lines), {"stages": stages, "total": total}, as_json)
    return 0
