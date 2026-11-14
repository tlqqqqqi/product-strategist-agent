"""Search (Tasks 5, 9): Brave, Tavily, Exa by kind with fall-through. No network: the HTTP
layer is replaced."""

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
    assert r.code == 2
    for key in ("BRAVE_API_KEY", "TAVILY_API_KEY", "EXA_API_KEY"):
        assert key in r.err
    assert "stop and ask the user" in r.err and "web search" in r.err


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
    assert r.code == 2 and "all search providers failed" in r.err
    assert "stop and ask the user" in r.err
    row = read_jsonl(case / "log.jsonl")[-1]
    assert row["status"] == "error" and row["step"] == "s2"


def test_key_from_dotenv_file(strat, case, brave, monkeypatch, tmp_path):
    monkeypatch.delenv("BRAVE_API_KEY")
    env = tmp_path / ".env"
    env.write_text("# comment\nBRAVE_API_KEY='from-file'\n")
    monkeypatch.setenv("STRAT_ENV_FILE", str(env))
    assert strat("search", "q", "--step", "s3").code == 0
    assert brave[-1][1]["X-Subscription-Token"] == "from-file"


# --- Task 9: several providers -------------------------------------------------------------

TAVILY_OK = {"results": [{"title": "Т", "url": "https://t.ru", "content": "из Tavily"}]}
EXA_OK = {"results": [{"title": "Э", "url": "https://e.ru", "highlights": ["из Exa"]}]}


@pytest.fixture
def three(monkeypatch, brave):
    """All three providers answer; a provider whose name is in FAIL raises."""
    from strat import providers, search

    fail, posts = set(), []

    def fake_post(url, payload, headers=None, timeout=30):
        name = "tavily" if "tavily" in url else "exa"
        posts.append(name)
        if name in fail:
            raise net.HttpError(f"HTTP 429 from {name}")
        return TAVILY_OK if name == "tavily" else EXA_OK

    monkeypatch.setattr(providers, "post_json", fake_post)
    routes = {"search": {"keyword": ["tavily", "exa", "brave"], "text": ["tavily", "brave"],
                         "semantic": ["exa", "brave"],
                         "usd_per_call": {"brave": 0.005, "tavily": 0.008, "exa": 0.007}}}
    monkeypatch.setattr(search, "load_config", lambda name: routes)
    for key in ("TAVILY_API_KEY", "EXA_API_KEY"):
        monkeypatch.setenv(key, "k")
    return fail, posts


def test_chain_follows_routes_order_as_written(monkeypatch):
    """The order per kind is the one in routes.yaml (set by the Russian query test); a kind
    with no entry falls back to every provider, Brave first."""
    from strat import search

    monkeypatch.setattr(search, "load_config",
                        lambda name: {"search": {"semantic": ["exa", "tavily", "brave"],
                                                 "keyword": ["brave", "exa", "tavily"]}})
    assert search.chain("semantic") == ["exa", "tavily", "brave"]
    assert search.chain("keyword") == ["brave", "exa", "tavily"]
    assert search.chain("text") == ["brave", "exa", "tavily"]


@pytest.mark.parametrize("kind", ["keyword", "text", "semantic"])
def test_real_routes_name_known_providers_and_prices(kind):
    from strat import search
    from strat.core import load_config

    names = search.chain(kind)
    assert sorted(names) == ["brave", "exa", "tavily"]  # every provider stays a fallback
    prices = load_config("routes")["search"]["usd_per_call"]
    for name in names:
        assert name in ("brave", "tavily", "exa") and prices[name] > 0


def test_kind_picks_the_first_provider_of_its_chain(strat, case, three):
    r = strat("search", "q", "--kind", "semantic", "--step", "s1", "--json")
    assert r.code == 0 and r.data[0]["provider"] == "exa"
    row = read_jsonl(case / "log.jsonl")[-1]
    assert row["usd"] == 0.007 and "exa" in row["note"]


@pytest.mark.parametrize("key", ["BRAVE_API_KEY", "TAVILY_API_KEY", "EXA_API_KEY"])
def test_any_single_key_works(strat, case, three, monkeypatch, key):
    for k in ("BRAVE_API_KEY", "TAVILY_API_KEY", "EXA_API_KEY"):
        if k != key:
            monkeypatch.delenv(k)
    r = strat("search", "q", "--kind", "keyword", "--step", "s1", "--json")
    assert r.code == 0, r.err
    assert r.data[0]["provider"] == key.split("_")[0].lower()


def test_failing_provider_falls_through_to_the_next(strat, case, three):
    fail, posts = three
    fail.add("tavily")
    r = strat("search", "q", "--kind", "keyword", "--step", "s1", "--json")
    assert r.code == 0 and r.data[0]["provider"] == "exa"
    assert posts == ["tavily", "exa"]
    rows = [x for x in read_jsonl(case / "log.jsonl") if x["tool"] == "search"]
    assert [x["status"] for x in rows] == ["error", "ok"]


def test_every_provider_failing_exits_2_and_asks(strat, case, three):
    fail, posts = three
    fail.update({"tavily", "exa"})
    r = strat("search", "fail", "--kind", "keyword", "--step", "s1")
    assert r.code == 2
    assert "tavily" in r.err and "exa" in r.err and "brave" in r.err
    assert "stop and ask the user" in r.err


def test_replay_after_fall_through_costs_nothing(strat, case, three):
    fail, posts = three
    fail.add("tavily")
    strat("search", "q", "--kind", "keyword", "--step", "s1")
    r = strat("search", "q", "--kind", "keyword", "--step", "s1", "--json")
    assert r.code == 0 and r.data[0]["provider"] == "exa"
    assert posts == ["tavily", "exa"]
