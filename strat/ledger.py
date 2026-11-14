"""Claim ledger: add, check, list, replace, withdraw, confirm; staleness, importance, claims.md."""

from __future__ import annotations


def add(type_: str, kind: str, text: str, case: str | None = None, source: str | None = None, where: str | None = None, quote: str | None = None, as_of: str | None = None, supports: str | None = None, step: str | None = None, as_json: bool = False) -> int:
    """Add one claim after the type and source rules."""
    raise NotImplementedError


def check(claim_id: str | None = None, case: str | None = None, all_: bool = False, as_json: bool = False) -> int:
    """Quote check, then the support judgment."""
    raise NotImplementedError


def list_claims(case: str | None = None, type_: str | None = None, load_bearing: bool = False, stale: bool = False, as_json: bool = False) -> int:
    """List claims with filters and regenerate claims.md."""
    raise NotImplementedError


def replace(old: str, new: str, case: str | None = None, as_json: bool = False) -> int:
    """Mark old as replaced by new."""
    raise NotImplementedError


def withdraw(claim_id: str, reason: str, case: str | None = None, as_json: bool = False) -> int:
    """Withdraw a claim; nothing is deleted."""
    raise NotImplementedError


def confirm(claim_id: str, source: str, where: str, quote: str, as_of: str, case: str | None = None, as_json: bool = False) -> int:
    """Re-confirm a stale claim with a newer source."""
    raise NotImplementedError
