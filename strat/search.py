"""One search command. One provider per call, chosen by kind from config/routes.yaml; on
failure it falls through to the next. Results are not merged. Every call is logged with its
price; the result list is saved to search/<step>.json so a replay costs nothing."""

from __future__ import annotations

import importlib
import json
import time

from strat import net
from strat.core import (
    UNAVAILABLE,
    StratError,
    case_path,
    emit,
    env,
    load_config,
    read_json,
    write_json,
)

KINDS = ("keyword", "text", "semantic")
STOP_AND_ASK = ("Do not retry: stop and ask the user how to proceed - add one key "
                "(BRAVE_API_KEY, TAVILY_API_KEY or EXA_API_KEY) to .env, or let you use the IDE's "
                "own web search tool and save each page with `strat read <url> --step ID`.")


def chain(kind: str) -> list[str]:
    routes = load_config("routes").get("search", {})
    names = list(routes.get(kind) or [])
    if "brave" in names:  # brave is always the last fallback
        names.remove("brave")
    return names + ["brave"]


def search(query: str, step: str, case: str | None = None, kind: str = "keyword",
           limit: int = 5, as_json: bool = False) -> int:
    """Print a JSON list of title, url, snippet, provider."""
    from strat.state import find_ok, log_action

    cdir = case_path(case)
    out_rel = f"search/{step}.json"
    done = find_ok(cdir, step)
    if done:
        if done["tool"] != "search":
            raise StratError(f"step id {step} is already used by `{done['tool']}`; pick a new id")
        results = read_json(cdir / done["out"])["results"]
        _print(results, as_json, replayed=True)
        return 0
    if kind not in KINDS:
        raise StratError(f"unknown --kind {kind!r}")
    prices = load_config("routes").get("search", {}).get("usd_per_call", {})
    tried, failures = [], []
    for name in chain(kind):
        provider = importlib.import_module(f"strat.providers.{name}")
        key = env(provider.KEY)
        if not key:
            tried.append(f"{name}: no {provider.KEY}")
            continue
        started = time.monotonic()
        try:
            results = provider.search(query, kind, limit, key)
        except net.HttpError as exc:
            failures.append(f"{name}: {exc}")
            log_action(cdir, step=step, tool="search", in_=query, status="error",
                       usd=float(prices.get(name, 0)), note=f"{name}: {exc}",
                       sec=time.monotonic() - started)
            continue
        results = [dict(r, provider=name) for r in results]
        (cdir / "search").mkdir(exist_ok=True)
        write_json(cdir / out_rel, {"query": query, "kind": kind, "provider": name,
                                    "results": results})
        log_action(cdir, step=step, tool="search", in_=query, out=out_rel,
                   usd=float(prices.get(name, 0)), note=f"{name}, {len(results)} results",
                   sec=time.monotonic() - started)
        _print(results, as_json, replayed=False)
        return 0
    head = ("all search providers failed: " + "; ".join(failures + tried) if failures
            else "no search key configured (" + "; ".join(tried) + ")")
    raise StratError(head + ". " + STOP_AND_ASK, UNAVAILABLE)


def _print(results: list[dict], as_json: bool, replayed: bool) -> None:
    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    lines = [("(replayed) " if replayed else "") + f"{len(results)} results"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}")
    lines.append("Save a page you use with `strat read <url> --step ID`.")
    print("\n".join(lines))
