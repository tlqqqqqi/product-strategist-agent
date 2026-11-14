"""Exa provider: search by meaning, with highlights as snippets.
Docs: https://github.com/exa-labs/openapi-spec, POST https://api.exa.ai/search (x-api-key)."""

from __future__ import annotations

from strat import providers

ENDPOINT = "https://api.exa.ai/search"
KEY = "EXA_API_KEY"


def search(query: str, kind: str, limit: int, api_key: str) -> list[dict]:
    """Type `auto` (Exa picks neural or keyword itself). `kind` does not change the request."""
    payload = {"query": query, "type": "auto", "numResults": max(1, min(limit, 10)),
               "contents": {"highlights": True}}
    data = providers.post_json(ENDPOINT, payload, headers={"x-api-key": api_key}, timeout=30)
    out = []
    for item in providers.results_of(data, "exa")[:limit]:
        highlights = [providers.clean(h) for h in item.get("highlights") or [] if h]
        text = " … ".join(highlights) or item.get("text")
        row = {"title": providers.clean(item.get("title")), "url": item.get("url") or "",
               "snippet": providers.snippet(text)}
        if providers.iso_date(item.get("publishedDate")):
            row["date"] = providers.iso_date(item.get("publishedDate"))
        out.append(row)
    return out
