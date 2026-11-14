"""Claim ledger: add, check, list, replace, withdraw, confirm; staleness, importance, claims.md.

Rules enforced here, not in a prompt:
- a `fact` needs a registered source, a `where`, a quote that passes the quote check and an
  `as_of`; it can never rest on a `conclusion` or a `synthetic` claim;
- a `conclusion` must name the claims it rests on (`supports`);
- nothing is deleted: replace and withdraw change the status, confirm keeps the history.
Staleness is computed from `as_of` and config/shelf-life.yaml each time, so it is never out of
date; importance ("load-bearing") is computed from the case documents.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from pathlib import Path

from strat import sources
from strat.core import (
    StratError,
    case_path,
    emit,
    load_config,
    now,
    read_jsonl,
    today,
    write_jsonl,
)

TYPES = ["fact", "hypothesis", "forecast", "assumption", "gap", "synthetic", "conclusion"]
TYPE_RU = {"fact": "Факты", "hypothesis": "Гипотезы", "forecast": "Прогнозы",
           "assumption": "Допущения", "gap": "Пробелы", "synthetic": "Синтетические данные",
           "conclusion": "Выводы"}
STATUS_RU = {"active": "действует", "stale": "устарело", "replaced": "заменено",
             "withdrawn": "отозвано"}
NOT_A_FACT_BASE = {"conclusion", "synthetic"}
CLAIM_ID = re.compile(r"^C\d{3,}$")
CITATION = re.compile(r"\[\s*(C\d{3,}(?:\s*,\s*C\d{3,})*)\s*\]")
AS_OF = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?|-Q([1-4]))?$")
LOAD_BEARING_FILES = ["decisions.md", "product.md", "comms.md", "verification.md"]


# --- storage ----------------------------------------------------------------------------------

def load(cdir: Path) -> list[dict]:
    return read_jsonl(cdir / "claims.jsonl")


def save(cdir: Path, claims: list[dict]) -> None:
    write_jsonl(cdir / "claims.jsonl", claims)
    render_md(cdir, claims)


def by_id(claims: list[dict]) -> dict[str, dict]:
    return {c["id"]: c for c in claims}


def cited_ids(text: str) -> list[str]:
    ids = []
    for match in CITATION.finditer(text):
        ids += [i.strip() for i in match.group(1).split(",")]
    return ids


# --- shelf life -------------------------------------------------------------------------------

def shelf_life() -> dict:
    return load_config("shelf-life")


def period_end(as_of: str) -> date:
    m = AS_OF.match(as_of or "")
    if not m:
        raise StratError(f"bad --as-of {as_of!r}: use YYYY, YYYY-MM, YYYY-MM-DD or YYYY-Qn")
    year, month, day, quarter = m.groups()
    y = int(year)
    if quarter:
        month = str(int(quarter) * 3)
    if not month:
        return date(y, 12, 31)
    mo = int(month)
    if not 1 <= mo <= 12:
        raise StratError(f"bad --as-of {as_of!r}: month out of range")
    try:
        return date(y, mo, int(day)) if day else date(y, mo, calendar.monthrange(y, mo)[1])
    except ValueError:
        raise StratError(f"bad --as-of {as_of!r}: no such date") from None


def is_stale(claim: dict, life: dict, on: date | None = None) -> bool:
    days = life.get(claim.get("kind"))
    if days is None or not claim.get("as_of"):
        return False
    return (on or today()) - period_end(claim["as_of"]) > timedelta(days=int(days))


def status_of(claim: dict, life: dict) -> str:
    """Stored status, with `stale` computed for active claims."""
    if claim["status"] == "active" and is_stale(claim, life):
        return "stale"
    return claim["status"]


# --- importance -------------------------------------------------------------------------------

def _recommendation_section(text: str) -> str:
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith("#"):
            inside = "рекомендац" in line.casefold()
            continue
        if inside:
            out.append(line)
    return "\n".join(out)


def load_bearing_ids(cdir: Path, claims: list[dict]) -> list[str]:
    """Claims cited by live decisions, the chosen option, strategies or open questions, plus
    every claim reachable from them through `supports`."""
    roots: list[str] = []
    for name in LOAD_BEARING_FILES:
        f = cdir / name
        if f.is_file():
            roots += cited_ids(f.read_text(encoding="utf-8"))
    options = cdir / "options.md"
    if options.is_file():
        roots += cited_ids(_recommendation_section(options.read_text(encoding="utf-8")))
    plan = cdir / "plan.md"
    if plan.is_file():
        for line in plan.read_text(encoding="utf-8").splitlines():
            if re.match(r"^\s*[-*]\s+\[ \]", line):
                roots += cited_ids(line)
    index = by_id(claims)
    seen: set[str] = set()
    stack = [r for r in roots if r in index]
    while stack:
        cid = stack.pop()
        if cid in seen:
            continue
        seen.add(cid)
        stack += [s for s in index[cid].get("supports", []) if s in index]
    return sorted(seen, key=lambda i: int(i[1:]))


# --- claims.md --------------------------------------------------------------------------------

def _cell(value) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def render_md(cdir: Path, claims: list[dict]) -> None:
    life = shelf_life()
    bearing = set(load_bearing_ids(cdir, claims))
    titles = {s["id"]: s.get("title", "") for s in sources.index(cdir)}
    lines = ["# Утверждения", "",
             "> Сгенерировано командой `strat claim list` из claims.jsonl. Не редактировать "
             "вручную.", "",
             f"> Всего: {len(claims)}. Опорные (на них стоят решения и стратегии) отмечены "
             "звёздочкой.", ""]
    for type_ in TYPES:
        group = [c for c in claims if c["type"] == type_]
        if not group:
            continue
        lines += [f"## {TYPE_RU[type_]}", "",
                  "| id | утверждение | источник | где | цитата | на дату | статус |",
                  "|---|---|---|---|---|---|---|"]
        for c in group:
            src = c.get("source") or ""
            if src in titles:
                src = f"{src} {titles[src]}"
            star = " *" if c["id"] in bearing else ""
            lines.append(f"| {c['id']}{star} | {_cell(c['text'])} | {_cell(src)} | "
                         f"{_cell(c.get('where'))} | {_cell(c.get('quote'))} | "
                         f"{_cell(c.get('as_of'))} | {STATUS_RU[status_of(c, life)]} |")
        lines.append("")
    (cdir / "claims.md").write_text("\n".join(lines), encoding="utf-8")


# --- commands ---------------------------------------------------------------------------------

def _check_supports(claims: list[dict], ids: list[str], type_: str) -> None:
    index = by_id(claims)
    for sid in ids:
        if sid not in index:
            raise StratError(f"--supports {sid}: no such claim")
        target = index[sid]
        if target["status"] == "withdrawn":
            raise StratError(f"--supports {sid}: the claim is withdrawn")
        if type_ == "fact" and target["type"] in NOT_A_FACT_BASE:
            raise StratError(f"{sid} is a {target['type']}: a {target['type']} can never be the "
                             "source of a fact")


def add(type_: str, kind: str, text: str, case: str | None = None, source: str | None = None,
        where: str | None = None, quote: str | None = None, as_of: str | None = None,
        supports: str | None = None, step: str | None = None, as_json: bool = False) -> int:
    """Add one claim after the type and source rules."""
    from strat.state import log_action, replay

    cdir = case_path(case)
    if replay(cdir, step, as_json, "claim add"):
        return 0
    life = shelf_life()
    if type_ not in TYPES:
        raise StratError(f"unknown --type {type_!r}; types: {', '.join(TYPES)}")
    if kind not in life:
        raise StratError(f"unknown --kind {kind!r}; kinds: {', '.join(life)}")
    if not text.strip():
        raise StratError("--text is empty")
    claims = load(cdir)
    support_ids = [s.strip() for s in (supports or "").split(",") if s.strip()]
    _check_supports(claims, support_ids, type_)
    if as_of:
        period_end(as_of)
    if source and CLAIM_ID.match(source):
        target = by_id(claims).get(source)
        if target and target["type"] in NOT_A_FACT_BASE:
            raise StratError(f"{source} is a {target['type']}: a {target['type']} can never be "
                             "the source of a fact; cite the claims it rests on via --supports")
        raise StratError(f"--source must be a source id (S001), not a claim; use --supports "
                         f"{source}")
    if type_ == "fact":
        missing = [n for n, v in (("source", source), ("where", where), ("quote", quote),
                                  ("as-of", as_of)) if not v]
        if missing:
            raise StratError("a fact needs --" + ", --".join(missing) + "; without a source it "
                             "is an assumption or a gap")
    if type_ == "conclusion" and not support_ids:
        raise StratError("a conclusion needs --supports: the claims it rests on")
    check = {"quote": None, "supported": None, "by": None}
    if source:
        if not sources.SOURCE_ID.match(source) or sources.get(cdir, source) is None:
            raise StratError(f"unknown source {source}: register it with `strat source add` or "
                             "`strat read` first")
        if quote:
            ok, label = sources.check_located_quote(cdir, source, where, quote)
            if not ok:
                raise StratError(f"quote not found in {label}: copy it exactly from "
                                 f"{sources.get(cdir, source)['snapshot']}")
            check["quote"] = True
    cid = f"C{len(claims) + 1:03d}"
    claim = {"id": cid, "text": text.strip(), "type": type_, "kind": kind, "source": source,
             "where": where, "quote": quote, "as_of": as_of, "status": "active",
             "supports": support_ids, "replaced_by": None, "check": check, "added": now()}
    claims.append(claim)
    save(cdir, claims)
    if step:
        log_action(cdir, step=step, tool="claim add", in_=source or "", out="claims.jsonl",
                   ref=cid)
    emit(f"added {cid} ({type_})", {"id": cid, "replayed": False, "claim": claim}, as_json)
    return 0


def check(claim_id: str | None = None, case: str | None = None, all_: bool = False,
          as_json: bool = False) -> int:
    """Quote check, then the support judgment."""
    cdir = case_path(case)
    claims = load(cdir)
    if not all_ and not claim_id:
        raise StratError("give a claim id or --all")
    targets = claims if all_ else [c for c in claims if c["id"] == claim_id]
    if not targets:
        raise StratError(f"no such claim: {claim_id}")
    results, failed = [], 0
    for c in targets:
        if c.get("source") and c.get("quote"):
            try:
                ok = sources.check_located_quote(cdir, c["source"], c.get("where"),
                                                 c["quote"])[0]
            except StratError:
                ok = False
            c["check"]["quote"] = ok
            failed += not ok
        results.append({"id": c["id"], "quote": c["check"]["quote"],
                        "supported": c["check"]["supported"], "by": c["check"]["by"]})
    save(cdir, claims)
    lines = [f"{r['id']}: quote {'ok' if r['quote'] else 'FAILED' if r['quote'] is False else '-'}"
             for r in results]
    lines.append("support judgment: no judge in this version; read the quote against the "
                 "claim yourself and report it as your own assessment")
    emit("\n".join(lines), {"results": results, "failed": failed}, as_json)
    return 1 if failed else 0


def list_claims(case: str | None = None, type_: str | None = None, load_bearing: bool = False,
                stale: bool = False, as_json: bool = False) -> int:
    """List claims with filters and regenerate claims.md."""
    cdir = case_path(case)
    claims = load(cdir)
    render_md(cdir, claims)
    life = shelf_life()
    bearing = set(load_bearing_ids(cdir, claims)) if load_bearing else None
    rows = []
    for c in claims:
        view = dict(c, status=status_of(c, life))
        if type_ and c["type"] != type_:
            continue
        if bearing is not None and c["id"] not in bearing:
            continue
        if stale and view["status"] != "stale":
            continue
        rows.append(view)
    text = "\n".join(f"{c['id']} [{c['type']}/{c['status']}] {c['text']}"
                     + (f"  ({c['source']}, {c['where']})" if c.get("source") else "")
                     for c in rows) or "no claims match"
    emit(text + "\nclaims.md regenerated", rows, as_json)
    return 0


def _get(claims: list[dict], cid: str) -> dict:
    for c in claims:
        if c["id"] == cid:
            return c
    raise StratError(f"no such claim: {cid}")


def replace(old: str, new: str, case: str | None = None, as_json: bool = False) -> int:
    """Mark old as replaced by new."""
    cdir = case_path(case)
    claims = load(cdir)
    o, n = _get(claims, old), _get(claims, new)
    if old == new or n["status"] != "active":
        raise StratError(f"{new} must be a different, active claim")
    o["status"], o["replaced_by"] = "replaced", new
    save(cdir, claims)
    emit(f"{old} replaced by {new}", {"id": old, "replaced_by": new}, as_json)
    return 0


def withdraw(claim_id: str, reason: str, case: str | None = None, as_json: bool = False) -> int:
    """Withdraw a claim; nothing is deleted."""
    cdir = case_path(case)
    claims = load(cdir)
    c = _get(claims, claim_id)
    c["status"], c["reason"] = "withdrawn", reason
    save(cdir, claims)
    emit(f"{claim_id} withdrawn", {"id": claim_id, "status": "withdrawn"}, as_json)
    return 0


def confirm(claim_id: str, source: str, where: str, quote: str, as_of: str,
            case: str | None = None, as_json: bool = False) -> int:
    """Re-confirm a stale claim with a newer source."""
    cdir = case_path(case)
    claims = load(cdir)
    c = _get(claims, claim_id)
    if c["status"] in ("replaced", "withdrawn"):
        raise StratError(f"{claim_id} is {c['status']}; add a new claim instead")
    if c.get("as_of") and period_end(as_of) <= period_end(c["as_of"]):
        raise StratError(f"--as-of {as_of} is not newer than {c['as_of']}")
    if sources.get(cdir, source) is None:
        raise StratError(f"unknown source {source}")
    ok, label = sources.check_located_quote(cdir, source, where, quote)
    if not ok:
        raise StratError(f"quote not found in {label}")
    c.setdefault("history", []).append({k: c.get(k) for k in ("source", "where", "quote",
                                                              "as_of")} | {"until": now()})
    c.update(source=source, where=where, quote=quote, as_of=as_of, status="active")
    c["check"]["quote"] = True
    save(cdir, claims)
    emit(f"{claim_id} confirmed as of {as_of}", {"id": claim_id, "as_of": as_of}, as_json)
    return 0
