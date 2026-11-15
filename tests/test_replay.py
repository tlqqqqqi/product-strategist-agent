"""Replay: session transcripts -> a compact chat script, and the static page that plays it."""

import json
import re
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "replay"
PAGE = REPO / "demo" / "replay" / "index.html"
FAKE_SECRETS = ("tvly-FAKEfake", "BSAfake0123", "ghp_FAKEfake", "sk-fakehookkey")
DROPPED = ("obey the hook", "Caveat", "private reasoning", "raw file body", "raw tool output",
           "hook output", "sidechain", "You've hit your limit", "Request interrupted",
           "/Users/someone", "/work/clone")


@pytest.fixture
def exported(strat, tmp_path):
    out = tmp_path / "replay" / "script.json"
    r = strat("replay", "export", "--transcripts", str(FIXTURE), "--out", str(out),
              "--label", "тестовый прогон", "--json")
    assert r.code == 0, r.err
    return json.loads(out.read_text(encoding="utf-8")), out


def test_export_keeps_the_conversation_in_order(exported):
    script, _ = exported
    kinds = [(e["kind"], e.get("text") or e.get("line")) for e in script["events"]]
    assert kinds == [
        ("user", "Отток вырос, откатывать ли цену? Ключ поиска [скрыто]. Материалы: [путь скрыт]"),
        ("agent", "Завожу кейс."),
        ("step", 'bin/strat new demo --title "Тест"'),
        ("step", "записал options.md"),
        ("step", "прочитал [путь скрыт]"),
        ("step", 'BRAVE_API_KEY=[скрыто] bin/strat search "семейные тарифы 2 ТБ" '
                 "--step research.q4.search.1"),
        ("step", "bin/strat gate check 1"),
        ("agent", "Это гейт 1. Утверждаете план?"),
        ("user", "Да, утверждаю план."),
        ("step", "bin/strat gate approve 1"),
        ("question", "Как читать лист cohorts?"),
        ("user", "Вся база на май"),
        ("user", "Продолжайте."),
        ("agent", "Готово, токен [скрыто] скрыт. Файл cases/demo/memo.md."),
    ]
    steps = [e for e in script["events"] if e["kind"] == "step"]
    assert [s["ok"] for s in steps] == [True, True, True, False, True, True]
    assert script["events"][0]["t"] == 0 and script["events"][-1]["t"] == 719


def test_gate_stops_carry_the_answer_buttons(exported):
    script, _ = exported
    gate = script["events"][7]
    assert gate["gate"]["n"] == 1
    assert gate["gate"]["chosen"] == 0 and gate["gate"]["typed"] is True
    assert len(gate["gate"]["buttons"]) == 2
    q = script["events"][10]
    assert q["buttons"] == ["Пришедшие в мае", "Вся база на май"] and q["chosen"] == 1
    assert script["events"][11]["via"] == "button"
    assert not any("gate" in e for i, e in enumerate(script["events"]) if i != 7)


def test_cost_is_per_step_and_totals(exported):
    script, _ = exported
    usd = [e.get("usd", 0) for e in script["events"]]
    # thinking (0.40) is carried to the next visible event; one message id is billed once
    assert usd == [0, 0.6, 0.2, 0.1, 0, 0, 0, 0.2, 0, 0, 0, 0, 0, 0.2]
    meta = script["meta"]
    assert meta["usd"] == 1.3 and meta["model"] == "claude-opus-5-5"
    assert meta["label"] == "тестовый прогон" and meta["date"] == "2026-11-15"
    assert meta["minutes"] == 12.0 and meta["sessions"] == 2


def test_secrets_system_text_and_raw_outputs_are_dropped(exported):
    _, out = exported
    text = out.read_text(encoding="utf-8")
    for s in FAKE_SECRETS + DROPPED:
        assert s not in text, s


def test_export_refuses_when_a_secret_survives(strat, tmp_path, monkeypatch):
    import strat.replay as replay

    monkeypatch.setattr(replay, "redact", lambda s, cwd=None: s)  # a broken redactor
    out = tmp_path / "script.json"
    r = strat("replay", "export", "--transcripts", str(FIXTURE), "--out", str(out))
    assert r.code == 1 and "secret" in r.err and not out.exists()


def test_export_without_transcripts_is_unavailable(strat, tmp_path):
    r = strat("replay", "export", "--transcripts", str(tmp_path / "none"),
              "--out", str(tmp_path / "s.json"))
    assert r.code == 2


def test_export_embeds_the_script_into_the_page(exported, tmp_path):
    script, out = exported
    page = out.parent / "index.html"
    shutil.copy(PAGE, page)
    from strat.replay import embed

    embed(page, script)
    html = page.read_text(encoding="utf-8")
    block = re.search(r'<script id="replay-data" type="application/json">(.*?)</script>', html,
                      re.S)
    assert json.loads(block.group(1)) == script
    # self-contained: works from file://, nothing loaded from the network
    assert not re.search(r'(src|href)\s*=\s*["\']?(https?:)?//', html)
    assert "@import" not in html and not re.search(r"url\(\s*['\"]?https?:", html)


def _chromium():
    pw = pytest.importorskip("playwright.sync_api")
    return pw.sync_playwright


def test_page_plays_the_script_to_the_end(exported, tmp_path):
    sync_playwright = _chromium()
    script, out = exported
    page_path = out.parent / "index.html"
    shutil.copy(PAGE, page_path)
    from strat.replay import embed

    embed(page_path, script)
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # browser binary not installed
            pytest.skip(f"no chromium: {exc}")
        page = browser.new_page()
        page.goto(page_path.as_uri() + "#speed=max&autoplay=1")
        page.wait_for_selector("#chat[data-done='1']", timeout=20_000)
        chat = page.inner_text("#chat")
        browser.close()
    assert script["events"][0]["text"] in chat
    assert script["events"][-1]["text"] in chat


def test_redact_keeps_slugs_and_dev_null_but_hides_keys_and_foreign_paths():
    from strat.replay import redact

    url = "https://rozetked.me/articles/22883-sravnenie-skol-ko-stoit-prostranstvo-v-oblachnyh"
    assert redact(f"[Rozetked]({url})") == f"[Rozetked]({url})"
    assert redact("ls cases 2>/dev/null") == "ls cases 2>/dev/null"
    assert redact("token Ab3dEf6hIj9kLm2nOp5qRs8tUv1wXy4zAb7dEf0hIj") == "token [скрыто]"
    assert redact("cat /work/clone/cases/x/memo.md /etc/hosts", cwd="/work/clone") == \
        "cat cases/x/memo.md [путь скрыт]"
