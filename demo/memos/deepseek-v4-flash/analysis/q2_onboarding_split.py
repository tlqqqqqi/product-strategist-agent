# Q2: did M1 retention inside non-ads channels change after onboarding v2 (May 2026)?
# unit: %; period: 2026-01..2026-09 (closed history); gaps: 2026-06 operator_bundle M1 empty;
# denominator: retained_m1/new_paying per channel per month; definition: cohorts sheet.
# test: mean M1 before v2 (2026-01..2026-04) vs after v2 (2026-05..2026-09), per channel.
from strat.analysis import load, figure, diff

t = load("S001", "cohorts")
before = ["2026-01", "2026-02", "2026-03", "2026-04"]
after = ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]

for ch in ("organic", "referral", "operator_bundle"):
    def mean_m1(months):
        vals = []
        for m in months:
            n = t.value("new_paying", {"month": m, "channel": ch})
            r = t.value("retained_m1", {"month": m, "channel": ch})
            if n and r is not None:
                vals.append(r / n * 100)
        return sum(vals) / len(vals) if vals else None
    b = mean_m1(before)
    a = mean_m1(after)
    if b is not None and a is not None:
        figure(f"m1_{ch}_before_v2", b, "%", "2026-01..2026-04")
        figure(f"m1_{ch}_after_v2", a, "%", "2026-05..2026-09")
        diff(figure(f"m1_{ch}_after", a, "%", "2026-05..2026-09"),
             figure(f"m1_{ch}_before", b, "%", "2026-01..2026-04"),
             f"m1_{ch}_change_pp")
