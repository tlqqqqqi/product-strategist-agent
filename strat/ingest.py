"""New material after a decision, and its impact. (Phase 2)"""

from __future__ import annotations


def ingest(path: str, case: str | None = None, as_json: bool = False) -> int:
    """Register new material after a decision."""
    raise NotImplementedError


def impact(claim_id: str, case: str | None = None, as_json: bool = False) -> int:
    """Lines and documents that depend on a claim."""
    raise NotImplementedError
