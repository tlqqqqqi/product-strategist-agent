"""Source index, snapshots, quote check."""

import json

from strat.sources import normalize, quote_found


def test_html_material_gets_an_s_id(strat, case):
    r = strat("source", "add", "materials/competitor.html", "--json")
    assert r.code == 0 and r.data["id"] == "S001"
    entry = json.loads((case / "sources" / "index.jsonl").read_text().splitlines()[0])
    assert entry["kind"] == "file" and entry["origin"] == "materials/competitor.html"
    assert len(entry["sha256"]) == 64 and entry["snapshot"] == "sources/S001.md"
    snap = (case / "sources" / "S001.md").read_text()
    assert "Семейный тариф: 2 ТБ на 5 человек — 299 ₽ в месяц." in snap
    assert "TRACKING_CODE_SHOULD_NOT_APPEAR" not in snap  # scripts are dropped


def test_same_file_twice_returns_the_same_id(strat, case):
    a = strat("source", "add", "materials/competitor.html", "--json").data["id"]
    b = strat("source", "add", "materials/competitor.html", "--json").data["id"]
    assert a == b == "S001"
    assert len((case / "sources" / "index.jsonl").read_text().splitlines()) == 1


def test_file_outside_the_case_is_copied_into_materials(strat, case, tmp_path):
    f = tmp_path / "notes.md"
    f.write_text("Цена конкурента выросла.")
    r = strat("source", "add", str(f), "--json")
    assert r.code == 0
    assert (case / "materials" / "notes.md").read_text() == "Цена конкурента выросла."
    assert f.exists()  # the original is untouched


def test_missing_file_fails(strat, case):
    assert strat("source", "add", "materials/nope.pdf").code == 1


def test_quote_check_collapses_whitespace_and_case():
    snap = "Семейный  тариф:\n2 ТБ на 5 человек"
    assert quote_found(snap, "семейный тариф: 2 тб")
    assert not quote_found(snap, "3 ТБ")


def test_quote_with_ellipsis_matches_parts_in_order():
    snap = "D30: 41,0 в мае, затем 37,5, в октябре 33,2"
    assert quote_found(snap, "41,0 ... 33,2")
    assert quote_found(snap, "41,0 … 33,2")
    assert not quote_found(snap, "33,2 ... 41,0")


def test_normalize_handles_nbsp():
    assert normalize("299 ₽") == normalize("299 ₽")


def test_analysis_output_stays_in_place_as_kind_analysis(strat, case):
    (case / "analysis").mkdir(exist_ok=True)
    (case / "analysis" / "q1.txt").write_text("excess churn: 3050")
    r = strat("source", "add", "analysis/q1.txt", "--json")
    assert r.code == 0 and r.data["origin"] == "analysis/q1.txt"
    entry = json.loads((case / "sources" / "index.jsonl").read_text().splitlines()[0])
    assert entry["kind"] == "analysis"
    assert not (case / "materials" / "q1.txt").exists()


def test_text_addressed_to_ai_is_flagged(strat, case):
    r = strat("source", "add", "materials/competitor.html", "--json")
    assert r.data["flags"] == ["instructions_to_ai"]
    text = strat("source", "add", "materials/product.docx").out
    assert "instructions" not in text
    out = strat("read", str(case / "materials" / "competitor.html"), "--step", "r1").out
    assert "addressed to AI" in out and "tell the user" in out


def test_shot_quote_is_checked_inside_the_named_element(strat, case):
    """For a screenshot source, --where names an element; a quote from another element of the
    same screenshot is refused (spec, Sources: "For shot, where names an element")."""
    from strat.sources import register, sha256

    doc = {"url": "https://example.org/plans", "viewport": [1280, 800], "targets": {
        "family_price": {"box": [10, 20, 300, 40], "text": "Семья: 1 ТБ — 249 ₽ в месяц"},
        "solo_price": {"box": [10, 80, 300, 40], "text": "Для себя: 199 ₽ в месяц"}}}
    register(case, kind="shot", origin="shots/cloud/01_plans.png", title="plans",
             text=json.dumps(doc, ensure_ascii=False), digest=sha256(b"png"), fmt="shot")
    base = ["claim", "add", "--type", "fact", "--kind", "price", "--source", "S001",
            "--as-of", "2026-11"]
    ok = strat(*base, "--text", "Семейный тариф стоит 249 ₽ в месяц",
               "--where", "family_price", "--quote", "249 ₽ в месяц")
    assert ok.code == 0, ok.err
    other = strat(*base, "--text", "Семейный тариф стоит 199 ₽ в месяц",
                  "--where", "family_price", "--quote", "199 ₽ в месяц")
    assert other.code == 1
    missing = strat(*base, "--text", "x 249", "--where", "header", "--quote", "249")
    assert missing.code == 1 and "family_price" in missing.err


def test_source_list_shows_every_source_with_its_flags(strat, case):
    assert strat("source", "add", "materials/metrics.xlsx").code == 0
    assert strat("source", "add", "materials/competitor.html").code == 0
    r = strat("source", "list", "--json")
    assert r.code == 0
    assert [s["id"] for s in r.data] == ["S001", "S002"]
    assert r.data[1]["flags"] == ["instructions_to_ai"]
    text = strat("source", "list").out
    assert "S001" in text and "metrics.xlsx" in text and "S002" in text
