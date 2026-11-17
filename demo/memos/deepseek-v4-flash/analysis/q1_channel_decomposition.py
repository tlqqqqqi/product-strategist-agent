# Q1: did the churn rise come from onboarding v2 or from the new performance_ads channel?
# unit: families (users) and %; period: months 2026-04..2026-10 (closed history, 2026-10 has gaps);
# gaps: cohorts.retained_m1 empty for 2026-10 (not yet known), operator_bundle 2026-06 empty;
#        column gaps read and printed as GAP lines;
# denominator: M1 retention = retained_m1 / new_paying of the same cohort;
#              churn_pct = churned / active_paying_start (about sheet);
# definition: `about` sheet, cohorts.retained_mN, monthly.new_retained_m1_pct.
from strat.analysis import load, figure, share

t = load("S001", "cohorts")

# M1 retention by channel and month
for row in t.rows:
    if row["month"] < "2026-04":
        continue
    n = row["new_paying"]
    m1 = row["retained_m1"]
    if n in (None, "") or m1 in (None, ""):
        continue
    r = figure(
        f"m1_{row['month']}_{row['channel']}",
        float(m1) / float(n) * 100,
        "%",
        row["month"],
    )

# share of performance_ads in new_paying per month
for row in t.rows:
    if row["channel"] != "performance_ads":
        continue
    month = row["month"]
    total = sum(
        float(r["new_paying"])
        for r in t.rows
        if r["month"] == month and r["new_paying"] not in (None, "")
    )
    share(
        figure(f"ads_new_{month}", float(row["new_paying"]), "families", month),
        figure(f"all_new_{month}", total, "families", month),
        f"ads_share_{month}",
    )
