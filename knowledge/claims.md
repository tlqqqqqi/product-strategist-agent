# Claims: types and rules

Every finding is one claim in `claims.jsonl`, added with `bin/strat claim add`. Documents
(options, strategies, memo) cite claim ids only: `[C014]` or `[C014, C021]`.

## One assertion per claim

"D30 retention fell from 41% to 33% and the onboarding is to blame" is two claims: a fact (the
fall, from the table) and a hypothesis (the cause). Split before you add.

## Types

| Type | Use when | Needs |
|---|---|---|
| `fact` | a source states it and you can quote it | `--source --where --quote --as-of`; the quote must pass the check |
| `hypothesis` | a cause or explanation not yet confirmed | a source if one suggests it |
| `forecast` | a statement about the future (yours or a source's) | say whose forecast it is in the text |
| `assumption` | something taken as true without a source (the user's word, a default) | nothing; it stays visible as an assumption |
| `gap` | something the decision needs that no source answers | nothing; it is shown as open |
| `synthetic` | output of a model respondent or other generated data | never a basis for a fact |
| `conclusion` | your inference from other claims | `--supports C..` with the claims it rests on |

Rules the CLI enforces: a fact without a source is refused (make it an assumption or a gap);
a quote that is not in the source snapshot is refused; a conclusion or synthetic claim can never
be the source of a fact; a conclusion must name its supports.

## Kinds and shelf life

`--kind` sets how long a claim stays usable (`config/shelf-life.yaml`): `product_metric` 60 days,
`price` 90, `competitor_feature` 180, `market` 365, `regulation` 365, `method` never stale.
`--as-of` is the end of the period the claim describes (`2026-10` for an October figure), not the
day you read it. Never move `as_of` to get past a check.

Shelf life is about claims that describe the current state ("churn is 6.8%", "the competitor
charges 299 ₽"). A claim about a closed past period that you use as history ("in August 2026
churn rose to 5.9%", "4,550 users of the May 2026 promo cohort paid in August 2026") is added with
`--historical`: it never goes stale, and its text must name its period (the CLI checks that the
year is there). Use it for causes, timelines and before/after comparisons, not to keep an old
figure alive as if it were current.

## When a claim you need is stale

A stale claim cannot support new conclusions. Tell the user in one message which claim, its
period and why you need it, and offer three ways out:

1. newer data: the user gives a newer material; register it and run `bin/strat claim confirm`;
2. use it as history: if the decision only needs what happened in that period, re-add it with
   `--historical` and wording that names the period, then `bin/strat claim replace` the old one;
3. record a gap: `--type gap`, and say what the decision loses without it.

Then wait for the answer; this is a question to the user, not a gate.

## Quotes and `where`

- Copy the quote from the snapshot (`sources/Sxxx.md`), not from memory. Keep it short: the
  words or numbers that carry the claim. Join distant parts with `...`.
- `where` points inside the source: `sheet!B4:B9` for tables, a heading or `paragraph N` for
  documents, `slide 7`, `page 12`, a section heading for web pages.
- A statement on a slide or in a document is its author's claim. Record who says it in the text
  ("По данным команды продукта, ...").

## Who checked

`check.quote` is the script's quote check. `check.supported` is a judgment whether the quote
supports the claim; when a model or you made it, report it as that model's or your assessment,
never as a verified fact.

## Status

`active`, `stale` (computed from shelf life), `replaced` (`strat claim replace old new`),
`withdrawn` (`strat claim withdraw id --reason`). Nothing is deleted.

## Load-bearing claims

A claim is load-bearing when `decisions.md`, the recommendation in `options.md`, `product.md`,
`comms.md`, `verification.md` or an open question (`- [ ]`) in `plan.md` cites it, or when a
load-bearing claim rests on it through `supports`. Reports and reminders show only these:
`bin/strat claim list --load-bearing`.
