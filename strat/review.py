"""Session-start review: due items, fired conditions, stale load-bearing claims. (Phase 2)"""

from __future__ import annotations


def review(case: str | None = None, as_json: bool = False) -> int:
    """Report what is due and what is stale."""
    raise NotImplementedError
