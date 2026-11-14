"""Small judgments through the routing table, with fallback. (Phase 2)"""

from __future__ import annotations


def judge(question: str, case: str | None = None, claim: str | None = None, other: str | None = None, as_json: bool = False) -> int:
    """Answer a typed question; exit 3 when no model is available."""
    raise NotImplementedError
