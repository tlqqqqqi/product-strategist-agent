"""New material after a decision (`strat ingest`) and the impact of a claim (`strat impact`).

`ingest` registers the file exactly as `strat source add` does (same snapshot, same S id rules),
but only once the decision is signed off (gate 3 approved). It moves the case to stage
`revision` and prints what the agent must do next: turn the material into claims, check them
for contradictions against the load-bearing claims, list the impact, propose an update. The CLI
never rewrites a decision; that needs the user's yes (skills/revise).
"""

from __future__ import annotations

from pathlib import Path

from strat.core import StratError, case_path, emit, read_jsonl


def ingest(path: str, case: str | None = None, title: str | None = None,
           step: str | None = None, as_json: bool = False) -> int:
    """Register new material after a decision; the case moves to revision."""
    from strat import convert as conv
    from strat import ledger, sources
    from strat.state import load, log_action, replay, save

    cdir = case_path(case)
    if replay(cdir, step, as_json, "ingest"):
        return 0
    state = load(cdir)
    if state["gates"].get("3") != "approved":
        raise StratError("no signed-off decision yet (gate 3 is not approved): register "
                         "material with `strat source add`")
    src = Path(path)
    if not src.is_absolute():
        src = cdir / path if (cdir / path).exists() else Path.cwd() / path
    if not src.is_file():
        raise StratError(f"{path}: file not found")
    src = sources.into_materials(cdir, src)
    text = conv.convert(str(src))
    origin = str(src.relative_to(cdir.resolve()))
    entry = sources.register(cdir, kind="file", origin=origin, title=title or src.name,
                             text=text, digest=sources.sha256(src.read_bytes()),
                             fmt=conv.fmt_of(src))
    sid = entry["id"]
    claims = ledger.load(cdir)
    bearing = ledger.load_bearing_ids(cdir, claims)
    index = ledger.by_id(claims)

    if state["stage"] != "revision":
        state["stage"] = "revision"
    state["next"] = (f"Revision: turn {sid} into claims, check them against the load-bearing "
                     "claims, list the impact, propose an update for the user's yes "
                     "(skills/revise)")
    save(cdir, state)
    logged = any(r.get("tool") == "ingest" and r.get("ref") == sid and r.get("status") == "ok"
                 for r in read_jsonl(cdir / "log.jsonl"))
    if not logged or step:
        log_action(cdir, step=step or f"ingest.{sid}", tool="ingest", stage="revision",
                   in_=origin, out=entry["snapshot"], ref=sid)

    next_steps = [
        f"read {entry['snapshot']}; add one claim per new finding: bin/strat claim add "
        f"--source {sid} --where ... --quote ... --as-of ...",
        "for each new claim on the same subject as a load-bearing claim: bin/strat judge "
        "contradiction --claim <new> --other <load-bearing>",
        "for each contradicted claim: bin/strat impact <id>",
        "bin/strat review; propose the update to the user and wait for a yes (skills/revise)",
    ]
    verb = "already registered as" if entry.get("existing") else "registered as"
    flags = entry.get("flags", [])
    lines = [f"{origin} {verb} {sid}; snapshot: {entry['snapshot']}; stage: revision"]
    if flags:
        lines.append(sources.FLAG_NOTE.format(sid=sid))
    lines.append("load-bearing claims to check the new material against:" if bearing
                 else "load-bearing claims: none")
    lines += [f"  {i} [{index[i]['type']}] {index[i]['text']}" for i in bearing]
    lines.append("next (skills/revise):")
    lines += [f"  {n}. {s}" for n, s in enumerate(next_steps, 1)]
    emit("\n".join(lines),
         {"id": sid, "snapshot": entry["snapshot"], "origin": origin,
          "existing": bool(entry.get("existing")), "flags": flags, "replayed": False,
          "stage": "revision", "load_bearing": bearing, "next_steps": next_steps}, as_json)
    return 0


def impact(claim_id: str, case: str | None = None, as_json: bool = False) -> int:
    """Conclusions that rest on a claim (transitively) and the document lines citing them."""
    from strat import ledger
    from strat.review import impact_of

    cdir = case_path(case)
    data = impact_of(cdir, ledger.load(cdir), claim_id)
    lines = [f"{claim_id}: conclusions resting on it: {', '.join(data['conclusions']) or 'none'}"]
    lines.append("lines citing it or those conclusions:" if data["lines"]
                 else "no document line cites it or those conclusions")
    lines += [f"  {r['file']}:{r['line']}: [{', '.join(r['cites'])}] {r['text']}"
              for r in data["lines"]]
    emit("\n".join(lines), data, as_json)
    return 0
