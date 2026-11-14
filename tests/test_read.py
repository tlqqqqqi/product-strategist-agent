"""Read. Expanded in Step 5."""


def test_saved_html_page_becomes_a_web_source(strat, case):
    r = strat("read", str(case / "materials" / "competitor.html"), "--step", "r1", "--json")
    assert r.code == 0 and r.data["id"] == "S001"
