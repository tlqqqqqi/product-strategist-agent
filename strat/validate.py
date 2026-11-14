"""Gate checks: citations, sourced facts, required files and headings, verdicts.

Citation unit: every bullet (with its indented continuation lines), every table data row and
every paragraph must cite at least one claim. Exempt: headings, blank lines, table header and
separator rows, lines starting with `>`, fenced code. A cited id must exist, must not be
withdrawn and must not be stale. Errors read `<file>:<line>: <reason>`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from strat import ledger, sources
from strat.core import FAILED, StratError, case_path, emit, read_jsonl, root
from strat.state import load as load_state
from strat.state import save as save_state

CHECKED = {"options.md", "product.md", "comms.md", "verification.md", "memo.md"}
TEMPLATE_OF = {"brief.md": "brief", "plan.md": "plan", "table.md": "table",
               "options.md": "options", "product.md": "product", "comms.md": "comms",
               "verification.md": "verification", "memo.md": "memo"}
GATE_FILES = {
    1: ["brief.md", "plan.md", "table.md", "options.md"],
    2: ["brief.md", "plan.md", "table.md", "options.md"],
    3: ["brief.md", "plan.md", "table.md", "options.md", "product.md", "comms.md",
        "verification.md"],
}
BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
TABLE_ROW = re.compile(r"^\s*\|")
SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
PLACEHOLDER = re.compile(r"<[^<>\n]{2,80}>|\[C\.\.\.\]")


# --- citations --------------------------------------------------------------------------------

def units(lines: list[str]) -> list[tuple[int, str]]:
    """Split a markdown file into citation units: (first line number, text)."""
    out: list[tuple[int, str]] = []
    in_code = False
    current: list | None = None  # [start, text, kind]

    def close():
        nonlocal current
        if current:
            out.append((current[0], current[1]))
        current = None

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            close()
            in_code = not in_code
            continue
        if in_code:
            continue
        if not stripped or stripped.startswith("#") or stripped.startswith(">"):
            close()
            continue
        if TABLE_ROW.match(line):
            close()
            if SEPARATOR.match(line):
                continue
            nxt = lines[i] if i < len(lines) else ""
            if SEPARATOR.match(nxt):  # header row
                continue
            out.append((i, line))
            continue
        if BULLET.match(line):
            close()
            current = [i, line, "bullet"]
            continue
        if current and (current[2] == "paragraph" or line.startswith((" ", "\t"))):
            current[1] += "\n" + line
            continue
        close()
        current = [i, line, "paragraph"]
    close()
    return out


def citation_errors(cdir: Path, name: str, claims: dict, life: dict) -> list[str]:
    path = cdir / name
    lines = path.read_text(encoding="utf-8").splitlines()
    errors = []
    for start, text in units(lines):
        if PLACEHOLDER.search(text):
            errors.append(f"{name}:{start}: template placeholder left in the text")
        ids = ledger.cited_ids(text)
        if not ids:
            errors.append(f"{name}:{start}: no citation; cite a claim [C...] or turn the "
                          "statement into an assumption or gap claim")
            continue
        for cid in ids:
            claim = claims.get(cid)
            if claim is None:
                errors.append(f"{name}:{start}: {cid} does not exist")
                continue
            status = ledger.status_of(claim, life)
            if status in ("withdrawn", "stale"):
                errors.append(f"{name}:{start}: {cid} is {status}")
    return errors


# --- headings ---------------------------------------------------------------------------------

def required_headings(template: str) -> list[str]:
    path = root() / "knowledge" / "templates" / f"{template}.md"
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith("## ")]


def heading_errors(cdir: Path, name: str) -> list[str]:
    template = TEMPLATE_OF.get(name)
    if template is None:
        return []
    lines = (cdir / name).read_text(encoding="utf-8").splitlines()
    errors = []
    for heading in required_headings(template):
        try:
            at = next(i for i, line in enumerate(lines) if line.strip() == heading)
        except StopIteration:
            errors.append(f"{name}: missing heading '{heading}'")
            continue
        body = []
        for line in lines[at + 1:]:
            if line.startswith("## ") or line.startswith("# "):
                break
            if line.strip() and not line.startswith("#"):
                body.append(line)
        if not body:
            errors.append(f"{name}: section '{heading}' is empty")
    return errors


# --- whole-case checks ------------------------------------------------------------------------

def fact_errors(cdir: Path, claims: list[dict]) -> list[str]:
    errors = []
    for c in claims:
        if c["type"] != "fact" or c["status"] in ("withdrawn", "replaced"):
            continue
        if not (c.get("source") and c.get("quote")):
            errors.append(f"claims.jsonl: {c['id']}: a fact without a source and quote")
            continue
        try:
            ok = sources.check_located_quote(cdir, c["source"], c.get("where"), c["quote"])[0]
        except StratError as exc:
            ok, _ = False, exc
        if not ok:
            errors.append(f"claims.jsonl: {c['id']}: quote check failed against {c['source']}")
    return errors


def objection_errors(cdir: Path) -> list[str]:
    return [f"objections.jsonl: {o.get('id', '?')} has no verdict"
            for o in read_jsonl(cdir / "objections.jsonl") if not o.get("verdict")]


def check_file(cdir: Path, name: str) -> list[str]:
    """Checks for one file the agent just wrote (used by `strat step --out`)."""
    name = Path(name).as_posix()
    errors = heading_errors(cdir, name)
    if name in CHECKED:
        claims = ledger.by_id(ledger.load(cdir))
        errors += citation_errors(cdir, name, claims, ledger.shelf_life())
    return errors


def gate_errors(cdir: Path, n: int) -> list[str]:
    state = load_state(cdir)
    errors = [f"state: gate {g} is not approved" for g in range(1, n)
              if state["gates"][str(g)] != "approved"]
    missing = [f for f in GATE_FILES[n] if not (cdir / f).is_file()]
    errors += [f"{f}: missing; write it from knowledge/templates/" for f in missing]
    claims = ledger.load(cdir)
    index, life = ledger.by_id(claims), ledger.shelf_life()
    for f in GATE_FILES[n]:
        if f in missing:
            continue
        errors += heading_errors(cdir, f)
        if f in CHECKED:
            errors += citation_errors(cdir, f, index, life)
    errors += fact_errors(cdir, claims)
    errors += objection_errors(cdir)
    return errors


def gate_check(n: int, case: str | None = None, as_json: bool = False) -> int:
    """Run the checks for gate n; errors as <file>:<line>: <reason>."""
    cdir = case_path(case)
    errors = gate_errors(cdir, n)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        emit(f"gate {n}: {len(errors)} problem(s); fix them and rerun",
             {"gate": n, "passed": False, "errors": errors}, as_json)
        return FAILED
    state = load_state(cdir)
    if state["gates"][str(n)] != "approved":
        state["stage"] = f"gate{n}"
        save_state(cdir, state)
    emit(f"gate {n}: all checks passed; stage: {state['stage']}. Present the gate to the user "
         "and wait for an explicit yes.", {"gate": n, "passed": True, "stage": state["stage"]},
         as_json)
    return 0
