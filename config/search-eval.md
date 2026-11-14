# Russian query test for search providers

Run 2026-11-14 with `scripts/search_eval.py` (live, keys from `.env`). It decides the order of
providers per kind in `config/routes.yaml`.

## Method

20 Russian product-research queries on open topics (tariffs and prices of Yandex 360, Cloud
Mail, SberPrime, MegaFon, Kinopoisk, VK Music, Ozon; churn and retention benchmarks; family
subscriptions; cloud storage market; 152-FZ and auto-renewal rules), tagged by kind: 7 keyword,
7 text, 6 semantic. The queries are in the script. Each provider got every query with 5 results.

Each top-5 list is scored by three heuristics, each 0..1 (share of the 5 results):

- **relevant**: the title and snippet are in Russian and share a word stem with the query;
- **fresh**: dated this year or last year (provider date, else a year in url, title or snippet);
- **snippet**: the snippet has 100+ characters and a query stem.

`mean` is the average of the three. The heuristics are rough proxies, not a relevance judgment,
so the semantic queries were also checked result by result (below).

## Results

| provider | kind | queries | errors | relevant | fresh | snippet | mean | sec |
|---|---|---|---|---|---|---|---|---|
| brave | all | 20 | 0 | 0.99 | 0.69 | 0.89 | 0.86 | 1.6 |
| brave | keyword | 7 | 0 | 1.00 | 0.60 | 0.86 | 0.82 | 1.6 |
| brave | semantic | 6 | 0 | 0.97 | 0.63 | 0.87 | 0.82 | 1.6 |
| brave | text | 7 | 0 | 1.00 | 0.83 | 0.94 | 0.92 | 1.5 |
| exa | all | 20 | 0 | 0.90 | 0.57 | 0.89 | 0.79 | 2.1 |
| exa | keyword | 7 | 0 | 1.00 | 0.51 | 1.00 | 0.84 | 2.1 |
| exa | semantic | 6 | 0 | 0.70 | 0.47 | 0.67 | 0.61 | 2.2 |
| exa | text | 7 | 0 | 0.97 | 0.71 | 0.97 | 0.89 | 1.9 |
| tavily | all | 20 | 0 | 0.98 | 0.44 | 0.91 | 0.78 | 2.1 |
| tavily | keyword | 7 | 0 | 0.94 | 0.43 | 0.89 | 0.75 | 2.6 |
| tavily | semantic | 6 | 0 | 1.00 | 0.27 | 0.83 | 0.70 | 1.7 |
| tavily | text | 7 | 0 | 1.00 | 0.60 | 1.00 | 0.87 | 1.9 |

Descriptive numbers over the 100 results of each provider:

| provider | results with a date | mean snippet length, chars | snippets with a number |
|---|---|---|---|
| brave | 74 | 181 | 61 |
| tavily | 56 | 413 | 71 |
| exa | 67 | 482 | 78 |

**Semantic check, result by result** (6 queries x 5 results, judged by the build agent, not by
a person): results that address the question asked - Exa about 28 of 30 (several of them in
English: papers on free trials, bundling and churn), Tavily about 14 of 30 (generic "what is a
cloud" pages, parenting articles, operator tariff pages instead of their experience,
machine-translated Reddit threads). The `relevant` heuristic counts an English answer as a miss
and a Russian page that repeats the query words as a hit, which is why it ranked Tavily higher.

## Decision

The first draft kept Brave last by an earlier design rule; the results contradicted that rule
and the owner dropped it (2026-11-14).

- keyword: `[brave, exa, tavily]` - Brave 0.82 and Exa 0.84 are close; Brave is cheaper
  (0.005 vs 0.007 USD) and faster (1.6 vs 2.1 s). Tavily 0.75 last.
- text: `[brave, exa, tavily]` - Brave 0.92 over Exa 0.89 and Tavily 0.87.
- semantic: `[exa, tavily, brave]` - the result-by-result check overrides the heuristic.
