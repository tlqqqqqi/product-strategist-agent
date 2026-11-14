"""Review after the decision: due checks, fired review conditions, stale and contradicted
load-bearing claims, and the impact of a claim on conclusions and document lines.

The decision record is `decisions.md` (template: knowledge/templates/decision-record.md). The
LAST "## Решение ..." section is the live decision; earlier ones are history. Machine-readable
parts of it:
- `- Дата проверки: YYYY-MM-DD` - the check date; due when today >= that date. A missing or
  non-ISO date is reported as a question.
- `- Условия пересмотра: ...` and its indented sub-bullets - one condition each. A condition
  fires when an ISO date written on its line has passed, or when a claim it cites is
  contradicted, replaced, withdrawn or stale.
Contradictions are the `contradiction` judgments stored on claims by `strat judge`; the latest
judgment on a pair wins, and a pair stops counting once either claim is replaced or withdrawn.

Module-level imports are standard library only: `strat state` (and the session-start hook)
imports this module. Shelf life needs PyYAML and is skipped with a note when it is missing.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from strat.core import StratError, case_path, emit, read_json, today

MAX_QUESTIONS = 3
DOCS = ["table.md", "options.md", "product.md", "comms.md", "verification.md", "memo.md",
        "decisions.md", "plan.md"]
MONITORING = ("monitoring", "revision")
CITATION = re.compile(r"\[\s*(C\d{3,}(?:\s*,\s*C\d{3,})*)\s*\]")
ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
CHECK_LINE = re.compile(r"^\s*[-*]\s+Дата проверки\s*:\s*(.*)$", re.I)
COND_LINE = re.compile(r"^\s*[-*]\s+Условия пересмотра\s*:\s*(.*)$", re.I)
TOP_BULLET = re.compile(r"^[-*]\s+")
SUB_BULLET = re.compile(r"^\s+[-*]\s+(.*)$")
GONE = ("replaced", "withdrawn")


def _num(cid: str) -> int:
    return int(cid[1:])


def cited(text: str) -> list[str]:
    ids: list[str] = []
    for m in CITATION.finditer(text):
        ids += [i.strip() for i in m.group(1).split(",")]
    return ids


def _date(text: str) -> date | None:
    m = ISO_DATE.search(text)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


# --- impact ------------------------------------------------------------------------------------

def dependents(claims: list[dict], cid: str) -> list[str]:
    """Every claim that rests on `cid` through `supports`, transitively."""
    users: dict[str, list[str]] = {}
    for c in claims:
        for s in c.get("supports") or []:
            users.setdefault(s, []).append(c["id"])
    seen: set[str] = set()
    stack = list(users.get(cid, []))
    while stack:
        x = stack.pop()
        if x in seen or x == cid:
            continue
        seen.add(x)
        stack += users.get(x, [])
    return sorted(seen, key=_num)


def citing_lines(cdir: Path, ids: set[str]) -> list[dict]:
    """Lines of the case documents that cite any of `ids`."""
    rows = []
    for name in DOCS:
        path = cdir / name
        if not path.is_file():
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            hit = sorted(set(cited(line)) & ids, key=_num)
            if hit:
                rows.append({"file": name, "line": n, "text": line.strip()[:240], "cites": hit})
    return rows


def impact_of(cdir: Path, claims: list[dict], cid: str) -> dict:
    if cid not in {c["id"] for c in claims}:
        raise StratError(f"no such claim: {cid}")
    deps = dependents(claims, cid)
    return {"claim": cid, "conclusions": deps, "lines": citing_lines(cdir, {cid, *deps})}


# --- decision record ---------------------------------------------------------------------------

def live_decision(cdir: Path) -> dict | None:
    """The last "## Решение" section of decisions.md: title, check date, conditions."""
    path = cdir / "decisions.md"
    if not path.is_file():
        return None
    sections: list[tuple[str, list[str]]] = []
    current: list[str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            current = None
            if line[3:].strip().casefold().startswith("решение"):
                current = []
                sections.append((line[3:].strip(), current))
            continue
        if current is not None:
            current.append(line)
    if not sections:
        return None
    title, body = sections[-1]
    found_check, check_raw, conditions, in_cond = False, "", [], False
    for line in body:
        m = CHECK_LINE.match(line)
        if m:
            found_check, check_raw, in_cond = True, m.group(1).strip(), False
            continue
        m = COND_LINE.match(line)
        if m:
            in_cond = True
            head = m.group(1).strip()
            if cited(head) or _date(head):
                conditions.append(head)
            continue
        if in_cond:
            sm = SUB_BULLET.match(line)
            if sm:
                conditions.append(sm.group(1).strip())
            elif TOP_BULLET.match(line) or (line.strip() and not line.startswith((" ", "\t"))):
                in_cond = False
    return {"title": title, "has_check": found_check, "check_raw": check_raw,
            "check": _date(check_raw) if found_check else None,
            "conditions": [{"text": t, "cites": cited(t), "date": _date(t)} for t in conditions]}


# --- contradictions ----------------------------------------------------------------------------

def contradicted_pairs(claims: list[dict]) -> list[tuple[str, str]]:
    """Pairs whose latest contradiction judgment is yes and whose claims are both still live."""
    index = {c["id"]: c for c in claims}
    latest: dict[frozenset, tuple[str, str, str]] = {}
    for c in claims:
        for j in (c.get("check") or {}).get("judgments", []):
            if j.get("question") != "contradiction" or not j.get("other") or j.get("escalated"):
                continue
            key = frozenset((c["id"], j["other"]))
            at = j.get("at") or ""
            if key not in latest or at >= latest[key][0]:
                latest[key] = (at, j.get("answer") or "", c["id"])
    pairs = []
    for key, (_, answer, _) in latest.items():
        if answer != "yes" or len(key) != 2 or not key <= index.keys():
            continue
        a, b = sorted(key, key=_num)
        if index[a]["status"] in GONE or index[b]["status"] in GONE:
            continue
        pairs.append((a, b))
    return sorted(pairs, key=lambda p: (_num(p[0]), _num(p[1])))


# --- the review --------------------------------------------------------------------------------

def collect(cdir: Path) -> dict:
    """Everything the review reports, plus at most MAX_QUESTIONS questions for the user."""
    from strat import ledger

    claims = ledger.load(cdir)
    index = ledger.by_id(claims)
    bearing = set(ledger.load_bearing_ids(cdir, claims))
    notes: list[str] = []
    try:
        life = ledger.shelf_life()
        status = {c["id"]: ledger.status_of(c, life) for c in claims}
    except ImportError:
        life = None
        status = {c["id"]: c["status"] for c in claims}
        notes.append("stale claims not computed here (no PyYAML): run bin/strat review")
    on = today()

    contradicted = []
    against: dict[str, str] = {}
    for a, b in contradicted_pairs(claims):
        if a in bearing:
            old, new = a, b
        elif b in bearing:
            old, new = b, a
        else:
            continue
        against.setdefault(old, new)
        hit = impact_of(cdir, claims, old)
        contradicted.append({"claim": old, "by": new, "claim_text": index[old]["text"],
                             "by_text": index[new]["text"], **{k: hit[k] for k in
                                                               ("conclusions", "lines")}})

    stale = [{"id": i, "text": index[i]["text"], "kind": index[i].get("kind"),
              "as_of": index[i].get("as_of")}
             for i in sorted(bearing, key=_num) if status.get(i) == "stale"]

    due = []
    decision = live_decision(cdir)
    if decision is not None:
        if decision["check"] is None:
            due.append({"what": "check", "date": None, "text": decision["check_raw"],
                        "reason": "the check date is missing or not a YYYY-MM-DD date"})
        elif decision["check"] <= on:
            due.append({"what": "check", "date": decision["check"].isoformat(),
                        "text": decision["title"], "reason": "the check date has passed"})
        for cond in decision["conditions"]:
            reasons = []
            if cond["date"] and cond["date"] <= on:
                reasons.append(f"its date {cond['date'].isoformat()} has passed")
            for cid in cond["cites"]:
                if cid in against:
                    reasons.append(f"{cid} is contradicted by {against[cid]}")
                elif status.get(cid) in ("stale", *GONE):
                    reasons.append(f"{cid} is {status[cid]}")
            if reasons:
                due.append({"what": "condition",
                            "date": cond["date"].isoformat() if cond["date"] else None,
                            "text": cond["text"], "cites": cond["cites"],
                            "reason": "; ".join(reasons)})

    return {"decision": decision["title"] if decision else None, "due": due,
            "contradicted": contradicted, "stale": stale, "notes": notes,
            "questions": questions(due, contradicted, stale)}


def questions(due: list[dict], contradicted: list[dict], stale: list[dict]) -> list[dict]:
    """The most important first; never more than MAX_QUESTIONS."""
    out = []
    for c in contradicted:
        concl = ", ".join(c["conclusions"]) or "no conclusions"
        out.append({"kind": "contradiction", "about": [c["claim"], c["by"]],
                    "text": f"Load-bearing {c['claim']} ({c['claim_text']}) is contradicted by "
                            f"newer {c['by']} ({c['by_text']}). It affects {concl} and "
                            f"{len(c['lines'])} document line(s). Revise the decision, or keep "
                            "it and record why?"})
    asked = {q["about"][0] for q in out}
    for d in due:
        if d["what"] == "condition":
            if all(any(r.startswith(f"{a} is contradicted") for a in asked)
                   for r in d["reason"].split("; ")):
                continue
            out.append({"kind": "condition", "about": d["cites"],
                        "text": f"Review condition \"{d['text']}\" has fired ({d['reason']}). "
                                "Is the decision still right?"})
        elif d["date"] is None:
            out.append({"kind": "check", "about": [],
                        "text": "The decision record has no machine-readable check date "
                                "(YYYY-MM-DD). When should the decision be reviewed?"})
        else:
            out.append({"kind": "check", "about": [],
                        "text": f"The decision's check date {d['date']} has passed. Review it "
                                "now, or set a new check date?"})
    if stale:
        ids = [s["id"] for s in stale]
        out.append({"kind": "stale", "about": ids,
                    "text": f"Load-bearing claims {', '.join(ids)} are stale (past their shelf "
                            "life). Bring newer data, keep them as history, or record gaps?"})
    return out[:MAX_QUESTIONS]


def due_for_state(cdir: Path) -> list[dict]:
    """Short due list for `strat state` at stage monitoring or revision."""
    if read_json(cdir / "state.json").get("stage") not in MONITORING:
        return []
    data = collect(cdir)
    items = [dict(d) for d in data["due"]]
    items += [{"what": "contradiction", "date": None,
               "text": f"{c['claim']} contradicted by {c['by']}",
               "reason": f"affects {', '.join(c['conclusions']) or 'no conclusions'}"}
              for c in data["contradicted"]]
    if data["stale"]:
        items.append({"what": "stale", "date": None,
                      "text": ", ".join(s["id"] for s in data["stale"]),
                      "reason": "load-bearing claims past their shelf life"})
    items += [{"what": "note", "date": None, "text": n, "reason": "partial check"}
              for n in data["notes"]]
    return items


def review(case: str | None = None, as_json: bool = False) -> int:
    """Report what is due, what is stale and what is contradicted; at most 3 questions."""
    cdir = case_path(case)
    data = collect(cdir)
    lines = [f"decision: {data['decision'] or 'none recorded (no ## Решение in decisions.md)'}"]
    lines.append("due:" if data["due"] else "due: nothing")
    for d in data["due"]:
        lines.append(f"  - {d['what']}{' ' + d['date'] if d['date'] else ''}: {d['text']} "
                     f"({d['reason']})")
    lines.append("contradicted load-bearing claims:" if data["contradicted"]
                 else "contradicted load-bearing claims: none")
    for c in data["contradicted"]:
        lines.append(f"  - {c['claim']} by {c['by']}; conclusions: "
                     f"{', '.join(c['conclusions']) or '-'}")
        lines += [f"      {r['file']}:{r['line']}: {r['text']}" for r in c["lines"]]
    lines.append("stale load-bearing claims: " + (", ".join(
        f"{s['id']} (as of {s['as_of']})" for s in data["stale"]) or "none"))
    lines += [f"note: {n}" for n in data["notes"]]
    if data["questions"]:
        lines.append(f"questions for the user (at most {MAX_QUESTIONS}, ask in Russian):")
        lines += [f"  {i}. {q['text']}" for i, q in enumerate(data["questions"], 1)]
        lines.append("propose an update and wait for the user's yes (skills/revise); never "
                     "rewrite the decision on your own")
    else:
        lines.append("questions for the user: none")
    emit("\n".join(lines), data, as_json)
    return 0
