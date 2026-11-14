"""Each provider turns a saved (synthetic) response into title, url, snippet. No network."""

import json

import pytest

from strat import net, providers
from strat.providers import brave, exa, tavily

TAVILY_OK = {"query": "q", "results": [
    {"title": "Тарифы на облако", "url": "https://example.ru/tariffs",
     "content": "Семейный тариф  на 6 человек\n стоит 299 руб.", "score": 0.8,
     "published_date": "2026-10-01"},
    {"title": "Без даты", "url": "https://example.ru/b", "content": "текст", "score": 0.5},
]}

EXA_OK = {"requestId": "r1", "results": [
    {"title": "Отток подписчиков", "url": "https://example.ru/churn", "id": "x",
     "publishedDate": "2026-09-30T00:00:00.000Z",
     "highlights": ["Отток в среднем 5% в месяц.", "Семейные тарифы удерживают лучше."]},
    {"title": None, "url": "https://example.ru/t", "text": "Полный текст " * 100},
], "costDollars": {"total": 0.007}}


@pytest.fixture
def posted(monkeypatch):
    calls = []

    def fake_post(url, payload, headers=None, timeout=30):
        calls.append((url, payload, headers))
        return TAVILY_OK if "tavily" in url else EXA_OK

    monkeypatch.setattr(providers, "post_json", fake_post)
    return calls


def test_tavily_parses_results_and_sends_key_and_language(posted):
    out = tavily.search("семейное облако", "text", 5, "tv-key")
    assert out == [
        {"title": "Тарифы на облако", "url": "https://example.ru/tariffs",
         "snippet": "Семейный тариф на 6 человек стоит 299 руб.", "date": "2026-10-01"},
        {"title": "Без даты", "url": "https://example.ru/b", "snippet": "текст"},
    ]
    url, payload, headers = posted[0]
    assert url == "https://api.tavily.com/search"
    assert headers["Authorization"] == "Bearer tv-key"
    assert payload["query"] == "семейное облако" and payload["max_results"] == 5
    assert payload["search_depth"] == "basic" and payload["language"] == "ru"


def test_exa_parses_highlights_or_cuts_text(posted):
    out = exa.search("why families leave a cloud plan", "semantic", 3, "ex-key")
    assert out[0] == {"title": "Отток подписчиков", "url": "https://example.ru/churn",
                      "snippet": "Отток в среднем 5% в месяц. … Семейные тарифы удерживают лучше.",
                      "date": "2026-09-30"}
    assert out[1]["title"] == "" and len(out[1]["snippet"]) <= 400
    url, payload, headers = posted[0]
    assert url == "https://api.exa.ai/search" and headers["x-api-key"] == "ex-key"
    assert payload["numResults"] == 3 and payload["contents"]["highlights"]


def test_brave_keeps_page_age_as_date(monkeypatch):
    body = {"web": {"results": [{"title": "T", "url": "https://e.ru", "description": "d",
                                 "page_age": "2026-08-01T10:00:00"}]}}
    monkeypatch.setattr(net, "get", lambda *a, **k: (200, {}, json.dumps(body).encode()))
    assert brave.search("q", "keyword", 5, "k") == [
        {"title": "T", "url": "https://e.ru", "snippet": "d", "date": "2026-08-01"}]


@pytest.mark.parametrize("module", [tavily, exa])
def test_response_without_results_list_is_a_provider_failure(monkeypatch, module):
    monkeypatch.setattr(providers, "post_json", lambda *a, **k: {"error": "quota"})
    with pytest.raises(net.HttpError):
        module.search("q", "keyword", 5, "k")


def test_post_json_reports_non_json_as_http_error(monkeypatch):
    class Resp:
        status = 200

        def read(self, n=-1):
            return b"<html>"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout: Resp())
    with pytest.raises(net.HttpError, match="not JSON"):
        providers.post_json("https://api.example.com/x", {"a": 1})
