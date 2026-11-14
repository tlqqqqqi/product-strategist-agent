"""Claim ledger. Expanded in Step 3."""


def test_assumption_without_source_is_accepted(strat, case):
    r = strat("claim", "add", "--type", "assumption", "--kind", "market",
              "--text", "Пользователи не сравнивают цены", "--json")
    assert r.code == 0 and r.data["id"] == "C001"
