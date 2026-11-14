"""The one HTTP helper. GET for pages and search APIs; POST only for JSON calls to model and
search APIs (strat/models.py, strat/providers). The CLI never submits a web form. Tests replace `get` and `post`."""

from __future__ import annotations

import urllib.error
import urllib.request

USER_AGENT = "strategist-cli/0.1 (research tool; +https://github.com/tlqqqqqi/product-strategist-agent)"
MAX_BYTES = 5_000_000


class HttpError(Exception):
    """`status` is the HTTP status, or None for a network failure or a timeout."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def get(url: str, headers: dict | None = None, timeout: int = 30,
        max_bytes: int | None = MAX_BYTES) -> tuple[int, dict, bytes]:
    """Return (status, lower-cased headers, body). Raises HttpError on any failure."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})},
                                 method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(max_bytes + 1 if max_bytes else -1)
            if max_bytes and len(body) > max_bytes:
                raise HttpError(f"{url}: larger than {max_bytes} bytes")
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, body
    except urllib.error.HTTPError as exc:
        raise HttpError(f"HTTP {exc.code} for {url}", exc.code) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HttpError(f"{url}: {getattr(exc, 'reason', exc)}") from None


def post(url: str, body: bytes, headers: dict | None = None, timeout: int = 30,
         max_bytes: int = MAX_BYTES) -> tuple[int, dict, bytes]:
    """POST a JSON body to an API (model APIs and the Tavily and Exa search APIs); same return
    and errors as `get`. Never used for web forms."""
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "User-Agent": USER_AGENT, "Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise HttpError(f"{url}: larger than {max_bytes} bytes")
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, body
    except urllib.error.HTTPError as exc:
        detail = exc.read(500).decode("utf-8", "replace")
        raise HttpError(f"HTTP {exc.code} for {url}: {detail}", exc.code) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HttpError(f"{url}: {getattr(exc, 'reason', exc)}") from None
