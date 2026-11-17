# Q1: where the second-month retention fall sits, by channel.
# unit: share of a cohort in % (retained_m1 / new_paying); period: cohorts 2025-11..2026-09;
# gaps: operator_bundle 2026-06 has no retained_m1 (operator export missing), printed as GAP;
# denominator: new_paying of the same cohort row; definition: `about` sheet, cohorts.retained_mN
#   = families of the cohort paying N months after the first payment.
import csv
from pathlib import Path

from strat.analysis import figure, load

t = load("materials/metrics.xlsx", "cohorts")

rows = t.rows
pre = [r for r in rows if r["month"] < "2026-05"]
post = [r for r in rows if r["month"] >= "2026-05" and r["channel"] != "performance_ads"]

for label, group in (("2025-11..2026-04", pre), ("2026-05..2026-09", post)):
    for ch in ("organic", "referral", "operator_bundle"):
        part = 0
        whole = 0
        for r in group:
            if r["channel"] != ch:
                continue
            if r["retained_m1"] in ("", None):
                print(f"GAP retained_m1 {r['month']} {ch}")
                continue
            part += int(r["retained_m1"])
            whole += int(r["new_paying"])
        if whole:
            figure(f"{label}_{ch}_m1_pct", round(part / whole * 100, 1), "%", label)

for r in rows:
    if r["channel"] == "performance_ads" and r["retained_m1"] not in ("", None):
        figure(
            f"ads_{r['month']}_m1_pct",
            round(int(r["retained_m1"]) / int(r["new_paying"]) * 100, 1),
            "%",
            r["month"],
        )
        figure(f"ads_{r['month']}_new_paying", int(r["new_paying"]), "families", r["month"])

ads_new = sum(int(r["new_paying"]) for r in rows if r["channel"] == "performance_ads"
              and r["month"] >= "2026-05")
other_new = sum(int(r["new_paying"]) for r in rows if r["channel"] != "performance_ads"
                and r["month"] >= "2026-05")
figure("ads_new_paying_2026-05_2026-09", ads_new, "families", "2026-05..2026-09")
figure("other_new_paying_2026-05_2026-09", other_new, "families", "2026-05..2026-09")
figure("ads_share_new_2026-05_2026-09", round(ads_new / (ads_new + other_new) * 100, 1),
       "%", "2026-05..2026-09")
