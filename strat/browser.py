"""Public flow capture with Playwright; never submits. (Phase 2)"""

from __future__ import annotations


def capture(url: str, flow: str, case: str | None = None, steps: int = 5, as_json: bool = False) -> int:
    """Walk a public flow into shots/."""
    raise NotImplementedError
