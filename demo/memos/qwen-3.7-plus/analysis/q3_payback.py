# Q3: does the ads channel pay back its acquisition cost.
# unit: RUB per family and months; period: cohorts 2026-05..2026-09 (first payment month);
# gaps: retained_m3 unknown for August 2026 (not yet reached), retained_m1 missing for
#   operator_bundle 2026-06 (not used here);
# denominator: one paying family; definitions: metrics.xlsx `about` (MRR 299 RUB in-app,
#   249 RUB via operator), product.docx p10 (CAC ~650 RUB for ads, 120-300 RUB elsewhere).
# Simplification, stated in the claim text: paid months are counted up to the last known
# cohort month (2026-10), so a family acquired in May 2026 counts at most ~5 paid months and
# the lifetime is a floor, not the final value. Other channels are compared on the same floor.
from strat.analysis import figure, load

cohorts = load("materials/metrics.xlsx", "cohorts")

PRICE = 299       # RUB per month, in-app subscription (product.docx p3)
ADS_CAC = 650     # RUB, product.docx p10
OTHER_CAC = 200   # RUB, midpoint of the 120-300 range, product.docx p10
LAST_MONTH = (2026, 10)


def months_seen(month):
    y, m = int(month[:4]), int(month[5:])
    return (LAST_MONTH[0] - y) * 12 + (LAST_MONTH[1] - m) + 1


def paid_months(month, retained, new):
    seen = months_seen(month)
    paid = new
    for n, r in enumerate(retained, start=1):
        if r is None or r == "":
            break
        if n <= seen - 1:
            paid += int(r)
    return paid


def run(prefix, channels, cac):
    total_paid = 0
    total_new = 0
    for r in cohorts.rows:
        if r["channel"] not in channels or r["month"] > "2026-09":
            continue
        new = int(r["new_paying"])
        paid = paid_months(r["month"], [r["retained_m1"], r["retained_m2"], r["retained_m3"]], new)
        total_paid += paid
        total_new += new
    lt = total_paid / total_new
    figure(f"{prefix}_paid_months_per_family_2026-05_2026-09", round(lt, 2), "months",
           "2026-05..2026-09")
    figure(f"{prefix}_revenue_per_family_2026-05_2026-09", round(lt * PRICE, 0), "RUB",
           "2026-05..2026-09")
    figure(f"{prefix}_cac_per_family", cac, "RUB", "2026-05..2026-09")
    figure(f"{prefix}_contribution_per_family_2026-05_2026-09", round(lt * PRICE - cac, 0), "RUB",
           "2026-05..2026-09")
    return lt


ads_lt = run("ads", ("performance_ads",), ADS_CAC)
other_lt = run("other", ("organic", "referral"), OTHER_CAC)
figure("ads_break_even_months", round(ADS_CAC / PRICE, 1), "months", "2026-05..2026-09")
figure("other_break_even_months", round(OTHER_CAC / PRICE, 1), "months", "2026-05..2026-09")
