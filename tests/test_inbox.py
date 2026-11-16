"""The user's own words gate the approvals (written by the harness's hook, read by the CLI).

Test runs: Sonnet 4.6 approved Gate 2 after the user said only «Продолжай.»; DeepSeek Flash
presented Gate 3 before its check passed and took the sign-off «Подписываю.» as acceptance of
risks it never asked about."""

import json
import time

from test_validate import ready, research, to_gate2  # noqa: F401


def said(cases, text, t=None):
    """What the harness hook appends when the user sends a message."""
    with (cases / ".inbox.jsonl").open("a") as f:
        f.write(json.dumps({"t": t or time.time() + 0.001, "text": text, "harness": "test"},
                           ensure_ascii=False) + "\n")


def test_without_an_inbox_the_old_rule_holds(strat, ready):
    assert strat("gate", "check", "1").code == 0
    assert strat("gate", "approve", "1").code == 0


def test_approval_needs_a_message_after_the_gate_became_ready(strat, ready, cases):
    """Flash's order: the user's words came before the check passed."""
    said(cases, "Подписываю.", t=time.time() - 60)
    assert strat("gate", "check", "1").code == 0
    r = strat("gate", "approve", "1")
    assert r.code == 1 and "has not answered since gate 1 became ready" in r.err
    said(cases, "Да, утверждаю план.")
    r = strat("gate", "approve", "1")
    assert r.code == 0, r.err
    log = [json.loads(x) for x in (ready / "log.jsonl").read_text().splitlines()]
    assert "«Да, утверждаю план.»" in log[-1]["note"]


def test_continue_is_not_a_yes(strat, ready, cases):
    """Sonnet 4.6 approved after «Продолжай.»."""
    said(cases, "Продолжай.", t=time.time() - 60)
    assert strat("gate", "check", "1").code == 0
    said(cases, "Продолжай.")
    r = strat("gate", "approve", "1")
    assert r.code == 1 and "is not a yes to gate 1" in r.err


def test_rechecking_does_not_move_the_ready_moment(strat, ready, cases):
    """The agent often runs the check again right before approving; the user's yes still counts."""
    assert strat("gate", "check", "1").code == 0
    said(cases, "Ок, утверждаю")
    assert strat("gate", "check", "1").code == 0
    assert strat("gate", "approve", "1").code == 0


def test_yes_words():
    from strat.inbox import is_yes

    for text in ("Да", "да, утверждаю план", "Подписываю.", "Выбираю вариант 2. Да.",
                 "Принимаю этот риск", "ок", "Согласен"):
        assert is_yes(text), text
    for text in ("Продолжай.", "По умолчанию.", "Нет", "Подожди, а почему вариант 3?",
                 "продолжи кейс", "Данные устарели"):
        assert not is_yes(text), text


def test_risk_accepted_must_quote_the_users_real_words(strat, ready, cases):
    from strat.consult import set_verdict
    from strat.core import write_jsonl

    write_jsonl(ready / "objections.jsonl", [
        {"id": "O001", "call": "challenge", "target": "Вариант 3", "severity": "major",
         "text": "Отток может не вернуться", "by": "test"}])
    said(cases, "Подписываю.")
    import pytest
    from strat.core import StratError

    with pytest.raises(StratError, match="user's own words"):
        set_verdict(ready, "O001", "risk-accepted", "Пользователь принял риск", False)
    with pytest.raises(StratError, match="user's own words"):
        set_verdict(ready, "O001", "risk-accepted", "Пользователь: «принимаю риск оттока»", False)
    said(cases, "Да, принимаю риск оттока, идём дальше")
    assert set_verdict(ready, "O001", "risk-accepted",
                       "Пользователь: «принимаю риск оттока»", False) == 0
