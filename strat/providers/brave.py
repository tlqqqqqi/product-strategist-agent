"""Brave Search provider: keyword web index. Docs: api-dashboard.search.brave.com."""

from __future__ import annotations

import json
import re
import urllib.parse

from strat import net, providers

ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
KEY = "BRAVE_API_KEY"
_TAG = re.compile(r"<[^>]+>")


def search(query: str, kind: str, limit: int, api_key: str) -> list[dict]:
    """Return results as dicts with title, url, snippet. `kind` does not change the request."""
    params = {"q": query, "count": max(1, min(limit, 20))}
    if providers.CYRILLIC.search(query):
        params["search_lang"] = "ru"
    url = f"{ENDPOINT}?{urllib.parse.urlencode(params)}"
    _, _, body = net.get(url, headers={"Accept": "application/json",
                                       "X-Subscription-Token": api_key}, timeout=20)
    try:
        data = json.loads(body)
    except ValueError:
        raise net.HttpError("Brave returned a response that is not JSON") from None
    out = []
    for item in (data.get("web") or {}).get("results", [])[:limit]:
        snippet = " ".join(_TAG.sub("", item.get("description") or "").split())
        row = {"title": item.get("title", ""), "url": item.get("url", ""), "snippet": snippet}
        if providers.iso_date(item.get("page_age")):
            row["date"] = providers.iso_date(item.get("page_age"))
        out.append(row)
    return out
