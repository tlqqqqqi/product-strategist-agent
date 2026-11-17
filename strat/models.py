"""One OpenAI-compatible client for outside models: 120 s timeout, one retry, cost logged.

The AnyModel roles (peer, jev) share one key and endpoint, ANYMODEL_API_KEY and
ANYMODEL_BASE_URL, and differ only by STRAT_<ROLE>_MODEL. Other roles (stt) are configured as
STRAT_<ROLE>_BASE_URL, _API_KEY and _MODEL.
Every call goes through `net.post`, so tests replace the network. Each call writes one log line
with its tokens and price (config/routes.yaml, `models:`), failed calls included. The key is
sent in the Authorization header only; it is never printed or logged.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

from strat import net
from strat.core import env, load_config

DEFAULT_BASE_URL = "https://anymodel.org/v1"
RETRY_PAUSE = 2.0  # seconds before the one retry; tests set it to 0


@dataclass
class Endpoint:
    role: str
    base_url: str
    key: str
    model: str


ANYMODEL_ROLES = ("peer", "jev")


def key_name(role: str) -> str:
    """The .env name of the key a role needs."""
    return "ANYMODEL_API_KEY" if role in ANYMODEL_ROLES else f"STRAT_{role.upper()}_API_KEY"


def endpoint(role: str) -> Endpoint | None:
    """The configured endpoint for a role, or None when it has no key."""
    prefix = "ANYMODEL_" if role in ANYMODEL_ROLES else f"STRAT_{role.upper()}_"
    key = env(prefix + "API_KEY")
    if not key:
        return None
    return Endpoint(role, (env(prefix + "BASE_URL") or DEFAULT_BASE_URL).rstrip("/"), key,
                    env(f"STRAT_{role.upper()}_MODEL"))


def _conf() -> dict:
    return load_config("routes").get("models", {})


def price(model: str, tokens_in: int, tokens_out: int) -> tuple[float, bool]:
    """USD for a call and whether the rate is an estimate (model not in routes.yaml)."""
    conf = _conf()
    rates = conf.get("usd_per_mtok") or {}
    estimated = model not in rates
    rate = float(conf.get("default_usd_per_mtok", 2.0) if estimated else rates[model])
    return (tokens_in + tokens_out) * rate / 1_000_000, estimated


def _retryable(exc: net.HttpError) -> bool:
    return exc.status is None or exc.status == 429 or exc.status >= 500


def call(ep: Endpoint, path: str, body: dict, *, cdir: Path | None = None,
         step: str = "model") -> dict:
    """POST `body` to base_url + path. Returns the parsed JSON plus "_usage" (tokens_in,
    tokens_out, usd, estimated). Raises net.HttpError after the retry is spent."""
    conf = _conf()
    timeout = int(conf.get("timeout_sec", 120))
    attempts_left = 1 + int(conf.get("retries", 1))
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Authorization": f"Bearer {ep.key}", "Accept": "application/json"}
    model = body.get("model", ep.model)
    started, attempts = time.monotonic(), 0
    while True:
        attempts += 1
        attempts_left -= 1
        try:
            _, _, resp = net.post(ep.base_url + path, raw, headers=headers, timeout=timeout)
            data = json.loads(resp)
            if not isinstance(data, dict):
                raise ValueError
            break
        except ValueError:
            exc = net.HttpError(f"{ep.role}: the response is not a JSON object")
            _log(cdir, step, ep, model, 0, 0, 0.0, "error", f"{exc}; {attempts} attempts",
                 started)
            raise exc from None
        except net.HttpError as exc:
            if attempts_left > 0 and _retryable(exc):
                time.sleep(RETRY_PAUSE)
                continue
            _log(cdir, step, ep, model, 0, 0, 0.0, "error",
                 f"{exc}; {attempts} attempt{'s' if attempts > 1 else ''}", started)
            raise
    usage = data.get("usage") or {}
    tin = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    tout = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    counted = bool(tin or tout)
    if not counted:  # no usage in the answer: estimate from the request size
        tin = math.ceil(len(raw.decode("utf-8")) / 3)
    usd, estimated = price(model, tin, tout)
    note = (f"{model}, {attempts} attempt{'s' if attempts > 1 else ''}"
            + ("" if counted else ", tokens estimated") + (", price estimated" if estimated
                                                            else ""))
    _log(cdir, step, ep, model, tin, tout, usd, "ok", note, started)
    data["_usage"] = {"tokens_in": tin, "tokens_out": tout, "usd": usd,
                      "estimated": estimated or not counted}
    return data


def _log(cdir, step, ep, model, tin, tout, usd, status, note, started) -> None:
    if cdir is None:
        return
    from strat.state import log_action

    log_action(cdir, step=step, tool=f"model {ep.role}", in_=model, tokens_in=tin,
               tokens_out=tout, usd=usd, status=status, note=note,
               sec=time.monotonic() - started)


def chat(role: str, messages: list[dict], *, cdir: Path | None = None, step: str = "model",
         model: str | None = None, **params) -> dict:
    """Chat completion with the model configured for role. Returns text, model, tokens_in,
    tokens_out, usd. Raises net.HttpError when the role has no key or the call fails."""
    ep = endpoint(role)
    if ep is None:
        raise net.HttpError(f"no {key_name(role)}")
    model = model or ep.model
    if not model:
        raise net.HttpError(f"no model for {role}: set STRAT_{role.upper()}_MODEL")
    data = call(ep, "/chat/completions", {"model": model, "messages": messages, **params},
                cdir=cdir, step=step)
    try:
        text = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise net.HttpError(f"{role}: no message in the chat response") from None
    u = data["_usage"]
    return {"text": text, "model": model, "tokens_in": u["tokens_in"],
            "tokens_out": u["tokens_out"], "usd": u["usd"]}
