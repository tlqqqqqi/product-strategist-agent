"""Strategy: what a lower promo churn by month 3 is worth per cohort the size of May 2026.

Inputs from sources/S001.md (cohorts: promo 9800, 21.4%) and S002.md (price 349 RUB).
Scenarios for churn by month 3 after the promo is rebuilt are analyst assumptions, not data.
"""

n, base_pct, price = 9800, 21.4, 349
base_stay = n * (1 - base_pct / 100)
for target in (18.0, 15.0, 12.0):
    stay = n * (1 - target / 100)
    extra = stay - base_stay
    print(f"churn by month 3 {target}%: +{extra:.0f} payers per cohort, +{extra * price / 1e6:.2f}M RUB per month")
