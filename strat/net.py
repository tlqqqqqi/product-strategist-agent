"""The one HTTP helper. GET only: the CLI never submits forms. Tests replace `get`."""

from __future__ import annotations

import urllib.error
import urllib.request

USER_AGENT = "strategist-cli/0.1 (research tool; +https://github.com/tlqqqqqi/product-strategist-agent)"
MAX_BYTES = 5_000_000


class HttpError(Exception):
    pass


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
        raise HttpError(f"HTTP {exc.code} for {url}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HttpError(f"{url}: {getattr(exc, 'reason', exc)}") from None
