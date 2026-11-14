"""Search providers. Each module exposes KEY (the env variable) and
search(query, kind, limit, api_key) -> list of dicts with title, url, snippet and, when the
provider gives one, date (YYYY-MM-DD). A provider failure raises net.HttpError.

Tavily and Exa take a JSON body, so they go through post_json below: a POST to a search API
endpoint, never to a page or a form. Tests replace post_json, as they replace net.get."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from strat import net

CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def post_json(url: str, payload: dict, headers: dict | None = None, timeout: int = 30) -> dict:
    """POST a JSON body to an API endpoint and return the decoded JSON reply."""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"User-Agent": net.USER_AGENT, "Content-Type": "application/json",
                 "Accept": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(net.MAX_BYTES)
    except urllib.error.HTTPError as exc:
        raise net.HttpError(f"HTTP {exc.code} for {url}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise net.HttpError(f"{url}: {getattr(exc, 'reason', exc)}") from None
    try:
        return json.loads(body)
    except ValueError:
        raise net.HttpError(f"{url} returned a response that is not JSON") from None


def results_of(data, provider: str) -> list[dict]:
    """The `results` list of a reply, or a provider failure."""
    items = data.get("results") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise net.HttpError(f"{provider} returned no results list")
    return items


def clean(text: str | None) -> str:
    return " ".join((text or "").split())
