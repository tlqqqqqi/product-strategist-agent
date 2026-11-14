"""Case state and the action log: new, state, step, gate approve.

The log is the resume mechanism. `step` in each line is the idempotency key: a command called
with a step id that already has an `ok` line returns the recorded result and does nothing else.
Order is always: write the output file, then append the log line.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from strat.core import (
    CASE_ID,
    FAILED,
    StratError,
    append_jsonl,
    case_path,
    cases_dir,
    current_case,
    emit,
    load_config,
    now,
    read_json,
    read_jsonl,
    root,
    write_json,
)

STAGES = ["intake", "plan", "gate1", "research", "gate2", "strategy", "gate3", "monitoring",
          "revision"]
# a work stage may be entered only when these gates are approved
REQUIRES = {"intake": [], "plan": [], "research": [1], "strategy": [1, 2],
            "monitoring": [1, 2, 3], "revision": [1, 2, 3]}
AFTER_GATE = {1: "research", 2: "strategy", 3: "monitoring"}
NEXT_AFTER_GATE = {
    1: "Research: answer the plan's questions in order of impact (skills/research)",
    2: "Strategy: product, communication, promise check, verification (skills/strategy)",
    3: "Write the decision record and the memo (skills/signoff, After sign-off)",
}


# --- state file -------------------------------------------------------------------------------

def load(cdir: Path) -> dict:
    return read_json(cdir / "state.json")


def save(cdir: Path, state: dict) -> None:
    state["updated"] = now()
    write_json(cdir / "state.json", state)


# --- log --------------------------------------------------------------------------------------

def find_ok(cdir: Path, step: str) -> dict | None:
    """The last `ok` line for this step id, or None."""
    hit = None
    for row in read_jsonl(cdir / "log.jsonl"):
        if row.get("step") == step and row.get("status") == "ok":
            hit = row
    return hit


def log_action(cdir: Path, *, step: str, tool: str, stage: str | None = None, in_: str = "",
               out: str = "", tokens_in: int = 0, tokens_out: int = 0, usd: float = 0.0,
               status: str = "ok", note: str = "", sec: float = 0.0, ref: str = "") -> dict:
    """Append one log line and add its cost to the budget. Call after the output is written."""
    state = load(cdir)
    row = {"step": step, "ts": now(), "stage": stage or state["stage"], "tool": tool,
           "in": in_, "out": out, "tokens_in": tokens_in, "tokens_out": tokens_out,
           "usd": round(usd, 6), "status": status, "note": note, "sec": round(sec, 3)}
    if ref:
        row["ref"] = ref  # the id this step created (S or C id), returned on replay
    append_jsonl(cdir / "log.jsonl", row)
    if usd:
        state["budget"]["spent_usd"] = round(state["budget"]["spent_usd"] + usd, 6)
        save(cdir, state)
    return row


def replay(cdir: Path, step: str | None, as_json: bool, tool: str) -> bool:
    """If `step` is already done, print its recorded result and return True.

    A step id belongs to one command: reusing it for another command is an error, not a replay.
    """
    if not step:
        return False
    row = find_ok(cdir, step)
    if row is None:
        return False
    if row["tool"] != tool:
        raise StratError(f"step id {step} is already used by `{row['tool']}`; pick a new id")
    ref = row.get("ref", "")
    emit(f"step {step} already done ({row['ts']}): {ref} {row['out']}\n{row['note']}".strip(),
         {"replayed": True, "step": step, "out": row["out"], "note": row["note"],
          "id": ref or None}, as_json)
    return True


# --- commands ---------------------------------------------------------------------------------

def new_case(case_id: str, title: str, as_json: bool = False) -> int:
    """Copy cases/_template, write state.json, set cases/.current."""
    if not CASE_ID.match(case_id):
        raise StratError(f"bad case id {case_id!r}: use lowercase letters, digits and '-'")
    target = cases_dir() / case_id
    if target.exists():
        raise StratError(f"case already exists: {case_id}")
    cases_dir().mkdir(parents=True, exist_ok=True)
    shutil.copytree(root() / "cases" / "_template", target)
    try:
        limit = float(load_config("limits")["budget"]["default_limit_usd"])
    except Exception:
        limit = 5.0
    state = {"case": case_id, "title": title, "stage": "intake", "mode": None,
             "gates": {"1": "pending", "2": "pending", "3": "pending"},
             "next": "Intake: read the request and materials, ask at most 5 questions "
                     "(skills/intake)",
             "budget": {"limit_usd": limit, "spent_usd": 0.0}, "created": now()}
    save(target, state)
    (cases_dir() / ".current").write_text(case_id + "\n", encoding="utf-8")
    emit(f"created case {case_id} at {target}\nstage: intake",
         {"case": case_id, "path": str(target), "stage": "intake"}, as_json)
    return 0


def show(case: str | None = None, as_json: bool = False) -> int:
    """Print stage, gates, next action, due items."""
    if not case and not current_case():
        names = sorted(p.parent.name for p in cases_dir().glob("*/state.json"))
        emit("no active case" + (f"; existing cases: {', '.join(names)}" if names else "")
             + "\nstart one with: bin/strat new <id> --title \"...\"",
             {"case": None, "cases": names}, as_json)
        return 0
    cdir = case_path(case)
    state = load(cdir)
    done = [r for r in read_jsonl(cdir / "log.jsonl") if r.get("status") == "ok"]
    last = done[-1] if done else None
    data = dict(state, last_step=last, recent_steps=[r["step"] for r in done[-8:]], due=[],
                path=str(cdir))
    gates = ", ".join(f"{n} {v}" for n, v in state["gates"].items())
    b = state["budget"]
    lines = [f"case: {state['case']} ({state.get('title', '')})",
             f"path: {cdir}",
             f"stage: {state['stage']}",
             f"gates: {gates}",
             f"next: {state.get('next') or '-'}",
             f"budget: ${b['spent_usd']:.2f} of ${b['limit_usd']:.2f} (CLI calls only)",
             "steps done (latest last): " + (", ".join(data["recent_steps"]) or "none"),
             "due: nothing (review is not available in this version)"]
    emit("\n".join(lines), data, as_json)
    return 0


def step(step_id: str, case: str | None = None, stage: str | None = None, out: str | None = None,
         next_: str | None = None, note: str | None = None, as_json: bool = False) -> int:
    """Log one agent action (idempotent by id), set stage and next."""
    cdir = case_path(case)
    if replay(cdir, step_id, as_json, "agent"):
        return 0
    state = load(cdir)
    if stage is not None:
        _check_stage_move(state, stage)
    if out is not None:
        target = (cdir / out).resolve()
        if cdir.resolve() not in target.parents or not target.is_file():
            raise StratError(f"{out}: file not found in the case; write it before logging the step")
        _check_written_file(cdir, out)
    if stage is not None:
        state["stage"] = stage
    if next_ is not None:
        state["next"] = next_
    save(cdir, state)
    log_action(cdir, step=step_id, tool="agent", stage=state["stage"], out=out or "",
               note=note or "")
    emit(f"logged {step_id}; stage: {state['stage']}; next: {state.get('next') or '-'}",
         {"replayed": False, "step": step_id, "stage": state["stage"], "next": state.get("next")},
         as_json)
    return 0


def gate_approve(n: int, case: str | None = None, as_json: bool = False) -> int:
    """Record the user's approval of gate n and advance the stage."""
    cdir = case_path(case)
    if replay(cdir, f"gate{n}.approve", as_json, "gate"):
        return 0
    state = load(cdir)
    if state["stage"] != f"gate{n}":
        raise StratError(f"stage is {state['stage']}, not gate{n}: run `strat gate check {n}` "
                         "first and present the gate to the user")
    _recheck_gate(cdir, n)
    state["gates"][str(n)] = "approved"
    state["stage"] = AFTER_GATE[n]
    state["next"] = NEXT_AFTER_GATE[n]
    save(cdir, state)
    log_action(cdir, step=f"gate{n}.approve", tool="gate", stage=f"gate{n}",
               note="approved by the user")
    emit(f"gate {n} approved; stage: {state['stage']}; next: {state['next']}",
         {"gate": n, "stage": state["stage"], "next": state["next"]}, as_json)
    return 0


# --- rules ------------------------------------------------------------------------------------

def _check_stage_move(state: dict, stage: str) -> None:
    if stage not in STAGES:
        raise StratError(f"unknown stage {stage!r}; stages: {', '.join(STAGES)}")
    if stage.startswith("gate"):
        raise StratError(f"stage {stage} is set by `strat gate check {stage[-1]}`, not by a step")
    missing = [g for g in REQUIRES[stage] if state["gates"][str(g)] != "approved"]
    if missing:
        raise StratError(f"stage {stage} needs gate {missing[0]} approved by the user first")


def _report(errors: list[str], what: str) -> None:
    for e in errors:
        print(e, file=sys.stderr)
    raise StratError(f"{what}: {len(errors)} problem(s) listed above; fix them and rerun", FAILED)


def _check_written_file(cdir: Path, out: str) -> None:
    """Citation and heading checks on a case document the agent just wrote."""
    from strat.validate import check_file

    errors = check_file(cdir, out)
    if errors:
        _report(errors, out)


def _recheck_gate(cdir: Path, n: int) -> None:
    """Files may have changed since the check: run it again before approving."""
    from strat.validate import gate_errors

    errors = gate_errors(cdir, n)
    if errors:
        _report(errors, f"gate {n} check no longer passes")
