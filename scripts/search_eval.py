"""Russian query test for the search providers (Task 9). Live: calls every provider that has a
key in .env, so it costs money (about 0.02 USD per query for all three; see config/routes.yaml).

    .venv/bin/python scripts/search_eval.py [--raw DIR] [--only brave,tavily,exa]

Scores each top-5 list on three heuristics, each 0..1:
  relevant  share of results in Russian that share a word stem with the query;
  fresh     share of results dated (provider date, else a year in url/title/snippet) this year
            or last year;
  snippet   share of results whose snippet has at least 100 characters and a query stem.
Prints a markdown table per provider and per kind. The scores are rough proxies, not a human
relevance judgment; config/search-eval.md records the run and what it decided."""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strat import net  # noqa: E402
from strat.core import env, load_config, today  # noqa: E402

PROVIDERS = ("brave", "tavily", "exa")
TOP = 5

# Open product-research topics only: tariffs, prices, churn, market, regulation. No personal data.
QUERIES = [
    ("keyword", "Яндекс 360 семейный тариф цена 2026"),
    ("keyword", "Облако Mail.ru тарифы 1 ТБ цена"),
    ("keyword", "СберПрайм стоимость подписки 2026"),
    ("keyword", "МегаФон семейный тариф условия"),
    ("keyword", "Кинопоиск семейная подписка цена"),
    ("keyword", "VK Музыка семейная подписка стоимость"),
    ("keyword", "Ozon Premium стоимость подписки"),
    ("text", "средний отток подписчиков онлайн-кинотеатров в России"),
    ("text", "удержание пользователей мобильных приложений бенчмарк Россия"),
    ("text", "доля семейных подписок в экосистемах России исследование"),
    ("text", "рынок облачных хранилищ для частных пользователей в России объем"),
    ("text", "152-ФЗ требования к хранению персональных данных в облачном сервисе"),
    ("text", "автоматическое продление платной подписки закон Россия изменения"),
    ("text", "сколько россиян платят за онлайн-подписки опрос 2026"),
    ("semantic", "почему пользователи отказываются от платного облачного хранилища"),
    ("semantic", "как семьи делят одну подписку на несколько человек и что их раздражает"),
    ("semantic", "чем экосистемные подписки удерживают клиентов лучше отдельных сервисов"),
    ("semantic", "какие функции семейного облака важны для родителей с детьми"),
    ("semantic", "опыт российских операторов связи по запуску семейных тарифов"),
    ("semantic", "как цена подписки влияет на отток после бесплатного пробного периода"),
]

_WORD = re.compile(r"[a-zа-яё0-9]+", re.I)
_CYR = re.compile(r"[а-яё]", re.I)
_LAT = re.compile(r"[a-z]", re.I)
_YEAR = re.compile(r"\b(20[12]\d)\b")


def stems(text: str) -> set[str]:
    """Crude stems: the first 5 letters of every word of 4+ letters."""
    return {w.lower()[:5] for w in _WORD.findall(text) if len(w) >= 4}


def is_russian(text: str) -> bool:
    cyr, lat = len(_CYR.findall(text)), len(_LAT.findall(text))
    return cyr > 0 and cyr >= lat


def result_year(r: dict) -> int | None:
    if r.get("date"):
        m = _YEAR.search(r["date"])
        if m:
            return int(m.group(1))
    years = [int(y) for y in _YEAR.findall(" ".join((r["url"], r["title"], r["snippet"])))]
    return max(years) if years else None


def score(query: str, results: list[dict], year: int) -> dict:
    """Three 0..1 scores over the top results; an empty list scores 0."""
    top = results[:TOP]
    q = stems(query)
    rel = fresh = snip = 0
    for r in top:
        text = f"{r['title']} {r['snippet']}"
        hit = bool(q & stems(text + " " + r["url"]))
        rel += is_russian(text) and hit
        y = result_year(r)
        fresh += y is not None and y >= year - 1
        snip += len(r["snippet"]) >= 100 and bool(q & stems(r["snippet"]))
    n = TOP
    return {"relevant": rel / n, "fresh": fresh / n, "snippet": snip / n}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", help="directory to save raw result lists (not committed)")
    ap.add_argument("--only", default=",".join(PROVIDERS))
    args = ap.parse_args(argv)
    prices = load_config("routes").get("search", {}).get("usd_per_call", {})
    year = today().year
    rows, spent = [], 0.0
    for name in args.only.split(","):
        mod = importlib.import_module(f"strat.providers.{name}")
        key = env(mod.KEY)
        if not key:
            print(f"skip {name}: no {mod.KEY}", file=sys.stderr)
            continue
        for kind, query in QUERIES:
            started = time.monotonic()
            try:
                results, error = mod.search(query, kind, TOP, key), ""
            except net.HttpError as exc:
                results, error = [], str(exc)
            sec = time.monotonic() - started
            spent += float(prices.get(name, 0))
            rows.append({"provider": name, "kind": kind, "query": query, "sec": round(sec, 2),
                         "n": len(results), "error": error, **score(query, results, year)})
            if args.raw:
                out = Path(args.raw) / f"{name}.jsonl"
                out.parent.mkdir(parents=True, exist_ok=True)
                with out.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"query": query, "results": results, "error": error},
                                        ensure_ascii=False) + "\n")
    print(table(rows))
    print(f"\nCalls: {len(rows)}; estimated cost {spent:.3f} USD at routes.yaml prices.")
    return 0


def table(rows: list[dict]) -> str:
    lines = ["| provider | kind | queries | errors | relevant | fresh | snippet | mean | sec |",
             "|---|---|---|---|---|---|---|---|---|"]
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        groups.setdefault((r["provider"], r["kind"]), []).append(r)
        groups.setdefault((r["provider"], "all"), []).append(r)
    for (prov, kind), rs in sorted(groups.items()):
        avg = {k: sum(r[k] for r in rs) / len(rs) for k in ("relevant", "fresh", "snippet", "sec")}
        mean = (avg["relevant"] + avg["fresh"] + avg["snippet"]) / 3
        errors = sum(1 for r in rs if r["error"])
        lines.append(f"| {prov} | {kind} | {len(rs)} | {errors} | {avg['relevant']:.2f} | "
                     f"{avg['fresh']:.2f} | {avg['snippet']:.2f} | {mean:.2f} | {avg['sec']:.1f} |")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
