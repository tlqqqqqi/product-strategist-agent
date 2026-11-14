"""Convert material files into plain-text snapshots with stable locations.

Each format writes block headers a claim's `where` can point to:
  xlsx, csv  ->  "## sheet: <name>"      where: "<sheet>!A1:C9"
  docx       ->  "## <heading>" lines    where: heading text or "paragraph N"
  pptx       ->  "## slide N"            where: "slide N"
  pdf        ->  "## page N"             where: "page N"
  html       ->  page text               where: free text (section or heading)
"""

from __future__ import annotations

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
    raise StratError(f"{p.name}: format .{fmt} is not supported", UNAVAILABLE)


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
