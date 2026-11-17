"""Q3: paying users the May 2026 promo cohort leaves after month 3, vs other channels.

Inputs from sources/S001.md (cohorts) and S002.md (price 349 RUB).
Simplification: everyone who stayed past month 3 pays the full price of 349 RUB.
"""

cohorts = {"promo_3_months_free": (9800, 21.4), "organic": (18200, 3.2),
           "partner_bank": (6100, 4.0), "paid_ads": (7100, None)}
price = 349

for name, (n, pct) in cohorts.items():
    if pct is None:
        print(f"{name}: joined {n}, churn by month 3 unknown")
        continue
    stay = n * (1 - pct / 100)
    print(f"{name}: joined {n}, remain after month 3 ~{stay:.0f}, monthly revenue ~{stay * price / 1e6:.2f}M RUB")

promo_stay = 9800 * (1 - 0.214)
known_stay = sum(n * (1 - p / 100) for n, p in cohorts.values() if p is not None)
print(f"promo share of remaining May users (known channels): {promo_stay / known_stay:.0%}")
print(f"promo payers vs October paying base 42300: {promo_stay / 42300:.0%}")
