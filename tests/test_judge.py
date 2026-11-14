"""strat judge (Task 8): Jev first, then a cheap chat model on the peer endpoint, then the IDE
agent. Low confidence escalates (exit 3) and is logged. No network: `net.post` is replaced."""

import json

import pytest

from strat import models, net
from strat.core import read_jsonl

KEYS = ("STRAT_JEV_API_KEY", "STRAT_JEV_BASE_URL", "STRAT_JEV_MODEL", "STRAT_PEER_API_KEY",
        "STRAT_PEER_BASE_URL", "STRAT_PEER_MODEL")
PRICE = "Семейный тариф: 2 ТБ на 5 человек — 299 ₽ в месяц."


@pytest.fixture
def claim(strat, case, monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(models, "RETRY_PAUSE", 0)
    assert strat("source", "add", "materials/competitor.html").code == 0
    r = strat("claim", "add", "--type", "fact", "--kind", "price",
              "--text", "Конкурент берёт 299 ₽ в месяц за семейный тариф на 5 человек",
              "--source", "S001", "--where", "Семейный", "--quote", PRICE, "--as-of", "2026-11")
    assert r.code == 0, r.err
    r = strat("claim", "add", "--type", "hypothesis", "--kind", "price",
              "--text", "Конкурент берёт 199 ₽ в месяц за семейный тариф")
    assert r.code == 0, r.err
    return "C001"


@pytest.fixture
def jev(monkeypatch):
    monkeypatch.setenv("STRAT_JEV_API_KEY", "jev-key")
    monkeypatch.setenv("STRAT_JEV_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("STRAT_JEV_MODEL", "jev/jev-1.14.0")


@pytest.fixture
def peer(monkeypatch):
    monkeypatch.setenv("STRAT_PEER_API_KEY", "peer-key")
    monkeypatch.setenv("STRAT_PEER_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("STRAT_PEER_MODEL", "vendor/cheap-model")


def jev_reply(p_yes):
    """The shape the live API returned on 2026-11-14."""
    return {"object": "decision", "model": "jev/jev-1.14.0",
            "answers": {"q": {"type": "noul", "noul": p_yes}},
            "usage": {"input_tokens": 280, "output_tokens": 20, "total_tokens": 300}}


def chat_reply(text):
    return {"choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 300, "completion_tokens": 5}}


@pytest.fixture
def post(monkeypatch):
    """Replies by URL: /systemone -> jev, /chat/completions -> peer. Set the lists in a test."""
    replies = {"systemone": [], "chat/completions": []}
    calls = []

    def fake(url, body, headers=None, timeout=30):
        calls.append({"url": url, "body": json.loads(body)})
        key = "systemone" if url.endswith("/systemone") else "chat/completions"
        reply = replies[key].pop(0) if len(replies[key]) > 1 else replies[key][0]
        if isinstance(reply, Exception):
            raise reply
        return 200, {}, json.dumps(reply).encode()

    monkeypatch.setattr(net, "post", fake)
    return replies, calls


def stored(case, cid="C001"):
    return {c["id"]: c for c in read_jsonl(case / "claims.jsonl")}[cid]["check"]


def test_confident_jev_answer_is_stored_on_the_claim(strat, case, claim, jev, post):
    replies, calls = post
    replies["systemone"] = [jev_reply(0.94)]
    r = strat("judge", "support", "--claim", "C001", "--json")
    assert r.code == 0, r.err
    assert r.data["answer"] == "yes" and r.data["by"] == "jev" and r.data["p"] == 0.94
    body = calls[0]["body"]
    assert body["model"] == "jev/jev-1.14.0" and body["state"]["evidence"] == PRICE
    check = stored(case)
    assert check["supported"] is True and check["by"] == "jev" and check["p"] == 0.94
    assert check["judgments"][-1]["question"] == "support"
    tools = [row["tool"] for row in read_jsonl(case / "log.jsonl")]
    assert tools[-2:] == ["model jev", "judge"]


def test_low_confidence_escalates_with_exit_3_and_is_logged(strat, case, claim, jev, post):
    replies, _ = post
    replies["systemone"] = [jev_reply(0.62)]
    r = strat("judge", "support", "--claim", "C001", "--json")
    assert r.code == 3
    assert "escalat" in r.err and "0.62" in r.err and "0.8" in r.err
    assert r.data["by"] == "agent" and r.data["escalated_from"]["by"] == "jev"
    row = read_jsonl(case / "log.jsonl")[-1]
    assert row["tool"] == "judge" and row["note"].startswith("escalated")
    check = stored(case)
    assert check["supported"] is None  # a low-confidence answer is not taken
    assert check["judgments"][-1]["escalated"] is True


def test_without_jev_key_the_peer_chat_model_answers(strat, case, claim, peer, post):
    replies, calls = post
    replies["chat/completions"] = [chat_reply("ANSWER: yes")]
    r = strat("judge", "support", "--claim", "C001", "--json")
    assert r.code == 0, r.err
    assert r.data["by"] == "peer" and r.data["answer"] == "yes" and r.data["p"] is None
    assert calls[0]["url"].endswith("/chat/completions")
    assert "ANSWER:" in calls[0]["body"]["messages"][0]["content"]
    assert stored(case)["by"] == "peer"


def test_peer_unsure_escalates(strat, case, claim, peer, post):
    replies, _ = post
    replies["chat/completions"] = [chat_reply("ANSWER: unsure")]
    r = strat("judge", "contradiction", "--claim", "C001", "--other", "C002")
    assert r.code == 3 and "unsure" in r.err
    assert read_jsonl(case / "log.jsonl")[-1]["note"].startswith("escalated")


def test_jev_failing_falls_back_to_peer(strat, case, claim, jev, peer, post):
    replies, calls = post
    replies["systemone"] = [net.HttpError("HTTP 503", status=503)]
    replies["chat/completions"] = [chat_reply("ANSWER: no")]
    r = strat("judge", "sufficient", "--claim", "C001", "--json")
    assert r.code == 0, r.err
    assert r.data["by"] == "peer" and r.data["answer"] == "no"
    assert sum(c["url"].endswith("/systemone") for c in calls) == 2  # one retry


def test_no_keys_exits_3_and_the_agent_answer_is_stored_as_agent(strat, case, claim, post):
    r = strat("judge", "support", "--claim", "C001", "--json")
    assert r.code == 3 and "--answer" in r.err
    assert r.data["by"] == "agent" and PRICE in r.data["prompt"]
    assert post[1] == []  # no call made
    r = strat("judge", "support", "--claim", "C001", "--answer", "yes", "--json")
    assert r.code == 0, r.err
    check = stored(case)
    assert check["supported"] is True and check["by"] == "agent" and check["p"] is None


def test_type_question_picks_the_most_likely_claim_type(strat, case, claim, jev, post):
    replies, calls = post
    probs = {"fact": 0.1, "hypothesis": 0.9, "forecast": 0.2, "assumption": 0.3, "gap": 0.01,
             "synthetic": 0.01, "conclusion": 0.05}
    replies["systemone"] = [{"answers": {k: {"type": "noul", "noul": v}
                                         for k, v in probs.items()}}]
    r = strat("judge", "type", "--claim", "C002", "--json")
    assert r.code == 0, r.err
    assert r.data["answer"] == "hypothesis" and r.data["p"] == 0.9
    qs = calls[0]["body"]["questions"]
    assert set(qs) == set(probs) and all(q["type"] == "noul" for q in qs.values())


def test_agent_answer_must_be_a_valid_label(strat, case, claim):
    r = strat("judge", "support", "--claim", "C001", "--answer", "maybe")
    assert r.code == 1 and "yes, no" in r.err


def test_contradiction_needs_other(strat, case, claim):
    r = strat("judge", "contradiction", "--claim", "C001")
    assert r.code == 1 and "--other" in r.err


def test_claim_check_shows_stored_judgments(strat, case, claim):
    strat("judge", "support", "--claim", "C001", "--answer", "no")
    r = strat("claim", "check", "C001", "--json")
    res = r.data["results"][0]
    assert res["supported"] is False and res["by"] == "agent"
    assert res["judgments"][-1]["answer"] == "no"
