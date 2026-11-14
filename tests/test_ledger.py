"""Claim ledger: add rules, replace, withdraw, stale by shelf life, confirm, importance,
claims.md."""

import json

import pytest

from strat.core import read_jsonl

PRICE = "Семейный тариф: 2 ТБ на 5 человек — 299 ₽ в месяц."


@pytest.fixture
def src(strat, case):
    assert strat("source", "add", "materials/competitor.html").code == 0
    return "S001"


def fact(strat, quote=PRICE, as_of="2026-11", kind="price", source="S001", text=None, *extra):
    return strat("claim", "add", "--type", "fact", "--kind", kind,
                 "--text", text or "Конкурент берёт 299 ₽ в месяц за семейный тариф",
                 "--source", source, "--where", "Семейный", "--quote", quote,
                 "--as-of", as_of, "--json", *extra)


def claims(case):
    return {c["id"]: c for c in read_jsonl(case / "claims.jsonl")}


def test_assumption_without_source_is_accepted(strat, case):
    r = strat("claim", "add", "--type", "assumption", "--kind", "market",
              "--text", "Пользователи не сравнивают цены", "--json")
    assert r.code == 0 and r.data["id"] == "C001"


def test_fact_with_a_passing_quote_is_added(strat, src, case):
    r = fact(strat)
    assert r.code == 0, r.err
    c = claims(case)["C001"]
    assert c["type"] == "fact" and c["status"] == "active"
    assert c["check"]["quote"] is True


def test_fact_needs_source_where_quote_and_as_of(strat, case):
    r = strat("claim", "add", "--type", "fact", "--kind", "price", "--text", "x")
    assert r.code == 1 and "source" in r.err


def test_fact_with_a_wrong_quote_is_refused(strat, src, case):
    r = fact(strat, quote="2 ТБ на 6 человек — 199 ₽")
    assert r.code == 1 and "quote not found in S001" in r.err
    assert claims(case) == {}


def test_unknown_source_is_refused(strat, case):
    assert fact(strat, source="S009").code == 1


def test_unknown_type_and_kind_are_refused(strat, case):
    assert strat("claim", "add", "--type", "rumour", "--kind", "price", "--text", "x").code == 1
    assert strat("claim", "add", "--type", "gap", "--kind", "gossip", "--text", "x").code == 1


def test_conclusion_is_refused_as_the_source_of_a_fact(strat, src, case):
    fact(strat)
    r = strat("claim", "add", "--type", "conclusion", "--kind", "market",
              "--text", "Мы дороже конкурента", "--supports", "C001", "--json")
    assert r.code == 0
    r = fact(strat, source="C002")
    assert r.code == 1 and "conclusion" in r.err
    r = strat("claim", "add", "--type", "fact", "--kind", "price", "--text", "x",
              "--source", "S001", "--where", "Семейный", "--quote", PRICE,
              "--as-of", "2026-11", "--supports", "C002")
    assert r.code == 1 and "conclusion" in r.err


def test_conclusion_must_rest_on_claims(strat, case):
    r = strat("claim", "add", "--type", "conclusion", "--kind", "market", "--text", "x")
    assert r.code == 1 and "supports" in r.err


def test_add_with_a_logged_step_replays(strat, src, case):
    a = fact(strat, PRICE, "2026-11", "price", "S001", None, "--step", "research.q1.claim.1")
    b = fact(strat, PRICE, "2026-11", "price", "S001", None, "--step", "research.q1.claim.1")
    assert a.data["id"] == "C001" and b.data["replayed"] is True and b.data["id"] == "C001"
    assert len(claims(case)) == 1


def test_replace_and_withdraw_keep_history(strat, src, case):
    fact(strat)
    fact(strat)
    assert strat("claim", "replace", "C001", "C002").code == 0
    assert strat("claim", "withdraw", "C002", "--reason", "страница устарела").code == 0
    c = claims(case)
    assert c["C001"]["status"] == "replaced" and c["C001"]["replaced_by"] == "C002"
    assert c["C002"]["status"] == "withdrawn" and c["C002"]["reason"] == "страница устарела"


def test_stale_by_shelf_life(strat, src, case, monkeypatch):
    fact(strat, as_of="2026-07")  # price: 90 days from 2026-07-31
    monkeypatch.setenv("STRAT_TODAY", "2026-10-29")
    assert strat("claim", "list", "--stale", "--json").data == []
    monkeypatch.setenv("STRAT_TODAY", "2026-10-30")
    stale = strat("claim", "list", "--stale", "--json").data
    assert [c["id"] for c in stale] == ["C001"] and stale[0]["status"] == "stale"


def test_method_never_goes_stale(strat, case, monkeypatch):
    strat("claim", "add", "--type", "assumption", "--kind", "method", "--text", "x",
          "--as-of", "2010-01")
    assert strat("claim", "list", "--stale", "--json").data == []


def test_confirm_reactivates_with_a_newer_source(strat, src, case, monkeypatch):
    fact(strat, as_of="2026-01")
    assert strat("claim", "list", "--stale", "--json").data[0]["id"] == "C001"
    r = strat("claim", "confirm", "C001", "--source", "S001", "--where", "Семейный",
              "--quote", PRICE, "--as-of", "2025-12")
    assert r.code == 1 and "newer" in r.err
    r = strat("claim", "confirm", "C001", "--source", "S001", "--where", "Семейный",
              "--quote", PRICE, "--as-of", "2026-11")
    assert r.code == 0, r.err
    c = claims(case)["C001"]
    assert c["as_of"] == "2026-11" and c["history"][0]["as_of"] == "2026-01"
    assert strat("claim", "list", "--stale", "--json").data == []


def test_load_bearing_follows_documents_and_supports(strat, src, case):
    fact(strat)                                                         # C001
    strat("claim", "add", "--type", "gap", "--kind", "market", "--text", "нет данных")  # C002
    strat("claim", "add", "--type", "conclusion", "--kind", "market", "--text", "дороже",
          "--supports", "C001")                                         # C003
    strat("claim", "add", "--type", "assumption", "--kind", "market", "--text", "y")  # C004
    (case / "product.md").write_text("# Продукт\n\n- Держим цену [C003]\n")
    (case / "plan.md").write_text("- [ ] Q1 почему уходят [C002]\n- [x] Q2 закрыт [C004]\n")
    ids = [c["id"] for c in strat("claim", "list", "--load-bearing", "--json").data]
    assert ids == ["C001", "C002", "C003"]


def test_claims_md_is_generated(strat, src, case):
    fact(strat)
    strat("claim", "list")
    md = (case / "claims.md").read_text()
    assert "C001" in md and "S001" in md and "299 ₽" in md
    assert md.startswith("# Утверждения")


def test_check_all_reports_a_quote_that_no_longer_matches(strat, src, case):
    fact(strat)
    snap = case / "sources" / "S001.md"
    snap.write_text(snap.read_text().replace("299 ₽", "349 ₽"))
    r = strat("claim", "check", "--all", "--json")
    assert r.code == 1
    assert r.data["results"][0] == {"id": "C001", "quote": False, "supported": None,
                                    "by": None}
    assert json.loads((case / "claims.jsonl").read_text())["check"]["quote"] is False


def test_impossible_date_is_a_validation_error(strat, case):
    r = strat("claim", "add", "--type", "gap", "--kind", "market", "--text", "x",
              "--as-of", "2026-02-31")
    assert r.code == 1 and "bad --as-of" in r.err


def test_snapshot_path_outside_sources_is_refused(strat, src, case):
    idx = case / "sources" / "index.jsonl"
    idx.write_text(idx.read_text().replace('"sources/S001.md"', '"../../outside.txt"'))
    r = fact(strat)
    assert r.code == 1 and "snapshot" in r.err


def test_historical_claim_never_goes_stale(strat, case, monkeypatch):
    strat("source", "add", "materials/metrics.xlsx")
    r = strat("claim", "add", "--type", "fact", "--kind", "product_metric", "--historical",
              "--text", "Из промо-когорты мая 2026 в августе заплатили 2050 человек",
              "--source", "S001", "--where", "cohorts!C2", "--quote", "2050",
              "--as-of", "2026-08", "--json")
    assert r.code == 0, r.err
    assert r.data["claim"]["historical"] is True
    monkeypatch.setenv("STRAT_TODAY", "2030-01-01")
    assert strat("claim", "list", "--stale", "--json").data == []
    assert "история" in (case / "claims.md").read_text()


def test_historical_claim_must_name_its_period(strat, case):
    strat("source", "add", "materials/metrics.xlsx")
    r = strat("claim", "add", "--type", "fact", "--kind", "product_metric", "--historical",
              "--text", "Из промо-когорты в августе заплатили 2050 человек",
              "--source", "S001", "--where", "cohorts!C2", "--quote", "2050",
              "--as-of", "2026-08")
    assert r.code == 1 and "2026" in r.err
    r = strat("claim", "add", "--type", "gap", "--kind", "market", "--historical", "--text", "x")
    assert r.code == 1 and "--as-of" in r.err
