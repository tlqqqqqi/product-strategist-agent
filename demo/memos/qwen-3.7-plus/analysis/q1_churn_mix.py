# Q1: how much of the extra churn volume comes from the ads cohort.
# unit: families per month and %/p.p.; period: August 2026 vs April 2026 (months);
# gaps: none in the columns read (monthly B..D have 0 empty cells);
# denominator: churn rate = churned / active_paying_start; the mix uses retained_m1 of the
#   ads cohort vs the non-ads cohorts of the same months (cohorts sheet).
from strat.analysis import figure, diff, load

monthly = load("materials/metrics.xlsx", "monthly")
cohorts = load("materials/metrics.xlsx", "cohorts")

for m in ("2026-04", "2026-08"):
    r = monthly.value("churned", {"month": m})
    figure(f"churned_{m}", int(r), "families", m)

aug = int(monthly.value("churned", {"month": "2026-08"}))
apr = int(monthly.value("churned", {"month": "2026-04"}))
figure("churned_change_2026-04_to_2026-08", aug - apr, "families", "2026-04..2026-08")

# ads families that stop paying in the second month, August 2026 cohort
row = [r for r in cohorts.rows if r["month"] == "2026-08" and r["channel"] == "performance_ads"][0]
lost = int(row["new_paying"]) - int(row["retained_m1"])
figure("ads_2026-08_lost_m1", lost, "families", "2026-08")
figure("ads_lost_share_of_churned_2026-08", round(lost / aug * 100, 1), "%", "2026-08")

# the same for the month the ads cohort could first stop paying: June 2026
row6 = [r for r in cohorts.rows if r["month"] == "2026-06" and r["channel"] == "performance_ads"][0]
lost6 = int(row6["new_paying"]) - int(row6["retained_m1"])
jun = int(monthly.value("churned", {"month": "2026-06"}))
figure("ads_2026-06_lost_m1", lost6, "families", "2026-06")
figure("ads_lost_share_of_churned_2026-06", round(lost6 / jun * 100, 1), "%", "2026-06")
