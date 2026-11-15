---
name: report
description: Use after Gate 3 sign-off once memo.md is written, or when the user asks for the memo as a page. Renders memo.md into a self-contained memo.html where every claim id opens its claim with source and quote.
---

# Report

`memo.html` is the memo a product lead can forward: one file that reads offline (the fonts load
when there is a network, else a system font), readable on a phone, light theme. Every claim id in the text is a link that opens the claim: its type, status, text, the
source title and origin (URL or material file), the place in the source (`where`) and the quote.
Assumptions, gaps, synthetic data, hypotheses, forecasts and conclusions carry a visible label
next to the citation, so a reader never takes them for facts.

## Numbers, charts and tables in the memo

The memo can carry fixed blocks; `bin/strat report` draws them, you only fill in data.

- Add a chart only when it shows the reason for the decision. At most 3 blocks per memo (the
  "Ключевые цифры" tiles count as one); the check refuses a fourth.
- Bars may all be negative (decreases, drawn by magnitude, values in red) but never mixed
  with positive ones: the check refuses a mix (use a table). Funnel steps are never negative.
- Copy every value from a claim exactly. Every number in a row (outside its label) must appear
  in the text or quote of a claim the row cites, or the check fails with
  `memo.md:<line>: <value> is not in the text or quote of <ids>`. Do not compute shares, sums
  or differences in a block: record a computed number as its own claim first.
- Every row ends with claim ids `[Cxxx]` that exist and are not withdrawn or stale.
- A block is a fenced block whose info string is its type. First `title:` (required), then
  `unit:` (optional), then rows. A decimal comma or point and spaces in thousands are fine
  (`88,8`, `1 200`). A label ending in `*` is the focal row, drawn in the accent colour
  (otherwise the largest bar, the biggest change or the last point).

One example per type:

````
```tiles
title: Главное за май
- Удержание органики*: 88,8 % - лучше всех каналов [C012]
- Платящих: 1 610 - на конец месяца [C014]
```

```bars
title: Удержание M1 по каналам, май 2026
unit: %
- органика*: 88,8 [C012]
- реклама: 52,1 [C012]
```

```line
title: Платящие по месяцам
unit: чел.
- 2026-03: 1 200 [C014]
- 2026-04: 1 350 [C014]
```

```slope
title: Конверсия в оплату
unit: %
columns: до | после
- конверсия: 3,4 | 4,1 [C015]
```

```funnel
title: Воронка за май
- установки: 10 000 [C016]
- регистрации: 4 200 [C016]
- оплаты: 380 [C016]
```

```table
title: Каналы
| Канал | Удержание M1, % | CAC, ₽ |
| органика* | 88,8 [C012] | 140 [C017] |
| реклама | 52,1 [C012] | 610 [C017] |
```
````

`line` points go in order; `slope` rows have two values split by `|`; `table` takes the first
pipe row as the header, every other row cites a claim, and its first column is the label.

The page also shows, without anything to write: the title and the "## Решение" section in the
header (the decision box), a strip with the check date ("Дата проверки: ГГГГ-ММ-ДД" in the memo
or decisions.md), the counts of facts and assumptions and the number of accepted risks; the
bullets under "## Риски..." as risk rows tagged with the objection ids (named in the bullet, or
risk-accepted objections whose claims the bullet cites); the options-by-criteria table from `table.md`
under "Таблица решения" with the option chosen at Gate 2 marked, and filter chips at the top
(факты, допущения, выводы...) that highlight the lines citing that type of claim.

## When

- At the end of sign-off, after `memo.md` passed `bin/strat step signoff.memo --out memo.md`.
- Again whenever `memo.md` or a claim it cites changes (a revision, a replaced or re-confirmed
  claim): the HTML is a rendering, never edited by hand.

## Steps

1. `bin/strat report`
2. Exit 1 prints `memo.md:<line>: <reason>`: a cited claim does not exist, is withdrawn or is
   stale, a line has no citation, or a block row has a number its claim does not state
   (`table.md:<line>` for the decision table). Fix `memo.md` (cite the replacement claim, re-confirm a
   stale claim with `bin/strat claim confirm`, or turn the statement into an assumption or a
   gap claim) and rerun. No HTML is written while a problem remains, so an old `memo.html` may be
   out of date: do not hand it over.
3. Exit 0 prints `wrote cases/<id>/memo.html: <n> claims linked`.

## What to tell the user (Russian)

Short, for example:

"Записка готова: `cases/<id>/memo.html` (открывается в любом браузере, без интернета, удобно
читать с телефона) и исходник `cases/<id>/memo.md`. Каждый номер [C...] в тексте открывает
карточку утверждения: источник, место в нём и цитату. Допущения, пробелы, выводы и синтетические
данные помечены прямо в тексте. Файл можно переслать как есть."

If the memo cites assumptions or gaps that the decision rests on, name them in one line: these
are what the verification plan checks first.

## Limits

- Blocks draw only these six types; the slope chart is drawn as paired bars (before, after),
  not as crossing lines; a `line` shows at most what fits in one row of labels on a phone
  (keep it to about 8 points).
- Markdown support covers what the templates use: headings, bullets, numbered lists, tables,
  paragraphs, bold, inline code, links, `>` notes, fenced code. Nested lists render flat.
- Links to material files and snapshots are relative to the case folder: they open when
  `memo.html` stays in `cases/<id>/`; a forwarded copy keeps the cards (with origin and quote)
  but not those file links.
