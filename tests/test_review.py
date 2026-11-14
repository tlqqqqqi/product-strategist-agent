"""Review and revision (Task 10): impact, due checks, stale and contradicted load-bearing claims.

The case is past Gate 3: a decision rests on a figure from an invented table
(tests/fixtures/revision). A later export contradicts it. No network, no models: the
contradiction judgment is recorded with `--answer` as the IDE agent would.
"""

import json
import shutil

import pytest

from conftest import REPO
from strat.core import read_json, write_json

REVISION = REPO / "tests" / "fixtures" / "revision"

DECISIONS = """# Журнал решений

## Решение 2026-11-15: запускаем семейный тариф

- Выбранный вариант: семейный тариф в первом квартале [C004]
- Владелец: руководитель продукта
- Метрики: удержание D30 [C001]
- Дата проверки: {check}
- Условия пересмотра: пересматриваем, если опорные данные изменятся [C001]
  - удержание D30 выше 38% [C001] (проверить: {cond})
- Опорные утверждения: [C001, C003, C004]

## Открытые вопросы

- Цена у конкурента не проверена [C005]

## История

- 2026-11-15: решение принято
"""


def write(cdir, name, text):
    (cdir / name).write_text(text, encoding="utf-8")


def add(strat, *args):
    r = strat("claim", "add", *args)
    assert r.code == 0, r.err
    return r


@pytest.fixture
def decided(strat, case):
    """A case at stage monitoring whose decision rests on C001 (retention 33.2%)."""
    shutil.copy(REVISION / "retention-oct.csv", case / "materials" / "retention-oct.csv")
    assert strat("source", "add", "materials/retention-oct.csv").code == 0
    add(strat, "--type", "fact", "--kind", "product_metric",
        "--text", "Удержание D30 в октябре 2026 упало до 33,2%", "--source", "S001",
        "--where", "retention-oct!B3", "--quote", "33.2", "--as-of", "2026-10")
    add(strat, "--type", "assumption", "--kind", "market",
        "--text", "Пользователи уходят, потому что нет семейного тарифа")
    add(strat, "--type", "conclusion", "--kind", "method",
        "--text", "Падение удержания требует семейного тарифа", "--supports", "C001,C002")
    add(strat, "--type", "conclusion", "--kind", "method",
        "--text", "Запускать семейный тариф в первом квартале", "--supports", "C003")
    add(strat, "--type", "assumption", "--kind", "price",
        "--text", "Конкурент берёт 299 ₽ за семейный тариф")
    write(case, "table.md", "# Таблица\n\n| вариант | удержание |\n|---|---|\n"
                            "| семейный | падает [C001] |\n")
    write(case, "options.md", "# Варианты\n\n## Варианты\n\n- Оставить как есть [C002]\n\n"
                              "## Рекомендация\n\n- Семейный тариф в первом квартале [C004]\n")
    write(case, "product.md", "# Продукт\n\n- Делаем семейный тариф [C003]\n")
    write(case, "comms.md", "# Коммуникация\n\n- Цена ниже конкурента [C005]\n")
    write(case, "decisions.md", DECISIONS.format(check="2026-12-01", cond="2027-01-15"))
    state = read_json(case / "state.json")
    state.update(stage="monitoring", gates={"1": "approved", "2": "approved", "3": "approved"})
    write_json(case / "state.json", state)
    return case


def contradict(strat, case):
    """New material after the decision: ingest, a claim from it, the agent's judgment."""
    shutil.copy(REVISION / "retention-nov.csv", case.parent / "retention-nov.csv")
    r = strat("ingest", str(case.parent / "retention-nov.csv"), "--json")
    assert r.code == 0, r.err
    add(strat, "--type", "fact", "--kind", "product_metric",
        "--text", "Удержание D30 в октябре 2026 после исправления выгрузки 40,1%",
        "--source", "S002", "--where", "retention-nov!B3", "--quote", "40.1", "--as-of", "2026-11")
    r = strat("judge", "contradiction", "--claim", "C006", "--other", "C001", "--answer", "yes")
    assert r.code == 0, r.err


def lines_of(data):
    return {(row["file"], row["line"]) for row in data["lines"]}


# --- the spec test -----------------------------------------------------------------------------

def test_contradicting_table_lists_the_affected_conclusions(strat, decided):
    contradict(strat, decided)

    r = strat("review", "--json")
    assert r.code == 0, r.err
    data = r.data
    [hit] = data["contradicted"]
    assert hit["claim"] == "C001" and hit["by"] == "C006"
    assert hit["conclusions"] == ["C003", "C004"]
    files = {row["file"] for row in hit["lines"]}
    assert files == {"table.md", "options.md", "product.md", "decisions.md"}
    assert any("C001" in q["text"] and "C006" in q["text"] for q in data["questions"])

    r = strat("impact", "C001", "--json")
    assert r.code == 0, r.err
    assert r.data["conclusions"] == ["C003", "C004"]
    assert lines_of(r.data) == {(row["file"], row["line"]) for row in hit["lines"]}

    text = strat("review").out
    assert "C001" in text and "C006" in text and "options.md" in text


def test_a_resolved_contradiction_is_no_longer_reported(strat, decided):
    contradict(strat, decided)
    assert strat("claim", "replace", "C001", "C006").code == 0
    assert strat("review", "--json").data["contradicted"] == []


def test_a_later_no_overrides_an_earlier_yes(strat, decided):
    contradict(strat, decided)
    r = strat("judge", "contradiction", "--claim", "C006", "--other", "C001", "--answer", "no")
    assert r.code == 0, r.err
    assert strat("review", "--json").data["contradicted"] == []


# --- impact ------------------------------------------------------------------------------------

def test_impact_follows_conclusions_transitively(strat, decided):
    r = strat("impact", "C002", "--json")
    assert r.code == 0, r.err
    assert r.data["conclusions"] == ["C003", "C004"]
    got = lines_of(r.data)
    assert ("options.md", 9) in got          # cites C004, two steps from C002
    assert ("options.md", 5) in got          # cites C002 directly
    assert ("product.md", 3) in got          # cites C003
    assert not any(f == "comms.md" for f, _ in got)  # C005 does not depend on C002
    assert all(row["cites"] for row in r.data["lines"])


def test_impact_of_an_unknown_claim_fails(strat, decided):
    assert strat("impact", "C999").code == 1


# --- due checks --------------------------------------------------------------------------------

def test_nothing_is_due_before_the_check_date(strat, decided):
    data = strat("review", "--json").data
    assert data["due"] == [] and data["contradicted"] == [] and data["stale"] == []
    assert data["questions"] == []


def test_a_due_check_date_shows_in_review_and_state(strat, decided, monkeypatch):
    monkeypatch.setenv("STRAT_TODAY", "2026-12-02")
    data = strat("review", "--json").data
    assert [d["date"] for d in data["due"] if d["what"] == "check"] == ["2026-12-01"]
    assert data["questions"]

    r = strat("state", "--json")
    assert any(d["date"] == "2026-12-01" for d in r.data["due"])
    assert "2026-12-01" in strat("state").out


def test_a_condition_with_its_own_date_comes_due(strat, decided, monkeypatch):
    monkeypatch.setenv("STRAT_TODAY", "2027-01-20")
    data = strat("review", "--json").data
    conds = [d for d in data["due"] if d["what"] == "condition" and d["date"]]
    assert [d["date"] for d in conds] == ["2027-01-15"]
    assert conds[0]["cites"] == ["C001"] and "2027-01-15 has passed" in conds[0]["reason"]
    monkeypatch.setenv("STRAT_TODAY", "2026-12-20")  # before its date, C001 still fresh
    assert strat("review", "--json").data["due"] == [
        d for d in strat("review", "--json").data["due"] if d["what"] == "check"]


def test_a_condition_fires_when_its_claim_is_contradicted(strat, decided):
    contradict(strat, decided)
    conds = [d for d in strat("review", "--json").data["due"] if d["what"] == "condition"]
    assert conds and all("C001" in d["reason"] for d in conds)


def test_only_the_last_decision_is_live(strat, decided, monkeypatch):
    old = DECISIONS.format(check="2026-11-20", cond="2026-11-20").split("## Открытые")[0]
    new = DECISIONS.format(check="2027-03-01", cond="2027-03-01").replace(
        "# Журнал решений\n\n", "").replace("2026-11-15: запускаем", "2026-11-25: подтверждаем")
    write(decided, "decisions.md", old + new)
    monkeypatch.setenv("STRAT_TODAY", "2026-12-02")
    assert strat("review", "--json").data["due"] == []


def test_an_unreadable_check_date_becomes_a_question(strat, decided):
    write(decided, "decisions.md",
          DECISIONS.format(check="в середине зимы", cond="2027-01-15"))
    data = strat("review", "--json").data
    assert any(d["what"] == "check" and d["date"] is None for d in data["due"])
    assert any("check date" in q["text"] for q in data["questions"])


def test_state_shows_nothing_due_outside_monitoring(strat, case):
    r = strat("state", "--json")
    assert r.data["due"] == []


# --- stale load-bearing claims -----------------------------------------------------------------

def test_stale_load_bearing_claims_are_listed(strat, decided, monkeypatch):
    # C001 is a product_metric as of 2026-10: 60 days after 2026-10-31 it is stale
    monkeypatch.setenv("STRAT_TODAY", "2027-01-05")
    data = strat("review", "--json").data
    assert [c["id"] for c in data["stale"]] == ["C001"]
    assert any("C001" in q["text"] for q in data["questions"])


# --- at most 3 questions -----------------------------------------------------------------------

def test_review_asks_at_most_three_questions(strat, decided, monkeypatch):
    contradict(strat, decided)
    extra = "".join(f"  - условие {i} [C005] (проверить: 2027-01-0{i})\n" for i in range(1, 6))
    text = DECISIONS.format(check="2026-12-01", cond="2027-01-15").replace(
        "- Опорные утверждения", extra.rstrip("\n") + "\n- Опорные утверждения")
    write(decided, "decisions.md", text)
    monkeypatch.setenv("STRAT_TODAY", "2027-02-20")
    data = strat("review", "--json").data
    assert len(data["due"]) > 3
    assert 1 <= len(data["questions"]) <= 3
    assert "C001" in data["questions"][0]["text"]  # the contradiction is asked first


def test_session_start_hook_shows_due_items(decided, monkeypatch):
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "CURSOR"))}
    env.update(STRAT_CASES=str(decided.parent), STRAT_TODAY="2026-12-02")
    proc = subprocess.run([sys.executable, str(REPO / "hooks" / "session-start")],
                          capture_output=True, text=True, env=env, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert "stage: monitoring" in proc.stdout and "check 2026-12-01" in proc.stdout
