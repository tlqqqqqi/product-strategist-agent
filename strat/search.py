"""One search command; one provider per call, falls through on failure."""

from __future__ import annotations


def search(query: str, step: str, case: str | None = None, kind: str = "keyword", limit: int = 5, as_json: bool = False) -> int:
    """Print a JSON list of title, url, snippet, provider."""
    raise NotImplementedError
