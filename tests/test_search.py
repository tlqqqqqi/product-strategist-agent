"""Search. Expanded in Step 5."""


def test_search_without_any_key_exits_2(strat, case):
    r = strat("search", "семейное облако цена", "--step", "research.q1.search.1")
    assert r.code == 2
