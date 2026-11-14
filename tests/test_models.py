"""The OpenAI-compatible client (Task 8): timeout, one retry, cost logged per call. No network:
`net.post` is replaced."""

import json

import pytest

from strat import models, net
from strat.core import read_jsonl

KEYS = ("STRAT_JEV_API_KEY", "STRAT_JEV_BASE_URL", "STRAT_JEV_MODEL", "STRAT_PEER_API_KEY",
        "STRAT_PEER_BASE_URL", "STRAT_PEER_MODEL")

CHAT_OK = {"choices": [{"index": 0, "message": {"role": "assistant", "content": "ANSWER: yes"}}],
           "usage": {"prompt_tokens": 1000, "completion_tokens": 10}}


@pytest.fixture
def peer(cases, monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("STRAT_PEER_API_KEY", "peer-key")
    monkeypatch.setenv("STRAT_PEER_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("STRAT_PEER_MODEL", "vendor/cheap-model")
    monkeypatch.setattr(models, "RETRY_PAUSE", 0)


def fake_post(monkeypatch, replies):
    """Each reply is a dict (a JSON answer) or an exception to raise."""
    calls = []

    def post(url, body, headers=None, timeout=30):
        calls.append({"url": url, "body": json.loads(body), "headers": headers,
                      "timeout": timeout})
        reply = replies[min(len(calls), len(replies)) - 1]
        if isinstance(reply, Exception):
            raise reply
        return 200, {"content-type": "application/json"}, json.dumps(reply).encode()

    monkeypatch.setattr(net, "post", post)
    return calls


def test_chat_sends_openai_format_with_120s_timeout(peer, monkeypatch):
    calls = fake_post(monkeypatch, [CHAT_OK])
    r = models.chat("peer", [{"role": "user", "content": "q"}], temperature=0)
    assert r["text"] == "ANSWER: yes"
    assert r["tokens_in"] == 1000 and r["tokens_out"] == 10
    call = calls[0]
    assert call["url"] == "https://example.test/v1/chat/completions"
    assert call["timeout"] == 120
    assert call["headers"]["Authorization"] == "Bearer peer-key"
    assert call["body"] == {"model": "vendor/cheap-model",
                            "messages": [{"role": "user", "content": "q"}], "temperature": 0}


def test_a_timeout_is_retried_once(peer, monkeypatch):
    calls = fake_post(monkeypatch, [net.HttpError("timed out"), CHAT_OK])
    assert models.chat("peer", [{"role": "user", "content": "q"}])["text"] == "ANSWER: yes"
    assert len(calls) == 2


def test_two_failures_give_up_after_one_retry(peer, monkeypatch):
    calls = fake_post(monkeypatch, [net.HttpError("timed out")])
    with pytest.raises(net.HttpError):
        models.chat("peer", [{"role": "user", "content": "q"}])
    assert len(calls) == 2


def test_a_client_error_is_not_retried(peer, monkeypatch):
    calls = fake_post(monkeypatch, [net.HttpError("HTTP 401", status=401)])
    with pytest.raises(net.HttpError):
        models.chat("peer", [{"role": "user", "content": "q"}])
    assert len(calls) == 1


def test_each_call_is_logged_with_its_cost(peer, monkeypatch, strat, case):
    fake_post(monkeypatch, [CHAT_OK])
    models.chat("peer", [{"role": "user", "content": "q"}], cdir=case, step="judge.x")
    row = read_jsonl(case / "log.jsonl")[-1]
    assert row["tool"] == "model peer" and row["status"] == "ok"
    assert row["tokens_in"] == 1000 and row["tokens_out"] == 10
    assert row["usd"] > 0 and "vendor/cheap-model" in row["note"]
    state = json.loads((case / "state.json").read_text())
    assert state["budget"]["spent_usd"] == pytest.approx(row["usd"])


def test_a_failed_call_is_logged_as_an_error(peer, monkeypatch, strat, case):
    fake_post(monkeypatch, [net.HttpError("timed out")])
    with pytest.raises(net.HttpError):
        models.chat("peer", [{"role": "user", "content": "q"}], cdir=case, step="judge.y")
    row = read_jsonl(case / "log.jsonl")[-1]
    assert row["status"] == "error" and "2 attempts" in row["note"]


def test_price_comes_from_routes_yaml():
    usd, estimated = models.price("jev/jev-1.14.0", 2_000_000, 0)
    assert usd == pytest.approx(1.0) and not estimated
    usd, estimated = models.price("unknown/model", 1_000_000, 0)
    assert usd > 0 and estimated


def test_no_key_means_no_endpoint(cases, monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    assert models.endpoint("jev") is None and models.endpoint("peer") is None
