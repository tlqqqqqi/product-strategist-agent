# Search queries

- Write queries in the language of the market: Russian for the Russian market.
- One intent per query: "<конкурент> тарифы семейный", "<категория> цены 2026",
  "<продукт> отзывы отмена подписки".
- Add the year for prices and tariffs; prices go stale (`price` shelf life is 90 days).
- Prefer the competitor's own tariff or help page over aggregators and news.
- For a number, search for the primary report (regulator, company disclosure) rather than
  an article quoting it.
- Search in rounds (see `research-themes.md`): a broad round over the sub-questions, then a
  round that follows the names, terms and numbers you found. Stop when two new queries in a
  row bring nothing new; then record a gap.

## Which `--kind`

`bin/strat search "<q>" --kind keyword|text|semantic --step ID` sends the query to one provider,
chosen by kind in `config/routes.yaml`; if it fails, the next one answers.

- `keyword` (default): a name, a tariff, a price, an exact term - "<конкурент> тариф семейный цена 2026".
- `text`: you need the numbers or the passage in the snippet - market size, a benchmark, a law.
- `semantic`: a question in plain words, when you do not know the terms - "почему пользователи
  отказываются от платного облака". Expect some results in English; they are still sources.

Exit 2 means no provider could answer (no key, or all failed): do not retry the same command;
stop and ask the user, or use your own web search tool and save pages with `bin/strat read`.
