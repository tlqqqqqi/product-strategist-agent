"""memo.md to memo.html from the fixed template config/memo.html.

The memo is checked first with the gate's citation rules (strat/validate.py): a cited claim
that does not exist, is withdrawn or is stale fails with `<file>:<line>: <reason>` and no HTML
is written. Every claim id in the text becomes a link to a card with the claim's type, status,
text, source, `where` and quote; conclusions also link the claims they rest on. Non-fact types
carry a visible label next to the citation. Markdown is converted by a small stdlib converter
for the subset the templates use: headings, bullets, numbered lists, tables, paragraphs, bold,
inline code, links, `>` notes and fenced code. Everything from claims and sources is escaped.

The page follows DESIGN.md: a header with the title, the "## Решение" section as the decision
box and a metadata strip; citation chips that open a claim-card popover from JSON embedded in the
page (each chip stays a link to the card list at the bottom without JS); risk rows under
"## Риски..." tagged with the accepted objections. Fonts come from Google Fonts with a system
fallback; nothing else is loaded.

Memo blocks (strat/blocks.py) are drawn with fixed code: `tiles` as figure rows, `table` as HTML, `bars`,
`slope` and `funnel` as HTML rows whose bar width is a CSS percentage (text stays readable at
360 px), `line` as an inline SVG on a 4 px grid with its labels in HTML below. Each value links
to its claim card. If the case has `table.md`, its options-by-criteria table is shown under
"Таблица решения" with the option chosen at Gate 2 marked. Elements carry `data-types` with the
types of the claims they cite, for the claim-type filter at the top of the page.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

from strat import blocks, ledger, sources, validate
from strat.core import FAILED, StratError, case_path, emit, read_jsonl, root, today
from strat.state import load as load_state

TEMPLATE = "memo.html"
TYPE_LABEL = {"fact": "факт", "hypothesis": "гипотеза", "forecast": "прогноз",
              "assumption": "допущение", "gap": "пробел", "synthetic": "синтетические данные",
              "conclusion": "вывод"}
TYPE_NOTE = {
    "fact": "Факт: подтверждён цитатой из источника.",
    "hypothesis": "Гипотеза: предположение, которое ещё проверяется; это не факт.",
    "forecast": "Прогноз: оценка будущего, а не наблюдение.",
    "assumption": "Допущение: принято без проверки по источнику; если оно неверно, вывод может "
                  "измениться.",
    "gap": "Данных нет: это известное неизвестное, а не факт.",
    "synthetic": "Синтетические данные: получены от модели (например, модельного респондента), "
                 "а не от реальных людей; фактом не являются.",
    "conclusion": "Вывод: сделан из утверждений, на которые он опирается (см. ниже).",
}
_TOKEN = re.compile(r"\x00(\d+)\x00")
_LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE = re.compile(r"`([^`\n]+)`")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_ORDERED = re.compile(r"^\s*\d+[.)]\s+")


def esc(text) -> str:
    return html.escape(str(text or ""), quote=True)


def safe_href(url: str) -> str | None:
    """http(s) URLs and relative paths only; anything with another scheme is dropped."""
    url = (url or "").strip()
    if re.match(r"^https?://", url, re.I):
        return url
    if not url or ":" in url.split("/")[0] or url.startswith(("/", "\\", "~")):
        return None  # another scheme, or an absolute path that would leak the machine's layout
    return url


# --- inline -----------------------------------------------------------------------------------

SOFT = ("gap", "assumption", "hypothesis", "forecast", "synthetic")  # dashed citation chip


def cite_html(ids: list[str], claims: dict) -> str:
    """Citation chips: each a link to the claim's card on the page; the script opens it as a
    popover. Non-fact types carry their label inside the chip."""
    links = []
    for cid in ids:
        type_ = claims.get(cid, {}).get("type", "")
        soft = " as" if type_ in SOFT else ""
        tag = "" if type_ in ("", "fact") else f'<span class="tag">{TYPE_LABEL[type_]}</span>'
        links.append(f'<a class="cite t-{type_ or "unknown"}{soft}" href="#{cid}" '
                     f'data-c="{cid}">{cid}{tag}</a>')
    return '<span class="cites">' + " ".join(links) + "</span>"


def inline(text: str, claims: dict) -> str:
    """Escape, then render citations, code, links and bold."""
    saved: list[str] = []

    def keep(fragment: str) -> str:
        saved.append(fragment)
        return f"\x00{len(saved) - 1}\x00"

    out = esc(text)
    out = _CODE.sub(lambda m: keep(f"<code>{m.group(1)}</code>"), out)
    out = ledger.CITATION.sub(lambda m: keep(cite_html(ledger.cited_ids(m.group(0)), claims)), out)

    def link(m: re.Match) -> str:
        href = safe_href(html.unescape(m.group(2)))
        if href is None:
            return m.group(1)
        return keep(f'<a href="{esc(href)}">') + m.group(1) + keep("</a>")

    out = _LINK.sub(link, out)
    out = _BOLD.sub(r"<strong>\1</strong>", out)
    while _TOKEN.search(out):
        out = _TOKEN.sub(lambda m: saved[int(m.group(1))], out)
    return out


def types_attr(text: str, claims: dict) -> str:
    return types_of(ledger.cited_ids(text), claims)


def types_of(ids: list[str], claims: dict) -> str:
    found = sorted({claims[c]["type"] for c in ids if c in claims})
    return f' data-types="{" ".join(found)}"' if found else ""


# --- memo blocks ------------------------------------------------------------------------------

def g4(value: float) -> int:
    """Snap a coordinate to the 4 px grid."""
    return int(round(value / 4.0)) * 4


def sign_of(shown: str) -> str:
    """`neg` for a figure written with a minus, `pos` for one written with a plus."""
    first = shown.strip()[:1]
    return "neg" if first and first in blocks.MINUS else "pos" if first == "+" else ""


def _shown(text: str) -> str:
    """A leading hyphen or en dash is shown as a true minus sign."""
    text = text.strip()
    return "−" + text[1:] if text[:1] in ("-", "–") else text


def _unit(unit: str) -> str:
    if not unit:
        return ""
    gap = "" if unit.startswith("%") else " "
    return f'<span class="u">{gap}{esc(unit)}</span>'


def _value_link(row: blocks.Row, k: int, unit: str = "") -> str:
    target = row.ids[0] if row.ids else ""
    return f'<a class="v" href="#{target}">{esc(_shown(row.shown[k]))}</a>{_unit(unit)}'


def _value(row: blocks.Row, k: int, unit: str = "", tag: str = "span", extra: str = "") -> str:
    cls = " ".join(c for c in ("blk-v num", sign_of(row.shown[k]), extra) if c)
    return f'<{tag} class="{cls}">{_value_link(row, k, unit)}</{tag}>'


def _focal(block: blocks.Block, key) -> int | None:
    marked = [i for i, r in enumerate(block.rows) if r.focal]
    if marked:
        return marked[0]
    if key is None or not block.rows:
        return None
    return max(range(len(block.rows)), key=lambda i: key(block.rows[i]))


def _block_ids(block: blocks.Block) -> list[str]:
    ids: list[str] = []
    for r in block.rows:
        ids += [c for c in r.ids if c not in ids]
    return ids


def _caption(block: blocks.Block, claims: dict, cites: bool = True) -> str:
    unit = f'<span class="blk-unit">, {esc(block.unit)}</span>' if block.unit else ""
    chips = cite_html(_block_ids(block), claims) if cites else ""
    return (f'<figcaption><span class="blk-title">{esc(block.title)}</span>{unit}{chips}'
            "</figcaption>")


def _row_unit(block: blocks.Block, row: blocks.Row) -> str:
    return "" if block.unit else row.unit


def _pct(value: float, top: float) -> str:
    if top <= 0:
        return "0"
    return f"{max(value / top * 100, 0.5):.1f}".rstrip("0").rstrip(".")


def _fill(width: str, cls: str) -> str:
    return (f'<span class="blk-track"><span class="blk-bar {cls}" style="width:{width}%">'
            "</span></span>")


def _bars(block: blocks.Block, claims: dict) -> str:
    top = max((abs(r.values[0]) for r in block.rows), default=0)
    focal = _focal(block, lambda r: abs(r.values[0]))
    rows = []
    for i, r in enumerate(block.rows):
        cls, fill = (" focal", "violet") if i == focal else ("", "lavender")
        rows.append(f'<div class="blk-row{cls}"{types_of(r.ids, claims)}>'
                    f'<span class="blk-l">{esc(r.label)}</span>'
                    f'{_fill(_pct(abs(r.values[0]), top), fill)}'
                    f'{_value(r, 0, _row_unit(block, r))}</div>')
    return f'<div class="blk-rows">{"".join(rows)}</div>'


def _slope(block: blocks.Block, claims: dict) -> str:
    cols = block.columns if len(block.columns) == 2 else ["до", "после"]
    top = max((abs(v) for r in block.rows for v in r.values), default=0)
    focal = _focal(block, lambda r: abs(r.values[1] - r.values[0]))
    rows = []
    for i, r in enumerate(block.rows):
        cls = " focal" if i == focal else ""
        unit = _row_unit(block, r)
        pair = "".join(
            f'<span class="blk-pair p{k}"><span class="blk-c">{esc(cols[k])}</span>'
            f'{_fill(_pct(abs(r.values[k]), top), "mark" if k and i == focal else "plain")}'
            f'{_value(r, k, unit)}</span>' for k in (0, 1))
        rows.append(f'<div class="blk-row{cls}"{types_of(r.ids, claims)}>'
                    f'<span class="blk-l">{esc(r.label)}</span>{pair}</div>')
    return f'<div class="blk-rows">{"".join(rows)}</div>'


def _funnel(block: blocks.Block, claims: dict) -> str:
    top = max((r.values[0] for r in block.rows), default=0)
    focal = _focal(block, None)
    focal = len(block.rows) - 1 if focal is None else focal
    rows = []
    for i, r in enumerate(block.rows):
        cls, fill = (" focal", "mark") if i == focal else ("", "plain")
        rows.append(f'<div class="blk-row{cls}"{types_of(r.ids, claims)}>'
                    f'<span class="blk-l">{esc(r.label)}</span>'
                    f'{_fill(_pct(r.values[0], top), fill)}'
                    f'{_value(r, 0, _row_unit(block, r))}</div>')
    return f'<div class="blk-rows">{"".join(rows)}</div>'


def _line(block: blocks.Block, claims: dict) -> str:
    """Marks only in the SVG: points sit at the centres of the label columns below it, so the
    HTML values and x labels line up with them at any width."""
    width, height, upper, lower = 720, 192, 24, 168
    vals = [r.values[0] for r in block.rows]
    lo, hi = min(vals), max(vals)
    n = len(vals)
    focal = _focal(block, None)
    focal = n - 1 if focal is None else focal

    def x(i: int) -> int:
        return g4(width * (i + 0.5) / n)

    def y(v: float) -> int:
        return g4((upper + lower) / 2 if hi == lo else lower - (v - lo) / (hi - lo) * (lower - upper))

    pts = [(x(i), y(v)) for i, v in enumerate(vals)]
    grid = "".join(f'<line class="grid" x1="0" x2="{width}" y1="{g}" y2="{g}"/>'
                   for g in (upper, (upper + lower) // 2, lower))
    trace = " ".join(f"{a},{b}" for a, b in pts)
    seg = (f'<polyline class="seg" points="{pts[focal - 1][0]},{pts[focal - 1][1]} '
           f'{pts[focal][0]},{pts[focal][1]}"/>' if focal > 0 else "")
    dots = "".join(f'<circle class="pt{" f" if i == focal else ""}" cx="{a}" cy="{b}" r="4"/>'
                   for i, (a, b) in enumerate(pts))
    label = ", ".join(f"{r.label}: {_shown(r.shown[0])}" for r in block.rows)
    svg = (f'<svg class="blk-plot" viewBox="0 0 {width} {height}" width="100%" '
           f'preserveAspectRatio="xMidYMid meet" role="img" '
           f'aria-label="{esc(block.title)}: {esc(label)}">'
           f'{grid}<polyline class="trace" points="{trace}"/>{seg}{dots}</svg>')
    labels = "".join(
        f'<li class="blk-pt{" focal" if i == focal else ""}"{types_of(r.ids, claims)}>'
        f'{_value(r, 0, _row_unit(block, r), "b")}'
        f'<span class="blk-l">{esc(r.label)}</span></li>' for i, r in enumerate(block.rows))
    return (svg + f'<ol class="blk-points" style="grid-template-columns:repeat({n},minmax(0,1fr))">'
            f"{labels}</ol>")


def _tiles(block: blocks.Block, claims: dict) -> str:
    """Key figures as rows: the figure, the sentence with its citations, a muted note."""
    rows = []
    for r in block.rows:
        cls = " focal" if r.focal else ""
        sign = sign_of(r.shown[0])
        note = f'<small class="fig-n">{esc(r.note)}</small>' if r.note else ""
        rows.append(f'<div class="fig{cls}"{types_of(r.ids, claims)}>'
                    f'<div class="fig-v num{" " + sign if sign else ""}">'
                    f'{_value_link(r, 0, r.unit or block.unit)}</div>'
                    f'<div class="fig-t"><span class="fig-l">{esc(r.label)}</span>'
                    f'{cite_html(r.ids, claims)}{note}</div></div>')
    return f'<div class="figs">{"".join(rows)}</div>'


def _table(block: blocks.Block, claims: dict) -> str:
    parts = ['<div class="table-wrap"><table class="dt">']
    if block.header:
        parts.append("<thead><tr>" + "".join(f"<th>{inline(c, claims)}</th>"
                                             for c in block.header) + "</tr></thead>")
    parts.append("<tbody>")
    for r in block.rows:
        cls = ' class="focal"' if r.cells and r.cells[0].rstrip().endswith("*") else ""
        cells = list(r.cells)
        if cls:
            cells[0] = cells[0].rstrip()[:-1].rstrip()
        parts.append(f"<tr{cls}{types_of(r.ids, claims)}>"
                     + "".join(f"<td>{inline(c, claims)}</td>" for c in cells) + "</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


DRAW = {"bars": _bars, "slope": _slope, "funnel": _funnel, "line": _line, "tiles": _tiles,
        "table": _table}


def block_html(block: blocks.Block, claims: dict) -> str:
    inner = DRAW[block.kind](block, claims)
    cites = block.kind not in ("tiles", "table")  # those cite in each row
    return (f'<figure class="blk blk-{block.kind}">{_caption(block, claims, cites)}{inner}'
            "</figure>")


# --- decision table ---------------------------------------------------------------------------

OPTION = re.compile(r"^\s*(?:\*\*)?\s*Вариант\s+(\d+)", re.I)
DECISION_HEADING = "## Варианты против критериев"


def decision_rows(cdir: Path) -> list[tuple[int, str]]:
    """The options-by-criteria table of table.md: (line number, line)."""
    path = cdir / "table.md"
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next((i for i, t in enumerate(lines) if t.strip() == DECISION_HEADING), None)
    if start is None:
        return []
    rows: list[tuple[int, str]] = []
    for i in range(start + 1, len(lines)):
        t = lines[i]
        if t.startswith("#"):
            break
        if validate.TABLE_ROW.match(t):
            rows.append((i + 1, t))
        elif rows and t.strip():
            break
    return rows


def decision_errors(rows: list[tuple[int, str]], claims: dict, life: dict) -> list[str]:
    errors = []
    for line, text in rows:
        for cid in ledger.cited_ids(text):
            claim = claims.get(cid)
            if claim is None:
                errors.append(f"table.md:{line}: {cid} does not exist")
            elif ledger.status_of(claim, life) in ("withdrawn", "stale"):
                errors.append(f"table.md:{line}: {cid} is {ledger.status_of(claim, life)}")
    return errors


def decision_html(rows: list[tuple[int, str]], claims: dict, chosen) -> str:
    lines = [t for _, t in rows]
    if not lines:
        return ""
    head = None
    if len(lines) > 1 and validate.SEPARATOR.match(lines[1]):
        head, lines = lines[0], lines[2:]
    lines = [t for t in lines if not validate.SEPARATOR.match(t)]

    def is_chosen(cell: str) -> bool:
        m = OPTION.match(cell)
        return bool(m and chosen is not None and int(m.group(1)) == int(chosen))

    col = None
    if head is not None:
        col = next((k for k, c in enumerate(_cells(head)) if is_chosen(c)), None)
    mark = '<span class="chosen-mark">выбран</span>'
    parts = ['<section class="decision"><h2>Таблица решения</h2><div class="table-wrap">'
             '<table class="dt">']
    if head is not None:
        parts.append("<thead><tr>" + "".join(
            f'<th class="chosen">{inline(c, claims)} {mark}</th>' if k == col
            else f"<th>{inline(c, claims)}</th>" for k, c in enumerate(_cells(head)))
            + "</tr></thead>")
    parts.append("<tbody>")
    for t in lines:
        cells = _cells(t)
        row_chosen = bool(cells) and is_chosen(cells[0])
        tds = []
        for k, c in enumerate(cells):
            cls = ' class="chosen"' if row_chosen or k == col else ""
            extra = f" {mark}" if row_chosen and k == 0 else ""
            tds.append(f"<td{cls}{types_attr(c, claims)}>{inline(c, claims)}{extra}</td>")
        parts.append(f"<tr{types_attr(t, claims)}>" + "".join(tds) + "</tr>")
    parts.append("</tbody></table></div></section>")
    return "".join(parts)


# --- claim-type filter ------------------------------------------------------------------------

def filter_html(ids: list[str], claims: dict) -> str:
    present = [t for t in ledger.TYPES if any(claims[c]["type"] == t for c in ids)]
    if not present:
        return ""
    chips = "".join(f'<button type="button" class="chip t-{t}" data-type="{t}" '
                    f'aria-pressed="false">{ledger.TYPE_RU[t].lower()}</button>' for t in present)
    return (f'<nav class="type-filter" hidden aria-label="Подсветить утверждения по типу">'
            f'<span class="filter-l">Показать опору:</span>{chips}</nav>')


# --- markdown ---------------------------------------------------------------------------------

def _cells(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line)]


def risk_tags(item: str, risks: list[dict]) -> list[str]:
    """Objection ids for a risk bullet: the ones it names, else the accepted risks whose
    claims it cites."""
    named = re.findall(r"\bO\d{3,}\b", item)
    if named:
        return list(dict.fromkeys(named))
    cited = set(ledger.cited_ids(item))
    return [o["id"] for o in risks if cited & set(o.get("claims") or [])]


def risk_html(items: list[str], claims: dict, risks: list[dict]) -> str:
    rows = []
    for it in items:
        tags = "".join(f'<span class="risk-id">{esc(o)}</span>' for o in risk_tags(it, risks))
        tags = f'<span class="risk-ids">{tags}</span>' if tags else ""
        rows.append(f'<div class="risk"{types_attr(it, claims)}>{tags}'
                    f'<div class="risk-t">{inline(it, claims)}</div></div>')
    return f'<div class="risks">{"".join(rows)}</div>'


def md_to_html(text: str, claims: dict, risks: list[dict] | None = None) -> str:
    lines = text.splitlines()
    out: list[str] = []
    i, n = 0, len(lines)
    section = ""
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if blocks.block_type(line):
            block = blocks.parse(lines, i)
            out.append(block_html(block, claims))
            i = block.end
            continue
        if stripped.startswith(validate.FENCE):
            fence, body = stripped[:3], []
            i += 1
            while i < n and not lines[i].strip().startswith(fence):
                body.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + esc("\n".join(body)) + "</code></pre>")
            continue
        m = _HEADING.match(line)
        if m:
            level = len(m.group(1))
            if level == 2:
                section = m.group(2)
            out.append(f"<h{level}>{inline(m.group(2), claims)}</h{level}>")
            i += 1
            continue
        if stripped.startswith(">"):
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            paras = " ".join(quote).strip()
            out.append(f"<blockquote{types_attr(paras, claims)}><p>{inline(paras, claims)}</p>"
                       "</blockquote>")
            continue
        if validate.TABLE_ROW.match(line):
            rows = []
            while i < n and validate.TABLE_ROW.match(lines[i]):
                rows.append(lines[i])
                i += 1
            head = None
            if len(rows) > 1 and validate.SEPARATOR.match(rows[1]):
                head, rows = rows[0], rows[2:]
            parts = ['<div class="table-wrap"><table>']
            if head is not None:
                parts.append("<thead><tr>" + "".join(f"<th>{inline(c, claims)}</th>"
                                                     for c in _cells(head)) + "</tr></thead>")
            parts.append("<tbody>")
            for row in rows:
                if validate.SEPARATOR.match(row):
                    continue
                parts.append(f"<tr{types_attr(row, claims)}>"
                             + "".join(f"<td>{inline(c, claims)}</td>" for c in _cells(row))
                             + "</tr>")
            parts.append("</tbody></table></div>")
            out.append("".join(parts))
            continue
        if validate.BULLET.match(line):
            tag = "ol" if _ORDERED.match(line) else "ul"
            items: list[str] = []
            while i < n:
                cur = lines[i]
                if validate.BULLET.match(cur):
                    items.append(validate.BULLET.sub("", cur, count=1).strip())
                elif cur.strip() and cur.startswith((" ", "\t")) and items:
                    items[-1] += " " + cur.strip()
                else:
                    break
                i += 1
            if risks is not None and section.casefold().startswith("риски"):
                out.append(risk_html(items, claims, risks))
                continue
            out.append(f"<{tag}>" + "".join(f"<li{types_attr(it, claims)}>{inline(it, claims)}</li>"
                                            for it in items) + f"</{tag}>")
            continue
        para = []
        while i < n:
            cur = lines[i]
            s = cur.strip()
            if (not s or s.startswith(("#", ">") + validate.FENCE)
                    or validate.TABLE_ROW.match(cur) or validate.BULLET.match(cur)):
                break
            para.append(s)
            i += 1
        text = " ".join(para)
        out.append(f"<p{types_attr(text, claims)}>{inline(text, claims)}</p>")
    return "\n".join(out)


# --- claim cards ------------------------------------------------------------------------------

def shown_ids(memo: str, claims: dict) -> list[str]:
    """Ids cited in the memo, in order, plus what they rest on or were replaced by."""
    order: list[str] = []
    stack = list(reversed(ledger.cited_ids(memo)))
    while stack:
        cid = stack.pop()
        if cid in order or cid not in claims:
            continue
        order.append(cid)
        claim = claims[cid]
        more = list(claim.get("supports") or [])
        if claim.get("replaced_by"):
            more.append(claim["replaced_by"])
        stack += reversed(more)
    return order


def _source_html(claim: dict, index: dict) -> str:
    sid = claim.get("source")
    if not sid:
        return ""
    entry = index.get(sid)
    if entry is None:
        return f"<dt>Источник</dt><dd>{esc(sid)} (нет в индексе источников)</dd>"
    origin = entry.get("origin", "")
    href = safe_href(origin)
    kind = "страница" if re.match(r"^https?://", origin, re.I) else "файл"
    shown = origin if href else re.split(r"[/\\]", origin)[-1]  # never an absolute path
    origin_html = f'<a href="{esc(href)}">{esc(shown)}</a>' if href else esc(shown)
    snap = entry.get("snapshot", "")
    snap_href = safe_href(snap)
    snap_html = (f'; снимок <a href="{esc(snap_href)}">{esc(snap)}</a>' if snap_href and snap
                 else "")
    fetched = f"; получен {esc(entry['fetched'][:10])}" if entry.get("fetched") else ""
    return (f"<dt>Источник</dt><dd>{esc(sid)} · {esc(entry.get('title') or origin)}<br>"
            f"{kind}: {origin_html}{snap_html}{fetched}</dd>")


def card_html(claim: dict, claims: dict, index: dict, life: dict) -> str:
    cid, type_ = claim["id"], claim["type"]
    status = ledger.status_of(claim, life)
    bad = " bad" if status != "active" else ""
    rows = [_source_html(claim, index)]
    if claim.get("where"):
        rows.append(f"<dt>Где</dt><dd>{esc(claim['where'])}</dd>")
    if claim.get("quote"):
        rows.append(f"<dt>Цитата</dt><dd><blockquote>«{esc(claim['quote'])}»</blockquote></dd>")
    if claim.get("as_of"):
        hist = " (закрытый период)" if claim.get("historical") else ""
        rows.append(f"<dt>На дату</dt><dd>{esc(claim['as_of'])}{hist}</dd>")
    if claim.get("supports"):
        rows.append("<dt>Опирается на</dt><dd>" + cite_html(claim["supports"], claims) + "</dd>")
    if claim.get("replaced_by"):
        rows.append("<dt>Заменено на</dt><dd>" + cite_html([claim["replaced_by"]], claims)
                    + "</dd>")
    check = claim.get("check") or {}
    notes = []
    if check.get("quote") is True:
        notes.append("цитата найдена в снимке источника")
    if check.get("supported") is not None:
        verdict = "подтверждает" if check["supported"] else "не подтверждает"
        notes.append(f"цитата {verdict} утверждение (оценка: {esc(check.get('by') or 'модель')})")
    if notes:
        rows.append("<dt>Проверка</dt><dd>" + "; ".join(notes) + "</dd>")
    return (f'<article class="claim t-{type_}" id="{cid}">'
            f'<header><span class="cid">{cid}</span>'
            f'<span class="tag">{TYPE_LABEL.get(type_, esc(type_))}</span>'
            f'<span class="status{bad}">{ledger.STATUS_RU.get(status, esc(status))}</span>'
            f"</header>"
            f'<p class="ctext">{esc(claim["text"])}</p>'
            f'<p class="note">{TYPE_NOTE.get(type_, "")}</p>'
            f"<dl>{''.join(r for r in rows if r)}</dl></article>")


# --- page -------------------------------------------------------------------------------------

def with_decision(body: str, decision: str) -> str:
    """The decision table goes before the memo's "Материалы" section, else at the end."""
    if not decision:
        return body
    at = body.find("<h2>Материалы</h2>")
    return body + "\n" + decision if at < 0 else body[:at] + decision + "\n" + body[at:]


CHECK_DATE = re.compile(r"Дата проверки\**\s*:\s*\**\s*(\d{4}-\d{2}-\d{2})")
_TITLE_PREFIX = re.compile(r"^\s*Записка\s*[:.—–-]\s*", re.I)


def split_memo(memo: str) -> tuple[str, list[str], str]:
    """(title, the lines of the "## Решение" section, the rest of the memo for the body)."""
    lines = memo.splitlines()
    title, keep, decision = "", [], []
    section = None
    for line in lines:
        m = _HEADING.match(line)
        if m and len(m.group(1)) == 1 and not title:
            title = m.group(2)
            continue
        if m and len(m.group(1)) <= 2:
            section = "decision" if m.group(2).strip().casefold() == "решение" else None
            if section:
                continue
        (decision if section else keep).append(line)
    return title, decision, "\n".join(keep)


def decision_box(lines: list[str], claims: dict) -> str:
    items, cur = [], []
    for line in lines:
        if validate.BULLET.match(line):
            if cur:
                items.append(" ".join(cur))
            cur = [validate.BULLET.sub("", line, count=1).strip()]
        elif line.strip() and not line.strip().startswith(">"):
            cur.append(line.strip())
        elif cur:
            items.append(" ".join(cur))
            cur = []
    if cur:
        items.append(" ".join(cur))
    if not items:
        return ""
    text = " ".join(inline(t, claims) for t in items)
    return (f'<div class="decision-box"{types_attr(" ".join(items), claims)}>'
            f"<b>Решение.</b> {text}</div>")


def check_date(cdir: Path, memo: str) -> str:
    found = CHECK_DATE.findall(memo)
    if not found and (cdir / "decisions.md").is_file():
        found = CHECK_DATE.findall((cdir / "decisions.md").read_text(encoding="utf-8"))
    return found[-1] if found else ""


def meta_html(date: str, counts: dict, risks: list[dict] | None) -> str:
    items = []
    if date:
        items.append(f'Проверка: <span class="mono">{esc(date)}</span>')
    items.append(f'Факты: <span class="num">{counts.get("fact", 0)}</span>')
    items.append(f'Допущения: <span class="num">{counts.get("assumption", 0)}</span>')
    if risks is not None:
        items.append(f'Принятые риски: <span class="num">{len(risks)}</span>')
    return '<div class="meta">' + "".join(f"<span>{t}</span>" for t in items) + "</div>"


def accepted_risks(cdir: Path) -> list[dict] | None:
    path = cdir / "objections.jsonl"
    if not path.is_file():
        return None
    return [o for o in read_jsonl(path) if o.get("verdict") == "risk-accepted"]


def card_data(ids: list[str], claims: dict, index: dict, life: dict) -> str:
    """What the claim-card popover shows, as JSON safe to embed in a <script> element."""
    out_claims, out_sources = {}, {}
    for cid in ids:
        c = claims[cid]
        status = ledger.status_of(c, life)
        out_claims[cid] = {
            "id": cid, "type": c["type"], "label": TYPE_LABEL.get(c["type"], c["type"]),
            "status": "" if status == "active" else ledger.STATUS_RU.get(status, status),
            "text": c.get("text", ""), "source": c.get("source"), "where": c.get("where"),
            "quote": c.get("quote"), "note": TYPE_NOTE.get(c["type"], ""),
            "supports": [x for x in (c.get("supports") or []) if x in claims]}
        sid = c.get("source")
        if sid and sid in index and sid not in out_sources:
            e = index[sid]
            origin = e.get("origin", "")
            href = safe_href(origin)
            out_sources[sid] = {
                "title": e.get("title") or re.split(r"[/\\]", origin)[-1],
                "kind": e.get("kind"), "href": href,
                "download": bool(href) and not re.match(r"^https?://", href, re.I),
                "snap": safe_href(e.get("snapshot", ""))}
    data = json.dumps({"claims": out_claims, "sources": out_sources}, ensure_ascii=False)
    return data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def render(cdir: Path, memo: str) -> tuple[str, int]:
    claims = ledger.by_id(ledger.load(cdir))
    index = {s["id"]: s for s in sources.index(cdir)}
    life = ledger.shelf_life()
    rows = decision_rows(cdir)
    decision = decision_html(rows, claims, load_state(cdir).get("chosen_option"))
    ids = shown_ids(memo + "\n" + "\n".join(t for _, t in rows), claims)
    title, decision_lines, rest = split_memo(memo)
    title = _TITLE_PREFIX.sub("", re.sub(r"\[[^\]]*\]", "", title)).strip() or "Записка"
    title = title[:1].upper() + title[1:]
    context = load_state(cdir).get("title") or ""
    risks = accepted_risks(cdir)
    counts = {t: sum(1 for c in ids if claims[c]["type"] == t) for t in ledger.TYPES}
    summary = "Утверждений в записке и её опорах: {} ({}).".format(
        len(ids), ", ".join(f"{TYPE_LABEL[t]} — {k}" for t, k in counts.items() if k))
    legend = "".join(f'<li><span class="tag t-{t}">{TYPE_LABEL[t]}</span></li>'
                     for t in ledger.TYPES if counts[t])
    values = {
        "TITLE": esc(title),
        "CONTEXT": f'<p class="ctx">{esc(context)}</p>' if context else "",
        "DECISION": decision_box(decision_lines, claims),
        "META": meta_html(check_date(cdir, memo), counts, risks),
        "BODY": with_decision(md_to_html(rest, claims, risks or []), decision),
        "FILTER": filter_html(ids, claims),
        "SUMMARY": esc(summary),
        "LEGEND": legend,
        "CLAIMS": "\n".join(card_html(claims[c], claims, index, life) for c in ids),
        "DATA": card_data(ids, claims, index, life),
        "GENERATED": esc(today().isoformat()),
    }
    template = (root() / "config" / TEMPLATE).read_text(encoding="utf-8")
    page = re.sub(r"\{\{([A-Z]+)\}\}", lambda m: values.get(m.group(1), m.group(0)), template)
    return page, len(ids)


def report(case: str | None = None, as_json: bool = False) -> int:
    """Check memo.md citations, then render memo.html next to it."""
    cdir = case_path(case)
    memo_path = cdir / "memo.md"
    if not memo_path.is_file():
        raise StratError(f"memo.md not found in cases/{cdir.name}: write it at sign-off first "
                         "(skills/signoff)")
    claims = ledger.load(cdir)
    index, life = ledger.by_id(claims), ledger.shelf_life()
    errors = validate.citation_errors(cdir, "memo.md", index, life)
    errors += decision_errors(decision_rows(cdir), index, life)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        emit(f"report: {len(errors)} problem(s) in memo.md; fix them and rerun; memo.html not "
             "written", {"passed": False, "errors": errors}, as_json)
        return FAILED
    page, count = render(cdir, memo_path.read_text(encoding="utf-8"))
    out = cdir / "memo.html"
    tmp = out.with_suffix(".html.tmp")
    tmp.write_text(page, encoding="utf-8")
    tmp.replace(out)
    emit(f"wrote cases/{cdir.name}/memo.html: {count} claims linked",
         {"passed": True, "out": f"cases/{cdir.name}/memo.html", "claims": count}, as_json)
    return 0
