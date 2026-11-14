"""strat ingest (Task 10): new material after a decision is registered as a source, the case
moves to revision, and the output tells the agent what to do next."""

import shutil

from strat.core import read_json, read_jsonl
from test_review import REVISION, decided  # noqa: F401  (fixture)


def test_ingest_registers_the_material_and_moves_to_revision(strat, decided, tmp_path):
    src = tmp_path / "retention-nov.csv"
    shutil.copy(REVISION / "retention-nov.csv", src)
    r = strat("ingest", str(src), "--json")
    assert r.code == 0, r.err
    assert r.data["id"] == "S002"
    assert (decided / "materials" / "retention-nov.csv").is_file()
    assert "40.1" in (decided / r.data["snapshot"]).read_text(encoding="utf-8")
    # what the agent checks the new claims against
    assert r.data["load_bearing"] == ["C001", "C002", "C003", "C004", "C005"]
    assert any("judge contradiction" in s for s in r.data["next_steps"])
    state = read_json(decided / "state.json")
    assert state["stage"] == "revision" and "S002" in state["next"]
    assert [row["ref"] for row in read_jsonl(decided / "log.jsonl")
            if row["tool"] == "ingest"] == ["S002"]


def test_ingest_text_names_the_next_steps(strat, decided, tmp_path):
    src = tmp_path / "retention-nov.csv"
    shutil.copy(REVISION / "retention-nov.csv", src)
    out = strat("ingest", str(src)).out
    assert "S002" in out and "skills/revise" in out and "C001" in out


def test_ingest_twice_does_not_register_twice(strat, decided, tmp_path):
    src = tmp_path / "retention-nov.csv"
    shutil.copy(REVISION / "retention-nov.csv", src)
    assert strat("ingest", str(src), "--step", "revise.ingest.1").code == 0
    r = strat("ingest", str(src), "--step", "revise.ingest.1", "--json")
    assert r.code == 0 and r.data["replayed"] is True
    r = strat("ingest", str(src), "--json")
    assert r.code == 0 and r.data["id"] == "S002" and r.data["existing"] is True
    assert len(read_jsonl(decided / "sources" / "index.jsonl")) == 2


def test_ingest_before_the_decision_is_refused(strat, case, tmp_path):
    src = tmp_path / "retention-nov.csv"
    shutil.copy(REVISION / "retention-nov.csv", src)
    r = strat("ingest", str(src))
    assert r.code == 1
    assert "source add" in r.err
    assert not (case / "sources" / "index.jsonl").exists() or \
        read_jsonl(case / "sources" / "index.jsonl") == []
