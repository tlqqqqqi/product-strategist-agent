"""Tavily provider: search that returns the relevant extracted text of each page.
Docs: https://docs.tavily.com/api-reference/endpoint/search (POST, Bearer key)."""

from __future__ import annotations

from strat import providers

ENDPOINT = "https://api.tavily.com/search"
KEY = "TAVILY_API_KEY"


def search(query: str, kind: str, limit: int, api_key: str) -> list[dict]:
    """Basic depth (1 credit). `kind` does not change the request."""
    payload = {"query": query, "max_results": max(1, min(limit, 20)), "search_depth": "basic",
               "include_answer": False, "include_raw_content": False,
               "include_published_date": True}
    if providers.CYRILLIC.search(query):
        payload["language"] = "ru"  # a ranking boost, not a strict filter
    data = providers.post_json(ENDPOINT, payload,
                               headers={"Authorization": f"Bearer {api_key}"}, timeout=30)
    out = []
    for item in providers.results_of(data, "tavily")[:limit]:
        row = {"title": providers.clean(item.get("title")), "url": item.get("url") or "",
               "snippet": providers.snippet(item.get("content"))}
        if providers.iso_date(item.get("published_date")):
            row["date"] = providers.iso_date(item.get("published_date"))
        out.append(row)
    return out
