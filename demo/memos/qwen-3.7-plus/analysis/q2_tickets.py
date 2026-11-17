# Q2: what the leavers write, by channel and by theme.
# unit: tickets (count) and share of channel tickets in %; period: 2026-02..2026-10;
# gaps: none (all 5 columns complete); denominator: tickets of the channel;
# definition: tickets.csv has no "reason to leave" field, themes are read from `subject`.
import re
from collections import Counter, defaultdict

from strat.analysis import figure, load

t = load("materials/support-tickets.csv", "support-tickets")

THEMES = [
    ("ads_mismatch", r"реклам|без установки|не тот, что в рекламе|согласие ребёнка"),
    ("no_number_lookup", r"по номеру"),
    ("companion_app", r"второе приложение|приложение и удалил|устанавливать"),
    ("accuracy", r"точность|район"),
    ("other_operator", r"другого оператора"),
    ("refund", r"вернуть деньги|отмените подписку|не работает по номеру"),
    ("tech_quality", r"батарея|в фоне|с опозданием|не обновляется"),
]


def theme(subject):
    for name, pat in THEMES:
        if re.search(pat, subject, re.I):
            return name
    return "other"


by_channel = Counter()
by_theme = defaultdict(Counter)
for r in t.rows:
    by_channel[r["channel"]] += 1
    by_theme[r["channel"]][theme(r["subject"])] += 1

for ch, n in sorted(by_channel.items()):
    figure(f"tickets_{ch}_total", n, "tickets", "2026-02..2026-10")

ads = by_channel["performance_ads"]
for name, _ in THEMES:
    figure(f"ads_tickets_{name}", by_theme["performance_ads"][name], "tickets", "2026-02..2026-10")
    if ads:
        figure(f"ads_tickets_{name}_share", round(by_theme["performance_ads"][name] / ads * 100, 1),
               "%", "2026-02..2026-10")

o = by_channel["organic"] or 1
figure("organic_tickets_companion_app_share",
       round(by_theme["organic"]["companion_app"] / o * 100, 1), "%", "2026-02..2026-10")
figure("organic_tickets_mismatch_share",
       round(by_theme["organic"]["ads_mismatch"] / o * 100, 1), "%", "2026-02..2026-10")

figure("ads_share_of_all_tickets", round(ads / sum(by_channel.values()) * 100, 1), "%",
       "2026-02..2026-10")
