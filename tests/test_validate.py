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
- [ ] Q2 Сколько стоит семейный тариф у конкурентов - ячейка: откат цены x выручка; влияние: среднее; тема: конкуренты; где искать: веб, тарифные страницы [C003]
- [ ] Q3 Какой отток типичен для семейных подписок - ячейка: оставить x отток; влияние: среднее; тема: бенчмарки; где искать: веб, отраслевые отчёты [C003]
- [ ] Q4 Как рынок облаков меняется в 2026 году - ячейка: закрыть x выручка; влияние: низкое; тема: рынок; где искать: веб, обзоры рынка [C003]
- [ ] Q5 Что пользователи пишут об отмене подписки - ячейка: откат цены x отток; влияние: среднее; тема: голос пользователей; где искать: веб, отзывы [C003]

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

### Вариант 4. Скидка за год

- Суть: годовой тариф со скидкой [C002]

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
    return case


WEB_QS = (2, 3, 4, 5)


def searched(case, q, k, kind="keyword", status="ok"):
    """What `strat search` leaves for research question q: the results file and a log line."""
    from strat.state import log_action

    step = f"research.q{q}.search.{k}"
    out = ""
    if status == "ok":
        (case / "search").mkdir(exist_ok=True)
        out = f"search/{step}.json"
        (case / out).write_text(json.dumps({"query": "q", "kind": kind, "results": []}))
    log_action(case, step=step, tool="search", in_="q", out=out, status=status)


def saved_page(case, q, k, site):
    """What `strat read <url>` leaves: a web source with a snapshot, and a log line."""
    from strat import sources
    from strat.state import log_action

    text = f"# {site}\n\nОтток семейных подписок {q}{k} процентов в месяц.\n"
    e = sources.register(case, kind="web", origin=f"https://www.{site}/page{q}{k}",
                         title=site, text=text, digest=f"{q}{k}{site}", fmt="text")
    log_action(case, step=f"research.q{q}.read.{k}", tool="read", out=e["snapshot"], ref=e["id"])
    return e["id"]


def research(strat, case, facts=8, sites=5):
    """Wide research: per web question 4 searches of 2 kinds and 4 saved pages; web facts."""
    pages = []
    for q in WEB_QS:
        for k in range(1, 5):
            searched(case, q, k, kind="keyword" if k % 2 else "semantic")
            pages.append((q, k, saved_page(case, q, k, f"site{(q * 4 + k) % sites}.ru")))
    for q, k, sid in pages[:facts]:
        r = strat("claim", "add", "--type", "fact", "--kind", "market", "--text",
                  f"Отток {q}{k}%", "--source", sid, "--where", "абзац 1", "--quote",
                  f"Отток семейных подписок {q}{k} процентов", "--as-of", "2026-10")
        assert r.code == 0, r.err
        cid = r.out.split()[1] if r.out.startswith("added") else r.out.split()[0]
        assert strat("judge", "support", "--claim", cid.strip(":"), "--answer", "yes").code == 0


def to_gate2(strat, case):
    assert strat("gate", "check", "1").code == 0
    assert strat("gate", "approve", "1").code == 0
    assert strat("judge", "support", "--claim", "C001", "--answer", "yes").code == 0


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
    to_gate2(strat, ready)
    research(strat, ready)
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


def test_gate1_needs_four_web_questions_over_three_themes(strat, ready):
    """With "one web question" the models searched once: the plan must look wide."""
    edit(ready, "plan.md", "где искать: веб, тарифные страницы", "где искать: S001")
    r = strat("gate", "check", "1")
    assert r.code == 1 and "3 web question(s)" in r.err and "research-themes.md" in r.err
    edit(ready, "plan.md", "где искать: S001", "где искать: веб, тарифные страницы")
    edit(ready, "plan.md", "тема: рынок", "тема: конкуренты")
    edit(ready, "plan.md", "тема: голос пользователей", "тема: бенчмарки")
    r = strat("gate", "check", "1")
    assert r.code == 1 and "over 2 theme(s)" in r.err


def test_gate2_needs_four_options(strat, ready):
    to_gate2(strat, ready)
    research(strat, ready)
    text = (ready / "options.md").read_text()
    (ready / "options.md").write_text(text.replace("### Вариант 4. Скидка за год\n\n"
                                                   "- Суть: годовой тариф со скидкой [C002]\n", ""))
    r = strat("gate", "check", "2")
    assert r.code == 1 and "options.md: 3 option(s); gate 2 needs at least 4" in r.err


def test_gate2_needs_several_searches_kinds_and_pages_per_web_question(strat, ready):
    to_gate2(strat, ready)
    r = strat("gate", "check", "2")
    assert r.code == 1 and "Q2 (web) is researched too narrowly: 0/4 searches" in r.err
    research(strat, ready)
    assert strat("gate", "check", "2").code == 0


def test_one_kind_of_search_is_not_enough(strat, ready):
    to_gate2(strat, ready)
    research(strat, ready)
    for k in range(5, 9):
        searched(ready, 6, k)
    edit(ready, "plan.md", "- [ ] Q5", "- [ ] Q6 Ещё вопрос - ячейка: x; тема: рынок; "
         "где искать: веб, новости [C003]\n- [ ] Q5")
    r = strat("gate", "check", "2")
    assert r.code == 1 and "Q6 (web)" in r.err and "1/2 search kinds" in r.err
    assert "0/4 saved pages" in r.err


def test_gate2_needs_many_web_facts_from_many_sites(strat, ready):
    to_gate2(strat, ready)
    research(strat, ready, facts=5)
    r = strat("gate", "check", "2")
    assert r.code == 1 and "5 fact(s) quoted from web pages" in r.err


def test_web_facts_from_too_few_sites_fail(strat, ready):
    to_gate2(strat, ready)
    research(strat, ready, sites=3)
    r = strat("gate", "check", "2")
    assert r.code == 1 and "from 3 site(s)" in r.err


def test_a_question_whose_searches_all_failed_ends_as_a_gap(strat, ready):
    """Every provider failed: the agent tried; the question is exempt from the page floors."""
    to_gate2(strat, ready)
    research(strat, ready)
    edit(ready, "plan.md", "- [ ] Q5", "- [ ] Q6 Ещё вопрос - ячейка: x; тема: рынок; "
         "где искать: веб, новости [C003]\n- [ ] Q5")
    assert strat("gate", "check", "2").code == 1
    for k in range(1, 3):
        searched(ready, 6, k, status="error")
    r = strat("gate", "check", "2")
    assert r.code == 0, r.err


# ---------- the seal: record files change only through bin/strat ----------

def test_a_hand_edited_claims_file_fails_the_gate(strat, ready):
    """A weak model wrote support verdicts into claims.jsonl by hand to pass Gate 2."""
    p = ready / "claims.jsonl"
    p.write_text(p.read_text().replace('"status": "active"', '"status": "active" ', 1))
    r = strat("gate", "check", "1")
    assert r.code == 1 and "claims.jsonl: changed outside bin/strat" in r.err


def test_a_rewritten_snapshot_and_a_forged_log_line_fail(strat, ready):
    snap = ready / "sources" / "S001.md"
    snap.write_text(snap.read_text() + "\nдописано\n")
    with (ready / "log.jsonl").open("a") as f:
        f.write(json.dumps({"step": "research.q2.search.9", "tool": "search", "status": "ok"}) + "\n")
    r = strat("gate", "check", "1")
    assert r.code == 1 and "sources/S001.md: changed outside" in r.err
    assert "log.jsonl: changed outside" in r.err


def test_a_cli_write_does_not_reseal_a_hand_edit(strat, ready):
    """Review: the next CLI append re-hashed log.jsonl with a forged row inside and the gate passed."""
    with (ready / "log.jsonl").open("a") as f:
        f.write(json.dumps({"step": "research.q2.search.9", "tool": "search", "status": "ok"}) + "\n")
    r = strat("step", "plan.note", "--note", "x")
    assert r.code == 1 and "log.jsonl: changed outside bin/strat" in r.err
    r = strat("gate", "check", "1")
    assert r.code == 1 and "log.jsonl: changed outside" in r.err
    p = ready / "claims.jsonl"
    p.write_text(p.read_text().replace('"status": "active"', '"status": "active" ', 1))
    r = strat("claim", "add", "--type", "gap", "--kind", "market", "--text", "Пробел")
    assert r.code == 1 and "claims.jsonl: changed outside bin/strat" in r.err


def test_a_record_file_missing_from_the_seal_fails(strat, ready):
    """Review: dropping an entry from .seal.json left that file unchecked."""
    import json as _json

    spath = ready / ".seal.json"
    data = _json.loads(spath.read_text())
    del data["claims.jsonl"]
    del data["sources/S001.md"]
    spath.write_text(_json.dumps(data))
    r = strat("gate", "check", "1")
    assert r.code == 1 and "claims.jsonl: not in the seal" in r.err
    assert "sources/S001.md: not in the seal" in r.err


def test_cli_writes_keep_the_seal(strat, ready):
    from strat.validate import seal_errors

    assert strat("claim", "add", "--type", "gap", "--kind", "market", "--text", "Пробел").code == 0
    assert strat("claim", "withdraw", "C004", "--reason", "не нужен").code == 0
    to_gate2(strat, ready)
    research(strat, ready)
    assert seal_errors(ready) == []
    assert strat("gate", "check", "2").code == 0


def test_ids_never_reuse_a_deleted_number(strat, ready):
    """len+1 ids reused a number after a hand deletion and overwrote a snapshot (GLM run)."""
    from strat import sources
    from strat.core import StratError, write_jsonl

    write_jsonl(ready / "sources" / "index.jsonl", [])  # S001's line deleted by hand
    with pytest.raises(StratError, match="S001.md exists"):
        sources.register(ready, kind="web", origin="https://x.ru", title="x", text="t",
                         digest="d", fmt="text")
    claims = [json.loads(x) for x in (ready / "claims.jsonl").read_text().splitlines()]
    write_jsonl(ready / "claims.jsonl", claims[1:])  # C001 deleted; C002, C003 remain
    r = strat("claim", "add", "--type", "gap", "--kind", "market", "--text", "Пробел")
    assert r.code == 0 and "C004" in r.out
