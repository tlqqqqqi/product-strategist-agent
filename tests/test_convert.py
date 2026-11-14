"""Materials to snapshots (Task 5a): one file of each kind becomes a snapshot, and a claim's
quote passes the quote check with a `where` of the right form."""

import shutil

import pytest

from conftest import SAMPLE
from strat.convert import convert

KINDS = SAMPLE.parent / "kinds"
METRICS = SAMPLE / "materials" / "metrics.xlsx"


def test_xlsx_snapshot_has_one_block_per_sheet():
    text = convert(str(METRICS))
    assert "## sheet: monthly" in text and "## sheet: cohorts" in text
    assert "rows: 7 (header + 6), columns: 4" in text
    assert "month,paying_users,churn_pct,arpu_rub" in text
    assert "2026-10,42300,6.8,334" in text


def test_xlsx_counts_empty_cells_per_column():
    text = convert(str(METRICS))
    cohorts = text.split("## sheet: cohorts")[1].split("## sheet:")[0]
    assert "empty cells: A 0, B 0, C 0, D 1, E 0" in cohorts


def test_cohort_sheet_is_unambiguous():
    """Cohort columns count May sign-ups and how many of them paid later; `about` defines them.
    Payers never exceed sign-ups, October never exceeds August, and the cohort is a small part
    of the monthly paying base (it is one month of sign-ups, not the base)."""
    text = convert(str(METRICS))
    monthly = text.split("## sheet: monthly")[1].split("## sheet:")[0]
    paying = {r.split(",")[0]: int(r.split(",")[1]) for r in monthly.splitlines()
              if r.startswith("2026-")}
    cohorts = text.split("## sheet: cohorts")[1].split("## sheet:")[0]
    assert "channel,new_users_2026_05,paid_users_2026_08,paid_users_2026_10,promo" in cohorts
    rows = {r.split(",")[0]: r.split(",")[1:] for r in cohorts.splitlines()
            if r.startswith(("promo_", "organic", "partner_", "paid_ads"))}
    assert rows == {
        "promo_3_months_free": ["9800", "2050", "1280", "yes"],
        "organic": ["1900", "1680", "1490", "no"],
        "partner_bank": ["700", "620", "560", "no"],
        "paid_ads": ["900", "770", "", "no"],
    }
    for new, aug, octo, _ in rows.values():
        assert 0 <= int(aug) <= int(new)
        assert octo == "" or 0 <= int(octo) <= int(aug)
    assert sum(int(r[1]) for r in rows.values()) < paying["2026-08"] / 5
    assert sum(int(r[2]) for r in rows.values() if r[2]) < paying["2026-10"] / 5
    about = text.split("## sheet: about")[1]
    for col in ("paying_users", "churn_pct", "new_users_2026_05", "paid_users_2026_08",
                "paid_users_2026_10"):
        assert col in about


def test_csv_is_one_block_named_after_the_file():
    text = convert(str(KINDS / "trials.csv"))
    assert "## sheet: trials" in text and "empty cells: A 0, B 0, C 1, D 1" in text


def test_docx_keeps_headings_paragraph_numbers_and_tables_in_order():
    text = convert(str(SAMPLE / "materials" / "product.docx"))
    about = text.index("## О продукте")
    price = text.index("349 ₽ в месяц")
    survey = text.index("## Опрос ушедших пользователей")
    row = text.index("| Закончился бесплатный период | 38% |")
    assert about < price < survey < row
    assert "[p3] Цена тарифа «Семья»" in text


def test_pptx_has_title_text_table_and_notes_per_slide():
    text = convert(str(KINDS / "deck.pptx"))
    s1 = text.split("## slide 1")[1].split("## slide 2")[0]
    assert "title: Итоги квартала" in s1 and "Выручка выросла на 12%" in s1
    assert "notes: Цифра без учёта возвратов" in s1
    assert "| Промо | 41% |" in text.split("## slide 2")[1]


def test_pdf_has_text_per_page_and_flags_pages_without_text():
    text = convert(str(KINDS / "report.pdf"))
    assert "Churn in October was 6.8 percent." in text.split("## page 1")[1]
    assert "no text layer" in text.split("## page 2")[1]


def test_unsupported_format_exits_2(strat, case, tmp_path):
    f = tmp_path / "a.xyz"
    f.write_text("x")
    assert strat("source", "add", str(f)).code == 2


CASES = [
    # file, where, quote, wrong where form
    (METRICS, "monthly!C2:C7", "4.1 ... 6.8", "monthly C2"),
    (KINDS / "trials.csv", "trials!D3", "12.0", "trials!E3"),
    (KINDS / "trials.csv", "trials!D2:D3", "26.0 ... 12.0", "trials!"),
    (SAMPLE / "materials" / "product.docx", "О продукте", "349 ₽ в месяц", "Раздел 9"),
    (SAMPLE / "materials" / "product.docx", "paragraph 3", "349 ₽ в месяц", "paragraph 99"),
    (KINDS / "deck.pptx", "slide 1", "Выручка выросла на 12%", "slide seven"),
    (KINDS / "report.pdf", "page 1", "6.8 percent", "p. 1"),
]


@pytest.mark.parametrize("path,where,quote,bad_where", CASES)
def test_fact_from_each_kind_passes_with_the_right_where(strat, case, path, where, quote,
                                                         bad_where):
    shutil.copy(path, case / "materials" / path.name)
    sid = strat("source", "add", f"materials/{path.name}", "--json").data["id"]

    def add(w):
        return strat("claim", "add", "--type", "fact", "--kind", "product_metric", "--text", "t",
                     "--source", sid, "--where", w, "--quote", quote, "--as-of", "2026-10")

    bad = add(bad_where)
    assert bad.code == 1 and "where" in bad.err
    good = add(where)
    assert good.code == 0, good.err


def test_quote_outside_the_named_range_is_refused(strat, case):
    sid = strat("source", "add", "materials/metrics.xlsx", "--json").data["id"]
    r = strat("claim", "add", "--type", "fact", "--kind", "product_metric", "--text", "t",
              "--source", sid, "--where", "monthly!B2:B7", "--quote", "6.8",
              "--as-of", "2026-10")
    assert r.code == 1 and "quote not found in monthly!B2:B7" in r.err


def test_docx_heading_path_must_be_nested():
    from strat.core import StratError
    from strat.sources import locate

    text = "## A\n[p1] one\n## Unrelated\n[p2] two\n## B\n[p3] three\n"
    with pytest.raises(StratError):
        locate(text, "docx", "A > B")
    nested = "## A\n[p1] one\n### B\n[p2] two\n## C\n[p3] three\n"
    assert locate(nested, "docx", "A > B")[0].strip() == "[p2] two"


@pytest.mark.parametrize("name", ["broken.xlsx", "broken.docx", "broken.pptx", "broken.pdf"])
def test_malformed_file_is_a_clean_error(strat, case, name):
    (case / "materials" / name).write_bytes(b"not really a " + name.encode())
    r = strat("source", "add", f"materials/{name}")
    assert r.code == 1 and "could not read" in r.err
