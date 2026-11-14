"""State and log. Expanded in Step 2."""


def test_new_case_starts_at_intake(strat, cases):
    assert strat("new", "demo", "--title", "Sample").code == 0
    r = strat("state", "--json")
    assert r.code == 0 and r.data["stage"] == "intake"
