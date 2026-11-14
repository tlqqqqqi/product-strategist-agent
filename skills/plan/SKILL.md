---
name: plan
description: Use at stage plan or gate1. Drafts at least three options, builds the decision table, derives the research questions that could flip the choice, estimates cost, and presents Gate 1.
---

# Plan

The research plan is built from the options, not from topics: first draft the options, then
ask which answers could change their ranking.

## 1. Draft options -> options.md

- Copy `knowledge/templates/options.md`. At least three options, always including
  "Оставить как есть" and "Закрыть / прекратить вкладываться". Others must differ in audience,
  mechanism or resource, not in wording.
- At this stage options rest on what intake gave you: facts from the materials and the user's
  assumptions. Cite them. Where an option rests on nothing yet, add a `gap` claim and cite it.
- The "Рекомендация" section holds a note only: `> Рекомендация будет после исследования.`
- Log: `bin/strat step plan.options --out options.md`

## 2. Decision table -> table.md

- Copy `knowledge/templates/table.md`. Criteria come from the brief's goal and the case type
  (`knowledge/case-types.md`); 3 to 5 criteria.
- Each cell: a short estimate and the claims behind it, or a `gap` claim when unknown.
- The "Влияние исследования" table starts with one row per planned question, answer `-` plus
  the `gap` claim that names what the question will find out (`- [C007]`).
- `strat step --out table.md` and `strat gate check 1` reject any criteria bullet or table data
  row without a claim id, as in `options.md`. Header and separator rows are exempt.
- Log: `bin/strat step plan.table --out table.md`

## 3. Research questions -> plan.md

- A question earns a place only if some answer would change the ranking in the table. Tie each
  to its cell ("вариант x критерий").
- Rate impact (could it flip the leader?) and cost (local material: low; web page: medium;
  needs new data: high). Order by impact, then cost.
- Name where the answer is likely to be: a material by S id, a type of web page, a competitor.
- Write the stop rule: stop when no open question can change the ranking, or when the budget is
  spent; what is left becomes a gap.
- Everything you decide not to research is listed under "Пробелы" as `gap` claims.
- Cost estimate: the number of CLI calls that cost money (`strat search` about 0.005 USD each;
  `read` and `source add` are free) plus the IDE model's own tokens, which the CLI cannot see;
  say so.
- Log: `bin/strat step plan.plan --out plan.md`

## 4. Gate 1

1. Run `bin/strat gate check 1`. Fix every reported line and rerun until it passes. Passing
   moves the stage to `gate1`.
2. Present in Russian, short:
   - the brief in 3-5 lines (decision, goal, recipient, deadline, constraints);
   - the draft options, one line each;
   - the top research questions with the cell each can flip;
   - the cost and time estimate;
   - the assumptions the user should confirm.
3. Ask: "Утверждаете план? Можно поправить любой пункт." Then stop and wait.

- An explicit yes ("да", "утверждаю", "согласен, дальше"): run `bin/strat gate approve 1`, then
  continue with `skills/research/SKILL.md`.
- A correction: `bin/strat step plan.revise.<n> --stage plan`, change the files, rerun the
  check, present again.
- Anything else (a question, "посмотрю позже"): answer it and wait. Do not approve.
