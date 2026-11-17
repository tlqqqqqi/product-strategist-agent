"""Q1: excess churn Aug-Oct 2026 vs the May-Jul baseline, and the May promo cohort's share.

Inputs are copied from sources/S001.md (metrics.xlsx, sheets monthly and cohorts).
Assumption: churn_pct is the share of the previous month's paying users lost in the month.
"""

monthly = {  # month: (paying_users, churn_pct)
    "2026-05": (41200, 4.1),
    "2026-06": (42900, 4.0),
    "2026-07": (44100, 4.3),
    "2026-08": (44800, 5.9),
    "2026-09": (43600, 6.6),
    "2026-10": (42300, 6.8),
}
cohorts = {"promo_3_months_free": (9800, 21.4), "organic": (18200, 3.2),
           "partner_bank": (6100, 4.0), "paid_ads": (7100, None)}

months = list(monthly)
baseline = sum(monthly[m][1] for m in ("2026-05", "2026-06", "2026-07")) / 3
print(f"baseline churn May-Jul 2026: {baseline:.2f}%")

total_excess = 0.0
for i, m in enumerate(months[3:], start=3):
    base_users = monthly[months[i - 1]][0]
    churn = monthly[m][1]
    lost = base_users * churn / 100
    excess = base_users * (churn - baseline) / 100
    total_excess += excess
    print(f"{m}: base {base_users}, churned ~{lost:.0f}, excess over baseline ~{excess:.0f}")
print(f"excess churned users Aug-Oct 2026: ~{total_excess:.0f}")

aug_lost = monthly["2026-07"][0] * monthly["2026-08"][1] / 100
aug_excess = monthly["2026-07"][0] * (monthly["2026-08"][1] - baseline) / 100
promo_n, promo_pct = cohorts["promo_3_months_free"]
promo_lost = promo_n * promo_pct / 100
print(f"May promo cohort lost by month 3: ~{promo_lost:.0f}")
print(f"promo cohort loss / August excess: {promo_lost / aug_excess:.2f}x")
print(f"promo cohort loss / all August churn: {promo_lost / aug_lost:.0%}")
print(f"promo cohort loss / excess Aug-Oct: {promo_lost / total_excess:.0%}")

cohort_sum = sum(n for n, _ in cohorts.values())
print(f"sum of joined_2026_05 over channels: {cohort_sum}; paying_users 2026-05: {monthly['2026-05'][0]}")
