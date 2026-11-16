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
                 "продолжи кейс", "Данные устарели", "Нет, не согласен", "Не утверждаю",
                 "Не подписываю", "нет, не ок", "Пока не принимаю", "no, not ok"):
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


def test_deleting_the_inbox_does_not_switch_the_check_off(strat, ready, cases):
    """Review: `rm cases/.inbox.jsonl` turned the user's-yes check into the old no-hook rule."""
    said(cases, "Начнём", t=time.time() - 60)
    assert strat("gate", "check", "1").code == 0
    (cases / ".inbox.jsonl").unlink()
    r = strat("gate", "approve", "1")
    assert r.code == 1 and "inbox" in r.err


def test_risk_accepted_quotes_a_message_sent_after_the_objection(strat, ready, cases):
    """Review: quoting «Подписываю» from an old message passed; the words must answer the risk."""
    from datetime import datetime

    import pytest
    from strat.consult import set_verdict
    from strat.core import StratError, write_jsonl

    said(cases, "Принимаю риск оттока", t=time.time() - 120)
    raised = datetime.fromtimestamp(time.time() - 60).astimezone().isoformat(timespec="seconds")
    write_jsonl(ready / "objections.jsonl", [
        {"id": "O001", "call": "challenge", "target": "Вариант 3", "severity": "major",
         "text": "Отток может не вернуться", "by": "test", "at": raised}])
    with pytest.raises(StratError, match="user's own words"):
        set_verdict(ready, "O001", "risk-accepted", "Пользователь: «принимаю риск оттока»", False)
    said(cases, "Да, принимаю риск оттока")
    assert set_verdict(ready, "O001", "risk-accepted",
                       "Пользователь: «принимаю риск оттока»", False) == 0


def test_risk_accepted_cannot_quote_a_refusal(strat, ready, cases):
    """Review: quoting «Нет» from the user's refusal passed the words check."""
    import pytest
    from strat.consult import set_verdict
    from strat.core import StratError, write_jsonl

    write_jsonl(ready / "objections.jsonl", [
        {"id": "O001", "call": "challenge", "target": "Вариант 3", "severity": "major",
         "text": "Отток может не вернуться", "by": "test"}])
    said(cases, "Нет, этот риск не принимаю")
    with pytest.raises(StratError, match="user's own words"):
        set_verdict(ready, "O001", "risk-accepted", "Пользователь: «Нет»", False)


def test_deleting_the_inbox_does_not_skip_the_risk_quote(strat, ready, cases):
    """Recheck: risk-accepted still skipped its words check when the inbox was deleted."""
    import pytest
    from strat.consult import set_verdict
    from strat.core import StratError, write_jsonl

    said(cases, "Начнём", t=time.time() - 60)
    assert strat("gate", "check", "1").code == 0      # the case now knows it has an inbox
    write_jsonl(ready / "objections.jsonl", [
        {"id": "O001", "call": "challenge", "target": "Вариант 3", "severity": "major",
         "text": "Отток может не вернуться", "by": "test"}])
    (cases / ".inbox.jsonl").unlink()
    with pytest.raises(StratError, match="inbox"):
        set_verdict(ready, "O001", "risk-accepted", "Пользователь принял риск", False)
