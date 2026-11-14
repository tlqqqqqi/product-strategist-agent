"""Source index. Expanded in Step 3."""


def test_html_material_gets_an_s_id(strat, case):
    r = strat("source", "add", "materials/competitor.html", "--json")
    assert r.code == 0 and r.data["id"] == "S001"
