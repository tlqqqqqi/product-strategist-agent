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


def transcript_line(ts, model="claude-opus-5-5", cwd=None, **usage):
    u = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
         "cache_creation_input_tokens": 0,
         "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0}}
    for k, v in usage.items():
        if k in ("w5m", "w1h"):
            key = "ephemeral_5m_input_tokens" if k == "w5m" else "ephemeral_1h_input_tokens"
            u["cache_creation"][key] = v
            u["cache_creation_input_tokens"] += v
        else:
            u[k] = v
    return json.dumps({"type": "assistant", "timestamp": ts, "cwd": cwd,
                       "message": {"id": ts, "model": model, "usage": u}})


def test_ide_usage_is_priced_and_assigned_to_stages(strat, case, tmp_path, monkeypatch):
    from strat.core import root

    # pin the case's creation time: cost counts transcript lines from 15 min before it, and the
    # real clock would otherwise drop the fixed transcript times below once the day moves on
    state = json.loads((case / "state.json").read_text())
    state["created"] = "2026-11-15T10:00:00+03:00"
    (case / "state.json").write_text(json.dumps(state, ensure_ascii=False))

    write_log(case, [
        row("intake.brief", "intake", "2026-11-15T10:00:00+03:00"),
        row("gate1.approve", "gate1", "2026-11-15T10:20:00+03:00", tool="gate"),
    ])
    tdir = tmp_path / "transcripts"
    tdir.mkdir()
    cwd = str(root())
    (tdir / "s1.jsonl").write_text("\n".join([
        transcript_line("2026-11-15T07:05:00Z", cwd=cwd, input_tokens=1_000_000),     # intake
        transcript_line("2026-11-15T07:25:00Z", cwd=cwd, output_tokens=100_000,
                        cache_read_input_tokens=1_000_000, w1h=1_000_000),             # gate1
        transcript_line("2026-11-15T07:26:00Z", cwd="/elsewhere", input_tokens=9),     # other
        json.dumps({"type": "user", "timestamp": "2026-11-15T07:06:00Z"}),
    ]) + "\n")
    monkeypatch.setenv("STRAT_TRANSCRIPTS", str(tdir))
    d = strat("cost", "--json").data
    ide = {s["stage"]: s for s in d["ide"]["stages"]}
    assert ide["intake"]["usd"] == 4.0                    # 1M input at $4
    assert ide["gate1"]["usd"] == 2.0 + 0.2 + 8.0          # output + cache read + 1h write
    assert d["ide"]["total"]["usd"] == 14.2 and d["ide"]["source"] == "claude-code transcripts"
    assert "IDE model" in strat("cost").out


def test_ide_usage_of_a_later_case_is_not_counted(strat, case, cases, tmp_path, monkeypatch):
    from strat.core import root

    write_log(case, [row("intake.brief", "intake", "2026-11-15T10:00:00+03:00")])
    mine = json.loads((case / "state.json").read_text())
    mine["created"] = "2026-11-15T10:00:00+03:00"  # pinned, see the test above
    (case / "state.json").write_text(json.dumps(mine, ensure_ascii=False))
    other = json.loads((case / "state.json").read_text())
    other["created"] = "2026-11-15T11:00:00+03:00"
    (cases / "later").mkdir()
    (cases / "later" / "state.json").write_text(json.dumps(other))
    tdir = tmp_path / "transcripts"
    tdir.mkdir()
    cwd = str(root())
    (tdir / "s.jsonl").write_text("\n".join([
        transcript_line("2026-11-15T07:05:00Z", cwd=cwd, input_tokens=1_000_000),  # this case
        transcript_line("2026-11-15T08:30:00Z", cwd=cwd, input_tokens=1_000_000),  # later case
        transcript_line("2026-11-15T07:06:00Z", input_tokens=1_000_000),           # no cwd
    ]) + "\n")
    monkeypatch.setenv("STRAT_TRANSCRIPTS", str(tdir))
    assert strat("cost", "--case", "demo", "--json").data["ide"]["total"]["usd"] == 4.0
