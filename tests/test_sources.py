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
