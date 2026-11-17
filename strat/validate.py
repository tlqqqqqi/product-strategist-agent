"""Gate checks: citations, sourced facts, required files and headings, verdicts.

Citation unit: every bullet (with its indented continuation lines), every table data row and
every paragraph must cite at least one claim. Exempt: headings, blank lines, table header and
separator rows, lines starting with `>`, fenced code. A cited id must exist, must not be
withdrawn and must not be stale. Fenced memo blocks (strat/blocks.py) are checked row by row:
each row cites a claim and its numbers appear in that claim. Errors read
`<file>:<line>: <reason>`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from strat import blocks, inbox, ledger, sources
from strat.core import FAILED, StratError, case_path, emit, read_jsonl, root
from strat.state import load as load_state
from strat.state import save as save_state

CHECKED = {"table.md", "options.md", "product.md", "comms.md", "verification.md", "memo.md"}
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
FENCE = ("```", "~~~")
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
        if stripped.startswith(FENCE):
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
    whole = path.read_text(encoding="utf-8")
    lines = whole.splitlines()
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
    return errors + blocks.errors(name, whole, claims, life)


# --- headings ---------------------------------------------------------------------------------

def required_headings(template: str) -> list[str]:
    path = root() / "knowledge" / "templates" / f"{template}.md"
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith("## ")]


def heading_errors(cdir: Path, name: str) -> list[str]:
    template = TEMPLATE_OF.get(name)
    if template is None:
        return []
    lines, in_code = [], False
    for line in (cdir / name).read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(FENCE):
            in_code = not in_code
            lines.append("")
            continue
        lines.append("" if in_code and line.startswith("#") else line)
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


def verdict_errors(claims: list[dict]) -> list[str]:
    """Gates 2 and 3: every active fact carries a settled support verdict (a model's or the
    agent's own), and the latest one says yes."""
    errors = []
    for c in claims:
        if c["type"] != "fact" or c["status"] in ("withdrawn", "replaced"):
            continue
        settled = [j for j in (c.get("check") or {}).get("judgments") or []
                   if j.get("question") == "support" and not j.get("escalated")]
        if not settled:
            errors.append(f"claims.jsonl: {c['id']}: no support verdict; run "
                          f"`bin/strat judge support --claim {c['id']}`")
        elif settled[-1].get("answer") != "yes":
            errors.append(f"claims.jsonl: {c['id']}: the quote does not support the claim "
                          f"(not supported, by {settled[-1].get('by')}); fix the claim or "
                          "replace it, then judge it again")
    return errors


def objection_errors(cdir: Path, n: int = 1) -> list[str]:
    """Every objection has a verdict; at Gate 3 no major or critical one is still open."""
    rows = read_jsonl(cdir / "objections.jsonl")
    errors = [f"objections.jsonl: {o.get('id', '?')} has no verdict"
              for o in rows if not o.get("verdict")]
    if n >= 3:
        errors += [f"objections.jsonl: {o['id']} [{o.get('severity')}] is open: answer it "
                   "(accepted or rejected with a claim), mark it not-chosen if its option was "
                   "not chosen at Gate 2, or ask the user whether they accept the risk and set "
                   "risk-accepted with their words"
                   for o in rows if o.get("verdict") == "open"
                   and o.get("severity") in ("major", "critical")]
    return errors


def accepted_risk_errors(cdir: Path, text: str) -> list[str]:
    """decisions.md names every objection whose risk the user accepted."""
    return [f"decisions.md: {o['id']} is risk-accepted but not named in the decision record; "
            "list it under \"Принятые риски\""
            for o in read_jsonl(cdir / "objections.jsonl")
            if o.get("verdict") == "risk-accepted" and o["id"] not in text]


# --- research reaches the web, widely --------------------------------------------------------
# Models take the cheapest path the checks allow: with "one web question, one search" they
# searched once. The floors below make the research wide; a case may go far beyond them.

QUESTION = re.compile(r"^\s*-\s*\[[ xX]\]\s*Q(\d+)\b(.*)$")
WHERE = re.compile(r"где искать:\s*([^;\[]*)", re.I)
THEME = re.compile(r"тема:\s*([^;\[]*)", re.I)
WEB = re.compile(r"веб|web|интернет|сайт|https?://|страниц", re.I)
OPTION = re.compile(r"^#{2,4}\s*Вариант\s+\d+", re.M)
FLOOR = {"web_questions": 4, "themes": 3, "searches": 4, "kinds": 2, "semantic": 2, "pages": 4,
         "web_facts": 8, "web_sites": 5, "options_gate1": 3, "options_gate2": 4}


def web_questions(cdir: Path) -> dict[int, str]:
    """plan.md questions whose "где искать" names the web -> their theme ("" if none)."""
    path = cdir / "plan.md"
    if not path.is_file():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = QUESTION.match(line)
        where = m and WHERE.search(m.group(2))
        if where and WEB.search(where.group(1)):
            theme = THEME.search(m.group(2))
            out[int(m.group(1))] = theme.group(1).strip().lower() if theme else ""
    return out


def _site(origin: str) -> str:
    from urllib.parse import urlparse

    host = urlparse(origin).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def research_tally(cdir: Path) -> dict[int, dict]:
    """Per research question: searches (ok or failed), kinds of the answered ones, saved pages."""
    tally: dict[int, dict] = {}
    for row in read_jsonl(cdir / "log.jsonl"):
        m = re.match(r"research\.q(\d+)\.", row.get("step") or "")
        if not m:
            continue
        t = tally.setdefault(int(m.group(1)), {"searches": 0, "failed": 0, "kinds": set(),
                                                "semantic": 0, "pages": set()})
        if row.get("tool") == "search" and row.get("status") in ("ok", "error"):
            t["searches"] += 1
            if row["status"] == "error":
                t["failed"] += 1
            elif row.get("out") and (cdir / row["out"]).is_file():
                kind = read_json_safe(cdir / row["out"]).get("kind")
                t["kinds"].add(kind)
                t["semantic"] += kind == "semantic"
        elif row.get("tool") == "read" and row.get("status") == "ok" and row.get("ref"):
            t["pages"].add(row["ref"])
    return tally


def read_json_safe(path: Path) -> dict:
    import json

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def web_errors(cdir: Path, n: int) -> list[str]:
    """Gate 1: wide web questions in the plan and enough options. Gate 2: each web question was
    searched in several ways and its pages saved; the case quotes many facts from many sites."""
    if not (cdir / "plan.md").is_file():
        return []
    errors = []
    qs = web_questions(cdir)
    themes = {t for t in qs.values() if t}
    if len(qs) < FLOOR["web_questions"] or len(themes) < FLOOR["themes"]:
        errors.append(
            f"plan.md: {len(qs)} web question(s) over {len(themes)} theme(s); the plan needs at "
            f"least {FLOOR['web_questions']} questions answered from the web (`где искать: веб, "
            f"<what pages>`) over at least {FLOOR['themes']} themes (`тема: <theme>`); pick "
            "themes from skills/research/references/research-themes.md")
    options = cdir / "options.md"
    count = len(OPTION.findall(options.read_text(encoding="utf-8"))) if options.is_file() else 0
    need = FLOOR["options_gate2" if n >= 2 else "options_gate1"]
    if options.is_file() and count < need:
        errors.append(f"options.md: {count} option(s); gate {n} needs at least {need} "
                      "(\"### Вариант N\"), including one built from what the research found")
    if n < 2:
        return errors
    tally = research_tally(cdir)
    for q in sorted(qs):
        t = tally.get(q, {"searches": 0, "failed": 0, "kinds": set(), "semantic": 0, "pages": set()})
        if t["searches"] and t["failed"] == t["searches"]:
            continue  # every provider failed each time: the question ends as a gap
        short = []
        if t["searches"] < FLOOR["searches"]:
            short.append(f"{t['searches']}/{FLOOR['searches']} searches")
        if len(t["kinds"] - {None}) < FLOOR["kinds"]:
            short.append(f"{len(t['kinds'] - {None})}/{FLOOR['kinds']} search kinds")
        if t["semantic"] < FLOOR["semantic"]:
            short.append(f"{t['semantic']}/{FLOOR['semantic']} semantic searches")
        if len(t["pages"]) < FLOOR["pages"]:
            short.append(f"{len(t['pages'])}/{FLOOR['pages']} saved pages")
        if short:
            errors.append(
                f"plan.md: Q{q} (web) is researched too narrowly: {', '.join(short)}; run more "
                f"`bin/strat search` queries (step research.q{q}.search.<k>, different "
                f"--kind, at least {FLOOR['semantic']} with --kind semantic) and save the pages you use (`bin/strat read <url> --step "
                f"research.q{q}.read.<k>`)")
    srcs = {s["id"]: s for s in sources.index(cdir)}
    web_facts = [c for c in ledger.load(cdir) if c["type"] == "fact"
                 and c["status"] not in ("withdrawn", "replaced")
                 and srcs.get(c.get("source"), {}).get("kind") == "web"]
    sites = {_site(srcs[c["source"]]["origin"]) for c in web_facts}
    if len(web_facts) < FLOOR["web_facts"] or len(sites) < FLOOR["web_sites"]:
        errors.append(
            f"claims.jsonl: {len(web_facts)} fact(s) quoted from web pages, from {len(sites)} "
            f"site(s); gate 2 needs at least {FLOOR['web_facts']} from at least "
            f"{FLOOR['web_sites']} different sites: quote what the saved pages say")
    return errors


# --- seal --------------------------------------------------------------------------------------

def seal_errors(cdir: Path) -> list[str]:
    """Record files must match the hashes the CLI wrote; a hand edit fails the gate."""
    import json

    from strat.core import SEAL, sha256_of

    spath = cdir / SEAL
    if not spath.is_file():
        return [f"{SEAL}: missing; the case record was edited outside bin/strat"]
    from strat.core import SEALED_NAMES

    sealed = json.loads(spath.read_text(encoding="utf-8"))
    present = [p.relative_to(cdir).as_posix() for p in (*cdir.glob("*"), *cdir.glob("sources/*"))
               if p.is_file() and (p.name in SEALED_NAMES
                                   or re.fullmatch(r"sources/S\d{3,}\.md", p.relative_to(cdir).as_posix()))]
    errors = [f"{rel}: not in the seal; the case record was edited outside bin/strat"
              for rel in sorted(set(present) - set(sealed))]
    for rel, digest in sorted(sealed.items()):
        path = cdir / rel
        if not path.is_file() or sha256_of(path) != digest:
            errors.append(f"{rel}: changed outside bin/strat (a hand edit or a script). Undo it: "
                          "change claims only with `strat claim add/replace/withdraw`, verdicts "
                          "with `strat judge` and `strat consult verdict`, sources with "
                          "`strat source add` and `strat read`")
    return errors


def check_file(cdir: Path, name: str) -> list[str]:
    """Checks for one file the agent just wrote (used by `strat step --out`)."""
    name = Path(name).as_posix()
    errors = heading_errors(cdir, name)
    if name == "decisions.md" and (cdir / name).is_file():
        errors += accepted_risk_errors(cdir, (cdir / name).read_text(encoding="utf-8"))
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
    if n >= 2:
        errors += verdict_errors(claims)
    errors += seal_errors(cdir)
    errors += web_errors(cdir, n)
    errors += objection_errors(cdir, n)
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
        if state["stage"] != f"gate{n}" or str(n) not in state.get("ready_at", {}):
            import time

            state.setdefault("ready_at", {})[str(n)] = time.time()  # the user answers after this
        state["stage"] = f"gate{n}"
        if inbox.available():
            state["inbox"] = True  # from now on a missing inbox is an error, not "no hook"
        save_state(cdir, state)
    flagged = [s["id"] for s in sources.index(cdir) if s.get("flags")]
    notes = "".join(f"\nnote: {sid} contains text addressed to AI; mention it to the user"
                    for sid in flagged)
    emit(f"gate {n}: all checks passed; stage: {state['stage']}. Present the gate to the user "
         "and wait for an explicit yes." + notes, {"gate": n, "passed": True, "stage": state["stage"]},
         as_json)
    return 0
