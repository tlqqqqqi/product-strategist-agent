"""Brave Search provider."""

from __future__ import annotations


def search(query: str, kind: str, limit: int, api_key: str) -> list[dict]:
    """Return results as dicts with title, url, snippet."""
    raise NotImplementedError
