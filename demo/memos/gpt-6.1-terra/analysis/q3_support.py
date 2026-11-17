# Q3: count support tickets about ad/product mismatch and companion-app expectations.
# unit: tickets; period: May-Oct 2026; gaps: none in ticket rows; denominator: all tickets in period;
# definition: support-tickets rows, each ticket counted once.
from strat.analysis import load, figure, share

t = load("S003", "support-tickets")
rows = [r for r in t.rows if "2026-05" <= r["month"] <= "2026-10"]
total = len(rows)
topics = ["В рекламе", "по номеру телефона", "приложение", "согласие ребёнка", "продукт не тот"]
matched = [r for r in rows if any(topic.lower() in r["subject"].lower() for topic in topics)]
figure("tickets_may_oct_total", total, "tickets", "2026-05..2026-10")
figure("tickets_mismatch_or_installation", len(matched), "tickets", "2026-05..2026-10")
share(figure("tickets_mismatch_or_installation_for_share", len(matched), "tickets", "2026-05..2026-10"), figure("tickets_may_oct_total_for_share", total, "tickets", "2026-05..2026-10"), "tickets_mismatch_share")
perf = [r for r in rows if r["channel"] == "performance_ads"]
figure("performance_ads_tickets", len(perf), "tickets", "2026-05..2026-10")
