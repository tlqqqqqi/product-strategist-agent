"""Q1-Q3: разложение прироста оттока по каналам и окупаемость performance_ads.

Q1: какой вклад в рост оттока дают новые когорты (особенно performance_ads) против старых семей.
Q2: LTV/CAC канала performance_ads при наблюдаемых m1/m2/m3 и при органическом удержании.
Q3 (косвенно): тренд m1/m2 органических когорт до/после мая (эффект онбординга v2 вне канала).
"""

from strat.analysis import figure, load, number

CHURN_BASE = "2026-04"
CHURN_LAST = "2026-10"

monthly = load("S001", "monthly")
cohorts = load("S001", "cohorts")

# --- Q1: прирост оттока и его источники ---
f_base_churn = figure("base_churn_pct", monthly.value("churn_pct", {"month": CHURN_BASE}), "%",
                      "2026-04")
f_last_churn = figure("last_churn_pct", monthly.value("churn_pct", {"month": CHURN_LAST}), "%",
                      "2026-10")
figure("churn_delta_pp", f_last_churn.value - f_base_churn.value, "п.п.",
       "2026-04..2026-10")

months = [f"2026-{m:02d}" for m in range(5, 11)]


def cohort_rows(channel: str) -> dict:
    out = {}
    for r in cohorts.rows:
        if r.get("month") in months and r.get("channel") == channel:
            out[r["month"]] = r
    return out


# потери внутри первых месяцев жизни когорты: new_paying минус последнее наблюдаемое retained
def early_losses(rows: dict) -> tuple[int, int]:
    total_new, total_lost = 0, 0
    for r in rows.values():
        new = r.get("new_paying")
        if new in (None, ""):
            continue
        new = number(new)
        total_new += new
        last = None
        for k in ("retained_m1", "retained_m2", "retained_m3"):
            if r.get(k) not in (None, ""):
                last = number(r[k])
        if last is not None:
            total_lost += new - last
    return total_new, total_lost


pa_new, pa_lost = early_losses(cohort_rows("performance_ads"))
org_new, org_lost = early_losses(cohort_rows("organic"))
ref_new, ref_lost = early_losses(cohort_rows("referral"))
opb_new, opb_lost = early_losses(cohort_rows("operator_bundle"))

figure("pa_new_families_may_oct", pa_new, "семей",
       "2026-05..2026-10")
figure("pa_early_losses", pa_lost, "семей",
       "2026-05..2026-10")
figure("other_channels_losses", org_lost + ref_lost + opb_lost, "семей",
       "2026-05..2026-10")
figure("pa_share_of_new", 100 * pa_new / (pa_new + org_new + ref_new + opb_new), "%",
       "2026-05..2026-10")
figure("pa_share_of_early_losses", 100 * pa_lost / (pa_lost + org_lost + ref_lost + opb_lost), "%",
       "2026-05..2026-10")

# майская когорта детально
pa5 = cohort_rows("performance_ads")["2026-05"]
org5 = cohort_rows("organic")["2026-05"]
figure("pa_m1_may_pct", 100 * number(pa5["retained_m1"]) / number(pa5["new_paying"]), "%",
       "2026-05")
figure("org_m1_may_pct", 100 * number(org5["retained_m1"]) / number(org5["new_paying"]), "%",
       "2026-05")
figure("pa_m3_may_pct", 100 * number(pa5["retained_m3"]) / number(pa5["new_paying"]), "%",
       "2026-05..2026-08")
figure("org_m3_may_pct", 100 * number(org5["retained_m3"]) / number(org5["new_paying"]), "%",
       "2026-05..2026-08")

# органические когорты до и после мая (Q3 косвенно: эффект v2 вне канала)
pre = [r for r in cohorts.rows if r.get("channel") == "organic" and r.get("month") < "2026-05"]
post = [r for r in cohorts.rows if r.get("channel") == "organic" and r.get("month") >= "2026-05"]
pre_m1 = [100 * number(r["retained_m1"]) / number(r["new_paying"]) for r in pre if r.get("retained_m1") not in (None, "")]
post_m1 = [100 * number(r["retained_m1"]) / number(r["new_paying"]) for r in post if r.get("retained_m1") not in (None, "")]
figure("organic_m1_pre_v2_avg", sum(pre_m1) / len(pre_m1), "%",
       "2025-11..2026-04")
figure("organic_m1_post_v2_avg", sum(post_m1) / len(post_m1), "%",
       "2026-05..2026-08")
pre_m2 = [100 * number(r["retained_m2"]) / number(r["new_paying"]) for r in pre if r.get("retained_m2") not in (None, "")]
post_m2 = [100 * number(r["retained_m2"]) / number(r["new_paying"]) for r in post if r.get("retained_m2") not in (None, "")]
figure("organic_m2_pre_v2_avg", sum(pre_m2) / len(pre_m2), "%",
       "2025-11..2026-03")
figure("organic_m2_post_v2_avg", sum(post_m2) / len(post_m2), "%",
       "2026-05..2026-07")

# --- Q2: окупаемость performance_ads ---
PRICE = 299
CAC_PA = 650
CAC_ORG = 200  # середина диапазона 120-300₽ из product.docx [S002]

f_ltv_pa = figure("ltv_pa_4pay_rub", PRICE * (1 + number(pa5["retained_m1"]) / number(pa5["new_paying"])
                                              + number(pa5["retained_m2"]) / number(pa5["new_paying"])
                                              + number(pa5["retained_m3"]) / number(pa5["new_paying"])), "₽",
                  "2026-05..2026-08")
figure("cac_payback_pa", f_ltv_pa.value / CAC_PA, "x",
       "2026-05..2026-08")
figure("pa_margin_month1_per_family", PRICE - CAC_PA, "₽",
       "2026-05")
figure("pa_margin_4pay_per_family", f_ltv_pa.value - CAC_PA, "₽",
       "2026-05..2026-08")

f_ltv_org = figure("ltv_org_4pay_rub", PRICE * (1 + number(org5["retained_m1"]) / number(org5["new_paying"])
                                                + number(org5["retained_m2"]) / number(org5["new_paying"])
                                                + number(org5["retained_m3"]) / number(org5["new_paying"])), "₽",
                   "2026-05..2026-08")
figure("cac_payback_org", f_ltv_org.value / CAC_ORG, "x",
       "2026-05..2026-08")
figure("org_margin_4pay_per_family", f_ltv_org.value - CAC_ORG, "₽",
       "2026-05..2026-08")

if __name__ == "__main__":
    pass
