"""Data analysis: scripts reproduce cited figures; unit, period and gap problems are reported.

tests/fixtures/analysis/sales.csv is synthetic (invented regions and numbers).
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO
from strat import analysis

FIXTURES = REPO / "tests" / "fixtures" / "analysis"

PROMO_SCRIPT = '''\
from strat.analysis import load, figure, pct_change, diff

t = load("materials/metrics.xlsx", "cohorts")
promo = {"channel": "promo_3_months_free"}
aug = figure("promo_paid_aug", t.value("paid_users_2026_08", promo), "users", "2026-08")
oct_ = figure("promo_paid_oct", t.value("paid_users_2026_10", promo), "users", "2026-10")
diff(oct_, aug, "promo_paid_change")
pct_change(oct_, aug, "promo_paid_change_pct")
'''

SALES_SCRIPT = '''\
from strat.analysis import load, figure

t = load("materials/sales.csv", "sales")
figure("revenue_total", sum(t.numbers("revenue_thousand_rub")), "thousand RUB", "2026-10")
figure("orders_total", sum(t.numbers("orders")), "orders", "2026-10")
'''


def run_script(case: Path, name: str, body: str) -> Path:
    """Write analysis/<name>.py, run it as the agent does, save stdout to analysis/<name>.txt."""
    (case / "analysis").mkdir(exist_ok=True)
    script = case / "analysis" / f"{name}.py"
    script.write_text(body, encoding="utf-8")
    out = case / "analysis" / f"{name}.txt"
    proc = subprocess.run([sys.executable, str(script)], cwd=case, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out.write_text(proc.stdout, encoding="utf-8")
    return out


def register(strat, path: str) -> str:
    r = strat("source", "add", path, "--json")
    assert r.code == 0, r.err
    return r.data["id"]


# --- reproduce a cited figure -----------------------------------------------------------------

def test_sample_case_promo_drop_is_reproduced(strat, case):
    out = run_script(case, "q1_promo_drop", PROMO_SCRIPT).read_text()
    assert "FIGURE promo_paid_aug = 4550 users | period 2026-08" in out
    assert "FIGURE promo_paid_oct = 1850 users | period 2026-10" in out
    assert "FIGURE promo_paid_change = -2700 users | period 2026-08..2026-10" in out
    assert "FIGURE promo_paid_change_pct = -59.34 % | period 2026-08..2026-10" in out

    sid = register(strat, "analysis/q1_promo_drop.txt")
    r = strat("claim", "add", "--type", "fact", "--kind", "product_metric",
              "--text", "Платящих из промо-когорты стало на 2700 меньше с августа по октябрь 2026",
              "--source", sid, "--where", "promo_paid_change",
              "--quote", "promo_paid_change = -2700 users", "--as-of", "2026-10", "--historical")
    assert r.code == 0, r.err

    r = strat("analysis", "check", sid)
    assert r.code == 0, r.out + r.err
    assert "reproduced" in r.out


def test_edited_data_fails_the_check_and_names_the_figure(strat, case):
    shutil.copy(FIXTURES / "sales.csv", case / "materials" / "sales.csv")
    run_script(case, "q2_sales", SALES_SCRIPT)
    sid = register(strat, "analysis/q2_sales.txt")
    assert strat("analysis", "check", sid).code == 0

    data = case / "materials" / "sales.csv"
    data.write_text(data.read_text().replace("north,1200", "north,1300"))
    r = strat("analysis", "check", sid)
    assert r.code == 1
    assert "revenue_total" in r.err
    assert "orders_total" not in r.err  # unchanged figures are not blamed
    assert "materials/sales.csv changed" in r.err


def test_changed_input_is_reported_even_when_the_figures_still_match(strat, case):
    shutil.copy(FIXTURES / "sales.csv", case / "materials" / "sales.csv")
    run_script(case, "q2_sales", SALES_SCRIPT)
    sid = register(strat, "analysis/q2_sales.txt")
    data = case / "materials" / "sales.csv"
    data.write_text(data.read_text().replace("east,", "east-1,"))  # no figure uses the region
    r = strat("analysis", "check", sid)
    assert r.code == 0, r.err  # the figures still reproduce
    assert "materials/sales.csv changed" in r.out + r.err


def test_check_refuses_a_non_analysis_source(strat, case):
    sid = register(strat, "materials/metrics.xlsx")
    r = strat("analysis", "check", sid)
    assert r.code == 1 and "not an analysis output" in r.err


# --- gaps -------------------------------------------------------------------------------------

def test_empty_cells_in_the_used_range_are_reported(strat, case):
    shutil.copy(FIXTURES / "sales.csv", case / "materials" / "sales.csv")
    out = run_script(case, "q2_sales", SALES_SCRIPT).read_text()
    assert "GAP sales!C3 (orders, region=south) is empty" in out
    sid = register(strat, "analysis/q2_sales.txt")
    r = strat("analysis", "check", sid)
    assert r.code == 0
    assert "sales!C3" in r.out


def test_a_gap_in_the_sample_cohort_is_reported(strat, case):
    body = ('from strat.analysis import load\n'
            't = load("materials/metrics.xlsx", "cohorts")\n'
            'print(t.value("paid_users_2026_10", {"channel": "paid_ads"}))\n')
    out = run_script(case, "q3_ads", body).read_text()
    assert "GAP cohorts!D5 (paid_users_2026_10, channel=paid_ads) is empty" in out


# --- unit and period mismatch -----------------------------------------------------------------

def test_monthly_and_quarterly_figures_are_not_combined(capsys):
    monthly = analysis.figure("churn_oct", 6.8, "%", "2026-10")
    quarterly = analysis.figure("churn_q3", 16.0, "%", "2026-Q3")
    with pytest.raises(analysis.Mismatch) as exc:
        analysis.diff(monthly, quarterly, "churn_change")
    assert "month" in str(exc.value) and "quarter" in str(exc.value)
    assert "MISMATCH" in capsys.readouterr().out


def test_rub_and_thousand_rub_are_not_combined():
    a = analysis.figure("arpu", 334, "₽", "2026-10")
    b = analysis.figure("revenue", 14128, "thousand RUB", "2026-10")
    with pytest.raises(analysis.Mismatch) as exc:
        analysis.share(a, b, "arpu_share")
    assert "RUB" in str(exc.value) and "thousand RUB" in str(exc.value)


def test_a_conclusion_over_mismatched_figures_is_reported(strat, case):
    run_script(case, "q4_churn", 'from strat.analysis import figure\n'
                                 'figure("churn_oct", 6.8, "%", "2026-10")\n')
    run_script(case, "q5_churn_q", 'from strat.analysis import figure\n'
                                   'figure("churn_q3", 16.0, "%", "2026-Q3")\n')
    s1 = register(strat, "analysis/q4_churn.txt")
    s2 = register(strat, "analysis/q5_churn_q.txt")
    ids = []
    for sid, quote, as_of in ((s1, "churn_oct = 6.8 %", "2026-10"),
                              (s2, "churn_q3 = 16 %", "2026-09")):
        r = strat("claim", "add", "--type", "fact", "--kind", "product_metric",
                  "--text", f"Отток {quote}", "--source", sid, "--where", "x",
                  "--quote", quote, "--as-of", as_of, "--json")
        assert r.code == 0, r.err
        ids.append(r.data["id"])
    r = strat("claim", "add", "--type", "conclusion", "--kind", "product_metric",
              "--text", "Отток в октябре ниже, чем в третьем квартале",
              "--supports", ",".join(ids), "--json")
    assert r.code == 0, r.err
    conclusion = r.data["id"]

    r = strat("analysis", "check", "--all")
    assert r.code == 1
    assert conclusion in r.err and "month" in r.err and "quarter" in r.err


def test_a_figure_needs_a_unit_and_a_known_period_form():
    with pytest.raises(ValueError):
        analysis.figure("x", 1, "", "2026-10")
    with pytest.raises(ValueError):
        analysis.figure("x", 1, "%", "October")
