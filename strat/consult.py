"""Challenger calls and capped debate. (Phase 2)"""

from __future__ import annotations


def consult(call: str, case: str | None = None, as_json: bool = False) -> int:
    """Run challenger call 'variants' or 'challenge', write objections.jsonl."""
    raise NotImplementedError


def debate(objection_id: str, case: str | None = None, as_json: bool = False) -> int:
    """One debate round; refuse past the caps."""
    raise NotImplementedError
