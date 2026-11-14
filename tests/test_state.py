"""State and log: new, state, step (idempotent by id), stage moves, gate approve, resume."""

import json

from strat.core import read_jsonl


def state_of(case):
    return json.loads((case / "state.json").read_text())


def test_new_case_starts_at_intake(strat, cases):
    assert strat("new", "demo", "--title", "Sample").code == 0
    r = strat("state", "--json")
    assert r.code == 0 and r.data["stage"] == "intake"
    assert r.data["gates"] == {"1": "pending", "2": "pending", "3": "pending"}
    assert (cases / ".current").read_text().strip() == "demo"
    assert (cases / "demo" / "claims.jsonl").is_file()


def test_new_case_has_the_working_folders(strat, cases):
    """Skills write into these folders directly (e.g. `> analysis/q1_x.txt`)."""
    assert strat("new", "folders", "--title", "T").code == 0
    for d in ("materials", "sources", "analysis"):
        assert (cases / "folders" / d).is_dir(), d


def test_new_refuses_an_existing_case_and_a_bad_id(strat, cases):
    assert strat("new", "demo", "--title", "A").code == 0
    assert strat("new", "demo", "--title", "B").code == 1
    assert strat("new", "../evil", "--title", "C").code == 1


def test_state_text_names_stage_and_next(strat, case):
    strat("step", "intake.brief", "--out", "materials/product.docx", "--next", "Составить план")
    r = strat("state")
    assert "stage: intake" in r.out and "next: Составить план" in r.out
    assert "intake.brief" in r.out


def test_step_is_logged_once_and_replays(strat, case):
    first = strat("step", "intake.brief", "--stage", "plan", "--next", "draft options", "--json")
    assert first.code == 0 and first.data["replayed"] is False
    again = strat("step", "intake.brief", "--stage", "research", "--next", "other", "--json")
    assert again.code == 0 and again.data["replayed"] is True
    assert len([r for r in read_jsonl(case / "log.jsonl") if r["step"] == "intake.brief"]) == 1
    assert state_of(case)["stage"] == "plan"  # the replay changed nothing
    assert state_of(case)["next"] == "draft options"


def test_step_out_file_must_exist(strat, case):
    r = strat("step", "intake.brief", "--out", "brief.md")
    assert r.code == 1 and "brief.md" in r.err
    assert read_jsonl(case / "log.jsonl") == [] or all(
        row["step"] != "intake.brief" for row in read_jsonl(case / "log.jsonl"))


def test_step_cannot_skip_a_gate(strat, case):
    r = strat("step", "x", "--stage", "research")
    assert r.code == 1 and "gate 1" in r.err
    r = strat("step", "y", "--stage", "gate1")
    assert r.code == 1 and "gate check" in r.err
    assert state_of(case)["stage"] == "intake"


def test_gate_approve_needs_the_gate_stage(strat, case):
    r = strat("gate", "approve", "1")
    assert r.code == 1 and "gate check 1" in r.err
    assert state_of(case)["gates"]["1"] == "pending"


def test_gate_approve_advances_and_logs(strat, case, monkeypatch):
    monkeypatch.setattr("strat.validate.gate_errors", lambda cdir, n: [])  # files: test_validate
    s = state_of(case)
    s["stage"] = "gate1"
    (case / "state.json").write_text(json.dumps(s))
    r = strat("gate", "approve", "1", "--json")
    assert r.code == 0
    s = state_of(case)
    assert s["stage"] == "research" and s["gates"]["1"] == "approved"
    assert any(row["step"] == "gate1.approve" for row in read_jsonl(case / "log.jsonl"))
    # a second approval is a replay, not a second advance
    assert strat("gate", "approve", "1").code == 0
    assert state_of(case)["stage"] == "research"


def test_restart_resumes_at_last_finished_step(strat, case):
    """A crash between writing the output and logging means the step runs again."""
    strat("step", "plan.options", "--stage", "plan", "--next", "write notes.md")
    (case / "notes.md").write_text("half-written")  # crash: file written, no log line
    r = strat("state", "--json")
    assert r.data["last_step"]["step"] == "plan.options"
    assert r.data["next"] == "write notes.md"
    (case / "notes.md").write_text("done")
    redo = strat("step", "plan.notes", "--out", "notes.md", "--json")
    assert redo.data["replayed"] is False


def test_logged_usd_is_added_to_the_budget(case):
    from strat.state import log_action

    log_action(case, step="research.q1.search.1", tool="search", stage="research",
               in_="q", out="sources/S001.md", usd=0.25)
    assert state_of(case)["budget"]["spent_usd"] == 0.25


def test_case_option_cannot_escape_the_cases_dir(strat, case, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "state.json").write_text("{}")
    r = strat("state", "--case", "../outside")
    assert r.code == 3 and "bad case id" in r.err


def test_step_id_reused_by_another_command_is_refused(strat, case):
    assert strat("source", "add", "materials/competitor.html", "--step", "research.q1.1").code == 0
    r = strat("claim", "add", "--type", "gap", "--kind", "market", "--text", "x",
              "--step", "research.q1.1")
    assert r.code == 1 and "already used by `source add`" in r.err
