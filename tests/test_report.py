"""strat report (Task 14): memo.md -> memo.html where every claim id opens its claim."""

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
    assert doc.resources == []
    assert "@import" not in doc.style and "url(" not in doc.style
    assert 'lang="ru"' in html and "prefers-color-scheme: dark" in html
    assert 'name="viewport"' in html


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
