"""Regenerate the binary fixtures of the sample case. All data is invented.

Run: .venv/bin/python tests/fixtures/make_sample_case.py
"""

from pathlib import Path

import openpyxl
from docx import Document

HERE = Path(__file__).resolve().parent
MATERIALS = HERE / "sample-case" / "materials"


def metrics_xlsx(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "monthly"
    ws.append(["month", "paying_users", "churn_pct", "arpu_rub"])
    for row in [
        ["2026-05", 41200, 4.1, 287],
        ["2026-06", 42900, 4.0, 288],
        ["2026-07", 44100, 4.3, 289],
        ["2026-08", 44800, 5.9, 318],
        ["2026-09", 43600, 6.6, 331],
        ["2026-10", 42300, 6.8, 334],
    ]:
        ws.append(row)
    cohorts = wb.create_sheet("cohorts")
    cohorts.append(["channel", "joined_2026_05", "churn_month3_pct", "promo"])
    for row in [
        ["promo_3_months_free", 9800, 21.4, "yes"],
        ["organic", 18200, 3.2, "no"],
        ["partner_bank", 6100, 4.0, "no"],
        ["paid_ads", 7100, None, "no"],
    ]:
        cohorts.append(row)
    note = wb.create_sheet("about")
    note.append(["ВЫМЫШЛЕННЫЕ ДАННЫЕ для тестов и примера. Продукт и цифры придуманы."])
    wb.save(path)


def product_docx(path: Path) -> None:
    doc = Document()
    doc.add_heading("Семейное облако: описание продукта", level=1)
    doc.add_paragraph("ВЫМЫШЛЕННЫЙ ПРОДУКТ. Документ создан для теста и примера.")
    doc.add_heading("О продукте", level=2)
    doc.add_paragraph(
        "«Семейное облако» — подписка на общее хранилище фото и документов для семьи "
        "до 6 человек, 2 ТБ."
    )
    doc.add_paragraph("Цена тарифа «Семья» с 1 августа 2026 года — 349 ₽ в месяц (было 299 ₽).")
    doc.add_paragraph(
        "В мае 2026 года запущена акция «3 месяца бесплатно» для новых пользователей; "
        "первые списания по ней прошли в августе."
    )
    doc.add_heading("Опрос ушедших пользователей (сентябрь 2026, n=212)", level=2)
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Причина ухода"
    table.rows[0].cells[1].text = "Доля ответов"
    for reason, share in [
        ("Закончился бесплатный период", "38%"),
        ("Дорого", "27%"),
        ("Не пользуюсь", "21%"),
        ("Другое", "14%"),
    ]:
        cells = table.add_row().cells
        cells[0].text = reason
        cells[1].text = share
    doc.save(path)


if __name__ == "__main__":
    MATERIALS.mkdir(parents=True, exist_ok=True)
    metrics_xlsx(MATERIALS / "metrics.xlsx")
    product_docx(MATERIALS / "product.docx")
    print("written:", *sorted(p.name for p in MATERIALS.iterdir()))
