"""Generate the invented materials of the demo case "Семейный компас".

Everything here is invented for the demo. The numbers come from one small cohort model, so the
monthly table, the cohort table and the totals agree with each other by construction.

Run from the repository root:
    .venv/bin/python demo/family-app/make_materials.py [--out DIR]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXED_TIME = dt.datetime(2026, 11, 1, 12, 0, 0)
NOTE = "Вымышленные данные для демонстрации. Не данные какой-либо реальной компании."

MONTHS = ["2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04",
          "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
LAUNCH = "2026-05"  # onboarding v2 for all new users and the first month of performance_ads
GAP = ("operator_bundle", "2026-06")  # the partner's export for this cohort was not received

CHANNELS = ["organic", "referral", "operator_bundle", "performance_ads"]
PRICE = {"organic": 299, "referral": 299, "operator_bundle": 249, "performance_ads": 299}

# Paying families at the end of 2025-10 by channel, and their monthly retention afterwards.
LEGACY = {"organic": 16000, "referral": 6000, "operator_bundle": 9000}
LEGACY_KEEP = {"organic": 0.958, "referral": 0.968, "operator_bundle": 0.976}

NEW = {
    "organic":         [1480, 1390, 1620, 1510, 1550, 1490, 1530, 1470, 1440, 1520, 1600, 1560],
    "referral":        [510, 470, 540, 500, 520, 490, 505, 480, 470, 515, 530, 525],
    "operator_bundle": [880, 840, 910, 900, 930, 890, 920, 905, 880, 940, 960, 950],
    "performance_ads": [0, 0, 0, 0, 0, 0, 2400, 2780, 3050, 3210, 3120, 3300],
}

# Share of a cohort still paying 1, 2, 3 months after the first payment; after that the
# cohort keeps `tail` of its payers each month. v2 is the curve under the new onboarding.
CURVES = {
    "organic":         {"v1": (0.900, 0.840, 0.800), "v2": (0.890, 0.830, 0.792), "tail": 0.966},
    "referral":        {"v1": (0.920, 0.870, 0.840), "v2": (0.915, 0.866, 0.836), "tail": 0.975},
    "operator_bundle": {"v1": (0.940, 0.900, 0.870), "v2": (0.940, 0.900, 0.870), "tail": 0.981},
    "performance_ads": {"v1": (0.520, 0.340, 0.270), "v2": (0.520, 0.340, 0.270), "tail": 0.950},
}
# Small month-to-month noise on M1 (percentage points), so the table does not look drawn.
NOISE = [0.4, -0.3, 0.2, -0.5, 0.3, 0.0, -0.2, 0.4, -0.4, 0.1, -0.1, 0.3]


def survival(channel: str, cohort_idx: int, k: int) -> float:
    curve = CURVES[channel]["v2" if MONTHS[cohort_idx] >= LAUNCH else "v1"]
    shift = NOISE[(cohort_idx + CHANNELS.index(channel)) % len(NOISE)] / 100
    m = [curve[0] + shift, curve[1] + shift, curve[2] + shift]
    if k == 0:
        return 1.0
    if k <= 3:
        return m[k - 1]
    return m[2] * CURVES[channel]["tail"] ** (k - 3)


def model():
    """Paying families at the end of each month per channel, and cohort retention counts."""
    n = len(MONTHS)
    end = {ch: [0] * n for ch in CHANNELS}
    retained = {}  # (channel, cohort idx) -> [count at end of month a, a+1, ...]
    for ch in CHANNELS:
        for m in range(n):
            legacy = round(LEGACY.get(ch, 0) * LEGACY_KEEP.get(ch, 1) ** (m + 1))
            end[ch][m] += legacy
        for a in range(n):
            new = NEW[ch][a]
            if not new:
                continue
            counts = [round(new * survival(ch, a, k)) for k in range(n - a)]
            retained[(ch, a)] = counts
            for k, c in enumerate(counts):
                end[ch][a + k] += c
    return end, retained


def monthly_rows(end, retained):
    start = sum(LEGACY.values())
    rows = []
    for m, month in enumerate(MONTHS):
        new = sum(NEW[ch][m] for ch in CHANNELS)
        total_end = sum(end[ch][m] for ch in CHANNELS)
        churned = start + new - total_end
        mrr = sum(end[ch][m] * PRICE[ch] for ch in CHANNELS)
        if m + 1 < len(MONTHS):
            kept = sum(retained[(ch, m)][1] for ch in CHANNELS if (ch, m) in retained)
            m1 = round(kept / new * 100, 1)
        else:
            m1 = None
        rows.append([month, start, new, churned, total_end, round(churned / start * 100, 1),
                     mrr, "v2" if month >= LAUNCH else "v1", m1])
        start = total_end
    return rows


def cohort_rows(retained):
    rows = []
    for a, month in enumerate(MONTHS):
        for ch in CHANNELS:
            if (ch, a) not in retained:
                continue
            counts = retained[(ch, a)]
            known = [counts[k] if k < len(counts) else None for k in (1, 2, 3)]
            if (ch, month) == GAP:
                known = [None, None, None]
            rows.append([month, ch, NEW[ch][a], *known])
    return rows


def write_xlsx(path: Path, monthly, cohorts):
    import openpyxl
    from openpyxl.styles import Font

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "monthly"
    ws.append(["month", "active_paying_start", "new_paying", "churned", "active_paying_end",
               "churn_pct", "mrr_rub", "onboarding_version", "new_retained_m1_pct"])
    for r in monthly:
        ws.append(r)
    ws2 = wb.create_sheet("cohorts")
    ws2.append(["month", "channel", "new_paying", "retained_m1", "retained_m2", "retained_m3"])
    for r in cohorts:
        ws2.append(r)
    ws3 = wb.create_sheet("about")
    about = [
        ["Поле", "Значение"],
        ["Данные", NOTE],
        ["Продукт", "«Семейный компас», вымышленное приложение семейной геолокации"],
        ["Единица", "платящая семья (одна подписка на семью)"],
        ["active_paying_start", "платящих семей на начало месяца (= конец прошлого месяца)"],
        ["new_paying", "семей, впервые оплативших подписку в этом месяце"],
        ["churned", "семей, не продливших подписку в этом месяце"],
        ["churn_pct", "churned / active_paying_start * 100, округлено до 0,1"],
        ["mrr_rub", "сумма месячных платежей на конец месяца, руб.: 299 в приложении, "
                    "249 через оператора-партнёра"],
        ["onboarding_version", "версия онбординга, которую видели новые пользователи месяца"],
        ["new_retained_m1_pct", "доля семей из new_paying этого месяца, оплативших и следующий "
                                "месяц; за последний месяц ещё неизвестна"],
        ["cohorts: month", "месяц первой оплаты"],
        ["cohorts: retained_mN", "сколько семей из когорты платили через N месяцев после "
                                 "первой оплаты; пусто, если месяц ещё не наступил"],
        ["Пропуск", "operator_bundle, когорта 2026-06: выгрузка от оператора-партнёра не "
                    "получена, удержание неизвестно (в monthly эта когорта учтена по биллингу)"],
    ]
    for r in about:
        ws3.append(r)
    for w in (ws, ws2, ws3):
        for cell in w[1]:
            cell.font = Font(bold=True)
    wb.properties.creator = "demo generator"
    wb.properties.created = FIXED_TIME
    wb.properties.modified = FIXED_TIME
    wb.save(path)


def write_docx(path: Path):
    from docx import Document

    d = Document()
    d.core_properties.author = "demo generator"
    d.core_properties.created = FIXED_TIME
    d.core_properties.modified = FIXED_TIME
    d.add_heading("«Семейный компас»: описание продукта", 0)
    d.add_paragraph(NOTE + " Название, цифры, тарифы и рекламные тексты придуманы.")
    d.add_heading("Что делает продукт", 1)
    d.add_paragraph(
        "Подписка для семьи: родители видят на карте, где находятся дети и пожилые "
        "родственники, получают уведомления о приходе в школу и домой, а ребёнок может нажать "
        "кнопку SOS. Для работы на телефон ребёнка ставится приложение-компаньон, ребёнок "
        "видит, что геолокация включена, и может это проверить в любой момент.")
    d.add_paragraph(
        "Без приложения-компаньона местоположение можно получить только для номеров "
        "оператора-партнёра: по сигналу сети, с точностью до нескольких сотен метров и после "
        "SMS-согласия владельца номера.")
    d.add_heading("Тарифы", 1)
    t = d.add_table(rows=1, cols=3)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text, t.rows[0].cells[2].text = (
        "Тариф", "Цена", "Где покупают")
    for row in (("«Семья» в приложении", "299 ₽ в месяц", "App Store, Google Play, сайт"),
                ("«Семья» у оператора-партнёра", "249 ₽ в месяц",
                 "опция в тарифе мобильной связи, списание со счёта телефона")):
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = v
    d.add_paragraph("Пробного периода нет; цены не менялись с 2025 года.")
    d.add_heading("Каналы привлечения", 1)
    for line in (
        "organic - магазины приложений и поиск.",
        "referral - приглашение от другой семьи, обе получают месяц в подарок после второй "
        "оплаты приглашённого.",
        "operator_bundle - опция у оператора-партнёра, подключается в его приложении.",
        "performance_ads - платная реклама в соцсетях и видеосервисах, запущена в мае 2026 года.",
    ):
        d.add_paragraph(line, style="List Bullet")
    d.add_heading("Новый онбординг (v2)", 1)
    d.add_paragraph(
        "Выпущен 30 апреля 2026 года; со 2 мая его видят все новые пользователи. Сократили путь "
        "с 7 экранов до 4, чтобы быстрее доводить до оплаты. Экран, объясняющий, что на телефон "
        "ребёнка нужно поставить приложение-компаньон и дать разрешения, перенесли после оплаты.")
    d.add_heading("Реклама в канале performance_ads", 1)
    d.add_paragraph(
        "Основной рекламный текст с мая 2026 года: «Узнайте, где ваш ребёнок, просто по номеру "
        "телефона. Ничего не нужно устанавливать на его телефон». Стоимость привлечения "
        "платящей семьи в канале - около 650 ₽, в остальных каналах - от 120 до 300 ₽.")
    d.add_heading("Что видит команда", 1)
    d.add_paragraph(
        "С июня доля неоплативших второй месяц заметно выросла. Команда онбординга считает, "
        "что виноват новый короткий онбординг, и предлагает вернуть прежний.")
    d.save(path)


TICKETS = [
    # month, channel, subject
    ("2026-02", "organic", "Не обновляется местоположение ребёнка в фоне"),
    ("2026-02", "operator_bundle", "Как отключить опцию у оператора"),
    ("2026-03", "referral", "Не пришёл бонусный месяц за приглашение"),
    ("2026-03", "organic", "Быстро садится батарея на телефоне ребёнка"),
    ("2026-03", "organic", "Как добавить второго родителя"),
    ("2026-04", "operator_bundle", "Списали за опцию дважды"),
    ("2026-04", "organic", "Уведомление о приходе в школу приходит с опозданием"),
    ("2026-05", "performance_ads", "В рекламе было без установки, а просят ставить приложение"),
    ("2026-05", "performance_ads", "Не могу найти ребёнка по номеру телефона"),
    ("2026-05", "organic", "Не понял после оплаты, что нужно ставить второе приложение"),
    ("2026-05", "performance_ads", "Прошу вернуть деньги: не работает по номеру"),
    ("2026-05", "referral", "Как добавить бабушку без смартфона"),
    ("2026-06", "performance_ads", "Ребёнок у другого оператора, на карте его нет"),
    ("2026-06", "performance_ads", "Ребёнок увидел приложение и удалил его"),
    ("2026-06", "performance_ads", "Почему нужно согласие ребёнка, в рекламе этого не было"),
    ("2026-06", "organic", "Не обновляется местоположение ребёнка в фоне"),
    ("2026-06", "performance_ads", "Отмените подписку, продукт не тот, что в рекламе"),
    ("2026-07", "performance_ads", "Не могу найти ребёнка по номеру телефона"),
    ("2026-07", "performance_ads", "Хочу видеть место скрытно, без приложения у ребёнка"),
    ("2026-07", "organic", "Не понял после оплаты, что нужно ставить второе приложение"),
    ("2026-07", "operator_bundle", "Как отключить опцию у оператора"),
    ("2026-07", "performance_ads", "Прошу вернуть деньги: не работает по номеру"),
    ("2026-08", "performance_ads", "Точность по сети - целый район, это бесполезно"),
    ("2026-08", "performance_ads", "В рекламе было без установки, а просят ставить приложение"),
    ("2026-08", "referral", "Не пришёл бонусный месяц за приглашение"),
    ("2026-08", "performance_ads", "Ребёнок у другого оператора, на карте его нет"),
    ("2026-09", "performance_ads", "Отмените подписку, продукт не тот, что в рекламе"),
    ("2026-09", "organic", "Быстро садится батарея на телефоне ребёнка"),
    ("2026-09", "performance_ads", "Почему нужно согласие ребёнка, в рекламе этого не было"),
    ("2026-10", "performance_ads", "Не могу найти ребёнка по номеру телефона"),
    ("2026-10", "operator_bundle", "Уведомление SOS пришло без адреса"),
    ("2026-10", "performance_ads", "Прошу вернуть деньги: не работает по номеру"),
]


def write_tickets(path: Path):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["ticket", "month", "channel", "subject", "data_note"])
        for i, (month, ch, subject) in enumerate(TICKETS, 1):
            w.writerow([f"T-{i:04d}", month, ch, subject, "вымышленные данные для демонстрации"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(HERE / "materials"))
    out = Path(ap.parse_args(argv).out)
    out.mkdir(parents=True, exist_ok=True)
    end, retained = model()
    write_xlsx(out / "metrics.xlsx", monthly_rows(end, retained), cohort_rows(retained))
    write_docx(out / "product.docx")
    write_tickets(out / "support-tickets.csv")
    print(f"wrote materials to {out}")


if __name__ == "__main__":
    main()
