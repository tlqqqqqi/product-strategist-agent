"""Cost by stage. Expanded in Step 2."""


def test_cost_of_a_new_case_is_zero(strat, case):
    r = strat("cost", "--json")
    assert r.code == 0 and r.data["total"]["usd"] == 0
