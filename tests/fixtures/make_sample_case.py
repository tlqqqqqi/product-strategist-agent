"""Regenerate the binary fixtures of the sample case. All data is invented.

Run: .venv/bin/python tests/fixtures/make_sample_case.py
"""

from pathlib import Path

import openpyxl
from docx import Document
from pptx import Presentation
from pptx.util import Inches

HERE = Path(__file__).resolve().parent
MATERIALS = HERE / "sample-case" / "materials"
KINDS = HERE / "kinds"


def metrics_xlsx(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "monthly"
    ws.append(["month", "paying_users", "churn_pct", "arpu_rub"])
    for row in [
        ["2026-05", 41200, 4.1, 287],
        ["2026-06", 42900, 4.0, 288],
        ["2026-07", 44100, 4.3, 289],
        ["2026-08", 48300, 4.2, 318],
        ["2026-09", 46560, 6.6, 331],
        ["2026-10", 44790, 6.8, 334],
    ]:
        ws.append(row)
    cohorts = wb.create_sheet("cohorts")
    cohorts.append(["channel", "new_users_2026_05", "paid_users_2026_08", "paid_users_2026_10",
                    "promo"])
    for row in [
        ["promo_3_months_free", 9800, 4550, 1850, "yes"],
        ["organic", 1900, 1670, 1530, "no"],
        ["partner_bank", 700, 620, 570, "no"],
        ["paid_ads", 900, 790, None, "no"],
    ]:
        cohorts.append(row)
    note = wb.create_sheet("about")
    note.append(["ВЫМЫШЛЕННЫЕ ДАННЫЕ для тестов и примера. Продукт и цифры придуманы."])
    note.append(["column", "meaning"])
    for row in [
        ["monthly.paying_users", "Пользователи, с которых в этом месяце прошло списание. "
         "Пользователи акции входят сюда с первого списания (август 2026)."],
        ["monthly.churn_pct", "Доля платящих прошлого месяца, с которых в этом месяце списания "
         "не было. Пользователи акции, ни разу не заплатившие, сюда не входят."],
        ["monthly.arpu_rub", "Выручка месяца, делённая на paying_users, ₽."],
        ["cohorts.new_users_2026_05", "Новые пользователи, зарегистрированные в мае 2026, "
         "по каналу привлечения."],
        ["cohorts.paid_users_2026_08", "Из них: с кого прошло списание в августе 2026. Для акции "
         "это первое списание, уже по цене 349 ₽."],
        ["cohorts.paid_users_2026_10", "Из них: с кого прошло списание в октябре 2026. Пусто - "
         "данные канала ещё не выгружены."],
        ["cohorts.promo", "yes - канал с акцией «3 месяца бесплатно» (май-июль без оплаты)."],
    ]:
        note.append(row)
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


def table_csv(path: Path) -> None:
    path.write_text(
        "channel,trials,paid,conversion_pct\n"
        "organic,1200,312,26.0\n"
        "promo,3400,408,12.0\n"
        "partner_bank,800,,\n",
        encoding="utf-8",
    )


def deck_pptx(path: Path) -> None:
    prs = Presentation()
    s1 = prs.slides.add_slide(prs.slide_layouts[1])
    s1.shapes.title.text = "Итоги квартала"
    s1.placeholders[1].text = "Выручка выросла на 12% (данные команды продукта)"
    s1.notes_slide.notes_text_frame.text = "Цифра без учёта возвратов"
    s2 = prs.slides.add_slide(prs.slide_layouts[5])
    s2.shapes.title.text = "Каналы"
    rows = [("Канал", "Доля"), ("Промо", "41%"), ("Органика", "37%")]
    shape = s2.shapes.add_table(3, 2, Inches(1), Inches(2), Inches(6), Inches(1.5))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            shape.table.cell(r, c).text = value
    prs.save(path)


def report_pdf(path: Path) -> None:
    """A two-page PDF written by hand: page 1 has a text layer, page 2 has none."""
    text = b"BT /F1 12 Tf 72 720 Td (Churn in October was 6.8 percent.) Tj ET"
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 6 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(text), text),
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (i, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    path.write_bytes(bytes(out))


if __name__ == "__main__":
    KINDS.mkdir(parents=True, exist_ok=True)
    table_csv(KINDS / "trials.csv")
    deck_pptx(KINDS / "deck.pptx")
    report_pdf(KINDS / "report.pdf")
    MATERIALS.mkdir(parents=True, exist_ok=True)
    metrics_xlsx(MATERIALS / "metrics.xlsx")
    product_docx(MATERIALS / "product.docx")
    print("written:", *sorted(p.name for p in MATERIALS.iterdir()))
