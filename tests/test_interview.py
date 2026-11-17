"""Interviews and model respondents (Task 12).

Real transcripts are registered as `interview` sources with phones and e-mails masked; a model
respondent's session is an `interview` source marked synthetic, and every claim citing it must be
`synthetic`. No network: `net.post` is replaced.
"""

import json

import pytest

from conftest import REPO
from strat import models, net
from strat.core import read_json, read_jsonl

FIX = REPO / "tests" / "fixtures" / "interview"
GUIDE = str(FIX / "guide_1.md")
PERSONA = str(FIX / "persona_mama.md")
BANNER_START = "> ВНИМАНИЕ: это имитация"


@pytest.fixture
def peer(monkeypatch):
    monkeypatch.setenv("ANYMODEL_API_KEY", "peer-key")
    monkeypatch.setenv("ANYMODEL_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("STRAT_PEER_MODEL", "vendor/strong-model")
    monkeypatch.setattr(models, "RETRY_PAUSE", 0)


@pytest.fixture
def chat(monkeypatch):
    """A fake chat endpoint answering each question with a numbered answer."""
    calls = []

    def fake(url, body, headers=None, timeout=30):
        data = json.loads(body)
        calls.append(data)
        n = len(calls)
        reply = {"choices": [{"message": {"role": "assistant",
                                          "content": f"Ответ номер {n}: подключила по акции."}}],
                 "usage": {"prompt_tokens": 400, "completion_tokens": 100}}
        return 200, {}, json.dumps(reply).encode()

    monkeypatch.setattr(net, "post", fake)
    return calls


def sources_of(case):
    return {s["id"]: s for s in read_jsonl(case / "sources" / "index.jsonl")}


def run_persona(strat, *extra):
    return strat("interview", "persona", PERSONA, "--guide", GUIDE, "--step", "persona.mama",
                 "--json", *extra)


# --- model respondents ------------------------------------------------------------------------

def test_persona_session_is_a_synthetic_source_with_a_banner(strat, case, peer, chat):
    r = run_persona(strat, "--questions", "3")
    assert r.code == 0, r.err
    sid = r.data["id"]
    src = sources_of(case)[sid]
    assert src["kind"] == "interview" and src["synthetic"] is True and src["by"] == "peer"
    out = case / "interviews" / "persona_mama.md"
    text = out.read_text(encoding="utf-8")
    assert text.startswith(BANNER_START)
    assert text.count("## Q") == 3 and "Ответ номер 3" in text
    assert len(chat) == 3
    system = chat[0]["messages"][0]["content"]
    assert "бухгалтером" in system  # the persona file is in the prompt
    assert chat[2]["messages"][-1]["content"].startswith("Как вы сейчас храните")


def test_persona_claim_is_stored_as_synthetic_and_refused_as_a_fact(strat, case, peer, chat):
    sid = run_persona(strat, "--questions", "2").data["id"]
    fact = strat("claim", "add", "--type", "fact", "--kind", "market",
                 "--text", "Пользователи подключали сервис по акции", "--source", sid,
                 "--where", "Q1", "--quote", "подключила по акции", "--as-of", "2026-11")
    assert fact.code == 1 and "synthetic" in fact.err
    hyp = strat("claim", "add", "--type", "hypothesis", "--kind", "market",
                "--text", "Пользователи подключали сервис по акции", "--source", sid,
                "--where", "Q1", "--quote", "подключила по акции")
    assert hyp.code == 1 and "synthetic" in hyp.err
    ok = strat("claim", "add", "--type", "synthetic", "--kind", "market",
               "--text", "Модельный респондент говорит, что подключила сервис по акции",
               "--source", sid, "--where", "Q1", "--quote", "подключила по акции", "--json")
    assert ok.code == 0, ok.err
    assert ok.data["claim"]["type"] == "synthetic"
    wrong_q = strat("claim", "add", "--type", "synthetic", "--kind", "market", "--text", "т",
                    "--source", sid, "--where", "Q2", "--quote", "Ответ номер 1")
    assert wrong_q.code == 1  # --where Q2 locates the second block only


def test_persona_source_cannot_back_a_fact_through_supports(strat, case, peer, chat):
    sid = run_persona(strat, "--questions", "1").data["id"]
    assert strat("claim", "add", "--type", "synthetic", "--kind", "market", "--text", "с",
                 "--source", sid, "--where", "Q1", "--quote", "по акции").code == 0
    assert strat("claim", "add", "--type", "hypothesis", "--kind", "market",
                 "--text", "Возможно, уходят пользователи акции", "--supports", "C001").code == 0
    assert strat("source", "add", "materials/competitor.html").code == 0
    direct = strat("claim", "add", "--type", "fact", "--kind", "price", "--text", "ф",
                   "--source", "S002", "--where", "Семейный", "--quote", "299 ₽",
                   "--as-of", "2026-11", "--supports", "C001")
    assert direct.code == 1 and "synthetic" in direct.err
    through = strat("claim", "add", "--type", "fact", "--kind", "price", "--text", "ф",
                    "--source", "S002", "--where", "Семейный", "--quote", "299 ₽",
                    "--as-of", "2026-11", "--supports", "C002")
    assert through.code == 1 and "synthetic" in through.err


def test_persona_cost_is_logged(strat, case, peer, chat):
    r = run_persona(strat, "--questions", "2")
    assert r.code == 0, r.err
    rows = read_jsonl(case / "log.jsonl")
    model_rows = [x for x in rows if x["tool"] == "model peer"]
    assert [x["step"] for x in model_rows] == ["persona.mama.q1", "persona.mama.q2"]
    assert all(x["usd"] > 0 for x in model_rows)
    assert rows[-1]["tool"] == "interview persona" and rows[-1]["ref"] == r.data["id"]
    assert read_json(case / "state.json")["budget"]["spent_usd"] > 0
    assert r.data["usd"] == pytest.approx(sum(x["usd"] for x in model_rows))


def test_persona_step_is_idempotent_and_resumes(strat, case, peer, chat, monkeypatch):
    def fail_second(url, body, headers=None, timeout=30):
        if fail_second.n == 1:
            raise net.HttpError("HTTP 500", status=500)
        fail_second.n += 1
        reply = {"choices": [{"message": {"content": "первый ответ"}}],
                 "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        return 200, {}, json.dumps(reply).encode()

    fail_second.n = 0
    monkeypatch.setattr(net, "post", fail_second)
    r = run_persona(strat, "--questions", "2")
    assert r.code == 2 and "again" in r.err
    monkeypatch.setattr(net, "post", lambda *a, **k: (200, {}, json.dumps(
        {"choices": [{"message": {"content": "второй ответ"}}],
         "usage": {"prompt_tokens": 10, "completion_tokens": 5}}).encode()))
    r = run_persona(strat, "--questions", "2")
    assert r.code == 0, r.err
    text = (case / "interviews" / "persona_mama.md").read_text(encoding="utf-8")
    assert "первый ответ" in text and "второй ответ" in text
    again = run_persona(strat, "--questions", "2")
    assert again.code == 0 and again.data["replayed"] is True


def test_no_peer_key_exits_3_with_the_import_path(strat, case):
    r = run_persona(strat)
    assert r.code == 3
    assert "agents/persona.md" in r.err and "interview add" in r.err and "--persona" in r.err
    assert not (case / "interviews" / "persona_mama.md").exists()


def test_subagent_output_is_imported_as_same_vendor_synthetic(strat, case):
    r = strat("interview", "add", str(FIX / "persona_session_subagent.md"), "--persona", "mama",
              "--json")
    assert r.code == 0, r.err
    src = sources_of(case)[r.data["id"]]
    assert src["synthetic"] is True and src["by"] == "same-vendor"
    text = (case / "interviews" / "persona_mama.md").read_text(encoding="utf-8")
    assert text.startswith(BANNER_START)
    fact = strat("claim", "add", "--type", "fact", "--kind", "market", "--text", "т",
                 "--source", r.data["id"], "--where", "Q2", "--quote", "сразу отписалась",
                 "--as-of", "2026-11")
    assert fact.code == 1 and "synthetic" in fact.err


def test_guide_without_consent_line_is_refused(strat, case, peer, chat):
    r = strat("interview", "persona", PERSONA, "--guide", str(FIX / "guide_no_consent.md"),
              "--step", "persona.x")
    assert r.code == 1 and "Согласие" in r.err
    assert chat == []


# --- real transcripts -------------------------------------------------------------------------

def test_transcript_phones_and_emails_are_masked(strat, case):
    r = strat("interview", "add", str(FIX / "interview_resp1.txt"), "--mask", "Мария Соколова",
              "--json")
    assert r.code == 0, r.err
    src = sources_of(case)[r.data["id"]]
    assert src["kind"] == "interview" and not src.get("synthetic")
    snap = (case / src["snapshot"]).read_text(encoding="utf-8")
    stored = (case / src["origin"]).read_text(encoding="utf-8")
    for text in (snap, stored):
        assert "example.com" not in text and "123-45-67" not in text and "765 43 21" not in text
        assert "Соколова" not in text
        assert "[ТЕЛЕФОН]" in text and "[EMAIL]" in text and "[ИМЯ]" in text
        assert "41,0" in text and "2 000 000" in text and "299 рублей" in text
    assert r.data["masked"] == {"phone": 2, "email": 1, "name": 3}
    assert not (case / "materials" / "interview_resp1.txt").exists()  # the raw file stays out
    ok = strat("claim", "add", "--type", "hypothesis", "--kind", "market",
               "--text", "Респондент отключил подписку после первого списания",
               "--source", r.data["id"], "--quote", "отключила подписку")
    assert ok.code == 0, ok.err


def test_source_add_of_an_interview_transcript_masks_too(strat, case):
    r = strat("source", "add", str(FIX / "interview_resp1.txt"), "--json")
    assert r.code == 0, r.err
    src = sources_of(case)[r.data["id"]]
    assert src["kind"] == "interview"
    snap = (case / src["snapshot"]).read_text(encoding="utf-8")
    assert "example.com" not in snap and "[ТЕЛЕФОН]" in snap
    assert not (case / "materials" / "interview_resp1.txt").exists()
