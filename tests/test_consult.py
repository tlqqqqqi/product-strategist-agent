"""strat consult / strat debate (Task 7): the challenger from another vendor, verdicts and the
capped debate. No network: `net.post` is replaced; the replies are the OpenAI chat shape."""

import json

import pytest

from strat import models, net
from strat.core import read_json, read_jsonl
from test_validate import ready  # noqa: F401  (a case whose Gate 1 files and claims pass)

KEYS = ("STRAT_PEER_API_KEY", "STRAT_PEER_BASE_URL", "STRAT_PEER_MODEL")


def chat(content):
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    return {"choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 4000, "completion_tokens": 600}}


OBJECTIONS = {"objections": [
    {"target": "Вариант 3. Откатить цену", "severity": "critical",
     "text": "Отток мог вырасти не из-за цены: рост начался до повышения [C001].",
     "claims": ["C001"]},
    {"target": "Вариант 1. Оставить как есть", "severity": "major",
     "text": "Не показан лучший случай для «оставить как есть».", "claims": []},
    {"target": "набор вариантов", "severity": "critical",
     "text": "Нет варианта со скидкой только для новых семей.", "claims": []},
]}


@pytest.fixture
def peer(monkeypatch):
    monkeypatch.setattr(models, "RETRY_PAUSE", 0)
    monkeypatch.setenv("STRAT_PEER_API_KEY", "peer-key")
    monkeypatch.setenv("STRAT_PEER_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("STRAT_PEER_MODEL", "vendor/strong-model")


@pytest.fixture
def post(monkeypatch):
    """Set `replies` in a test; each call pops the next one (the last one repeats)."""
    replies, calls = [], []

    def fake(url, body, headers=None, timeout=30):
        calls.append({"url": url, "body": json.loads(body)})
        reply = replies.pop(0) if len(replies) > 1 else replies[0]
        if isinstance(reply, Exception):
            raise reply
        return 200, {}, json.dumps(reply).encode()

    monkeypatch.setattr(net, "post", fake)
    return replies, calls


def objections(case):
    return read_jsonl(case / "objections.jsonl")


def sent_text(call):
    return "\n".join(m["content"] for m in call["body"]["messages"])


# --- consult ------------------------------------------------------------------------------------

def test_challenge_sends_the_case_files_and_writes_objections(strat, ready, peer, post):
    replies, calls = post
    replies.append(chat(OBJECTIONS))
    r = strat("consult", "challenge", "--json")
    assert r.code == 0, r.err
    assert len(calls) == 1 and calls[0]["body"]["model"] == "vendor/strong-model"
    text = sent_text(calls[0])
    for needle in ("Откатывать ли цену тарифа", "## Варианты против критериев",
                   "### Вариант 3. Откатить цену", "Отток в октябре 6.8%"):
        assert needle in text  # brief, table, options and claims.md, nothing else
    rows = objections(ready)
    assert [o["id"] for o in rows] == ["O001", "O002", "O003"]
    first = rows[0]
    assert {k: first[k] for k in ("call", "target", "severity", "verdict", "reason", "debate")} \
        == {"call": "challenge", "target": "Вариант 3. Откатить цену", "severity": "critical",
            "verdict": None, "reason": None, "debate": []}
    assert first["by"] == "peer" and first["model"] == "vendor/strong-model"
    assert first["claims"] == ["C001"]


def test_variants_sends_no_claims_file(strat, ready, peer, post):
    replies, calls = post
    replies.append(chat(OBJECTIONS))
    assert strat("consult", "variants").code == 0
    text = sent_text(calls[0])
    assert "### Вариант 3. Откатить цену" in text and "Отток в октябре 6.8%" not in text
    assert {o["call"] for o in objections(ready)} == {"variants"}


def test_cost_is_logged_and_added_to_the_budget(strat, ready, peer, post):
    replies, _ = post
    replies.append(chat(OBJECTIONS))
    assert strat("consult", "challenge").code == 0
    log = read_jsonl(ready / "log.jsonl")
    model_rows = [row for row in log if row["tool"] == "model peer"]
    assert len(model_rows) == 1 and model_rows[0]["usd"] > 0
    assert model_rows[0]["tokens_in"] == 4000 and model_rows[0]["tokens_out"] == 600
    assert log[-1]["tool"] == "consult" and log[-1]["step"] == "consult.challenge"
    assert read_json(ready / "state.json")["budget"]["spent_usd"] == pytest.approx(
        model_rows[0]["usd"])


def test_a_logged_call_is_not_repeated(strat, ready, peer, post):
    replies, calls = post
    replies.append(chat(OBJECTIONS))
    assert strat("consult", "challenge").code == 0
    r = strat("consult", "challenge")
    assert r.code == 0 and "already done" in r.out
    assert len(calls) == 1 and len(objections(ready)) == 3
    assert strat("consult", "challenge", "--step", "consult.challenge.2").code == 0
    assert len(calls) == 2 and len(objections(ready)) == 6


@pytest.mark.parametrize("reply", [
    "Вот мои возражения: вариант 3 слабый.",                       # not JSON
    {"objections": "вариант 3 слабый"},                            # not a list
    {"objections": [{"target": "Вариант 3", "text": "x"}]},        # no severity
    {"objections": [{"target": "Вариант 3", "severity": "fatal", "text": "x"}]},
    {"items": []},                                                 # wrong key
])
def test_malformed_model_json_is_an_error_not_an_empty_list(strat, ready, peer, post, reply):
    replies, _ = post
    replies.append(chat(reply))
    r = strat("consult", "challenge")
    assert r.code == 1 and "fixed JSON shape" in r.err
    assert objections(ready) == []
    assert read_jsonl(ready / "log.jsonl")[-1]["status"] == "error"


def test_json_in_a_code_fence_is_accepted(strat, ready, peer, post):
    replies, _ = post
    replies.append(chat("```json\n" + json.dumps(OBJECTIONS, ensure_ascii=False) + "\n```"))
    assert strat("consult", "challenge").code == 0
    assert len(objections(ready)) == 3


def test_missing_case_file_is_an_error(strat, ready, peer, post):
    (ready / "table.md").unlink()
    r = strat("consult", "variants")
    assert r.code == 1 and "table.md" in r.err


# --- no peer key: native subagent, file import ---------------------------------------------------

def test_without_peer_key_exits_3_and_the_file_import_works(strat, ready, post, tmp_path):
    _, calls = post
    r = strat("consult", "challenge")
    assert r.code == 3 and calls == []
    assert "agents/challenger.md" in r.err and "--from-file" in r.err
    f = tmp_path / "objections.json"
    f.write_text(json.dumps(OBJECTIONS, ensure_ascii=False))
    r = strat("consult", "challenge", "--from-file", str(f))
    assert r.code == 0, r.err
    rows = objections(ready)
    assert len(rows) == 3 and {o["by"] for o in rows} == {"same-vendor"}
    row = read_jsonl(ready / "log.jsonl")[-1]
    assert row["tool"] == "consult" and "same-vendor" in row["note"]


def test_a_malformed_import_file_is_an_error(strat, ready, tmp_path):
    f = tmp_path / "objections.json"
    f.write_text('{"objections": [{"target": "x"}]}')
    r = strat("consult", "challenge", "--from-file", str(f))
    assert r.code == 1 and objections(ready) == []


# --- verdicts -----------------------------------------------------------------------------------

@pytest.fixture
def challenged(strat, ready, peer, post):
    replies, calls = post
    replies.append(chat(OBJECTIONS))
    assert strat("consult", "challenge").code == 0
    return ready


def test_each_objection_needs_a_verdict_before_the_gate_passes(strat, challenged):
    r = strat("gate", "check", "1")
    assert r.code == 1 and "O001 has no verdict" in r.err
    assert strat("consult", "verdict", "O001", "rejected", "--reason",
                 "Рост оттока начался после повышения цены [C001]").code == 0
    assert strat("consult", "verdict", "O002", "accepted", "--reason",
                 "Добавили лучший случай для варианта 1").code == 0
    r = strat("gate", "check", "1")
    assert r.code == 1 and "O003 has no verdict" in r.err and "O001" not in r.err
    assert strat("consult", "verdict", "O003", "open", "--reason",
                 "Нужны данные о новых семьях").code == 0
    assert strat("gate", "check", "1").code == 0


def test_gate3_refuses_an_open_major_or_critical_objection(strat, challenged):
    """omp on DeepSeek Flash signed off with a major objection to the chosen option still open.
    Gate 3 now refuses it until it is answered, its option was not chosen, or the user accepts
    the risk; an accepted risk must be named in decisions.md."""
    from strat import validate

    for oid in ("O001", "O002", "O003"):
        assert strat("consult", "verdict", oid, "open", "--reason", "Нужны данные").code == 0
    r = strat("gate", "check", "3")
    assert r.code == 1
    assert all(f"{oid} [" in r.err and "is open" in r.err for oid in ("O001", "O002", "O003"))
    assert "is open" not in strat("gate", "check", "2").err      # Gate 2 shows them instead
    assert strat("consult", "verdict", "O001", "not-chosen", "--reason",
                 "Руководитель выбрал вариант 2").code == 0
    assert strat("consult", "verdict", "O002", "risk-accepted", "--reason",
                 "Пользователь: «риск понимаю, идём дальше»").code == 0
    assert strat("consult", "verdict", "O003", "rejected", "--reason",
                 "Рост начался после повышения [C001]").code == 0
    assert "is open" not in strat("gate", "check", "3").err
    steps = [r["step"] for r in read_jsonl(challenged / "log.jsonl") if r["tool"] == "consult verdict"]
    assert len(steps) == len(set(steps)), steps   # a changed verdict is a new step, not a repeat
    (challenged / "decisions.md").write_text("# Журнал решений\n\n- Выбранный вариант: 2\n")
    assert any("O002" in e and "risk-accepted" in e
               for e in validate.check_file(challenged, "decisions.md"))
    (challenged / "decisions.md").write_text("# Журнал решений\n\n- Принятые риски: O002\n")
    assert not any("risk-accepted" in e for e in validate.check_file(challenged, "decisions.md"))


def test_verdict_rules(strat, challenged):
    assert strat("consult", "verdict", "O001", "rejected").code == 1          # no reason
    r = strat("consult", "verdict", "O001", "rejected", "--reason", "Не согласны")
    assert r.code == 1 and "claim" in r.err                                    # cites no claim
    r = strat("consult", "verdict", "O001", "rejected", "--reason", "См. [C099]")
    assert r.code == 1 and "C099" in r.err                                     # unknown claim
    assert strat("consult", "verdict", "O001", "maybe", "--reason", "x").code == 1
    assert strat("consult", "verdict", "O999", "open", "--reason", "x").code == 1
    assert all(o["verdict"] is None for o in objections(challenged))
    assert strat("consult", "verdict", "O001", "rejected", "--reason",
                 "Рост начался после повышения [C001]").code == 0
    o = objections(challenged)[0]
    assert o["verdict"] == "rejected" and o["reason"].endswith("[C001]")
    assert read_jsonl(challenged / "log.jsonl")[-1]["tool"] == "consult verdict"


def test_list_shows_open_and_disputed(strat, challenged):
    strat("consult", "verdict", "O002", "open", "--reason", "Нужны данные")
    r = strat("consult", "list", "--json")
    assert r.code == 0
    rows = {o["id"]: o for o in r.data["objections"]}
    assert rows["O002"]["unresolved"] and rows["O001"]["unresolved"]  # no verdict yet
    assert r.data["unresolved"] == ["O001", "O002", "O003"]


# --- debate -------------------------------------------------------------------------------------

def reject(strat, oid, reason="Рост начался после повышения цены [C001]"):
    assert strat("consult", "verdict", oid, "rejected", "--reason", reason).code == 0


def test_debate_refuses_a_non_rejected_or_non_critical_objection(strat, challenged, post):
    _, calls = post
    n = len(calls)
    r = strat("debate", "O001")
    assert r.code == 1 and "rejected" in r.err                                 # no verdict yet
    strat("consult", "verdict", "O002", "rejected", "--reason", "Лучший случай есть [C002]")
    r = strat("debate", "O002")
    assert r.code == 1 and "critical" in r.err
    assert len(calls) == n


def test_debate_sends_objection_reason_and_cited_claims_and_stores_the_reply(
        strat, challenged, post):
    replies, calls = post
    reject(strat, "O001")
    replies.clear()
    replies.append(chat({"stance": "maintain", "text": "Данные за сентябрь не исключают сезон."}))
    r = strat("debate", "O001", "--json")
    assert r.code == 0, r.err
    text = sent_text(calls[-1])
    assert "Отток мог вырасти не из-за цены" in text
    assert "Рост начался после повышения цены" in text
    assert "Отток в октябре 6.8%" in text and "6.8" in text  # the cited claim with its quote
    o = objections(challenged)[0]
    assert len(o["debate"]) == 1
    entry = o["debate"][0]
    assert entry["round"] == 1 and entry["stance"] == "maintain" and entry["by"] == "peer"
    assert entry["agent_reason"].startswith("Рост начался")
    assert o["verdict"] == "open"  # the challenger maintains: the agent must decide again
    log = read_jsonl(challenged / "log.jsonl")
    assert log[-1]["tool"] == "debate" and log[-2]["tool"] == "model peer"


def test_a_concession_keeps_the_rejection(strat, challenged, post):
    replies, _ = post
    reject(strat, "O001")
    replies.clear()
    replies.append(chat({"stance": "concede", "text": "Согласен."}))
    assert strat("debate", "O001").code == 0
    assert objections(challenged)[0]["verdict"] == "rejected"


def test_debate_rounds_are_capped(strat, challenged, post):
    replies, calls = post
    replies.clear()
    replies.append(chat({"stance": "maintain", "text": "Остаюсь при своём."}))
    for _ in range(2):
        reject(strat, "O001")
        assert strat("debate", "O001").code == 0
    reject(strat, "O001", "Третий ответ [C001]")
    n = len(calls)
    r = strat("debate", "O001")
    assert r.code == 1 and "max_rounds" in r.err
    assert len(calls) == n and len(objections(challenged)[0]["debate"]) == 2


def test_debates_per_case_are_capped(strat, challenged, post, tmp_path):
    replies, calls = post
    f = tmp_path / "more.json"
    f.write_text(json.dumps({"objections": [
        {"target": "Вариант 2. Закрыть тариф", "severity": "critical", "text": "Ещё одно."}]},
        ensure_ascii=False))
    assert strat("consult", "challenge", "--from-file", str(f), "--step", "c.2").code == 0
    replies.clear()
    replies.append(chat({"stance": "concede", "text": "Согласен."}))
    for oid in ("O001", "O003"):
        reject(strat, oid)
        assert strat("debate", oid).code == 0
    reject(strat, "O004")
    n = len(calls)
    r = strat("debate", "O004")
    assert r.code == 1 and "max_debates_per_case" in r.err and len(calls) == n


def test_malformed_debate_reply_is_an_error(strat, challenged, post):
    replies, _ = post
    reject(strat, "O001")
    replies.clear()
    replies.append(chat({"stance": "maybe", "text": "x"}))
    r = strat("debate", "O001")
    assert r.code == 1 and "fixed JSON shape" in r.err
    assert objections(challenged)[0]["debate"] == []


def test_debate_without_peer_key_exits_3_and_imports_a_file(strat, challenged, post,
                                                            monkeypatch, tmp_path):
    _, calls = post
    reject(strat, "O001")
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    n = len(calls)
    r = strat("debate", "O001")
    assert r.code == 3 and "agents/challenger.md" in r.err and len(calls) == n
    f = tmp_path / "reply.json"
    f.write_text(json.dumps({"stance": "concede", "text": "Принимаю ответ."}, ensure_ascii=False))
    assert strat("debate", "O001", "--from-file", str(f)).code == 0
    entry = objections(challenged)[0]["debate"][0]
    assert entry["by"] == "same-vendor" and entry["stance"] == "concede"
