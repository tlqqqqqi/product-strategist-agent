---
name: report
description: Use after Gate 3 sign-off once memo.md is written, or when the user asks for the memo as a page. Renders memo.md into a self-contained memo.html where every claim id opens its claim with source and quote.
---

# Report

`memo.html` is the memo a product lead can forward: one offline file, readable on a phone, light
and dark. Every claim id in the text is a link that opens the claim: its type, status, text, the
source title and origin (URL or material file), the place in the source (`where`) and the quote.
Assumptions, gaps, synthetic data, hypotheses, forecasts and conclusions carry a visible label
next to the citation, so a reader never takes them for facts.

## When

- At the end of sign-off, after `memo.md` passed `bin/strat step signoff.memo --out memo.md`.
- Again whenever `memo.md` or a claim it cites changes (a revision, a replaced or re-confirmed
  claim): the HTML is a rendering, never edited by hand.

## Steps

1. `bin/strat report`
2. Exit 1 prints `memo.md:<line>: <reason>`: a cited claim does not exist, is withdrawn or is
   stale, or a line has no citation. Fix `memo.md` (cite the replacement claim, re-confirm a
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

- Markdown support covers what the templates use: headings, bullets, numbered lists, tables,
  paragraphs, bold, inline code, links, `>` notes, fenced code. Nested lists render flat.
- Links to material files and snapshots are relative to the case folder: they open when
  `memo.html` stays in `cases/<id>/`; a forwarded copy keeps the cards (with origin and quote)
  but not those file links.
