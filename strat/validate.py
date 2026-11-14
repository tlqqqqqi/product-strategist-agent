"""Gate checks: citations, sourced facts, required files and headings, verdicts."""

from __future__ import annotations


def gate_check(n: int, case: str | None = None, as_json: bool = False) -> int:
    """Run the checks for gate n; errors as <file>:<line>: <reason>."""
    raise NotImplementedError
