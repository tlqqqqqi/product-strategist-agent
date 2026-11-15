"""Browser capture (Task 13): a public flow becomes screenshots with element boxes, each a `shot`
source a claim can cite; submit, login and payment clicks are refused by the script.

Tests that drive a browser serve tests/fixtures/capture from a local http server and skip when
Playwright or its Chromium is not installed. Nothing here touches the internet.
"""

import http.server
import json
import sys
import threading
from functools import partial
from pathlib import Path

import pytest

from strat import browser
from strat.core import read_jsonl

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "capture"


# --- without a browser ------------------------------------------------------------------------

def test_without_playwright_exits_2_and_names_setup(strat, case, monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    r = strat("capture", "https://example.org/tariffs", "--flow", "tariffs")
    assert r.code == 2
    assert "playwright install chromium-headless-shell" in r.err
    assert not (case / "shots").exists()


@pytest.mark.parametrize("el", [
    {"tag": "input", "type": "submit", "text": "Найти"},
    {"tag": "input", "type": "password"},
    {"tag": "button", "type": "submit", "text": "Далее", "in_form": True},
    {"tag": "button", "type": "", "text": "Отправить", "in_form": True},
    {"tag": "a", "text": "Войти", "href": "https://example.org/account"},
    {"tag": "a", "text": "Личный кабинет", "href": "https://example.org/login?next=/"},
    {"tag": "button", "type": "button", "text": "Купить"},
    {"tag": "button", "type": "button", "text": "Подключить тариф"},
    {"tag": "a", "text": "Pay now", "href": "#"},
    {"tag": "a", "text": "Sign up", "href": "#"},
    {"tag": "a", "text": "Оформить", "href": "/checkout"},
])
def test_risky_elements_are_refused(el):
    assert browser.refuse_reason(el)


@pytest.mark.parametrize("el", [
    {"tag": "a", "text": "Подробнее о тарифах", "href": "plans.html"},
    {"tag": "button", "type": "button", "text": "Показать годовые цены"},
    {"tag": "button", "type": "button", "text": "Display options", "in_form": True},
    {"tag": "div", "role": "tab", "text": "Для бизнеса"},
])
def test_plain_navigation_is_allowed(el):
    assert browser.refuse_reason(el) is None


def test_plan_with_typing_is_refused_before_any_browser(strat, case, tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"steps": [{"name": "start"},
                                          {"name": "form", "fill": {"#q": "x"}}]}))
    r = strat("capture", "https://example.org/", "--flow", "f", "--plan", str(plan))
    assert r.code == 1 and "fill" in r.err


def test_plan_may_scroll_and_goto_must_be_a_string(tmp_path):
    ok = tmp_path / "ok.json"
    ok.write_text(json.dumps({"steps": [{"name": "top"}, {"name": "below", "scroll": True}]}))
    assert browser.load_plan(str(ok))[1]["scroll"] is True
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"steps": [{"name": "a", "goto": 123}]}))
    with pytest.raises(browser.StratError, match="http"):
        browser.load_plan(str(bad))
    for combo in ({"click": "a.next", "scroll": True}, {"goto": "https://example.org/b",
                                                       "scroll": True}):
        two = tmp_path / "two.json"
        two.write_text(json.dumps({"steps": [{"name": "a", **combo}]}))
        with pytest.raises(browser.StratError, match="one action"):
            browser.load_plan(str(two))
    notbool = tmp_path / "nb.json"
    notbool.write_text(json.dumps({"steps": [{"name": "a", "scroll": "yes"}]}))
    with pytest.raises(browser.StratError, match="scroll"):
        browser.load_plan(str(notbool))


@pytest.mark.parametrize("landed, why", [
    ("https://cloud.example.org/login?next=/", "login"),
    ("https://evil.example.net/promo", "another site"),
    ("ftp://cloud.example.org/x", "another site"),
])
def test_landing_page_off_the_public_flow_is_refused(landed, why):
    sites = browser.allowed_sites("https://www.example.org/tariffs", [])
    assert why in browser.landing_refusal(landed, sites)


def test_landing_page_on_the_same_site_or_a_planned_one_is_allowed():
    sites = browser.allowed_sites("https://www.example.org/tariffs",
                                  [{"name": "b", "goto": "https://other.example.com/plans"}])
    for url in ("https://example.org/plans", "https://cloud.example.org/family",
                "https://other.example.com/plans#x", "about:blank"):
        assert browser.landing_refusal(url, sites) is None, url


def test_where_names_an_element_and_the_quote_is_its_text():
    shot = json.dumps({"url": "u", "viewport": [1, 1], "targets": {
        "price": {"box": [0, 0, 1, 1], "text": "1 ТБ — 249 ₽"},
        "other": {"box": [0, 0, 1, 1], "text": "99 ₽"}}}, ensure_ascii=False)
    assert browser.locate_shot(shot, "price") == "1 ТБ — 249 ₽"
    with pytest.raises(Exception, match="no element 'nope'"):
        browser.locate_shot(shot, "nope")


# --- with a browser ---------------------------------------------------------------------------

class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _record(self):
        self.server.seen.append((self.command, self.path))

    def do_GET(self):
        self._record()
        super().do_GET()

    def do_POST(self):
        self._record()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"posted")


@pytest.fixture(scope="module")
def chromium():
    pytest.importorskip("playwright.sync_api", exc_type=ImportError)
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            p.chromium.launch().close()
    except Exception as exc:  # the browser binary is not installed
        pytest.skip(f"Chromium for Playwright is not installed: {exc}")


@pytest.fixture
def site(chromium):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                                             partial(_Handler, directory=str(FIXTURES)))
    server.seen = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", server.seen
    server.shutdown()


def _plan(tmp_path, steps):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"steps": steps}, ensure_ascii=False))
    return str(path)


def test_public_flow_yields_screenshots_with_boxes_and_text(strat, case, site, tmp_path):
    base, seen = site
    plan = _plan(tmp_path, [
        {"name": "tariffs", "targets": {"family_price": "#family-price", "details": "#details"}},
        {"name": "compare", "click": "#details"},
    ])
    r = strat("capture", f"{base}/index.html", "--flow", "cloud", "--plan", plan, "--json")
    assert r.code == 0, r.err
    assert [s["shot"] for s in r.data["shots"]] == ["shots/cloud/01_tariffs.png",
                                                     "shots/cloud/02_compare.png"]
    for name in ("01_tariffs", "02_compare"):
        png = case / "shots" / "cloud" / f"{name}.png"
        assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    first = json.loads((case / "shots" / "cloud" / "01_tariffs.json").read_text())
    assert first["url"] == f"{base}/index.html"
    assert first["viewport"] == [1440, 900]
    price = first["targets"]["family_price"]
    assert price["text"] == "6 человек, 1 ТБ — 249 ₽ в месяц"
    x, y, w, h = price["box"]
    assert w > 0 and h > 0 and 0 <= y < 900
    # auto-detected elements carry text too: the heading is there without being named
    assert "Тарифы ОблакоПлюс" in [t["text"] for t in first["targets"].values()]
    second = json.loads((case / "shots" / "cloud" / "02_compare.json").read_text())
    assert second["url"] == f"{base}/plans.html"

    entries = read_jsonl(case / "sources" / "index.jsonl")
    assert [e["kind"] for e in entries] == ["shot", "shot"]
    assert entries[0]["origin"] == "shots/cloud/01_tariffs.png"
    assert json.loads((case / entries[0]["snapshot"]).read_text()) == first
    assert entries[0]["flags"] == ["instructions_to_ai"]  # the planted line is flagged as data

    c = strat("claim", "add", "--type", "fact", "--kind", "price",
              "--text", "Семейный тариф ОблакоПлюс стоит 249 ₽ в месяц", "--source", "S001",
              "--where", "family_price", "--quote", "1 ТБ — 249 ₽ в месяц", "--as-of", "2026-11")
    assert c.code == 0, c.err
    bad = strat("claim", "add", "--type", "fact", "--kind", "price",
                "--text", "Семейный тариф стоит 199 ₽", "--source", "S001",
                "--where", "family_price", "--quote", "199 ₽ в месяц", "--as-of", "2026-11")
    assert bad.code == 1

    assert all(method == "GET" for method, _ in seen)  # the page's own submit and POST blocked
    row = read_jsonl(case / "log.jsonl")[-1]
    assert row["tool"] == "capture" and row["status"] == "ok" and row["usd"] == 0
    assert "blocked" in row["note"]


@pytest.mark.parametrize("target, what", [("#login", "login"), ("#send", "submit"),
                                          ("#buy", "pay")])
def test_risky_click_is_refused_and_logged(strat, case, site, tmp_path, target, what):
    base, seen = site
    plan = _plan(tmp_path, [{"name": "start"}, {"name": "next", "click": target}])
    r = strat("capture", f"{base}/index.html", "--flow", "risky", "--plan", plan)
    assert r.code == 1
    assert "refused" in r.err and what in r.err
    assert (case / "shots" / "risky" / "01_start.png").is_file()
    assert not (case / "shots" / "risky" / "02_next.png").exists()
    refused = [row for row in read_jsonl(case / "log.jsonl") if row["status"] == "refused"]
    assert len(refused) == 1 and target in refused[0]["in"]
    assert ("GET", "/login.html") not in seen
    assert all(method == "GET" for method, _ in seen)


def test_a_failed_step_is_logged_and_keeps_earlier_shots(strat, case, site, tmp_path):
    base, _ = site
    plan = _plan(tmp_path, [{"name": "start"}, {"name": "next", "click": "#no-such-link"}])
    r = strat("capture", f"{base}/index.html", "--flow", "broken", "--plan", plan)
    assert r.code == 1 and "step 2 (next) failed" in r.err and "Traceback" not in r.err
    assert "01_start.png" in r.err
    row = read_jsonl(case / "log.jsonl")[-1]
    assert row["status"] == "error" and row["ref"] == "S001"


def test_without_a_plan_steps_are_screens_of_one_page(strat, case, site):
    base, _ = site
    r = strat("capture", f"{base}/index.html", "--flow", "scroll", "--steps", "2", "--json")
    assert r.code == 0, r.err
    assert [s["shot"] for s in r.data["shots"]] == ["shots/scroll/01_screen.png",
                                                     "shots/scroll/02_screen.png"]
    # a page has only so many screens: asking for more stops at the end
    r = strat("capture", f"{base}/index.html", "--flow", "scroll2", "--steps", "9", "--json")
    assert len(r.data["shots"]) == 3
    last = json.loads((case / "shots" / "scroll2" / "03_screen.json").read_text())
    assert "Конец страницы" in [t["text"] for t in last["targets"].values()]


def test_a_captured_flow_is_never_overwritten(strat, case, site):
    base, _ = site
    assert strat("capture", f"{base}/index.html", "--flow", "once", "--steps", "1",
                 "--step", "a").code == 0
    r = strat("capture", f"{base}/index.html", "--flow", "once", "--steps", "1", "--step", "b")
    assert r.code == 1 and "already captured" in r.err


def test_a_finished_capture_step_replays_without_a_browser(strat, case, site, monkeypatch):
    base, seen = site
    assert strat("capture", f"{base}/index.html", "--flow", "f1", "--steps", "1",
                 "--step", "research.q2.capture.1").code == 0
    hits = len(seen)
    r = strat("capture", f"{base}/index.html", "--flow", "f1", "--steps", "1",
              "--step", "research.q2.capture.1", "--json")
    assert r.code == 0 and r.data["replayed"] is True
    assert len(seen) == hits


def test_only_http_urls(strat, case, chromium):
    r = strat("capture", "file:///etc/hosts", "--flow", "x", "--steps", "1")
    assert r.code == 1 and "http" in r.err
