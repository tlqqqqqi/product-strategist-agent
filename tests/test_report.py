"""strat report (Task 14): memo.md -> memo.html where every claim id opens its claim."""

import json
import re
from html.parser import HTMLParser

import pytest

PRICE = "Семейный тариф: 2 ТБ на 5 человек — 299 ₽ в месяц."

MEMO = """# Записка: цену не откатываем

> Одна страница для директора по продукту. Каждое утверждение цитирует [C...].

## Решение

- Цена остаётся, акцию перестраиваем **через тест** [C001, C004].

## Почему

- Конкурент берёт 299 ₽ [C001]; пользователи не сравнивают цены [C002].
- Данных об отказах на оплате нет [C003].

## Как проверим

| Метрика | Срок |
|---|---|
| Доля платящих [C005] | 2027-04-30 [C004] |

## Материалы

> Полные документы: claims.md, sources/.
"""


class Doc(HTMLParser):
    """Collects links, element ids, the text inside each id'd element, and resource refs."""

    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []
        self.resources: list[str] = []
        self.text_by_id: dict[str, str] = {}
        self._open: list[tuple[str, str | None]] = []
        self.tags: list[str] = []
        self.style = ""
        self._in_style = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append(tag)
        if tag == "a" and a.get("href"):
            self.hrefs.append(a["href"])
        for key in ("src", "srcset", "poster", "data"):
            if a.get(key):
                self.resources.append(f"{tag} {key}={a[key]}")
        if tag == "link":
            self.resources.append(f"link {a.get('href')}")
        if tag == "script" and a.get("src"):
            self.resources.append(f"script {a['src']}")
        self._in_style = tag == "style"
        if tag not in ("br", "img", "meta", "hr", "input", "link"):
            self._open.append((tag, a.get("id")))
            if a.get("id"):
                self.text_by_id.setdefault(a["id"], "")

    def handle_endtag(self, tag):
        if tag == "style":
            self._in_style = False
        for i in range(len(self._open) - 1, -1, -1):
            if self._open[i][0] == tag:
                del self._open[i:]
                break

    def handle_data(self, data):
        if self._in_style:
            self.style += data
        for _, eid in self._open:
            if eid:
                self.text_by_id[eid] += data


def parse(path) -> Doc:
    doc = Doc()
    doc.feed(path.read_text(encoding="utf-8"))
    return doc


@pytest.fixture
def memo_case(strat, case):
    assert strat("source", "add", "materials/competitor.html",
                 "--title", "ОблакоПлюс — тарифы").code == 0
    adds = [
        ["--type", "fact", "--kind", "price", "--text", "Конкурент берёт 299 ₽ в месяц",
         "--source", "S001", "--where", "Семейный", "--quote", PRICE, "--as-of", "2026-11"],
        ["--type", "assumption", "--kind", "market", "--text", "Пользователи не сравнивают цены"],
        ["--type", "gap", "--kind", "method", "--text", "Нет данных об отказах на оплате"],
        ["--type", "conclusion", "--kind", "method", "--text", "Цену не откатываем",
         "--supports", "C001,C002"],
        ["--type", "synthetic", "--kind", "market", "--text", "Модельный респондент: цена ок"],
    ]
    for args in adds:
        r = strat("claim", "add", *args)
        assert r.code == 0, r.err
    (case / "memo.md").write_text(MEMO, encoding="utf-8")
    return case


def cited(text: str) -> set[str]:
    return set(re.findall(r"C\d{3,}", text.replace("[C...]", "")))


def test_every_claim_id_links_to_its_claim_with_source_and_quote(strat, memo_case):
    r = strat("report")
    assert r.code == 0, r.err
    doc = parse(memo_case / "memo.html")
    ids = cited(MEMO)
    assert ids == {"C001", "C002", "C003", "C004", "C005"}
    for cid in ids:
        assert f"#{cid}" in doc.hrefs, f"{cid} is not linked"
        assert cid in doc.text_by_id, f"{cid} has no claim card"
    fact = doc.text_by_id["C001"]
    assert "Конкурент берёт 299 ₽ в месяц" in fact
    assert "ОблакоПлюс" in fact  # source title from the index
    assert "materials/competitor.html" in fact  # origin
    assert "Семейный" in fact  # where
    assert "2 ТБ на 5 человек" in fact  # the quote
    # the conclusion's supports open too
    assert "C001" in doc.text_by_id["C004"] and "C002" in doc.text_by_id["C004"]


def test_non_fact_types_are_labelled(strat, memo_case):
    assert strat("report").code == 0
    doc = parse(memo_case / "memo.html")
    labels = {"C002": "допущение", "C003": "пробел", "C004": "вывод",
              "C005": "синтетические данные"}
    for cid, label in labels.items():
        assert label in doc.text_by_id[cid].casefold()
    html = (memo_case / "memo.html").read_text(encoding="utf-8")
    # the label is visible next to the citation in the text, not only in the card
    body = html.split('id="claims"')[0]
    for label in labels.values():
        assert label in body.casefold()


def test_markdown_subset_is_rendered(strat, memo_case):
    assert strat("report").code == 0
    doc = parse(memo_case / "memo.html")
    for tag in ("h1", "h2", "ul", "li", "table", "th", "td", "strong", "blockquote"):
        assert tag in doc.tags, tag


def test_output_has_no_external_resources(strat, memo_case):
    assert strat("report").code == 0
    html = (memo_case / "memo.html").read_text(encoding="utf-8")
    doc = parse(memo_case / "memo.html")
    # the only outside resource is the Google Fonts stylesheet (the page reads without it)
    assert all(r.startswith("link https://fonts.g") for r in doc.resources), doc.resources
    assert "@import" not in doc.style and "url(" not in doc.style
    assert 'lang="ru"' in html and 'name="viewport"' in html
    assert "prefers-color-scheme: dark" not in html  # light only (DESIGN.md)


def test_source_text_is_escaped(strat, memo_case):
    claims = memo_case / "claims.jsonl"
    claims.write_text(claims.read_text(encoding="utf-8").replace(
        "Пользователи не сравнивают цены", "<script>alert(1)</script>"), encoding="utf-8")
    assert strat("report").code == 0
    html = (memo_case / "memo.html").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_unknown_id_fails_and_names_the_line(strat, memo_case):
    memo = memo_case / "memo.md"
    memo.write_text(MEMO.replace("[C003]", "[C099]"), encoding="utf-8")
    line = next(i for i, t in enumerate(MEMO.splitlines(), 1) if "[C003]" in t)
    r = strat("report")
    assert r.code == 1
    assert f"memo.md:{line}: C099 does not exist" in r.err
    assert not (memo_case / "memo.html").exists()


def test_withdrawn_id_fails(strat, memo_case):
    assert strat("claim", "withdraw", "C002", "--reason", "поправка").code == 0
    line = next(i for i, t in enumerate(MEMO.splitlines(), 1) if "[C002]" in t)
    r = strat("report")
    assert r.code == 1 and f"memo.md:{line}: C002 is withdrawn" in r.err


def test_stale_id_fails(strat, memo_case, monkeypatch):
    monkeypatch.setenv("STRAT_TODAY", "2030-01-01")
    r = strat("report")
    assert r.code == 1 and "C001 is stale" in r.err


def test_missing_memo_is_an_error(strat, case):
    r = strat("report")
    assert r.code == 1 and "memo.md" in r.err


# --- memo blocks (Task 17b) -------------------------------------------------------------------

BLOCK_CLAIMS = [
    # C006
    ["--type", "assumption", "--kind", "market",
     "--text", "Удержание M1 в мае 2026: органика 88,8%, реклама 52,1%, партнёры 61%"],
    # C007
    ["--type", "forecast", "--kind", "market",
     "--text", "Платящих по месяцам: 1 200, 1 350, 1 610, 1 740 человек"],
    # C008
    ["--type", "assumption", "--kind", "market",
     "--text", "Конверсия в оплату была 3,4%, после теста 4.1%"],
    # C009
    ["--type", "assumption", "--kind", "market",
     "--text", "Воронка: 10 000 установок, 4 200 регистраций, 380 оплат"],
]

BLOCKS = {
    "tiles": """```tiles
title: Главное
- Удержание органики*: 88,8 % - лучше всех каналов [C006]
- Платящих: 1 610 - на конец периода [C007]
```""",
    "bars": """```bars
title: Удержание M1 по каналам, май 2026
unit: %
- органика: 88,8 [C006]
- реклама: 52.1 [C006]
-   партнёры :61[C006]
```""",
    "line": """```line
title: Платящие по месяцам
unit: чел.
- 2026-03: 1 200 [C007]
- 2026-04: 1 350 [C007]
- 2026-05: 1 610 [C007]
- 2026-06: 1 740 [C007]
```""",
    "slope": """```slope
title: Конверсия в оплату
unit: %
columns: до | после
- конверсия: 3,4 | 4,1 [C008]
```""",
    "funnel": """```funnel
title: Воронка за май
- установки: 10 000 [C009]
- регистрации: 4 200 [C009]
- оплаты: 380 [C009]
```""",
    "table": """```table
title: Каналы
| Канал | Удержание M1, % |
| органика | 88,8 [C006] |
| реклама | 52,1 [C006] |
```""",
}


@pytest.fixture
def block_case(memo_case, strat):
    for args in BLOCK_CLAIMS:
        r = strat("claim", "add", *args)
        assert r.code == 0, r.err
    return memo_case


def with_blocks(*blocks: str) -> str:
    return MEMO.replace("## Почему", "## Ключевые цифры\n\n" + "\n\n".join(blocks)
                        + "\n\n## Почему")


def block_html(case) -> str:
    html = (case / "memo.html").read_text(encoding="utf-8")
    return html.split("<main>")[1].split('id="claims"')[0]


GRID_ATTRS = ("x", "y", "x1", "x2", "y1", "y2", "cx", "cy", "width", "height")


class Svg(HTMLParser):
    def __init__(self):
        super().__init__()
        self.svgs = 0
        self.coords: list[tuple[str, str]] = []
        self.links_in_svg: list[str] = []
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "svg":
            self.svgs += 1
            self.depth += 1
            assert "viewbox" in a and a.get("width") == "100%"
            return
        if not self.depth:
            return
        if tag == "a":
            self.links_in_svg.append(a.get("href"))
        for key in GRID_ATTRS:
            if key in a:
                self.coords.append((key, a[key]))
        if "points" in a:
            for p in a["points"].split():
                self.coords += [("points", v) for v in p.split(",")]

    def handle_endtag(self, tag):
        if tag == "svg":
            self.depth -= 1


def block_section(body: str, kind: str) -> str:
    m = re.search(rf'<figure class="blk blk-{kind}[^"]*".*?</figure>', body, re.S)
    assert m, f"no {kind} block"
    return m.group(0)


def test_line_block_renders_as_svg_on_the_grid_with_linked_values(strat, block_case):
    (block_case / "memo.md").write_text(with_blocks(BLOCKS["line"]), encoding="utf-8")
    r = strat("report")
    assert r.code == 0, r.err
    body = block_html(block_case)
    fig = block_section(body, "line")
    svg = Svg()
    svg.feed(fig)
    assert svg.svgs == 1
    assert svg.coords, "no coordinates drawn"
    off = [(k, v) for k, v in svg.coords if float(v) % 4]
    assert not off, f"off the 4 px grid: {off}"
    assert "<text" not in fig  # labels are HTML, so they do not shrink with the viewBox
    for value in ("1 200", "1 350", "1 610", "2026-03"):
        assert value in fig
    assert "Платящие по месяцам" in fig and "чел." in fig
    assert "<script" not in body
    assert '<a class="v" href="#C007"' in fig


@pytest.mark.parametrize("kind", ["bars", "slope", "funnel"])
def test_bar_like_blocks_render_as_html_rows_with_percent_widths(strat, block_case, kind):
    (block_case / "memo.md").write_text(with_blocks(BLOCKS[kind]), encoding="utf-8")
    r = strat("report")
    assert r.code == 0, r.err
    body = block_html(block_case)
    fig = block_section(body, kind)
    assert "<svg" not in fig
    widths = re.findall(r'style="width:\s*([\d.]+)%"', fig)
    assert widths and all(0 < float(w) <= 100 for w in widths)
    assert max(float(w) for w in widths) == 100
    title = re.search(r"^title: (.+)$", BLOCKS[kind], re.M).group(1)
    assert title in fig
    cids = cited(BLOCKS[kind])
    for cid in cids:
        assert f'href="#{cid}"' in fig
    doc = parse(block_case / "memo.html")
    for cid in cids:
        assert cid in doc.text_by_id, f"{cid} has no claim card"


def test_bars_mark_one_focal_bar_and_show_the_unit(strat, block_case):
    (block_case / "memo.md").write_text(with_blocks(BLOCKS["bars"]), encoding="utf-8")
    assert strat("report").code == 0
    fig = block_section(block_html(block_case), "bars")
    assert fig.count("focal") == 1
    assert "%" in fig
    for value in ("88,8", "52.1", "61"):
        assert value in fig


def test_tiles_and_table_render_as_html_with_claim_links(strat, block_case):
    (block_case / "memo.md").write_text(with_blocks(BLOCKS["tiles"], BLOCKS["table"]),
                                        encoding="utf-8")
    r = strat("report")
    assert r.code == 0, r.err
    body = block_html(block_case)
    assert "blk-tiles" in body and "blk-table" in body
    assert "88,8" in body and "1 610" in body and "лучше всех каналов" in body
    assert "Удержание органики" in body and "Удержание органики*" not in body
    doc = parse(block_case / "memo.html")
    assert "#C006" in doc.hrefs and "#C007" in doc.hrefs


def test_value_not_in_its_claim_fails_with_the_line_and_no_html(strat, block_case):
    memo = with_blocks(BLOCKS["bars"].replace("52.1", "57,3"))
    (block_case / "memo.md").write_text(memo, encoding="utf-8")
    line = next(i for i, t in enumerate(memo.splitlines(), 1) if "57,3" in t)
    r = strat("report")
    assert r.code == 1
    assert f"memo.md:{line}: 57,3 is not in the text or quote of C006" in r.err
    assert not (block_case / "memo.html").exists()


def test_number_in_a_tile_note_is_checked_too(strat, block_case):
    memo = with_blocks(BLOCKS["tiles"].replace("лучше всех каналов", "в 2 раза лучше"))
    (block_case / "memo.md").write_text(memo, encoding="utf-8")
    r = strat("report")
    assert r.code == 1 and "2 is not in the text or quote of C006" in r.err


def test_unknown_or_withdrawn_claim_in_a_block_fails(strat, block_case):
    memo = with_blocks(BLOCKS["funnel"].replace("380 [C009]", "380 [C099]"))
    (block_case / "memo.md").write_text(memo, encoding="utf-8")
    line = next(i for i, t in enumerate(memo.splitlines(), 1) if "C099" in t)
    r = strat("report")
    assert r.code == 1 and f"memo.md:{line}: C099 does not exist" in r.err
    assert not (block_case / "memo.html").exists()
    (block_case / "memo.md").write_text(with_blocks(BLOCKS["funnel"]), encoding="utf-8")
    assert strat("claim", "withdraw", "C009", "--reason", "поправка").code == 0
    r = strat("report")
    assert r.code == 1 and "C009 is withdrawn" in r.err


def test_row_without_citation_or_unreadable_fails(strat, block_case):
    memo = with_blocks(BLOCKS["bars"].replace("88,8 [C006]", "88,8"))
    (block_case / "memo.md").write_text(memo, encoding="utf-8")
    line = next(i for i, t in enumerate(memo.splitlines(), 1) if t.endswith("88,8"))
    r = strat("report")
    assert r.code == 1 and f"memo.md:{line}: no citation" in r.err
    memo = with_blocks(BLOCKS["bars"].replace("- органика: 88,8", "- органика много"))
    (block_case / "memo.md").write_text(memo, encoding="utf-8")
    r = strat("report")
    assert r.code == 1 and "cannot read this row" in r.err


def test_template_placeholder_in_a_block_fails(strat, block_case):
    memo = with_blocks("```bars\ntitle: <заголовок>\n- <подпись>: <число> [C...]\n```")
    (block_case / "memo.md").write_text(memo, encoding="utf-8")
    r = strat("report")
    assert r.code == 1 and "template placeholder" in r.err


def test_more_than_three_blocks_fail(strat, block_case):
    memo = with_blocks(BLOCKS["bars"], BLOCKS["line"], BLOCKS["funnel"], BLOCKS["slope"])
    (block_case / "memo.md").write_text(memo, encoding="utf-8")
    r = strat("report")
    assert r.code == 1 and "more than 3 blocks" in r.err


def test_step_out_runs_the_block_check(strat, block_case):
    memo = with_blocks(BLOCKS["bars"].replace("52.1", "57,3"))
    (block_case / "memo.md").write_text(memo, encoding="utf-8")
    r = strat("step", "signoff.memo", "--out", "memo.md")
    # the short test memo also lacks template headings; the block error is reported with them
    assert r.code == 1 and "57,3 is not in the text or quote of C006" in r.err


def test_memo_without_blocks_renders_as_before(strat, memo_case):
    assert strat("report").code == 0
    body = block_html(memo_case)
    assert "<svg" not in body and "blk" not in body


TABLE_MD = """# Таблица решения

## Критерии

- Рост платящих [C001]

## Варианты против критериев

| Критерий | Вариант 1 | Вариант 2 | Вариант 3 |
|---|---|---|---|
| Рост | слабый [C002] | сильный [C004] | средний [C003] |

## Влияние исследования

| Вопрос | Ячейка | Ответ | Изменил ранжирование |
|---|---|---|---|
| Q1 | В2 x Рост | да [C001] | нет |
"""


class Cells(HTMLParser):
    """Text of each table cell inside the decision section, with its class."""

    def __init__(self):
        super().__init__()
        self.inside = False
        self.cells: list[list] = []
        self.cell = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "section" and "decision" in (a.get("class") or ""):
            self.inside = True
        if self.inside and tag in ("td", "th"):
            self.cell = [a.get("class") or "", ""]
            self.cells.append(self.cell)

    def handle_endtag(self, tag):
        if tag == "section":
            self.inside = False
        if tag in ("td", "th"):
            self.cell = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell[1] += data


def test_decision_table_renders_with_the_chosen_option_marked(strat, block_case):
    (block_case / "table.md").write_text(TABLE_MD, encoding="utf-8")
    state = json.loads((block_case / "state.json").read_text(encoding="utf-8"))
    state["chosen_option"] = 2
    (block_case / "state.json").write_text(json.dumps(state), encoding="utf-8")
    assert strat("report").code == 0
    html = (block_case / "memo.html").read_text(encoding="utf-8")
    assert "Таблица решения" in html.split('id="claims"')[0]
    cells = Cells()
    cells.feed(html)
    chosen = [text for cls, text in cells.cells if "chosen" in cls]
    assert chosen and all(("Вариант 2" in t or "сильный" in t) for t in chosen)
    assert any("сильный" in t for t in chosen)
    assert not any("Q1" in t for _, t in cells.cells)  # only the options-by-criteria table
    doc = parse(block_case / "memo.html")
    assert "#C004" in doc.hrefs


def test_decision_table_with_options_as_rows_marks_the_row(strat, block_case):
    (block_case / "table.md").write_text(
        "# Таблица решения\n\n## Варианты против критериев\n\n"
        "| Вариант | Рост |\n|---|---|\n| Вариант 1: тест | слабый [C002] |\n"
        "| Вариант 2: откат | сильный [C004] |\n", encoding="utf-8")
    state = json.loads((block_case / "state.json").read_text(encoding="utf-8"))
    state["chosen_option"] = 1
    (block_case / "state.json").write_text(json.dumps(state), encoding="utf-8")
    assert strat("report").code == 0
    cells = Cells()
    cells.feed((block_case / "memo.html").read_text(encoding="utf-8"))
    chosen = [t for cls, t in cells.cells if "chosen" in cls]
    assert any("тест" in t for t in chosen) and any("слабый" in t for t in chosen)
    assert not any("сильный" in t for t in chosen)


def test_claim_type_filter_tags_elements_and_is_hidden_without_js(strat, block_case):
    (block_case / "memo.md").write_text(with_blocks(BLOCKS["bars"]), encoding="utf-8")
    assert strat("report").code == 0
    html = (block_case / "memo.html").read_text(encoding="utf-8")
    nav = re.search(r'<nav class="type-filter"[^>]*>(.*?)</nav>', html, re.S)
    assert nav and " hidden" in nav.group(0).split(">")[0]
    for label in ("факты", "допущения", "пробелы", "выводы"):
        assert label in nav.group(1)
    assert 'data-types="assumption"' in html  # the bars cite an assumption
    assert re.search(r'data-types="[^"]*\bgap\b', html)  # the gap bullet


# --- design (Task 17d, DESIGN.md) -------------------------------------------------------------

TOKENS = {
    "--page": "#F5F8FF", "--surface": "#FFFFFF", "--surface-2": "#F2F8FF", "--ink": "#1A1F3B",
    "--muted": "#56627A", "--hairline": "#D3E1F2", "--accent": "#2563EB",
    "--accent-mark": "#3B82F6", "--accent-press": "#1D4ED8", "--accent-soft": "#E3EDFF",
    "--neg": "#C01D38", "--neg-mark": "#F4455E", "--neg-soft": "#FFE3E7",
    "--pos": "#157A3F", "--pos-mark": "#22A55B", "--pos-soft": "#DCF5E6",
    "--violet": "#7C5CFF", "--lavender": "#C7B8FF", "--warn": "#A8470F", "--sel": "#C7DBFF",
}


def css_rules(style: str) -> list[tuple[str, str]]:
    """(selector, declarations) of every plain rule, with @media blocks flattened."""
    style = re.sub(r"/\*.*?\*/", "", style, flags=re.S)
    return [(sel.strip(), body) for sel, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", style)]


def style_for(style: str, cls: str) -> str:
    """All declarations of rules whose selector ends with the class `cls`."""
    return " ".join(body for sel, body in css_rules(style)
                    if any(re.search(rf"\.{cls}\b[^\s]*$", s.strip()) for s in sel.split(",")))


class Classes(HTMLParser):
    """Every element: (tag, attrs, text inside it)."""

    def __init__(self):
        super().__init__()
        self.els: list[list] = []
        self._open: list[list] = []

    def handle_starttag(self, tag, attrs):
        el = [tag, dict(attrs), ""]
        self.els.append(el)
        if tag not in ("br", "img", "meta", "hr", "input", "link", "circle", "line", "polyline"):
            self._open.append(el)

    def handle_endtag(self, tag):
        for i in range(len(self._open) - 1, -1, -1):
            if self._open[i][0] == tag:
                del self._open[i:]
                break

    def handle_data(self, data):
        for el in self._open:
            el[2] += data

    def with_class(self, cls: str) -> list[list]:
        return [e for e in self.els if cls in (e[1].get("class") or "").split()]


def classes(html: str) -> Classes:
    c = Classes()
    c.feed(html)
    return c


def test_page_defines_the_design_tokens_light_only(strat, memo_case):
    assert strat("report").code == 0
    doc = parse(memo_case / "memo.html")
    root = " ".join(body for sel, body in css_rules(doc.style) if sel == ":root")
    for name, value in TOKENS.items():
        m = re.search(rf"{re.escape(name)}\s*:\s*(#[0-9A-Fa-f]{{6}})", root)
        assert m and m.group(1).upper() == value, f"{name} is not {value}"
    body_font = " ".join(b for s, b in css_rules(doc.style) if s in ("html", "body"))
    family = re.search(r"font-family\s*:\s*([^;]+)", body_font).group(1)
    family = re.sub(r"var\((--[\w-]+)\)", lambda m: re.search(
        rf"{m.group(1)}\s*:\s*([^;]+)", root).group(1), family)
    assert family.lstrip().startswith('"Geologica"') and "sans-serif" in family  # system fallback


NEG_CLAIMS = [
    # C006
    ["--type", "assumption", "--kind", "product_metric",
     "--text", "Платящих акции стало на 59,34% меньше, органики — на 8,38% меньше"],
    # C007
    ["--type", "assumption", "--kind", "product_metric", "--text", "ARPU вырос на 45 ₽, до 334 ₽"],
]

NEG_TILES = """```tiles
title: Главное
- платящих акции: −59,34 % - отток здесь [C006]
- ARPU: +45 ₽ - цена не обрушила выручку [C007]
- ARPU в октябре: 334 ₽ - уровень [C007]
```"""

NEG_BARS = """```bars
title: Изменение платящих, август → октябрь
unit: %
- Акция: −59,34 [C006]
- Органика: -8,38 [C006]
```"""


@pytest.fixture
def neg_case(memo_case, strat):
    for args in NEG_CLAIMS:
        r = strat("claim", "add", *args)
        assert r.code == 0, r.err
    return memo_case


def test_tile_values_are_figure_rows_coloured_by_sign(strat, neg_case):
    (neg_case / "memo.md").write_text(with_blocks(NEG_TILES), encoding="utf-8")
    r = strat("report")
    assert r.code == 0, r.err
    page = classes(block_html(neg_case))
    figs = page.with_class("fig")
    assert len(figs) == 3
    values = page.with_class("fig-v")
    assert [("neg" in v[1]["class"].split(), "pos" in v[1]["class"].split()) for v in values] \
        == [(True, False), (False, True), (False, False)]
    assert "59,34" in values[0][2] and "45" in values[1][2]
    first = figs[0][2]
    assert "платящих акции" in first and "отток здесь" in first and "C006" in first
    notes = page.with_class("fig-n")
    assert [n[2] for n in notes][0] == "отток здесь"


def test_bars_draw_the_focal_bar_violet_and_negative_values_in_neg(strat, neg_case):
    (neg_case / "memo.md").write_text(with_blocks(NEG_BARS), encoding="utf-8")
    r = strat("report")
    assert r.code == 0, r.err
    page = classes(block_html(neg_case))
    fills = page.with_class("blk-bar")
    assert [f[1]["class"].split()[-1] for f in fills] == ["violet", "lavender"]
    widths = [float(re.search(r"width:([\d.]+)%", f[1]["style"]).group(1)) for f in fills]
    assert widths[0] == 100 and 0 < widths[1] < 20  # by magnitude
    vals = page.with_class("blk-v")
    assert all("neg" in v[1]["class"].split() for v in vals)
    doc = parse(neg_case / "memo.html")
    assert "var(--violet)" in style_for(doc.style, "violet")
    assert "var(--lavender)" in style_for(doc.style, "lavender")
    assert "var(--neg)" in style_for(doc.style, "neg")


def test_bars_with_mixed_signs_fail(strat, neg_case):
    memo = with_blocks(NEG_BARS.replace("-8,38", "8,38"))
    (neg_case / "memo.md").write_text(memo, encoding="utf-8")
    r = strat("report")
    assert r.code == 1 and "same sign" in r.err


def claims_data(html: str) -> dict:
    m = re.search(r'<script id="claims-data" type="application/json">(.*?)</script>', html, re.S)
    assert m, "no claims data for the claim card"
    return json.loads(m.group(1))


def test_each_citation_carries_the_data_for_its_claim_card(strat, memo_case):
    assert strat("report").code == 0
    html = (memo_case / "memo.html").read_text(encoding="utf-8")
    data = claims_data(html)
    page = classes(html.split('id="claims"')[0])
    cites = page.with_class("cite")
    assert cites
    for el in cites:
        cid = el[1]["data-c"]
        assert el[1]["href"] == f"#{cid}"  # without JS: a link to the card on the page
        claim = data["claims"][cid]
        assert claim["type"] and claim["text"]
    fact = data["claims"]["C001"]
    assert fact["type"] == "fact" and fact["quote"] == PRICE and fact["where"] == "Семейный"
    src = data["sources"][fact["source"]]
    assert src["title"] == "ОблакоПлюс — тарифы"
    assert src["href"] == "materials/competitor.html"
    assert src["snap"].startswith("sources/")
    # gap and assumption citations are told apart from facts on the chip itself
    gap = next(e for e in cites if e[1]["data-c"] == "C003")
    assert "as" in gap[1]["class"].split()


def test_gap_claim_card_says_there_is_no_data(strat, memo_case):
    assert strat("report").code == 0
    html = (memo_case / "memo.html").read_text(encoding="utf-8")
    doc = parse(memo_case / "memo.html")
    assert "Данных нет" in doc.text_by_id["C003"]  # the no-JS card on the page
    assert "Данных нет" in claims_data(html)["claims"]["C003"]["note"]  # the popover


def test_output_has_no_file_urls_or_absolute_paths(strat, memo_case):
    index = memo_case / "sources" / "index.jsonl"
    rows = [json.loads(t) for t in index.read_text(encoding="utf-8").splitlines() if t.strip()]
    rows[0]["origin"] = str(memo_case / "materials" / "competitor.html")
    rows[0]["snapshot"] = "file:///etc/passwd"
    index.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                     encoding="utf-8")
    assert strat("report").code == 0
    html = (memo_case / "memo.html").read_text(encoding="utf-8")
    assert "file://" not in html
    assert str(memo_case) not in html and str(memo_case.parent) not in html
    doc = parse(memo_case / "memo.html")
    assert not [h for h in doc.hrefs if h.startswith(("/", "\\"))]
    assert claims_data(html)["sources"]["S001"]["href"] is None


def test_header_shows_the_decision_and_the_metadata(strat, memo_case):
    memo = MEMO.replace("## Как проверим", "## Как проверим\n\n- Дата проверки: 2027-02-01 [C004]")
    memo = memo.replace("## Материалы", "## Риски и открытые вопросы\n\n"
                        "- Покупатели могут уйти к конкуренту [C003]\n"
                        "- Цены могут вырасти [C001]\n\n## Материалы")
    (memo_case / "memo.md").write_text(memo, encoding="utf-8")
    (memo_case / "objections.jsonl").write_text(json.dumps(
        {"id": "O007", "call": "challenge", "target": "x", "severity": "major", "text": "y",
         "claims": ["C003"], "verdict": "risk-accepted", "reason": "z"}, ensure_ascii=False)
        + "\n", encoding="utf-8")
    r = strat("report")
    assert r.code == 0, r.err
    html = (memo_case / "memo.html").read_text(encoding="utf-8")
    page = classes(html.split('id="claims"')[0])
    head = page.with_class("memo-head")[0][2]
    assert "Цену не откатываем" in head and "Записка:" not in head
    box = page.with_class("decision-box")[0][2]
    assert box.startswith("Решение.") and "через тест" in box and "C001" in box
    assert not [e for e in page.els if e[0] == "h2" and e[2].strip() == "Решение"]
    meta = re.sub(r"\s+", " ", page.with_class("meta")[0][2])
    assert "Проверка: 2027-02-01" in meta
    assert "Факты: 1" in meta and "Допущения: 1" in meta and "Принятые риски: 1" in meta
    risks = page.with_class("risk")
    assert len(risks) == 2
    tags = [e[2] for e in page.with_class("risk-id")]
    assert tags == ["O007"]
    assert "уйти к конкуренту" in risks[0][2]


def test_line_needs_four_points_and_labels_its_axis(strat, case):
    """Owner: a two-point line looked ridiculous and had unlabelled gridlines. A line needs at
    least 4 points (a before/after is a slope); gridlines carry their values."""
    from strat import blocks
    two = "```line\ntitle: Отток\nunit: %\n- июль: 4,3 [C001]\n- октябрь: 6,8 [C001]\n```"
    errs = [m for blk in blocks.blocks_in(two.splitlines()) for _, m in blk.errors]
    assert any("at least 4 points" in m and "slope" in m for m in errs), errs
    four = two.replace("- октябрь", "- август: 4,2 [C001]\n- сентябрь: 6,6 [C001]\n- октябрь")
    assert not [m for blk in blocks.blocks_in(four.splitlines()) for _, m in blk.errors]
    from strat import report
    html = report._line(blocks.blocks_in(four.splitlines())[0], {})
    assert html.count('class="blk-tick"') >= 3 and ">5%<" in html


def test_a_long_tile_value_wraps_in_a_capped_column_with_a_smaller_font(strat, neg_case):
    tiles = NEG_TILES.replace("−59,34 %", "−59,34 % платящих после акции против прошлого года")
    (neg_case / "memo.md").write_text(with_blocks(tiles), encoding="utf-8")
    r = strat("report")
    assert r.code == 0, r.err
    values = classes(block_html(neg_case)).with_class("fig-v")
    assert ["long" in v[1]["class"].split() for v in values] == [True, False, False]
    doc = parse(neg_case / "memo.html")
    assert "fit-content" in style_for(doc.style, "figs")  # the value column is capped
    assert "nowrap" not in style_for(doc.style, "long")
