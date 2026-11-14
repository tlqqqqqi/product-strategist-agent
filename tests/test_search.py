"""Search (Task 5) with one provider, Brave. No network: the HTTP layer is replaced."""

import json

import pytest

from strat import net
from strat.core import read_jsonl

BRAVE_OK = {"web": {"results": [
    {"title": "Тарифы Яндекс 360", "url": "https://360.yandex.ru/premium-plans/",
     "description": "Семейный тариф <strong>до 6</strong> человек"},
    {"title": "Облако Mail", "url": "https://cloud.mail.ru/promo", "description": "1 ТБ"},
]}}


@pytest.fixture
def brave(monkeypatch):
    calls = []

    def fake_get(url, headers=None, timeout=30, max_bytes=None):
        calls.append((url, headers))
        if "fail" in url:
            raise net.HttpError("HTTP 500 from api.search.brave.com")
        return 200, {"content-type": "application/json"}, json.dumps(BRAVE_OK).encode()

    monkeypatch.setattr(net, "get", fake_get)
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")
    return calls


def test_search_without_any_key_exits_2(strat, case):
    r = strat("search", "семейное облако цена", "--step", "research.q1.search.1")
    assert r.code == 2 and "BRAVE_API_KEY" in r.err and "web search tool" in r.err


def test_search_returns_results_and_saves_them(strat, case, brave):
    r = strat("search", "семейное облако цена", "--step", "research.q1.search.1", "--json")
    assert r.code == 0, r.err
    assert r.data == [
        {"title": "Тарифы Яндекс 360", "url": "https://360.yandex.ru/premium-plans/",
         "snippet": "Семейный тариф до 6 человек", "provider": "brave"},
        {"title": "Облако Mail", "url": "https://cloud.mail.ru/promo", "snippet": "1 ТБ",
         "provider": "brave"},
    ]
    url, headers = brave[0]
    assert headers["X-Subscription-Token"] == "test-key"
    assert "search_lang=ru" in url and "count=5" in url
    saved = json.loads((case / "search" / "research.q1.search.1.json").read_text())
    assert saved["results"] == r.data
    row = read_jsonl(case / "log.jsonl")[-1]
    assert row["tool"] == "search" and row["status"] == "ok" and row["usd"] > 0


def test_logged_search_replays_without_calling_the_provider(strat, case, brave):
    strat("search", "q", "--step", "s1")
    r = strat("search", "q", "--step", "s1", "--json")
    assert r.code == 0 and r.data[0]["provider"] == "brave"
    assert len(brave) == 1


def test_all_providers_failing_stops_and_asks(strat, case, brave):
    r = strat("search", "fail", "--step", "s2")
    assert r.code == 3 and "all search providers failed" in r.err
    row = read_jsonl(case / "log.jsonl")[-1]
    assert row["status"] == "error" and row["step"] == "s2"


def test_key_from_dotenv_file(strat, case, brave, monkeypatch, tmp_path):
    monkeypatch.delenv("BRAVE_API_KEY")
    env = tmp_path / ".env"
    env.write_text("# comment\nBRAVE_API_KEY='from-file'\n")
    monkeypatch.setenv("STRAT_ENV_FILE", str(env))
    assert strat("search", "q", "--step", "s3").code == 0
    assert brave[-1][1]["X-Subscription-Token"] == "from-file"
