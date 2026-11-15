"""Memo blocks: fenced blocks with numbers that `strat report` draws with fixed code.

A block is a fenced block whose info string is its type (`tiles`, `bars`, `line`, `slope`,
`funnel`, `table`). The body is a few `key: value` lines (`title:` required, `unit:` and, for
`slope`, `columns: before | after` optional) and rows:

    tiles   - <label>: <value> <unit?> - <one-line note> [Cxxx]
    bars    - <label>: <value> [Cxxx]
    funnel  - <label>: <value> [Cxxx]          steps from top to bottom
    line    - <x label>: <value> [Cxxx]        points in order
    slope   - <label>: <before> | <after> [Cxxx]
    table   | header | header |                 first pipe row is the header
            | label | cell | cell [Cxxx] |      every other row cites a claim

A label ending in `*` marks the focal row (drawn in the accent colour). Values may use a decimal
comma or point and spaces between thousands; a `%` or a unit word may follow. Bars may all be
negative (decreases, drawn by magnitude) but not mixed; funnel steps are never negative.

The check (run by the gate, `strat step --out` and `strat report`): every row cites at least one
claim that exists and is not withdrawn or stale, and every number in a row outside its label
(table: outside the first column) appears in the text or quote of a claim the row cites.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from strat import ledger

TYPES = ("tiles", "bars", "line", "slope", "funnel", "table")
MAX_BLOCKS = 3
FENCE = re.compile(r"^\s*(```|~~~)\s*([A-Za-z]+)?\s*$")
KEY = re.compile(r"^\s*(title|unit|columns|заголовок|единица|столбцы)\s*:\s*(.*?)\s*$", re.I)
KEYS = {"заголовок": "title", "единица": "unit", "столбцы": "columns"}
ROW = re.compile(r"^\s*[-*+•]\s*")
SEP_ROW = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
PLACEHOLDER = re.compile(r"<[^<>\n]{2,80}>|\[C\.\.\.\]")
CITES = re.compile(r"\[\s*C[^\]]*\]")
MINUS = "-−–"
# a number: thousands groups split by (narrow) spaces, then an optional decimal part
NUMBER = re.compile(r"(?<![\d.,])(?:\d{1,3}(?:[   ]\d{3})+|\d+)(?:[.,]\d+)?")
SIMPLE = re.compile(r"\d+(?:[.,]\d+)?")
NOTE_SEP = re.compile(r"\s+[-–—]\s+")


@dataclass
class Row:
    line: int
    label: str = ""
    focal: bool = False
    values: list[float] = field(default_factory=list)
    shown: list[str] = field(default_factory=list)  # values exactly as written
    unit: str = ""
    note: str = ""
    cells: list[str] = field(default_factory=list)
    ids: list[str] = field(default_factory=list)


@dataclass
class Block:
    kind: str
    line: int
    end: int  # index of the line after the closing fence (0-based)
    title: str = ""
    unit: str = ""
    columns: list[str] = field(default_factory=list)
    header: list[str] = field(default_factory=list)
    rows: list[Row] = field(default_factory=list)
    errors: list[tuple[int, str]] = field(default_factory=list)


def number_value(text: str) -> Decimal | None:
    try:
        return Decimal(re.sub(r"[   ]", "", text).replace(",", "."))
    except InvalidOperation:
        return None


def numbers_in(text: str) -> set[Decimal]:
    """Every number a claim states, read both with and without thousands grouping."""
    found = set()
    for rx in (NUMBER, SIMPLE):
        for m in rx.finditer(text or ""):
            v = number_value(m.group(0))
            if v is not None:
                found.add(v)
    return found


def split_cells(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def block_type(line: str) -> str | None:
    m = FENCE.match(line)
    if m and m.group(2) and m.group(2).lower() in TYPES:
        return m.group(2).lower()
    return None


def _label_split(text: str) -> tuple[str, str] | None:
    """`label: rest` at the first colon followed by a number."""
    for m in re.finditer(r":", text):
        rest = text[m.end():]
        if re.match(rf"^\s*[{MINUS}+]?\s*\d", rest):
            return text[:m.start()].strip(), rest.strip()
    return None


def _take_number(text: str) -> tuple[float, str, str] | None:
    """Leading signed number of `text`: (value, as written, the rest)."""
    m = re.match(rf"^\s*([{MINUS}+]?)\s*({NUMBER.pattern})", text)
    if not m:
        return None
    v = number_value(m.group(2))
    if v is None:
        return None
    sign = -1 if m.group(1) and m.group(1) in MINUS else 1
    shown = (m.group(1) + m.group(2)).strip()
    return sign * float(v), shown, text[m.end():]


def _parse_row(block: Block, line_no: int, raw: str) -> Row | None:
    row = Row(line=line_no)
    ids = ledger.cited_ids(raw)
    row.ids = ids
    body = CITES.sub("", raw).strip()
    if block.kind == "table":
        row.cells = split_cells(raw)
        return row
    body = ROW.sub("", body, count=1)
    split = _label_split(body)
    if split is None:
        hint = "- label: before | after [Cxxx]" if block.kind == "slope" else "- label: value [Cxxx]"
        block.errors.append((line_no, f"cannot read this row; write \"{hint}\""))
        return None
    label, rest = split
    if label.endswith("*"):
        label, row.focal = label[:-1].strip(), True
    row.label = label
    first = _take_number(rest)
    if first is None:
        block.errors.append((line_no, "cannot read this row; the value must be a number"))
        return None
    row.values.append(first[0])
    row.shown.append(first[1])
    rest = first[2].strip()
    if block.kind == "slope":
        rest = re.sub(r"^(\||->|→|—|–)\s*", "", rest)
        second = _take_number(rest)
        if second is None:
            block.errors.append((line_no, "a slope row needs two values: "
                                          "\"- label: before | after [Cxxx]\""))
            return None
        row.values.append(second[0])
        row.shown.append(second[1])
        rest = second[2].strip()
    if block.kind == "tiles":
        parts = NOTE_SEP.split(" " + rest + " ", maxsplit=1)
        row.unit = parts[0].strip()
        row.note = parts[1].strip() if len(parts) > 1 else ""
        if rest.startswith(("-", "–", "—")) and not row.note:
            row.unit, row.note = "", rest.lstrip("-–— ").strip()
    else:
        row.unit = rest
    return row


def parse(lines: list[str], start: int) -> Block:
    """Parse the block whose opening fence is lines[start] (0-based)."""
    kind = block_type(lines[start])
    block = Block(kind=kind, line=start + 1, end=len(lines))
    fence = FENCE.match(lines[start]).group(1)
    i = start + 1
    closed = False
    while i < len(lines):
        raw = lines[i]
        if raw.strip().startswith(fence):
            closed = True
            i += 1
            break
        line_no = i + 1
        i += 1
        if not raw.strip():
            continue
        if PLACEHOLDER.search(raw):
            block.errors.append((line_no, "template placeholder left in the block"))
            continue
        key = KEY.match(raw)
        if key and not block.rows and not ledger.cited_ids(raw):
            name = KEYS.get(key.group(1).lower(), key.group(1).lower())
            if name == "columns":
                block.columns = [c for c in split_cells(key.group(2)) if c]
            else:
                setattr(block, name, key.group(2))
            continue
        if block.kind == "table":
            if SEP_ROW.match(raw):
                continue
            if "|" not in raw:
                block.errors.append((line_no, "cannot read this row; write "
                                              "\"| label | cell | cell [Cxxx] |\""))
                continue
            if not block.header and not ledger.cited_ids(raw):
                block.header = split_cells(raw)
                continue
        elif not ROW.match(raw):
            block.errors.append((line_no, "cannot read this row; start it with \"- \""))
            continue
        row = _parse_row(block, line_no, raw)
        if row is not None:
            block.rows.append(row)
    block.end = i
    if not closed:
        block.errors.append((block.line, f"{kind} block is not closed with {fence}"))
    if not block.title:
        block.errors.append((block.line, f"{kind} block has no title; add \"title: ...\""))
    if not block.rows and not any(e for e in block.errors if e[0] != block.line):
        block.errors.append((block.line, f"{kind} block has no rows"))
    values = [v for r in block.rows for v in r.values]
    if kind == "funnel" and any(v < 0 for v in values):
        block.errors.append((block.line, "funnel values must not be negative; use a line "
                                         "or a table"))
    if kind == "bars" and any(v < 0 for v in values) and any(v > 0 for v in values):
        block.errors.append((block.line, "bars values must all have the same sign (all "
                                         "decreases or all increases); use a table"))
    if kind == "line" and block.rows and len(block.rows) < 4:
        block.errors.append((block.line, f"line needs at least 4 points (has {len(block.rows)}); "
                                         "for a before/after use slope"))
    if kind == "slope" and block.columns and len(block.columns) != 2:
        block.errors.append((block.line, "slope columns: write two names, \"columns: до | после\""))
    return block


def blocks_in(lines: list[str]) -> list[Block]:
    out, i = [], 0
    while i < len(lines):
        m = FENCE.match(lines[i])
        if not m:
            i += 1
            continue
        if block_type(lines[i]):
            block = parse(lines, i)
            out.append(block)
            i = block.end
            continue
        fence, i = m.group(1), i + 1  # a plain code block: skip to its end
        while i < len(lines) and not lines[i].strip().startswith(fence):
            i += 1
        i += 1
    return out


def _row_numbers(block: Block, row: Row, raw: str) -> list[str]:
    """Numbers in the row that must come from the cited claims, as written."""
    if block.kind == "table":
        text = " | ".join(CITES.sub("", c) for c in row.cells[1:])
    else:
        body = ROW.sub("", CITES.sub("", raw), count=1)
        split = _label_split(body)
        text = split[1] if split else body
    return [m.group(0) for m in NUMBER.finditer(text)]


def errors(name: str, text: str, claims: dict, life: dict) -> list[str]:
    lines = text.splitlines()
    found = blocks_in(lines)
    out = []
    if name == "memo.md" and len(found) > MAX_BLOCKS:
        out.append(f"{name}:{found[MAX_BLOCKS].line}: more than {MAX_BLOCKS} blocks; keep the "
                   "ones that show the reason for the decision")
    for block in found:
        out += [f"{name}:{line}: {reason}" for line, reason in block.errors]
        for row in block.rows:
            at = f"{name}:{row.line}:"
            if not row.ids:
                out.append(f"{at} no citation; end the row with the claim id, e.g. [C001]")
                continue
            known = set()
            for cid in row.ids:
                claim = claims.get(cid)
                if claim is None:
                    out.append(f"{at} {cid} does not exist")
                    continue
                status = ledger.status_of(claim, life)
                if status in ("withdrawn", "stale"):
                    out.append(f"{at} {cid} is {status}")
                known |= numbers_in(claim.get("text", "")) | numbers_in(claim.get("quote", ""))
            if not any(c in claims for c in row.ids):
                continue
            for shown in _row_numbers(block, row, lines[row.line - 1]):
                if number_value(shown) not in known:
                    out.append(f"{at} {shown} is not in the text or quote of "
                               f"{', '.join(row.ids)}; copy the value from the claim")
    return out
