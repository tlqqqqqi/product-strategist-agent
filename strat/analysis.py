"""Data analysis: a helper for scripts in cases/<case>/analysis/ and the check that reruns them.

A script imports this module, loads a table from a material or a source snapshot, and prints
each figure it computes as one machine-readable line:

    INPUT materials/metrics.xlsx sha256=1a2b3c4d5e6f
    GAP cohorts!D5 (paid_users_2026_10, channel=paid_ads) is empty
    FIGURE promo_paid_change = -770 users | period 2026-08..2026-10

Rules enforced here, not in a prompt:
- every figure has a unit and a period in a known form (month, quarter, year, week, day, range);
- an empty cell the script reads is printed as a GAP line, never silently skipped;
- diff, pct_change and share refuse figures with different units or period granularity
  (RUB vs thousand RUB, a monthly rate vs a quarterly one) and print a MISMATCH line;
- `strat analysis check` reruns the script behind a registered output and names every figure
  that no longer reproduces, and reports conclusions that combine figures of the same unit
  family at different scales or periods.
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# --- units and periods ------------------------------------------------------------------------

_UNIT_ALIASES = {
    "RUB": {"rub", "₽", "руб", "руб.", "rubles", "рублей"},
    "thousand RUB": {"thousand rub", "тыс. ₽", "тыс ₽", "тыс. руб", "тыс. руб.", "тыс руб",
                     "k rub", "krub", "thousand ₽"},
    "million RUB": {"million rub", "млн ₽", "млн руб", "млн руб.", "m rub", "mrub"},
    "%": {"%", "pct", "percent", "процент", "процентов"},
    "p.p.": {"p.p.", "pp", "п.п.", "п. п.", "percentage points"},
    "users": {"users", "пользователей", "пользователи"},
    "thousand users": {"thousand users", "тыс. пользователей", "k users"},
}
_CANON = {alias: name for name, aliases in _UNIT_ALIASES.items() for alias in aliases}
# unit -> (family, scale): figures of one family at different scales must not be combined
_FAMILY = {"RUB": ("money", 1), "thousand RUB": ("money", 1e3), "million RUB": ("money", 1e6),
           "users": ("users", 1), "thousand users": ("users", 1e3)}

_PERIOD_FORMS = [
    ("day", re.compile(r"^\d{4}-\d{2}-\d{2}$")),
    ("week", re.compile(r"^\d{4}-W\d{2}$")),
    ("month", re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")),
    ("quarter", re.compile(r"^\d{4}-Q[1-4]$")),
    ("year", re.compile(r"^\d{4}$")),
]
PERIOD_HELP = "2026-10 (month), 2026-Q3 (quarter), 2026 (year), 2026-W40, 2026-10-15, or A..B"


def unit_of(unit: str) -> str:
    """The canonical spelling of a unit; an unknown unit is kept as written."""
    text = " ".join(str(unit).split())
    return _CANON.get(text.casefold(), text)


def granularity(period: str) -> str:
    """month, quarter, year, week or day; a range A..B has the granularity of its ends."""
    ends = str(period).split("..")
    kinds = []
    for end in ends:
        kind = next((k for k, rx in _PERIOD_FORMS if rx.match(end)), None)
        if kind is None or len(ends) > 2:
            raise ValueError(f"period {period!r} is not in a known form: {PERIOD_HELP}")
        kinds.append(kind)
    if len(set(kinds)) > 1:
        raise ValueError(f"period {period!r} mixes a {kinds[0]} and a {kinds[1]}")
    return kinds[0]


def _fmt(value: float, digits: int = 2) -> str:
    value = round(float(value), digits)
    if value.is_integer():
        return str(int(value))
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


# --- figures ----------------------------------------------------------------------------------

class Mismatch(ValueError):
    """Two figures cannot be combined: different units or period granularity."""


@dataclass(frozen=True)
class Figure:
    name: str
    value: float
    unit: str
    period: str

    @property
    def line(self) -> str:
        return f"FIGURE {self.name} = {_fmt(self.value)} {self.unit} | period {self.period}"


NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


def figure(name: str, value, unit: str, period: str, digits: int = 2) -> Figure:
    """Record and print one figure. Returns it for use in diff, pct_change and share."""
    if not NAME.match(str(name)):
        raise ValueError(f"figure name {name!r}: use letters, digits, '_', '.', '-'")
    if value is None:
        raise ValueError(f"figure {name}: no value (an empty cell?); record a gap instead")
    if not str(unit).strip():
        raise ValueError(f"figure {name}: a unit is required (RUB, thousand RUB, %, p.p., users)")
    granularity(period)
    fig = Figure(name, round(float(value), digits), unit_of(unit), str(period))
    print(fig.line, flush=True)
    return fig


def _describe(f: Figure) -> str:
    return f"{f.name} ({f.unit}, {granularity(f.period)} {f.period})"


def _compatible(op: str, a: Figure, b: Figure, same_period: bool = False) -> None:
    reason = None
    if a.unit != b.unit:
        reason = "different units"
    elif granularity(a.period) != granularity(b.period):
        reason = "different period granularity"
    elif same_period and a.period != b.period:
        reason = "different periods"
    if reason:
        msg = f"MISMATCH {op}: {_describe(a)} vs {_describe(b)}: {reason}"
        print(msg, flush=True)
        raise Mismatch(msg + "; convert one of them first and record it as its own figure")


def _span(old: Figure, new: Figure) -> str:
    if old.period == new.period:
        return old.period
    return f"{old.period.split('..')[0]}..{new.period.split('..')[-1]}"


def diff(new: Figure, old: Figure, name: str) -> Figure:
    """new - old, in the same unit (a difference of two % values is in p.p.)."""
    _compatible("diff", new, old)
    unit = "p.p." if new.unit == "%" else new.unit
    return figure(name, new.value - old.value, unit, _span(old, new))


def pct_change(new: Figure, old: Figure, name: str) -> Figure:
    """Relative change (new - old) / old in %."""
    _compatible("pct_change", new, old)
    if old.value == 0:
        raise ValueError(f"{name}: {old.name} is 0, a relative change is undefined")
    return figure(name, (new.value - old.value) / old.value * 100, "%", _span(old, new))


def share(part: Figure, whole: Figure, name: str) -> Figure:
    """part / whole in %, for the same period."""
    _compatible("share", part, whole, same_period=True)
    if whole.value == 0:
        raise ValueError(f"{name}: {whole.name} is 0")
    return figure(name, part.value / whole.value * 100, "%", part.period)


# --- tables -----------------------------------------------------------------------------------

def case_dir() -> Path:
    """The case the running script belongs to."""
    env = os.environ.get("STRAT_ANALYSIS_CASE")
    if env:
        return Path(env)
    script = Path(sys.argv[0]).resolve() if sys.argv and sys.argv[0] else None
    if script and script.suffix == ".py" and script.parent.name == "analysis":
        return script.parent.parent
    return Path.cwd()


def number(text: str) -> float:
    """'41 200' -> 41200, '4,1' -> 4.1, '6.8%' -> 6.8, '349 ₽' -> 349."""
    s = str(text)
    for ch in (" ", " ", " ", " ", "%", "₽"):
        s = s.replace(ch, "")
    return float(s.replace(",", "."))


_INPUTS_PRINTED: set[str] = set()


class Table:
    def __init__(self, sheet: str, header: list[str], rows: list[list[str]]):
        self.sheet, self.columns, self._rows = sheet, header, rows
        self._gaps: set[str] = set()

    @property
    def rows(self) -> list[dict]:
        return [dict(zip(self.columns, r)) for r in self._rows]

    def _col(self, column: str) -> int:
        if column not in self.columns:
            raise KeyError(f"no column {column!r} in {self.sheet} (columns: "
                           f"{', '.join(self.columns)})")
        return self.columns.index(column)

    def _match(self, where: dict | None) -> list[int]:
        idx = range(len(self._rows))
        for col, val in (where or {}).items():
            c = self._col(col)
            idx = [i for i in idx if self._rows[i][c] == str(val)]
        return list(idx)

    def _read(self, i: int, c: int) -> float | None:
        raw = self._rows[i][c] if c < len(self._rows[i]) else ""
        if raw.strip():
            try:
                return number(raw)
            except ValueError:
                raise ValueError(f"{self.address(i, c)}: {raw!r} is not a number") from None
        addr = self.address(i, c)
        if addr not in self._gaps:
            self._gaps.add(addr)
            key = f"{self.columns[0]}={self._rows[i][0]}" if c else f"row {i + 2}"
            print(f"GAP {addr} ({self.columns[c]}, {key}) is empty", flush=True)
        return None

    def address(self, i: int, c: int) -> str:
        from strat.convert import column_letter
        return f"{self.sheet}!{column_letter(c + 1)}{i + 2}"  # the header is row 1

    def value(self, column: str, where: dict | None = None) -> float | None:
        """The one number in `column` on the row matching `where`; None (and a GAP line) if empty."""
        rows = self._match(where)
        if len(rows) != 1:
            raise ValueError(f"{self.sheet}: {len(rows)} rows match {where}; need exactly one")
        return self._read(rows[0], self._col(column))

    def numbers(self, column: str, where: dict | None = None) -> list[float]:
        """Numbers of `column` on matching rows; empty cells are left out and printed as GAP."""
        c = self._col(column)
        return [v for i in self._match(where) if (v := self._read(i, c)) is not None]


def load(ref: str, sheet: str) -> Table:
    """A sheet from a source snapshot ("S001") or a file in the case ("materials/x.xlsx").

    A csv's sheet is the file name without extension. Prints an INPUT line once per ref.
    """
    from strat import convert, sources

    cdir = case_dir()
    if sources.SOURCE_ID.match(ref):
        entry = sources.get(cdir, ref)
        if entry is None:
            raise KeyError(f"unknown source {ref}")
        text, digest = sources.snapshot_text(cdir, entry), entry["sha256"]
    else:
        path = cdir / ref
        if not path.is_file():
            raise FileNotFoundError(f"{ref}: not found in the case {cdir}")
        text = convert.convert(str(path))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if ref not in _INPUTS_PRINTED:
        _INPUTS_PRINTED.add(ref)
        print(f"INPUT {ref} sha256={digest[:12]}", flush=True)
    blocks = sources._blocks(text, re.compile(r"^## sheet: (.+)$"))
    if sheet not in blocks:
        raise KeyError(f"no sheet {sheet!r} in {ref} (sheets: {', '.join(blocks)})")
    body = blocks[sheet]
    fenced = body.split("```csv\n", 1)[1].rsplit("```", 1)[0] if "```csv" in body else ""
    grid = list(csv.reader(io.StringIO(fenced)))
    if not grid:
        raise ValueError(f"{ref}: sheet {sheet!r} is empty")
    return Table(sheet, grid[0], grid[1:])


# --- check ------------------------------------------------------------------------------------

_FIGURE = re.compile(r"^FIGURE (\S+) = (\S+) (.+?) \| period (\S+)$")
_INPUT = re.compile(r"^INPUT (\S+) sha256=(\w+)$")


def parse(text: str) -> tuple[dict[str, Figure], dict[str, str], list[str]]:
    """Figures by name, input hashes by ref, gap lines."""
    figures, inputs, gaps = {}, {}, []
    for line in text.splitlines():
        line = line.strip()
        if m := _FIGURE.match(line):
            figures[m[1]] = Figure(m[1], float(m[2]), m[3], m[4])
        elif m := _INPUT.match(line):
            inputs[m[1]] = m[2]
        elif line.startswith("GAP "):
            gaps.append(line[4:])
    return figures, inputs, gaps


def _show(f: Figure) -> str:
    return f"{_fmt(f.value)} {f.unit} ({f.period})"


def rerun(cdir: Path, script: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, STRAT_ANALYSIS_CASE=str(cdir))
    pkg_root = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = pkg_root + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, str(script)], cwd=cdir, env=env, capture_output=True,
                          text=True, timeout=120)


def check_source(cdir: Path, entry: dict) -> tuple[list[str], list[str], int]:
    """(problems, gaps, figures reproduced) for one registered analysis output."""
    from strat import sources

    origin = entry["origin"]
    if entry.get("kind") != "analysis":
        return [f"{entry['id']}: {origin} is not an analysis output (kind {entry.get('kind')})"], \
            [], 0
    registered, reg_inputs, _ = parse(sources.snapshot_text(cdir, entry))
    if not registered:
        return [f"{origin}: no FIGURE lines; print figures with strat.analysis.figure()"], [], 0
    script = cdir / Path(origin).with_suffix(".py")
    if not script.is_file():
        return [f"{origin}: no script {script.relative_to(cdir)} next to the output"], [], 0
    try:
        proc = rerun(cdir, script)
    except subprocess.TimeoutExpired:
        return [f"{origin}: {script.name} ran longer than 120 s"], [], 0
    if proc.returncode != 0:
        last = (proc.stderr.strip().splitlines() or ["no error output"])[-1]
        return [f"{origin}: {script.name} failed: {last}"], [], 0
    now_figs, now_inputs, gaps = parse(proc.stdout)
    problems = []
    for name, old in registered.items():
        new = now_figs.get(name)
        if new is None:
            problems.append(f"{origin}: figure {name} is no longer produced by {script.name}")
        elif _show(new) != _show(old):
            problems.append(f"{origin}: figure {name} does not reproduce: registered "
                            f"{_show(old)}, rerun gives {_show(new)}")
    notes = [f"{origin}: {g}" for g in gaps]
    changed = [ref for ref, digest in reg_inputs.items() if now_inputs.get(ref, digest) != digest]
    for ref in changed:
        if problems:
            problems.append(f"{origin}: input {ref} changed since the output was registered "
                            "(register the new output and replace the claims that cite it)")
        else:
            notes.append(f"{origin}: input {ref} changed since the output was registered; the "
                         "figures still reproduce")
    figure_problems = len(problems) - (len(changed) if problems else 0)
    return problems, notes, len(registered) - figure_problems


def _figure_of(cdir: Path, claim: dict, index: dict, cache: dict) -> Figure | None:
    from strat import sources

    entry = index.get(claim.get("source") or "")
    if not entry or entry.get("kind") != "analysis" or not claim.get("quote"):
        return None
    if entry["id"] not in cache:
        cache[entry["id"]] = parse(sources.snapshot_text(cdir, entry))[0]
    for fig in cache[entry["id"]].values():
        if sources.quote_found(fig.line, claim["quote"]):
            return fig
    return None


def conclusion_problems(cdir: Path, only_sources: set[str] | None = None) -> list[str]:
    """Conclusions that combine figures of one unit family at different scales or periods."""
    from strat import ledger, sources

    claims = ledger.by_id(ledger.load(cdir))
    index = {e["id"]: e for e in sources.index(cdir)}
    cache: dict = {}
    problems = []
    for c in claims.values():
        if c.get("type") != "conclusion" or c.get("status") == "withdrawn":
            continue
        seen, stack, figs = set(), list(c.get("supports", [])), []
        while stack:
            cid = stack.pop()
            if cid in seen or cid not in claims:
                continue
            seen.add(cid)
            stack += claims[cid].get("supports", [])
            fig = _figure_of(cdir, claims[cid], index, cache)
            if fig:
                figs.append((cid, claims[cid]["source"], fig))
        if only_sources is not None and not any(s in only_sources for _, s, _ in figs):
            continue
        for i, (ca, _, a) in enumerate(figs):
            for cb, _, b in figs[i + 1:]:
                fa, fb = _FAMILY.get(a.unit), _FAMILY.get(b.unit)
                if a.unit != b.unit and fa and fb and fa[0] == fb[0]:
                    why = f"one quantity at different scales ({a.unit} vs {b.unit})"
                elif a.unit == b.unit and granularity(a.period) != granularity(b.period):
                    why = (f"the same unit over a {granularity(a.period)} and a "
                           f"{granularity(b.period)}")
                else:
                    continue
                problems.append(f"{c['id']}: combines {ca} {_describe(a)} and {cb} "
                                f"{_describe(b)}: {why}; restate one so both share a definition")
    return problems


def check(source_id: str | None = None, all_: bool = False, case: str | None = None,
          as_json: bool = False) -> int:
    """Rerun the scripts behind analysis outputs; report figures that do not reproduce, gaps,
    and conclusions that combine mismatched figures."""
    from strat import sources
    from strat.core import FAILED, StratError, case_path, emit, warn

    cdir = case_path(case)
    if bool(source_id) == bool(all_):
        raise StratError("give one source id (S001) or --all")
    if all_:
        targets = [e for e in sources.index(cdir) if e.get("kind") == "analysis"]
    else:
        entry = sources.get(cdir, source_id)
        if entry is None:
            raise StratError(f"unknown source {source_id}")
        targets = [entry]
    problems, gaps, lines = [], [], []
    for entry in targets:
        p, g, n = check_source(cdir, entry)
        problems += p
        gaps += g
        if not p:
            lines.append(f"{entry['id']} {entry['origin']}: {n} figures reproduced")
    problems += conclusion_problems(cdir, None if all_ else {t["id"] for t in targets})
    if gaps:
        lines.append("empty cells the scripts read (say so in every claim that uses them):")
        lines += [f"  gap: {g}" for g in gaps]
    if not targets:
        lines.append("no analysis outputs registered")
    emit("\n".join(lines) or "nothing to report",
         {"ok": not problems, "problems": problems, "gaps": gaps,
          "checked": [t["id"] for t in targets]}, as_json)
    for p in problems:
        warn(p)
    return FAILED if problems else 0
