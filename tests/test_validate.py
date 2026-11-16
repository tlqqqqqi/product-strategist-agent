"""Gate checks (Task 2 test: the gate fails on an uncited statement and names the line)."""

import json

import pytest

BRIEF = """# Бриф: цена тарифа

## Решение

Откатывать ли цену тарифа «Семья» [C002].

## Цель

Вернуть отток к уровню весны [C001].

## Получатель

Директор по продукту [C002].

## Срок

1 декабря 2026 года [C002].

## Ограничения

> Пользователь не назвал ограничений.

## Тип кейса

Диагностика [C002].

## Материалы

- metrics.xlsx [C001]

## Допущения

- Решение принимает директор по продукту [C002]
"""

PLAN = """# План исследования

## Вопросы, которые могут изменить выбор

- [ ] Q1 Где сосредоточен отток - ячейка: откат цены x отток; влияние: высокое; где искать: S001 [C001]
- [ ] Q2 Сколько стоит семейный тариф у конкурентов - ячейка: откат цены x выручка; влияние: среднее; где искать: веб, тарифные страницы [C003]

## Правило остановки

Стоп, когда ни один вопрос не меняет ранжирование [C002].

## Оценка стоимости

> Около 10 шагов, платных вызовов нет.

## Пробелы

- Нет данных об отказах на этапе оплаты [C003]
"""

TABLE = """# Таблица решения

## Критерии

- Отток [C001]

## Варианты против критериев

| Критерий | Оставить | Закрыть | Откатить цену |
|---|---|---|---|
| Отток | высокий [C001] | - [C003] | ниже? [C002] |

## Влияние исследования

| Вопрос | Ячейка | Ответ | Изменил ранжирование |
|---|---|---|---|
| Q1 | откат x отток | - [C003] | нет |
"""

OPTIONS = """# Варианты

## Ситуация

- Отток вырос до 6.8% [C001]

## Варианты

### Вариант 1. Оставить как есть

- Суть: ничего не меняем [C002]

### Вариант 2. Закрыть тариф

- Суть: прекращаем продвигать тариф [C003]

### Вариант 3. Откатить цену

- Суть: возвращаем 299 ₽ [C002]
  продолжение пункта без ссылки допустимо

## Возражения

- Отток мог вырасти не из-за цены - вердикт: открыто [C003]

## Рекомендация

> Рекомендация будет после исследования.

## Что изменило бы рекомендацию

- Данные по когортам [C003]
"""


@pytest.fixture
def ready(strat, case):
    """A case whose Gate 1 files and claims pass."""
    assert strat("source", "add", "materials/metrics.xlsx").code == 0
    for args in (
        ["--type", "fact", "--kind", "product_metric", "--text", "Отток в октябре 6.8%",
         "--source", "S001", "--where", "monthly!C7", "--quote", "6.8", "--as-of", "2026-10"],
        ["--type", "assumption", "--kind", "market", "--text", "По словам пользователя, ..."],
        ["--type", "gap", "--kind", "market", "--text", "Нет данных об отказах"],
    ):
        assert strat("claim", "add", *args).code == 0
    for name, text in (("brief.md", BRIEF), ("plan.md", PLAN), ("table.md", TABLE),
                       ("options.md", OPTIONS)):
        (case / name).write_text(text)
    searched(case, 2)
    return case


def searched(case, n, tool="search", status="ok"):
    """The log line `strat search` (or `strat read <url>`) leaves for research question n."""
    with (case / "log.jsonl").open("a") as f:
        f.write(json.dumps({"step": f"research.q{n}.{tool}.1", "tool": tool, "status": status,
                            "stage": "research", "usd": 0}) + "\n")


def unsearched(case):
    rows = [r for r in (case / "log.jsonl").read_text().splitlines()
            if '"research.q' not in r]
    (case / "log.jsonl").write_text("".join(r + "\n" for r in rows))


def stage(case):
    return json.loads((case / "state.json").read_text())["stage"]


def edit(case, name, old, new):
    p = case / name
    text = p.read_text()
    assert old in text
    p.write_text(text.replace(old, new, 1))


def line_of(case, name, needle):
    return next(i for i, line in enumerate((case / name).read_text().splitlines(), 1)
                if needle in line)


def test_gate1_fails_without_files(strat, case):
    r = strat("gate", "check", "1")
    assert r.code == 1 and "brief.md" in r.err


def test_gate1_passes_and_moves_the_stage(strat, ready):
    r = strat("gate", "check", "1")
    assert r.code == 0, r.err
    assert stage(ready) == "gate1"


def test_uncited_bullet_fails_and_names_the_line(strat, ready):
    edit(ready, "options.md", "- Суть: прекращаем продвигать тариф [C003]",
         "- Суть: прекращаем продвигать тариф")
    r = strat("gate", "check", "1")
    n = line_of(ready, "options.md", "прекращаем продвигать")
    assert r.code == 1 and f"options.md:{n}: no citation" in r.err
    assert stage(ready) == "intake"


def test_uncited_decision_table_row_fails_gate1(strat, ready):
    edit(ready, "table.md", "| Отток | высокий [C001] | - [C003] | ниже? [C002] |",
         "| Отток | высокий | - | ниже? |")
    r = strat("gate", "check", "1")
    n = line_of(ready, "table.md", "| Отток | высокий |")
    assert r.code == 1 and f"table.md:{n}: no citation" in r.err
    assert "| Критерий |" not in r.err  # header and separator rows stay exempt
    assert stage(ready) == "intake"


def test_uncited_criteria_bullet_in_table_fails(strat, ready):
    edit(ready, "table.md", "- Отток [C001]", "- Отток")
    r = strat("gate", "check", "1")
    assert r.code == 1 and f"table.md:{line_of(ready, 'table.md', '- Отток')}: no citation" in r.err


def test_cited_table_passes_gate2_after_gate1(strat, ready):
    assert strat("gate", "check", "1").code == 0
    assert strat("gate", "approve", "1").code == 0
    assert strat("judge", "support", "--claim", "C001", "--answer", "yes").code == 0
    r = strat("gate", "check", "2")
    assert r.code == 0, r.err


def test_gate2_needs_a_support_verdict_on_every_fact(strat, ready):
    """A weak model forgets `judge support` (Pi on DeepSeek checked 0 of 16 facts), so the gate
    enforces it: every active fact carries a settled support verdict, by a model or the agent."""
    assert strat("gate", "check", "1").code == 0  # gate 1 does not ask for it yet
    assert strat("gate", "approve", "1").code == 0
    r = strat("gate", "check", "2")
    assert r.code == 1 and "C001" in r.err and "judge support" in r.err
    assert "C002" not in r.err  # an assumption needs no verdict
    assert strat("judge", "support", "--claim", "C001", "--answer", "no").code == 0
    r = strat("gate", "check", "2")
    assert r.code == 1 and "C001" in r.err and "not supported" in r.err


def test_step_out_checks_table_citations(strat, ready):
    edit(ready, "table.md", "| Q1 | откат x отток | - [C003] | нет |", "| Q1 | откат x отток | - | нет |")
    r = strat("step", "plan.table", "--out", "table.md")
    assert r.code != 0 and "table.md:" in r.err and "no citation" in r.err


def test_uncited_paragraph_and_table_row_fail(strat, ready):
    edit(ready, "options.md", "> Рекомендация будет после исследования.",
         "Пока рекомендуем откатить цену.")
    edit(ready, "options.md", "## Ситуация\n", "## Ситуация\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    r = strat("gate", "check", "1")
    assert f"options.md:{line_of(ready, 'options.md', 'Пока рекомендуем')}: no citation" in r.err
    assert f"options.md:{line_of(ready, 'options.md', '| 1 | 2 |')}: no citation" in r.err
    assert "| a | b |" not in r.err  # the header row is exempt


def test_exempt_lines(strat, ready):
    edit(ready, "options.md", "## Ситуация\n",
         "## Ситуация\n\n> заметка для пользователя\n\n```\nкод без ссылок\n```\n\n"
         "Абзац из двух строк,\nссылка во второй [C001].\n")
    assert strat("gate", "check", "1").code == 0


def test_unknown_withdrawn_and_stale_citations_fail(strat, ready, monkeypatch):
    edit(ready, "options.md", "- Данные по когортам [C003]", "- Данные по когортам [C003, C099]")
    strat("claim", "withdraw", "C002", "--reason", "пользователь поправил")
    monkeypatch.setenv("STRAT_TODAY", "2027-03-01")  # C001 (product_metric, 2026-10) is stale
    err = strat("gate", "check", "1").err
    assert "C099 does not exist" in err
    assert "C002 is withdrawn" in err
    assert "C001 is stale" in err


def test_missing_heading_and_empty_section_fail(strat, ready):
    edit(ready, "options.md", "## Возражения\n", "## Возражения к вариантам\n")
    edit(ready, "brief.md", "> Пользователь не назвал ограничений.\n", "")
    err = strat("gate", "check", "1").err
    assert "options.md: missing heading '## Возражения'" in err
    assert "brief.md: section '## Ограничения' is empty" in err


def test_template_placeholder_fails(strat, ready):
    edit(ready, "options.md", "- Суть: ничего не меняем [C002]", "- Суть: <что делаем> [C002]")
    assert "template placeholder" in strat("gate", "check", "1").err


def test_fact_whose_quote_no_longer_matches_fails(strat, ready):
    snap = ready / "sources" / "S001.md"
    snap.write_text(snap.read_text().replace("44790,6.8,334", "44790,7.1,334"))
    assert "claims.jsonl: C001: quote check failed" in strat("gate", "check", "1").err


def test_objection_without_verdict_fails(strat, ready):
    (ready / "objections.jsonl").write_text(
        json.dumps({"id": "O001", "call": "challenge", "target": "option 3", "severity": "high",
                    "text": "x", "verdict": None}) + "\n")
    assert "objections.jsonl: O001 has no verdict" in strat("gate", "check", "1").err


def test_gate2_needs_gate1_approved(strat, ready):
    r = strat("gate", "check", "2")
    assert r.code == 1 and "gate 1 is not approved" in r.err


def test_approve_rechecks_the_files(strat, ready):
    assert strat("gate", "check", "1").code == 0
    edit(ready, "options.md", "- Данные по когортам [C003]", "- Данные по когортам")
    r = strat("gate", "approve", "1")
    assert r.code == 1 and "no citation" in r.err
    assert stage(ready) == "gate1"


def test_full_path_through_gate1(strat, ready):
    assert strat("gate", "check", "1").code == 0
    assert strat("gate", "approve", "1").code == 0
    assert stage(ready) == "research"


def test_step_out_on_a_checked_file_validates_it(strat, ready):
    edit(ready, "options.md", "- Данные по когортам [C003]", "- Данные по когортам")
    r = strat("step", "plan.options", "--out", "options.md")
    assert r.code == 1 and "options.md:" in r.err and "no citation" in r.err
    assert strat("step", "plan.brief", "--out", "brief.md").code == 0


def test_heading_inside_code_does_not_count(strat, ready):
    edit(ready, "options.md", "## Возражения\n", "```\n## Возражения\n")
    edit(ready, "options.md", "## Рекомендация\n", "```\n\n## Рекомендация\n")
    assert "missing heading '## Возражения'" in strat("gate", "check", "1").err


def test_tilde_fence_is_code_and_cannot_hide_text_under_a_citation(strat, ready):
    edit(ready, "options.md", "## Ситуация\n",
         "## Ситуация\n\nАбзац со ссылкой [C001].\n~~~\nкод\n~~~\nТекст без ссылки.\n")
    err = strat("gate", "check", "1").err
    assert f"options.md:{line_of(ready, 'options.md', 'Текст без ссылки')}: no citation" in err


def test_gate_check_reminds_about_flagged_sources(strat, ready):
    strat("source", "add", "materials/competitor.html")
    r = strat("gate", "check", "1")
    assert r.code == 0 and "S002 contains text addressed to AI" in r.out


def test_gate1_needs_a_research_question_answered_from_the_web(strat, ready):
    """Two of three test runs never searched: the plan must look outside the materials."""
    edit(ready, "plan.md", "где искать: веб, тарифные страницы", "где искать: S001")
    r = strat("gate", "check", "1")
    assert r.code == 1 and "plan.md" in r.err and "web" in r.err


def test_gate2_needs_a_search_or_a_saved_page_for_each_web_question(strat, ready):
    assert strat("gate", "check", "1").code == 0
    assert strat("gate", "approve", "1").code == 0
    assert strat("judge", "support", "--claim", "C001", "--answer", "yes").code == 0
    unsearched(ready)
    r = strat("gate", "check", "2")
    assert r.code == 1 and "Q2" in r.err and "strat search" in r.err
    searched(ready, 1)  # a search for another question does not count
    assert strat("gate", "check", "2").code == 1
    searched(ready, 2, tool="read")  # a saved page for Q2 does
    r = strat("gate", "check", "2")
    assert r.code == 0, r.err


def test_a_failed_search_counts_as_an_attempt(strat, ready):
    """Every provider failed: the agent tried; the question ends as a gap, not a blocked gate."""
    assert strat("gate", "check", "1").code == 0
    assert strat("gate", "approve", "1").code == 0
    assert strat("judge", "support", "--claim", "C001", "--answer", "yes").code == 0
    unsearched(ready)
    searched(ready, 2, status="error")
    r = strat("gate", "check", "2")
    assert r.code == 0, r.err
