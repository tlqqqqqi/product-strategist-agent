"""Case state and the action log: new, state, step, gate approve."""

from __future__ import annotations

from strat.core import cases_dir, current_case, emit


def new_case(case_id: str, title: str, as_json: bool = False) -> int:
    """Copy cases/_template, write state.json, set cases/.current."""
    raise NotImplementedError


def show(case: str | None = None, as_json: bool = False) -> int:
    """Print stage, gates, next action, due items."""
    if not case and not current_case():
        names = sorted(p.parent.name for p in cases_dir().glob("*/state.json"))
        emit("no active case" + (f"; existing cases: {', '.join(names)}" if names else "")
             + "\nstart one with: bin/strat new <id> --title \"...\"",
             {"case": None, "cases": names}, as_json)
        return 0
    raise NotImplementedError


def step(step_id: str, case: str | None = None, stage: str | None = None, out: str | None = None, next_: str | None = None, note: str | None = None, as_json: bool = False) -> int:
    """Log one agent action (idempotent by id), set stage and next."""
    raise NotImplementedError


def gate_approve(n: int, case: str | None = None, as_json: bool = False) -> int:
    """Record the user's approval of gate n and advance the stage."""
    raise NotImplementedError
