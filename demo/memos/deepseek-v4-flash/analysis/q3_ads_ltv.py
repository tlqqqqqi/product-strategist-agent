# Q3: does performance_ads pay back? LTV (12 months, M1 retention based) vs CAC ~650 RUB.
# unit: RUB; period: 2026-05..2026-09 cohorts, projected to 12 months (forecast, not fact);
# gaps: 2026-10 retained_m1 unknown; M2/M3 gaps for recent months;
# denominator: LTV per paying family from the ads cohort; price 299 RUB/month in-app;
# definition: about sheet (mrr 299 app / 249 operator); ads use in-app price 299 (best case).
# ASSUMPTION we must state: after M3 we assume the monthly survival stays at the M3 ratio
# (the data has no M4+), so LTV is an upper-ish estimate. CAC = 650 RUB (S002).
from strat.analysis import load, figure, share

t = load("S001", "cohorts")
months = ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
price = 299  # RUB/month, in-app

for m in months:
    n = t.value("new_paying", {"month": m, "channel": "performance_ads"})
    m1 = t.value("retained_m1", {"month": m, "channel": "performance_ads"})
    if n is None or m1 is None:
        continue
    m1_ratio = m1 / n
    # crude LTV: month1 fully paid, then retention ~ m1_ratio held flat after (assumption)
    # expected paid months ~ 1 + (m1_ratio) + (m1_ratio^2) + ... capped at 12
    ltv = price * sum(m1_ratio ** k for k in range(12))
    figure(f"ads_ltv_est_{m}", ltv, "RUB", m)
    share(figure(f"ads_ltv_{m}", ltv, "RUB", m),
          figure(f"ads_cac_{m}", 650, "RUB", m),
          f"ads_ltv_over_cac_{m}")

# compare with an organic cohort (m1 ~0.89) for contrast, same formula
n = t.value("new_paying", {"month": "2026-05", "channel": "organic"})
m1 = t.value("retained_m1", {"month": "2026-05", "channel": "organic"})
if n and m1:
    r = m1 / n
    ltv = price * sum(r ** k for k in range(12))
    figure("organic_ltv_est_2026-05", ltv, "RUB", "2026-05")
    share(figure("organic_ltv_2026-05", ltv, "RUB", "2026-05"),
          figure("organic_cac_2026-05", 200, "RUB", "2026-05"),
          "organic_ltv_over_cac_2026-05")
