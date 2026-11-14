"""Convert material files into plain-text snapshots with stable locations.

Each format writes block headers a claim's `where` can point to:
  xlsx, csv  ->  "## sheet: <name>"      where: "<sheet>!A1:C9"
  docx       ->  "## <heading>" lines    where: heading text or "paragraph N"
  pptx       ->  "## slide N"            where: "slide N"
  pdf        ->  "## page N"             where: "page N"
  html       ->  page text               where: free text (section or heading)
"""

from __future__ import annotations

import csv
import io
from html.parser import HTMLParser
from pathlib import Path

from strat.core import UNAVAILABLE, StratError

TEXT_SUFFIXES = {".md", ".txt"}
HTML_SUFFIXES = {".html", ".htm"}


def fmt_of(path: Path) -> str:
    """The format name stored in the source index."""
    suffix = path.suffix.lower()
    if suffix in HTML_SUFFIXES:
        return "html"
    if suffix in TEXT_SUFFIXES:
        return "text"
    return suffix.lstrip(".")


def convert(path: str) -> str:
    """Return the snapshot text of a material file."""
    p = Path(path)
    fmt = fmt_of(p)
    if fmt == "text":
        return p.read_text(encoding="utf-8", errors="replace")
    if fmt == "html":
        title, text = html_to_text(p.read_text(encoding="utf-8", errors="replace"))
        return (f"# {title}\n\n" if title else "") + text
    handler = {"xlsx": xlsx_to_text, "xlsm": xlsx_to_text, "csv": csv_to_text,
               "docx": docx_to_text, "pptx": pptx_to_text, "pdf": pdf_to_text}.get(fmt)
    if handler is None:
        raise StratError(f"{p.name}: format .{fmt} is not supported; supported: xlsx, csv, docx, "
                         "pptx, pdf, html, md, txt. Images are read by the agent directly.",
                         UNAVAILABLE)
    try:
        return handler(p)
    except StratError:
        raise
    except ImportError as exc:
        raise StratError(f"{p.name}: missing library ({exc.name}); run bin/strat doctor",
                         UNAVAILABLE) from None
    except Exception as exc:  # a malformed file: report it, never a traceback
        raise StratError(f"could not read {p.name}: {type(exc).__name__}: {exc}") from None


# --- tables -----------------------------------------------------------------------------------

def column_letter(n: int) -> str:
    """1 -> A, 27 -> AA."""
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def _cell(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def sheet_block(name: str, rows: list[list[str]]) -> str:
    """One CSV block with the header row, row count and empty cells per column."""
    while rows and not any(c.strip() for c in rows[-1]):
        rows.pop()
    width = max((len(r) for r in rows), default=0)
    rows = [r + [""] * (width - len(r)) for r in rows]
    empty = [sum(1 for r in rows[1:] if not r[c].strip()) for c in range(width)]
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    data_rows = max(len(rows) - 1, 0)
    return (f"## sheet: {name}\n"
            f"rows: {len(rows)} (header + {data_rows}), columns: {width}\n"
            "empty cells: " + ", ".join(f"{column_letter(i + 1)} {e}" for i, e in enumerate(empty))
            + f"\n```csv\n{buf.getvalue()}```\n")


def xlsx_to_text(path: Path) -> str:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    blocks = []
    for ws in wb.worksheets:
        rows = [[_cell(v) for v in row] for row in ws.iter_rows(min_row=1, min_col=1,
                                                                 values_only=True)]
        blocks.append(sheet_block(ws.title, rows))
    wb.close()
    return f"# {path.name}\n\nFormulas are shown as their last saved values. Charts are not " \
           "included.\n\n" + "\n".join(blocks)


def csv_to_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1251"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t") if text.strip() else csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    return f"# {path.name}\n\n" + sheet_block(path.stem, rows)


# --- documents --------------------------------------------------------------------------------

def _heading_level(style_name: str) -> int | None:
    name = (style_name or "").lower()
    if name == "title":
        return 1
    if name.startswith("heading"):
        digits = "".join(ch for ch in name if ch.isdigit())
        return int(digits) if digits else 1
    return None


def docx_to_text(path: Path) -> str:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(path)
    lines, n_par = [f"# {path.name}", ""], 0
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para = Paragraph(child, doc)
            text = " ".join(para.text.split())
            if not text:
                continue
            level = _heading_level(para.style.name if para.style is not None else "")
            if level:
                lines += ["", "#" * (level + 1) + " " + text, ""]
            else:
                n_par += 1
                lines.append(f"[p{n_par}] {text}")
        elif tag == "tbl":
            for row in Table(child, doc).rows:
                cells = [" ".join(c.text.split()) for c in row.cells]
                lines.append("| " + " | ".join(cells) + " |")
            lines.append("")
    lines.append("")
    lines.append("Pictures and charts inside the document are not in this text.")
    return "\n".join(lines) + "\n"


def pptx_to_text(path: Path) -> str:
    from pptx import Presentation

    prs = Presentation(path)
    lines = [f"# {path.name}", ""]
    for i, slide in enumerate(prs.slides, 1):
        lines.append(f"## slide {i}")
        title_shape = slide.shapes.title
        title_id = title_shape.shape_id if title_shape is not None else None
        if title_shape is not None and title_shape.text.strip():
            lines.append("title: " + " ".join(title_shape.text.split()))
        for shape in slide.shapes:
            if shape.shape_id == title_id:
                continue
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    text = " ".join("".join(r.text for r in para.runs).split())
                    if text:
                        lines.append(text)
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    lines.append("| " + " | ".join(" ".join(c.text.split()) for c in row.cells)
                                 + " |")
            if shape.shape_type == 13:  # picture
                lines.append("[picture: not in this text; read the slide as an image if it "
                             "matters]")
        if slide.has_notes_slide:
            notes = " ".join(slide.notes_slide.notes_text_frame.text.split())
            if notes:
                lines.append("notes: " + notes)
        lines.append("")
    return "\n".join(lines)


def pdf_to_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    lines = [f"# {path.name}", ""]
    for i, page in enumerate(reader.pages, 1):
        lines.append(f"## page {i}")
        text = (page.extract_text() or "").strip()
        lines.append(text if text else "[no text layer: read this page as an image]")
        lines.append("")
    return "\n".join(lines)


# --- html ---------------------------------------------------------------------------------------

_SKIP = {"script", "style", "noscript", "template", "svg", "head"}
_BLOCK = {"p", "div", "section", "article", "main", "header", "footer", "nav", "aside", "li",
          "ul", "ol", "table", "tr", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
          "blockquote", "pre", "dd", "dt", "figcaption", "form", "label", "option"}


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        elif tag in _SKIP:
            self._skip += 1
        elif tag in _BLOCK:
            self.parts.append("\n")
            if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                self.parts.append("#" * int(tag[1]) + " ")
        elif tag in {"td", "th"}:
            self.parts.append(" | ")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag in _SKIP:
            self._skip = max(self._skip - 1, 0)
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def html_to_text(raw: str) -> tuple[str, str]:
    """Visible text of a page, scripts and styles dropped, one block per line."""
    parser = _Text()
    parser.feed(raw)
    lines = []
    for line in "".join(parser.parts).splitlines():
        line = " ".join(line.split())
        if line:
            lines.append(line)
    return " ".join(parser.title.split()), "\n".join(lines) + "\n"
