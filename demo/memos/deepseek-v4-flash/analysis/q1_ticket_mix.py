# Q1: support-ticket mix by channel and theme (does the ads channel's churn match ad/product gap?)
# unit: tickets (count); period: 2026-02..2026-10 (closed history); gaps: none in this file;
# denominator: all 32 tickets; definition: support-tickets.csv columns channel, subject.
from strat.analysis import load, figure, share

t = load("S003", "support-tickets")
rows = t.rows

total = figure("tickets_total", len(rows), "tickets", "2026-02..2026-10")
for ch in ("performance_ads", "organic", "referral", "operator_bundle"):
    n = sum(1 for r in rows if r["channel"] == ch)
    share(figure(f"tickets_{ch}", n, "tickets", "2026-02..2026-10"), total, f"tickets_share_{ch}")

# ads tickets that are about the ad/product gap (install, number, consent, refund "not what advertised")
gap_keys = ("без установки", "по номеру", "согласие", "не тот, что в рекламе",
            "удалил", "точность", "скрытно")
ads_gap = [r for r in rows if r["channel"] == "performance_ads"
           and any(k in r["subject"] for k in gap_keys)]
figure("ads_gap_tickets", len(ads_gap), "tickets", "2026-02..2026-10")
share(figure("ads_gap_num", len(ads_gap), "tickets", "2026-02..2026-10"),
      figure("ads_all", sum(1 for r in rows if r["channel"] == "performance_ads"),
             "tickets", "2026-02..2026-10"),
      "ads_gap_share_of_ads")

# by month for organic "did not understand second app" theme
organic_app = [r for r in rows if r["channel"] == "organic" and "второе приложение" in r["subject"]]
figure("organic_app_confusion_tickets", len(organic_app), "tickets", "2026-02..2026-10")
