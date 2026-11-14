"""memo.md to memo.html from the fixed template config/memo.html.

The memo is checked first with the gate's citation rules (strat/validate.py): a cited claim
that does not exist, is withdrawn or is stale fails with `<file>:<line>: <reason>` and no HTML
is written. Every claim id in the text becomes a link to a card with the claim's type, status,
text, source, `where` and quote; conclusions also link the claims they rest on. Non-fact types
carry a visible label next to the citation. Markdown is converted by a small stdlib converter
for the subset the templates use: headings, bullets, numbered lists, tables, paragraphs, bold,
inline code, links, `>` notes and fenced code. Everything from claims and sources is escaped.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from strat import ledger, sources, validate
from strat.core import FAILED, StratError, case_path, emit, root, today

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
    "gap": "Пробел: данных нет. Это известное неизвестное, а не факт.",
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
    if not url or ":" in url.split("/")[0] or url.startswith("//"):
        return None
    return url


# --- inline -----------------------------------------------------------------------------------

def cite_html(ids: list[str], claims: dict) -> str:
    links = []
    for cid in ids:
        type_ = claims.get(cid, {}).get("type", "")
        tag = "" if type_ in ("", "fact") else f'<span class="tag">{TYPE_LABEL[type_]}</span>'
        links.append(f'<a class="cite t-{type_ or "unknown"}" href="#{cid}">{cid}{tag}</a>')
    return '<span class="cites">[' + ", ".join(links) + "]</span>"


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


# --- blocks -----------------------------------------------------------------------------------

def _cells(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line)]


def md_to_html(text: str, claims: dict) -> str:
    lines = text.splitlines()
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
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
            out.append(f"<h{level}>{inline(m.group(2), claims)}</h{level}>")
            i += 1
            continue
        if stripped.startswith(">"):
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            paras = " ".join(quote).strip()
            out.append(f"<blockquote><p>{inline(paras, claims)}</p></blockquote>")
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
                parts.append("<tr>" + "".join(f"<td>{inline(c, claims)}</td>"
                                              for c in _cells(row)) + "</tr>")
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
            out.append(f"<{tag}>" + "".join(f"<li>{inline(it, claims)}</li>" for it in items)
                       + f"</{tag}>")
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
        out.append(f"<p>{inline(' '.join(para), claims)}</p>")
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
    origin_html = f'<a href="{esc(href)}">{esc(origin)}</a>' if href else esc(origin)
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

def render(cdir: Path, memo: str) -> tuple[str, int]:
    claims = ledger.by_id(ledger.load(cdir))
    index = {s["id"]: s for s in sources.index(cdir)}
    life = ledger.shelf_life()
    ids = shown_ids(memo, claims)
    title = next((m.group(2) for m in map(_HEADING.match, memo.splitlines())
                  if m and len(m.group(1)) == 1), "Записка")
    counts = {t: sum(1 for c in ids if claims[c]["type"] == t) for t in ledger.TYPES}
    summary = "Утверждений в записке и её опорах: {} ({}).".format(
        len(ids), ", ".join(f"{TYPE_LABEL[t]} — {k}" for t, k in counts.items() if k))
    legend = "".join(f'<li><span class="tag t-{t}">{TYPE_LABEL[t]}</span></li>'
                     for t in ledger.TYPES if counts[t])
    values = {
        "TITLE": esc(re.sub(r"\[[^\]]*\]", "", title).strip()),
        "BODY": md_to_html(memo, claims),
        "SUMMARY": esc(summary),
        "LEGEND": legend,
        "CLAIMS": "\n".join(card_html(claims[c], claims, index, life) for c in ids),
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
    errors = validate.citation_errors(cdir, "memo.md", ledger.by_id(claims), ledger.shelf_life())
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
