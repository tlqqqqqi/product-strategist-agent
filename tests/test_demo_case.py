"""Demo case materials (Task 17): the numbers, read through the project's own converter, keep
the intended story. The monthly table points at the new onboarding (same month), the cohort
table puts the drop in one new paid channel, and the other channels retain as before."""

import csv
import io
import shutil
import subprocess
import sys

import pytest

from conftest import REPO
from strat.convert import convert

DEMO = REPO / "demo" / "family-app"
MATERIALS = DEMO / "materials"
METRICS = MATERIALS / "metrics.xlsx"
NEW_CHANNEL = "performance_ads"


def sheet(text: str, name: str) -> list[dict]:
    block = text.split(f"## sheet: {name}\n")[1].split("```csv\n")[1].split("```")[0]
    return list(csv.DictReader(io.StringIO(block)))


def num(value: str):
    return None if value == "" else float(value)


@pytest.fixture(scope="module")
def tables():
    text = convert(str(METRICS))
    monthly = sheet(text, "monthly")
    cohorts = sheet(text, "cohorts")
    return monthly, cohorts


def m1(row):
    r = num(row["retained_m1"])
    return None if r is None else r / float(row["new_paying"]) * 100


def test_monthly_totals_are_consistent(tables):
    monthly, _ = tables
    assert 9 <= len(monthly) <= 12
    prev_end = None
    for row in monthly:
        start, new, churned, end = (int(row[k]) for k in
                                    ("active_paying_start", "new_paying", "churned",
                                     "active_paying_end"))
        assert end == start + new - churned
        if prev_end is not None:
            assert start == prev_end
        prev_end = end
        assert abs(float(row["churn_pct"]) - churned / start * 100) <= 0.05
        assert 249 * end <= int(row["mrr_rub"]) <= 299 * end


def test_cohort_new_payers_sum_to_the_monthly_new_payers(tables):
    monthly, cohorts = tables
    for row in monthly:
        rows = [c for c in cohorts if c["month"] == row["month"]]
        assert rows, row["month"]
        assert sum(int(c["new_paying"]) for c in rows) == int(row["new_paying"])


def test_cohort_retention_matches_monthly_m1_where_all_channels_are_known(tables):
    monthly, cohorts = tables
    checked = 0
    for row in monthly:
        rows = [c for c in cohorts if c["month"] == row["month"]]
        if row["new_retained_m1_pct"] == "" or any(c["retained_m1"] == "" for c in rows):
            continue
        pct = sum(int(c["retained_m1"]) for c in rows) / int(row["new_paying"]) * 100
        assert abs(pct - float(row["new_retained_m1_pct"])) <= 0.05
        checked += 1
    assert checked >= 6


def test_retained_counts_never_grow(tables):
    _, cohorts = tables
    for c in cohorts:
        seq = [int(c["new_paying"])] + [int(c[k]) for k in ("retained_m1", "retained_m2",
                                                            "retained_m3") if c[k] != ""]
        assert seq == sorted(seq, reverse=True), c


def test_drop_month_equals_onboarding_release_and_new_channel_launch(tables):
    monthly, cohorts = tables
    base = [float(r["new_retained_m1_pct"]) for r in monthly[:3]]
    drop = next(r["month"] for r in monthly
                if r["new_retained_m1_pct"] != ""
                and float(r["new_retained_m1_pct"]) < min(base) - 5)
    onboarding = next(r["month"] for r in monthly
                      if r["onboarding_version"] != monthly[0]["onboarding_version"])
    launch = min(c["month"] for c in cohorts if c["channel"] == NEW_CHANNEL)
    assert drop == onboarding == launch
    before = [float(r["churn_pct"]) for r in monthly if r["month"] <= drop]
    after = [float(r["churn_pct"]) for r in monthly if r["month"] > drop]
    assert min(after) > max(before) + 1.5  # the monthly churn rises after that month


def test_new_channel_retains_far_worse_than_every_other(tables):
    _, cohorts = tables
    new = [c for c in cohorts if c["channel"] == NEW_CHANNEL]
    others = [c for c in cohorts if c["channel"] != NEW_CHANNEL]
    for k, gap in (("retained_m1", 25), ("retained_m2", 30)):
        worst_new = max(int(c[k]) / int(c["new_paying"]) for c in new if c[k] != "")
        best_other = min(int(c[k]) / int(c["new_paying"]) for c in others if c[k] != "")
        assert (best_other - worst_new) * 100 > gap


def test_other_channels_retain_as_before_with_at_most_a_small_dip(tables):
    _, cohorts = tables
    launch = min(c["month"] for c in cohorts if c["channel"] == NEW_CHANNEL)
    channels = {c["channel"] for c in cohorts} - {NEW_CHANNEL}
    assert len(channels) >= 3
    for ch in channels:
        rows = [c for c in cohorts if c["channel"] == ch and m1(c) is not None]
        before = [m1(c) for c in rows if c["month"] < launch][-3:]
        after = [m1(c) for c in rows if c["month"] >= launch][:3]
        assert before and after
        dip = sum(before) / len(before) - sum(after) / len(after)
        assert -1 <= dip < 2, (ch, dip)


def test_one_honest_data_gap(tables):
    _, cohorts = tables
    launch = min(c["month"] for c in cohorts if c["channel"] == NEW_CHANNEL)
    gaps = [c for c in cohorts if c["retained_m1"] == "" and c["month"] < "2026-10"]
    assert len(gaps) == 1
    assert gaps[0]["channel"] != NEW_CHANNEL and gaps[0]["month"] >= launch


def test_generator_reproduces_the_committed_materials(tmp_path):
    out = tmp_path / "materials"
    subprocess.run([sys.executable, str(DEMO / "make_materials.py"), "--out", str(out)],
                   check=True)
    names = sorted(p.name for p in MATERIALS.iterdir())
    assert names == sorted(p.name for p in out.iterdir())
    for name in names:
        assert convert(str(out / name)).replace(str(out), "") == \
            convert(str(MATERIALS / name)).replace(str(MATERIALS), "")


def test_every_material_registers_as_a_source(strat, cases):
    assert strat("new", "family", "--title", "Demo").code == 0
    shutil.copytree(MATERIALS, cases / "family" / "materials", dirs_exist_ok=True)
    ids = []
    for f in sorted(MATERIALS.iterdir()):
        r = strat("source", "add", f"materials/{f.name}", "--json")
        assert r.code == 0, r.err
        ids.append(r.data["id"])
        assert (cases / "family" / r.data["snapshot"]).stat().st_size > 200
    assert len(set(ids)) == len(ids) >= 3
