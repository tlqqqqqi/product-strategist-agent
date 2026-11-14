"""Gate checks. Expanded in Step 7."""


def test_gate1_fails_without_files(strat, case):
    r = strat("gate", "check", "1")
    assert r.code == 1 and "brief.md" in r.err
