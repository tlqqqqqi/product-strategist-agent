# Q1/Q2: compare first-month retention by acquisition channel before and after May 2026.
# unit: families and percent; period: cohort month; gaps: retained_m1 has one gap in June operator_bundle;
# denominator: new_paying families in each cohort/channel; definition: cohorts.retained_m1 / new_paying.
from strat.analysis import load, figure, diff, pct_change

t = load("S001", "cohorts")

def rate(month, channel):
    rows = [r for r in t.rows if r["month"] == month and r["channel"] == channel]
    if not rows:
        print(f"GAP cohort {month} {channel}")
        return None
    row = rows[0]
    if not row["retained_m1"]:
        print(f"GAP retained_m1 {month} {channel}")
        return None
    return 100 * float(row["retained_m1"]) / float(row["new_paying"])

for channel in ["organic", "referral", "operator_bundle", "performance_ads"]:
    april = rate("2026-04", channel)
    may = rate("2026-05", channel)
    if april is not None and may is not None:
        a = figure(f"{channel}_apr_m1", april, "%", "2026-04")
        m = figure(f"{channel}_may_m1", may, "%", "2026-05")
        diff(m, a, f"{channel}_may_minus_apr_pp")
        pct_change(m, a, f"{channel}_relative_change_pct")

for month in ["2026-05", "2026-06", "2026-07"]:
    rows = [r for r in t.rows if r["month"] == month]
    total_new = sum(float(r["new_paying"]) for r in rows)
    total_retained = sum(float(r["retained_m1"]) for r in rows if r["retained_m1"])
    missing = [r["channel"] for r in rows if not r["retained_m1"]]
    if missing:
        print(f"GAP retained_m1 {month} channels={','.join(missing)}")
    figure(f"{month}_cohort_m1_observed", 100 * total_retained / total_new, "%", month)
