"""Cost: time and money by stage from log.jsonl."""

import json


def write_log(case, rows):
    with (case / "log.jsonl").open("a") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def row(step, stage, ts, usd=0.0, status="ok", tool="agent", tin=0, tout=0):
    return {"step": step, "ts": ts, "stage": stage, "tool": tool, "in": "", "out": "",
            "tokens_in": tin, "tokens_out": tout, "usd": usd, "status": status, "note": ""}


def test_cost_of_a_new_case_is_zero(strat, case):
    r = strat("cost", "--json")
    assert r.code == 0 and r.data["total"]["usd"] == 0


def test_cost_by_stage(strat, case):
    write_log(case, [
        row("intake.brief", "intake", "2026-11-15T10:00:00+03:00"),
        row("plan.options", "plan", "2026-11-15T10:10:00+03:00"),
        row("research.q1.search.1", "research", "2026-11-15T10:30:00+03:00", usd=0.005,
            tool="search"),
        row("research.q1.search.2", "research", "2026-11-15T10:31:00+03:00", usd=0.5,
            status="error", tool="search"),
        row("research.q1.read.1", "research", "2026-11-15T10:45:00+03:00", tin=100, tout=20),
    ])
    r = strat("cost", "--json")
    by = {s["stage"]: s for s in r.data["stages"]}
    assert by["research"]["usd"] == 0.505  # failed calls still cost money
    assert by["research"]["steps"] == 3 and by["research"]["errors"] == 1
    assert by["intake"]["minutes"] == 10.0 and by["plan"]["minutes"] == 20.0
    assert by["research"]["tokens_in"] == 100
    assert r.data["total"]["usd"] == 0.505
    text = strat("cost").out
    assert "research" in text and "0.505" in text
