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
    assert steps["summary"] == "Прочитал 1 файл, выполнил 2 команды, искал в интернете 1 раз, изменил 1 файл, 1 ошибка"
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
    # works from file://: no scripts or data from the network; only the Google Fonts stylesheet,
    # with local fallbacks when it does not load
    remote = re.findall(r'(?:src|href)\s*=\s*["\']?((?:https?:)?//[^"\'\s>]+)', html)
    assert all(re.match(r"https://fonts\.(googleapis|gstatic)\.com(/|$)", u) for u in remote), remote
    assert not re.search(r"<script[^>]+src=", html)
    assert "@import" not in html and not re.search(r"url\(\s*['\"]?https?:", html)


def test_committed_demo_bundle_is_version_2_and_clean():
    from strat import replay

    bundle = json.loads((REPO / "demo" / "replay" / "script.json").read_text(encoding="utf-8"))
    ids = [r["id"] for r in bundle["runs"]]
    assert bundle["version"] == 2 and ids[0] == "gpt-6.1-terra" and "sample-opus" in ids
    labels = {r["id"]: r["label"] for r in bundle["runs"]}
    assert labels["gpt-6.1-terra"].startswith("Демо-кейс «Семейный компас»")
    assert labels["sample-opus"].startswith("Учебный кейс «Семейное облако»")
    assert all(r["meta"].get("web") is not None for r in bundle["runs"] if r["harness"] == "opencode")
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


# ---------- claims and sources of the run's case ----------

def _case_dir(tmp_path):
    """A case folder outside the repo, as a run leaves it: claims, sources, a copied material."""
    import hashlib

    cdir = tmp_path / "clone" / "cases" / "family-cloud-price"
    (cdir / "sources").mkdir(parents=True)
    (cdir / "materials").mkdir()
    (cdir / "analysis").mkdir()
    src = REPO / "demo" / "family-app" / "materials" / "metrics.xlsx"
    shutil.copy(src, cdir / "materials" / "metrics.xlsx")
    (cdir / "materials" / "product.docx").write_bytes(b"not the repo file")
    (cdir / "analysis" / "q1.txt").write_text("x = 1\n", encoding="utf-8")
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    sources = [
        {"id": "S001", "kind": "file", "origin": "materials/metrics.xlsx", "title": "metrics.xlsx",
         "sha256": sha, "snapshot": "sources/S001.md"},
        {"id": "S002", "kind": "file", "origin": "materials/product.docx", "title": "product.docx",
         "sha256": "0" * 64, "snapshot": "sources/S002.md"},
        {"id": "S003", "kind": "analysis", "origin": "analysis/q1.txt", "title": "q1.txt",
         "sha256": "1" * 64, "snapshot": "sources/S003.md"},
    ]
    (cdir / "sources" / "index.jsonl").write_text(
        "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in sources), encoding="utf-8")
    claims = [
        {"id": "C001", "type": "fact", "status": "active", "text": "Платящих стало на 59,3% меньше.",
         "source": "S001", "where": "cohorts!A2:D2", "quote": "promo 9800 4550 1850",
         "kind": "product_metric", "check": {"p": 0.9}, "supports": []},
        {"id": "C002", "type": "fact", "status": "replaced", "text": "Старая цифра.",
         "source": "S003", "where": "/Users/someone/clone/cases/x/analysis/q1.txt",
         "quote": "key=tvly-FAKEcase0123456789abcdef", "replaced_by": "C001"},
        {"id": "C003", "type": "fact", "status": "withdrawn", "text": "Отозвано.",
         "source": "S001", "where": "a", "quote": "b"},
        {"id": "C004", "type": "gap", "status": "active", "text": "Нет данных о причинах.",
         "source": None, "where": None, "quote": None},
    ]
    (cdir / "claims.jsonl").write_text(
        "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in claims), encoding="utf-8")
    return cdir


def _strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from _strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from _strings(x)


def test_export_embeds_the_claims_and_sources_of_the_case(strat, tmp_path):
    cdir = _case_dir(tmp_path)
    out = tmp_path / "replay" / "script.json"
    run = _export(strat, out, "--opencode", str(OPENCODE), "--id", "flash",
                  "--case-dir", str(cdir))["runs"][0]
    assert [c["id"] for c in run["claims"]] == ["C001", "C002", "C004"]  # never withdrawn
    assert all(set(c) == {"id", "type", "text", "source", "where", "quote"} for c in run["claims"])
    c1, c2, c4 = run["claims"]
    assert c1 == {"id": "C001", "type": "fact", "text": "Платящих стало на 59,3% меньше.",
                  "source": "S001", "where": "cohorts!A2:D2", "quote": "promo 9800 4550 1850"}
    assert c2["quote"] == "key=[скрыто]" and c2["where"] == "[путь скрыт]"
    assert c4["source"] is None and c4["quote"] is None
    assert run["sources"] == [
        # the material is the repo's own file (same bytes): linked relative to demo/replay/
        {"id": "S001", "title": "metrics.xlsx", "kind": "file",
         "path": "../family-app/materials/metrics.xlsx"},
        # same name, other bytes, and an analysis output: not in the repo, no link
        {"id": "S002", "title": "product.docx", "kind": "file", "path": None},
        {"id": "S003", "title": "q1.txt", "kind": "analysis", "path": None},
    ]
    for s in _strings({"claims": run["claims"], "sources": run["sources"]}):
        assert not s.startswith("/") and str(tmp_path) not in s and "tvly-FAKE" not in s


def test_the_case_folder_is_found_under_the_run_folder(tmp_path):
    from strat import replay

    cdir = _case_dir(tmp_path)
    run_folder = str(tmp_path / "clone")
    assert replay.find_case_dir(run_folder, "family-cloud-price") == cdir
    assert replay.find_case_dir(run_folder, "other-case") is None
    assert replay.find_case_dir(None, "family-cloud-price") is None
    assert replay.find_case_dir(run_folder, "../clone") is None  # a case is a plain name


def test_a_run_without_its_case_folder_has_no_claims(opencode):
    run, _ = opencode
    assert "claims" not in run and "sources" not in run


# ---------- the page ----------

def _page_with(tmp_path, bundle):
    page_path = tmp_path / "page" / "index.html"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(PAGE, page_path)
    from strat.replay import embed

    embed(page_path, bundle)
    return page_path


class _Browser:
    """One chromium page per test; Google Fonts answered locally; page errors collected."""

    def __enter__(self):
        sync_playwright = _chromium()
        self._pw = sync_playwright().start()
        try:
            self.browser = self._pw.chromium.launch()
        except Exception as exc:  # browser binary not installed
            self._pw.stop()
            pytest.skip(f"no chromium: {exc}")
        self.errors = []
        return self

    def open(self, page_path, hash_="", width=1280):
        page = self.browser.new_page(viewport={"width": width, "height": 900})
        page.route(re.compile(r"https://fonts\.(googleapis|gstatic)\.com/.*"),
                   lambda r: r.fulfill(status=200, body="", content_type="text/css"))
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and self.errors.append(m.text))
        page.goto(page_path.as_uri() + hash_)
        return page

    def __exit__(self, *exc):
        self.browser.close()
        self._pw.stop()


def _nav_units(run):
    return sum(1 + ("gate" in e) for e in run["events"] if e["kind"] != "steps")


def _three_runs(strat, tmp_path):
    out = tmp_path / "replay" / "script.json"
    _export(strat, out, "--transcripts", str(FIXTURE), "--id", "cc", "--label", "первый")
    _export(strat, out, "--opencode", str(OPENCODE), "--id", "flash", "--model",
            "DeepSeek V4 Flash", "--label", "второй")
    return _export(strat, out, "--transcripts", str(FIXTURE), "--id", "cc2", "--model",
                   "GPT-6.1 Terra", "--label", "третий")


def test_page_switches_between_runs_and_remembers_the_run(strat, tmp_path):
    bundle = _three_runs(strat, tmp_path)
    page_path = _page_with(tmp_path, bundle)
    with _Browser() as b:
        page = b.open(page_path, "#speed=max&autoplay=1")
        page.wait_for_selector("#chat[data-done='1']")
        pills = page.locator("#models .model")
        assert pills.count() == 3
        assert pills.nth(1).inner_text() == "DeepSeek V4 Flash"
        assert pills.nth(0).get_attribute("aria-pressed") == "true"
        pills.nth(1).click()
        page.wait_for_selector("#chat[data-done='1']")
        assert pills.nth(1).get_attribute("aria-pressed") == "true"
        assert "run=flash" in page.evaluate("location.hash")
        assert bundle["runs"][1]["events"][-1]["text"] in page.inner_text("#chat")
        # the run in the hash is the one shown on load
        page2 = b.open(page_path, "#run=cc2&speed=max&autoplay=1")
        page2.wait_for_selector("#chat[data-done='1']")
        assert page2.locator("#models .model").nth(2).get_attribute("aria-pressed") == "true"
        assert "запись реального прогона" in page2.inner_text("body").lower()
    assert not b.errors, b.errors


def test_committed_page_plays_every_run_to_the_end_without_errors():
    bundle = json.loads((REPO / "demo" / "replay" / "script.json").read_text(encoding="utf-8"))
    assert len(bundle["runs"]) >= 3
    with _Browser() as b:
        for run in bundle["runs"]:
            page = b.open(PAGE, f"#run={run['id']}&speed=max&autoplay=1")
            page.wait_for_selector("#chat[data-done='1']", timeout=20_000)
            assert page.inner_text("#pos") == f"{_nav_units(run)} из {_nav_units(run)}"
            assert page.locator("#next").is_disabled()
            for w in (390,):
                page.set_viewport_size({"width": w, "height": 800})
                assert page.evaluate("document.documentElement.scrollWidth") <= w
    assert not b.errors, b.errors


def test_prev_and_next_jump_between_messages_and_skip_steps(strat, tmp_path, exported):
    bundle, _ = exported
    run = bundle["runs"][0]
    page_path = _page_with(tmp_path, bundle)
    total = _nav_units(run)
    with _Browser() as b:
        page = b.open(page_path, "#speed=max&autoplay=0")
        page.wait_for_selector("#chat .current")
        assert page.inner_text("#pos") == f"1 из {total}"
        assert page.locator("#prev").is_disabled()
        kinds = []
        for i in range(2, total + 1):
            page.click("#next")
            assert page.inner_text("#pos") == f"{i} из {total}"
            cur = page.locator("#chat .current")
            assert cur.count() == 1
            kinds.append(cur.get_attribute("data-kind"))
        assert page.locator("#next").is_disabled()
        assert set(kinds) <= {"user", "agent", "question", "gate"} and "gate" in kinds
        assert page.locator("#chat .fold").count() == sum(e["kind"] == "steps"
                                                          for e in run["events"])
        # steps are folded by default and open on a click
        fold = page.locator("#chat .fold").first
        assert not fold.locator(".steps").is_visible()
        fold.locator("button").click()
        assert fold.locator(".steps").is_visible()
        page.keyboard.press("ArrowLeft")
        assert page.inner_text("#pos") == f"{total - 1} из {total}"
    assert not b.errors, b.errors


def _bundle_with(events, claims=None, sources=None):
    run = {"id": "x", "label": "тест", "model": "m", "harness": "opencode", "case": "c",
           "meta": {"date": "2026-11-15", "start": "2026-11-15T10:00:00+00:00", "minutes": 1.0,
                    "usd": None, "tokens": {"input": 1000, "output": 10, "cache_read": 0},
                    "sessions": 1, "gates": 0, "steps": 0, "priced": False},
           "materials": [], "events": events}
    if claims is not None:
        run["claims"], run["sources"] = claims, sources
    return {"version": 2, "runs": [run]}


def test_a_question_window_has_one_tab_per_question_and_marks_the_answer(tmp_path):
    q = {"kind": "question", "t": 1, "answers": [
        {"question": "Что важнее?", "answer": "Выручка"},
        {"question": "Какая когорта?", "answer": "Майская"}],
         "questions": [
             {"header": "Метрика", "question": "Что важнее?", "options": ["Выручка", "LTV"],
              "multi": False},
             {"header": "Когорта", "question": "Какая когорта?", "options": ["Вся база", "Майская"],
              "multi": False}]}
    bundle = _bundle_with([{"kind": "user", "text": "Вопрос", "t": 0}, q,
                           {"kind": "agent", "text": "Ок", "t": 2}])
    with _Browser() as b:
        page = b.open(_page_with(tmp_path, bundle), "#speed=max&autoplay=1")
        page.wait_for_selector("#chat[data-done='1']")
        tabs = page.locator(".qwin [role=tab]")
        assert [tabs.nth(i).inner_text() for i in range(2)] == ["Метрика", "Когорта"]
        assert tabs.nth(0).get_attribute("aria-selected") == "true"
        assert page.locator(".qwin .opt.sel").inner_text() == "Выручка"
        tabs.nth(1).click()
        assert tabs.nth(1).get_attribute("aria-selected") == "true"
        assert "Какая когорта?" in page.inner_text(".qwin")
        assert page.locator(".qwin .opt.sel").inner_text() == "Майская"
    assert not b.errors, b.errors


def test_agent_text_signs_figures_and_opens_claim_cards(tmp_path):
    text = ("Отток **в когорте**: −59,3% [C001], ARPU +45 ₽ (C004); `bin/strat <x>` "
            "<img src=x onerror=alert(1)> *по умолчанию*\n- пункт")
    claims = [{"id": "C001", "type": "fact", "text": "Платящих стало меньше.", "source": "S001",
               "where": "cohorts!A2", "quote": "9800 4550"},
              {"id": "C004", "type": "gap", "text": "Нет данных.", "source": None, "where": None,
               "quote": None}]
    sources = [{"id": "S001", "title": "metrics.xlsx", "kind": "file",
                "path": "../family-app/materials/metrics.xlsx"}]
    events = [{"kind": "user", "text": "Вопрос", "t": 0}, {"kind": "agent", "text": text, "t": 1}]
    with _Browser() as b:
        page = b.open(_page_with(tmp_path, _bundle_with(events, claims, sources)),
                      "#speed=max&autoplay=1")
        page.wait_for_selector("#chat[data-done='1']")
        msg = page.locator(".msg.agent")
        assert msg.locator(".neg").inner_text() == "−59,3%"
        assert msg.locator(".pos").inner_text() == "+45 ₽"
        assert msg.locator("strong").inner_text() == "в когорте"
        assert msg.locator("em").inner_text() == "по умолчанию"
        assert msg.locator("code").inner_text() == "bin/strat <x>"
        assert msg.locator("img").count() == 0 and "<img src=x" in msg.inner_text()
        assert msg.locator("li").inner_text() == "пункт"
        assert msg.locator(".cite").count() == 2
        assert msg.locator(".cite").nth(1).get_attribute("class").split() == ["cite", "as"]
        msg.locator(".cite").first.click()
        card = page.locator("#ccard")
        page.wait_for_selector("#ccard.on")
        assert "Платящих стало меньше." in card.inner_text()
        link = card.locator("a.cc-file")
        assert link.get_attribute("href") == "../family-app/materials/metrics.xlsx"
        assert link.get_attribute("download") == "metrics.xlsx"
        page.keyboard.press("Escape")
        page.wait_for_selector("#ccard", state="hidden")
        msg.locator(".cite").nth(1).click()
        page.wait_for_selector("#ccard.on")
        assert "известное неизвестное" in card.inner_text()
    assert not b.errors, b.errors


def test_citations_without_claims_are_plain_chips(tmp_path):
    events = [{"kind": "user", "text": "Вопрос", "t": 0},
              {"kind": "agent", "text": "См. C025.", "t": 1}]
    with _Browser() as b:
        page = b.open(_page_with(tmp_path, _bundle_with(events)), "#speed=max&autoplay=1")
        page.wait_for_selector("#chat[data-done='1']")
        chip = page.locator(".msg.agent .cite")
        assert chip.inner_text() == "C025" and chip.evaluate("e => e.tagName") == "SPAN"
        chip.click()
        assert page.locator("#ccard").is_hidden()
    assert not b.errors, b.errors


def test_info_panel_opens_over_the_chat(strat, exported, tmp_path):
    bundle, _ = exported
    with _Browser() as b:
        page = b.open(_page_with(tmp_path, bundle), "#speed=max&autoplay=1")
        page.wait_for_selector("#chat[data-done='1']")
        assert not page.locator("#info").is_visible()
        before = page.locator("#chat").bounding_box()
        page.click("#infoBtn")
        page.wait_for_selector("#info.on")
        assert page.get_attribute("#infoBtn", "aria-expanded") == "true"
        assert "Gate 1" in page.inner_text("#info")
        assert page.locator("#chat").bounding_box() == before  # overlays, does not push
        page.keyboard.press("Escape")
        page.wait_for_selector("#info", state="hidden")
    assert not b.errors, b.errors


def test_redact_hides_the_local_user_name_and_export_refuses_it(monkeypatch):
    from strat import replay

    monkeypatch.setattr(replay.getpass, "getuser", lambda: "alicebob")
    out = replay.redact("-rw-r--r--  1 alicebob  wheel  7003 Nov 15 metrics.xlsx; alicebobby")
    assert out == "-rw-r--r--  1 [скрыто]  wheel  7003 Nov 15 metrics.xlsx; alicebobby"
    assert replay.leaked({"x": "drwxr-xr-x 5 alicebob staff"}) == ["alicebob"]


def test_redact_keeps_long_snake_case_metric_names():
    from strat.replay import redact

    name = "promo_3_months_free_aug_to_oct_change_pct"
    assert redact(f"{name} = -59.34 %") == f"{name} = -59.34 %"
    assert redact("key Ab3dEf6hIj9kLm2nOp5qRs8tUv1wXy4zAb7dEf0hIj") == "key [скрыто]"


def test_summary_names_web_search_pages_and_second_model_checks():
    from strat.replay import summarize

    items = [
        {"tool": "Bash", "line": 'bin/strat search "отток подписки бенчмарк" --step research.q1.search.1'},
        {"tool": "bash", "line": 'bin/strat search "churn paid ads cohort" --kind semantic'},
        {"tool": "Bash", "line": "bin/strat read https://example.org/a --step research.q1.read.1"},
        {"tool": "Bash", "line": "bin/strat read materials/metrics.xlsx --step intake.read.1"},
        {"tool": "Bash", "line": "bin/strat consult challenge --step options.challenge"},
        {"tool": "Bash", "line": "bin/strat judge support C001"},
        {"tool": "WebSearch", "line": "веб-поиск: «x»"},
    ]
    assert summarize(items) == ("Выполнил 1 команду, искал в интернете 3 раза, открыл 1 страницу, "
                                "сверился с другой моделью 2 раза")


def _play_bundle(tmp_path, text):
    bundle = {"version": 2, "runs": [{"id": "r", "model": "m", "harness": "opencode", "meta": {},
                                      "events": [{"kind": "user", "text": "Вопрос", "t": 0},
                                                 {"kind": "agent", "text": text, "t": 1}]}]}
    page_path = tmp_path / "index.html"
    shutil.copy(PAGE, page_path)
    from strat.replay import embed

    embed(page_path, bundle)
    sync_playwright = _chromium()
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:
            pytest.skip(f"no chromium: {exc}")
        page = browser.new_page()
        page.goto(page_path.as_uri() + "#speed=max&autoplay=1")
        page.wait_for_selector("#chat[data-done='1']", timeout=20_000)
        lists = page.eval_on_selector_all(
            ".msg.agent ol", "els => els.map(e => [e.start, e.children.length])")
        items = page.eval_on_selector_all(".msg.agent li", "els => els.map(e => e.innerText)")
        browser.close()
    return lists, items


def test_a_loose_numbered_list_with_indented_lines_stays_one_list(tmp_path):
    text = ("Уточните:\n\n1. **Охват:** для всех?  \n   *По умолчанию: для всех.*\n\n"
            "2. **Метрика:** выручка?  \n   *По умолчанию: маржа.*\n\n3. **Тест:** да?\n\nСпасибо.")
    lists, items = _play_bundle(tmp_path, text)
    assert lists == [[1, 3]]
    assert "По умолчанию: для всех." in items[0]


def test_a_list_split_by_a_paragraph_keeps_its_numbers(tmp_path):
    lists, _ = _play_bundle(tmp_path, "1. один\n2. два\n\nПояснение.\n\n3. три")
    assert lists == [[1, 2], [3, 1]]


def test_web_counts_come_from_the_case_log_by_time(tmp_path):
    """A shell loop ran 3 searches in one command; the summary and the run count all 3, with the
    provider that answered and the results returned."""
    from strat.replay import attach_web

    cdir = tmp_path / "case"
    cdir.mkdir()
    rows = [
        {"step": "research.q1.search.1", "ts": "2026-11-16T10:00:20+03:00", "tool": "search",
         "status": "ok", "note": "brave, 10 results"},
        {"step": "research.q1.search.2", "ts": "2026-11-16T10:00:21+03:00", "tool": "search",
         "status": "ok", "note": "exa, 8 results"},
        {"step": "research.q1.search.3", "ts": "2026-11-16T10:00:22+03:00", "tool": "search",
         "status": "error", "note": "tavily: 500"},
        {"step": "research.q1.read.1", "ts": "2026-11-16T10:00:40+03:00", "tool": "read",
         "status": "ok", "in": "https://example.org/a"},
        {"step": "research.q2.search.1", "ts": "2026-11-16T10:05:00+03:00", "tool": "search",
         "status": "ok", "note": "brave, 5 results"},
    ]
    (cdir / "log.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    loop = {"tool": "Bash", "line": 'for q in a b c; do bin/strat search "$q"; done', "t": 15}
    run = {"meta": {"start": "2026-11-16T07:00:00+00:00"}, "events": [
        {"kind": "steps", "t": 15, "items": [loop], "summary": ""},
        {"kind": "agent", "t": 60, "text": "..."},
        {"kind": "steps", "t": 290, "items": [{"tool": "Bash", "line": "bin/strat search x", "t": 290}],
         "summary": ""},
    ]}
    attach_web(run, cdir)
    g1, g2 = run["events"][0], run["events"][2]
    assert g1["summary"] == ("Искал в интернете 2 раза, "
                             "открыл 1 страницу")
    assert g2["summary"] == "Искал в интернете 1 раз"
    assert run["meta"]["web"] == {"searches": 3, "results": 23, "pages": 1,
                                  "providers": ["brave", "exa"]}


def test_active_minutes_leave_out_sleep_and_pauses():
    """A turn that ran 2 min, slept 90 min, worked 1 more min and then hung until the timeout."""
    from strat.replay import active_minutes

    ms = 60_000
    logs = {"1": [{"timestamp": 0}, {"timestamp": 2 * ms}, {"timestamp": 92 * ms},
                  {"timestamp": 93 * ms}]}
    assert active_minutes(logs, {"1": 93 * 60.0}) == 3.0
    assert active_minutes(logs, {"1": 140 * 60.0}) == 3.0          # idle tail after the last event
    assert active_minutes(logs, {"1": 95 * 60.0}) == 5.0           # a short tail is thinking time
    assert active_minutes({"1": [{"timestamp": 0}, {"timestamp": 3 * ms}]}, {}) == 3.0
