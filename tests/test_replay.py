"""Replay: session transcripts (Claude Code, OpenCode) -> a bundle of runs, and the page that
plays it."""

import json
import re
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "replay"
OPENCODE = REPO / "tests" / "fixtures" / "replay-opencode"
PAGE = REPO / "demo" / "replay" / "index.html"
FAKE_SECRETS = ("tvly-FAKEfake", "BSAfake0123", "ghp_FAKEfake", "sk-fakehookkey",
                "tvly-FAKEopencode", "sk-fakeopencodekey")
DROPPED = ("obey the hook", "Caveat", "private reasoning", "raw file body", "raw tool output",
           "hook output", "sidechain", "You've hit your limit", "Request interrupted",
           "/Users/someone", "/work/clone", "/private/tmp", "skill body")
FAMILY = [
    {"name": "metrics.xlsx", "path": "../family-app/materials/metrics.xlsx"},
    {"name": "product.docx", "path": "../family-app/materials/product.docx"},
    {"name": "support-tickets.csv", "path": "../family-app/materials/support-tickets.csv"},
]


def _export(strat, out, *args):
    r = strat("replay", "export", "--out", str(out), "--json", *args)
    assert r.code == 0, r.err
    return json.loads(out.read_text(encoding="utf-8"))


@pytest.fixture
def exported(strat, tmp_path):
    out = tmp_path / "replay" / "script.json"
    bundle = _export(strat, out, "--transcripts", str(FIXTURE), "--id", "cc",
                     "--label", "тестовый прогон")
    return bundle, out


@pytest.fixture
def opencode(strat, tmp_path):
    out = tmp_path / "replay" / "script.json"
    bundle = _export(strat, out, "--opencode", str(OPENCODE), "--id", "flash",
                     "--label", "DeepSeek через OpenCode", "--model", "deepseek-v4-flash")
    return bundle["runs"][0], out


def _view(ev):
    if ev["kind"] == "steps":
        return ("steps", [i["line"] for i in ev["items"]])
    if ev["kind"] == "question":
        return ("question", [q["question"] for q in ev["questions"]])
    return (ev["kind"], ev["text"])


def test_claude_code_run_keeps_the_conversation_in_order(exported):
    bundle, _ = exported
    assert bundle["version"] == 2 and [r["id"] for r in bundle["runs"]] == ["cc"]
    run = bundle["runs"][0]
    assert run["harness"] == "claude-code" and run["model"] == "claude-opus-5-5"
    assert run["label"] == "тестовый прогон" and run["case"] == "demo"
    assert [_view(e) for e in run["events"]] == [
        ("user", "Отток вырос, откатывать ли цену? Ключ поиска [скрыто]. Материалы: [путь скрыт]"),
        ("agent", "Завожу кейс."),
        ("steps", ['bin/strat new demo --title "Тест"', "записал options.md",
                   "прочитал [путь скрыт]",
                   'BRAVE_API_KEY=[скрыто] bin/strat search "семейные тарифы 2 ТБ" '
                   "--step research.q4.search.1",
                   "bin/strat gate check 1"]),
        ("agent", "Это гейт 1. Утверждаете план?"),
        ("user", "Да, утверждаю план."),
        ("steps", ["bin/strat gate approve 1"]),
        ("question", ["Как читать лист cohorts?"]),
        ("user", "Продолжайте."),
        ("agent", "Готово, токен [скрыто] скрыт. Файл cases/demo/memo.md."),
    ]
    steps = run["events"][2]
    assert [i["ok"] for i in steps["items"]] == [True, True, True, False, True]
    assert [i["tool"] for i in steps["items"]] == ["Bash", "Write", "Read", "Bash", "Bash"]
    assert steps["summary"] == "Прочитал 1 файл, выполнил 3 команды, изменил 1 файл, 1 ошибка"
    assert steps["t"] == steps["items"][0]["t"] == 6
    assert run["events"][0]["t"] == 0 and run["events"][-1]["t"] == 719


def test_step_items_carry_short_command_output_but_not_file_bodies(exported):
    bundle, _ = exported
    items = bundle["runs"][0]["events"][2]["items"]
    assert items[0]["detail"] == "created demo"
    assert items[3]["detail"] == "Exit code 2\nstrat: no search key"
    assert "detail" not in items[2]  # a Read's body is never shown


def test_question_event_from_ask_user_question(exported):
    bundle, _ = exported
    events = bundle["runs"][0]["events"]
    q = events[6]
    assert q["questions"] == [{"header": "cohorts", "question": "Как читать лист cohorts?",
                               "options": ["Пришедшие в мае", "Вся база на май"],
                               "multi": False}]
    assert q["answers"] == [{"question": "Как читать лист cohorts?", "answer": "Вся база на май"}]


def test_gate_stops_carry_the_answer_buttons(exported):
    bundle, _ = exported
    events = bundle["runs"][0]["events"]
    gate = events[3]
    assert gate["gate"]["n"] == 1
    assert gate["gate"]["chosen"] == 0 and gate["gate"]["typed"] is True
    assert len(gate["gate"]["buttons"]) == 2
    assert not any("gate" in e for i, e in enumerate(events) if i != 3)


def test_cost_tokens_and_meta(exported):
    bundle, _ = exported
    run = bundle["runs"][0]
    usd = [e.get("usd", 0) for e in run["events"]]
    # thinking (0.40) is carried to the next visible event; one message id is billed once;
    # a group of steps carries the sum of its steps
    assert usd == [0, 0.6, 0.3, 0.2, 0, 0, 0, 0, 0.2]
    meta = run["meta"]
    assert meta["usd"] == 1.3 and meta["date"] == "2026-11-15"
    assert meta["minutes"] == 12.0 and meta["sessions"] == 2
    assert meta["steps"] == 6 and meta["gates"] == 1 and meta["priced"] is True
    assert meta["tokens"] == {"input": 150000, "output": 35000, "cache_read": 0}


def test_opencode_run_maps_turns_tools_and_tokens(opencode):
    run, _ = opencode
    assert run["harness"] == "opencode" and run["model"] == "deepseek-v4-flash"
    assert run["case"] == "family-cloud-price"
    assert [_view(e) for e in run["events"]] == [
        ("user", "Отток вырос, откатывать ли цену? Материалы: demo/family-app/materials"),
        ("steps", ["открыл навык using-strategist"]),
        ("agent", "I'll start by loading the bootstrap skill."),
        ("steps", ["ошибка модели: Expected 'function.name' to be a string."]),
        ("user", "Продолжай."),
        ("steps", ['bin/strat new family-cloud-price --title "Семейное облако"',
                   "env | grep KEY", "прочитал sources/S002.md",
                   "искал «cohort» в cases/family-cloud-price", "изменил options.md",
                   "bin/strat gate check 1"]),
        ("agent", "Это **гейт 1**. Утверждаете план?"),
        ("user", "Да, утверждаю план."),
        ("steps", ["bin/strat gate approve 1", "открыл страницу https://example.org/tariffs"]),
        ("agent", "Готово. Файл cases/family-cloud-price/memo.md."),
    ]
    ev = run["events"]
    assert [i["tool"] for i in ev[5]["items"]] == ["bash", "bash", "read", "grep", "edit", "bash"]
    assert ev[5]["summary"] == "Прочитал 1 файл, выполнил 3 команды, искал 1 раз, изменил 1 файл"
    assert ev[8]["summary"] == "Выполнил 1 команду, открыл 1 страницу, 1 ошибка"
    assert ev[1]["summary"] == "Открыл 1 навык"
    assert [i["ok"] for i in ev[8]["items"]] == [True, False]
    assert ev[3]["items"][0]["ok"] is False
    assert ev[6]["gate"]["n"] == 1 and ev[6]["gate"]["chosen"] == 0
    assert ev[5]["items"][1]["detail"] == "TAVILY_API_KEY=[скрыто]\nSTRAT_PEER_API_KEY=[скрыто]"
    meta = run["meta"]
    assert meta["tokens"] == {"input": 42286, "output": 929, "cache_read": 14976}
    assert meta["usd"] is None and meta["priced"] is False
    assert meta["minutes"] == 2.0 and meta["steps"] == 10 and meta["gates"] == 1
    assert ev[0]["t"] == 0 and ev[-1]["t"] == 603


def test_materials_named_in_the_first_message_link_into_the_repo(opencode):
    run, _ = opencode
    assert run["materials"] == FAMILY


def test_materials_outside_the_repo_are_never_listed(tmp_path):
    from strat import replay

    text = ("Материалы: /work/clone/demo/family-app/materials/metrics.xlsx, /etc/passwd, "
            "../../etc, demo/../../outside, demo/family-app/materials/product.docx")
    found = replay.materials(text, "/work/clone")
    assert found == [FAMILY[0], FAMILY[1]]
    assert all(not m["path"].startswith("/") for m in found)


def test_bundle_holds_runs_from_both_formats_and_replaces_by_id(strat, exported, tmp_path):
    _, out = exported
    _export(strat, out, "--opencode", str(OPENCODE), "--id", "flash", "--model", "m")
    bundle = _export(strat, out, "--transcripts", str(FIXTURE), "--id", "cc",
                     "--label", "новая подпись")
    assert [r["id"] for r in bundle["runs"]] == ["cc", "flash"]
    assert [r["harness"] for r in bundle["runs"]] == ["claude-code", "opencode"]
    assert bundle["runs"][0]["label"] == "новая подпись"


def test_a_version_1_script_is_kept_as_one_run(strat, exported, tmp_path):
    from strat import replay

    v1 = {"version": 1, "meta": {"label": "старый", "model": "claude-opus-5-5", "minutes": 1.0,
                                 "usd": 0.5, "steps": 2, "gates": 0, "date": "2026-11-14"},
          "events": [{"kind": "user", "text": "Вопрос", "t": 0},
                     {"kind": "step", "tool": "Bash", "line": "bin/strat new x", "ok": True,
                      "t": 1, "usd": 0.1},
                     {"kind": "step", "tool": "Read", "line": "прочитал a.md", "ok": True,
                      "t": 2, "usd": 0.2},
                     {"kind": "question", "text": "Как?", "buttons": ["А", "Б"], "chosen": 1,
                      "t": 3},
                     {"kind": "user", "text": "Б", "via": "button", "t": 3},
                     {"kind": "agent", "text": "Ок", "t": 4}]}
    old = tmp_path / "old" / "script.json"
    old.parent.mkdir()
    old.write_text(json.dumps(v1), encoding="utf-8")
    bundle = replay.load_bundle(old, legacy_id="sample-opus")
    run = bundle["runs"][0]
    assert run["id"] == "sample-opus" and run["label"] == "старый" and run["case"] == "x"
    assert [e["kind"] for e in run["events"]] == ["user", "steps", "question", "agent"]
    assert run["events"][1]["summary"] == "Прочитал 1 файл, выполнил 1 команду"
    assert run["events"][1]["usd"] == 0.3
    assert run["events"][2]["answers"] == [{"question": "Как?", "answer": "Б"}]
    bundle = _export(strat, old, "--transcripts", str(FIXTURE), "--id", "cc")
    assert [r["id"] for r in bundle["runs"]] == ["legacy", "cc"]


@pytest.mark.parametrize("counts,summary", [
    ({"read": 1}, "Прочитал 1 файл"),
    ({"read": 3, "command": 5}, "Прочитал 3 файла, выполнил 5 команд"),
    ({"command": 21, "edit": 22}, "Выполнил 21 команду, изменил 22 файла"),
    ({"command": 11, "search": 12}, "Выполнил 11 команд, искал 12 раз"),
    ({"search": 2, "web": 2, "other": 2}, "Искал 2 раза, открыл 2 страницы, ещё 2 действия"),
    ({"web": 5, "other": 1, "fail": 3}, "Открыл 5 страниц, ещё 1 действие, 3 ошибки"),
    ({"skill": 2, "fail": 11}, "Открыл 2 навыка, 11 ошибок"),
])
def test_step_summaries_use_russian_plurals(counts, summary):
    from strat import replay

    assert replay.summarize_counts(counts) == summary


def test_secrets_system_text_and_raw_outputs_are_dropped(strat, exported):
    _, out = exported
    _export(strat, out, "--opencode", str(OPENCODE), "--id", "flash")
    for f in (out, out.parent / "index.html"):
        if f.exists():
            text = f.read_text(encoding="utf-8")
            for s in FAKE_SECRETS + DROPPED:
                assert s not in text, s


@pytest.mark.parametrize("source", ["--transcripts", "--opencode"])
def test_export_refuses_when_a_secret_survives(strat, tmp_path, monkeypatch, source):
    import strat.replay as replay

    monkeypatch.setattr(replay, "redact", lambda s, cwd=None: s)  # a broken redactor
    out = tmp_path / "script.json"
    r = strat("replay", "export", source, str(FIXTURE if source == "--transcripts" else OPENCODE),
              "--out", str(out))
    assert r.code == 1 and "secret" in r.err and not out.exists()


def test_export_without_transcripts_is_unavailable(strat, tmp_path):
    for flag in ("--transcripts", "--opencode"):
        r = strat("replay", "export", flag, str(tmp_path / "none"),
                  "--out", str(tmp_path / "s.json"))
        assert r.code == 2


def test_export_embeds_the_bundle_into_the_page(exported, tmp_path):
    bundle, out = exported
    page = out.parent / "index.html"
    shutil.copy(PAGE, page)
    from strat.replay import embed

    embed(page, bundle)
    html = page.read_text(encoding="utf-8")
    block = re.search(r'<script id="replay-data" type="application/json">(.*?)</script>', html,
                      re.S)
    assert json.loads(block.group(1)) == bundle
    # self-contained: works from file://, nothing loaded from the network
    assert not re.search(r'(src|href)\s*=\s*["\']?(https?:)?//', html)
    assert "@import" not in html and not re.search(r"url\(\s*['\"]?https?:", html)


def test_committed_demo_bundle_is_version_2_and_clean():
    from strat import replay

    bundle = json.loads((REPO / "demo" / "replay" / "script.json").read_text(encoding="utf-8"))
    assert bundle["version"] == 2 and bundle["runs"][0]["id"] == "sample-opus"
    assert bundle["runs"][0]["label"].startswith("Пример: кейс «Семейное облако»")
    assert not replay.leaked(bundle)
    html = PAGE.read_text(encoding="utf-8")
    block = re.search(r'<script id="replay-data" type="application/json">(.*?)</script>', html,
                      re.S)
    assert json.loads(block.group(1)) == bundle


def _chromium():
    pw = pytest.importorskip("playwright.sync_api")
    return pw.sync_playwright


def _play(page_path):
    sync_playwright = _chromium()
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
    return chat


def test_page_plays_the_first_run_of_a_bundle_to_the_end(strat, exported, tmp_path):
    bundle, out = exported
    bundle = _export(strat, out, "--opencode", str(OPENCODE), "--id", "flash")
    page_path = out.parent / "index.html"
    shutil.copy(PAGE, page_path)
    from strat.replay import embed

    embed(page_path, bundle)
    chat = _play(page_path)
    events = bundle["runs"][0]["events"]
    assert events[0]["text"] in chat and events[-1]["text"] in chat
    assert "Вся база на май" in chat


def test_redact_keeps_slugs_and_dev_null_but_hides_keys_and_foreign_paths():
    from strat.replay import redact

    url = "https://rozetked.me/articles/22883-sravnenie-skol-ko-stoit-prostranstvo-v-oblachnyh"
    assert redact(f"[Rozetked]({url})") == f"[Rozetked]({url})"
    assert redact("ls cases 2>/dev/null") == "ls cases 2>/dev/null"
    assert redact("token Ab3dEf6hIj9kLm2nOp5qRs8tUv1wXy4zAb7dEf0hIj") == "token [скрыто]"
    assert redact("cat /work/clone/cases/x/memo.md /etc/hosts", cwd="/work/clone") == \
        "cat cases/x/memo.md [путь скрыт]"


def test_usage_after_the_last_visible_reply_does_not_crash(tmp_path):
    """A turn whose model reply was empty (e.g. interrupted) still has usage; export keeps going."""
    from strat import replay

    rows = [
        {"type": "user", "timestamp": "2026-11-15T07:00:00.000Z", "sessionId": "s", "cwd": "/w",
         "message": {"role": "user", "content": "Продолжи кейс"}},
        {"type": "assistant", "timestamp": "2026-11-15T07:00:05.000Z", "sessionId": "s",
         "cwd": "/w", "message": {"id": "m1", "model": "claude-opus-5-5", "role": "assistant",
                                  "content": [{"type": "thinking", "thinking": "..."}],
                                  "usage": {"input_tokens": 1000, "output_tokens": 50}}},
    ]
    (tmp_path / "s.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    run = replay.build(tmp_path)
    assert [e["kind"] for e in run["events"]] == ["user"]
    assert run["meta"]["usd"] > 0


def test_opencode_turns_are_in_natural_order():
    from strat import replay

    assert sorted(["10", "2", "1b", "1"], key=replay.turn_key) == ["1", "1b", "2", "10"]


def test_gate_numbers_are_read_whole():
    from strat import replay

    assert replay.GATE_CMD.search("bin/strat gate check 12").group(2) == "12"
