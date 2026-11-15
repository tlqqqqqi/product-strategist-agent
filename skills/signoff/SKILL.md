---
name: signoff
description: Use at stage gate3 or monitoring. Presents the strategies for sign-off at Gate 3; after an explicit yes writes the decision record and the one-page memo.
---

# Sign-off

## Gate 3

1. `bin/strat gate check 3`; fix and rerun until it passes (the stage becomes `gate3`).
   It refuses while a major or critical objection is `open` (`bin/strat consult list`). For
   each one: answer it if the strategy now does (`accepted` or `rejected` with a claim); mark it
   `not-chosen` if its option was not chosen at Gate 2; otherwise show it to the user in one
   line and ask: "Это возражение не снято. Принимаете этот риск?" Only on their yes set
   `bin/strat consult verdict <O> risk-accepted --reason "<their words>"`; on a no, go back
   to the strategy (`bin/strat step signoff.revise.<n> --stage strategy`).
2. Present in Russian, short: the product direction and refusals, the key message and its
   proof, the promise check result, the expected change and when it will be measured.
3. Ask for sign-off: "Подписываете стратегию? После подписи я запишу решение и подготовлю
   записку." Stop and wait.

- An explicit yes: `bin/strat gate approve 3`, then "After sign-off" below.
- A correction: `bin/strat step signoff.revise.<n> --stage strategy`, change the files, rerun
  `bin/strat gate check 3`, present again.

## After sign-off

1. **Decision record.** Copy `knowledge/templates/decision-record.md` to `decisions.md` (or add
   a new "Решение" section below the old ones if it exists; the last one is the live decision).
   Fill the chosen option, the owner (a role), the metrics and review conditions from
   `verification.md`, the check date, and the load-bearing claims. Two parts are read by
   `bin/strat review`, so keep their form:
   - `- Дата проверки: ГГГГ-ММ-ДД` - an ISO date, never "в начале весны". Ask the user for
     the date if the verification plan does not give one.
   - `- Принятые риски:` every `risk-accepted` objection id with its text in a few words, or
     "нет". The step fails while one is missing.
   - Under `- Условия пересмотра:` one sub-bullet per condition, citing the claim it watches,
     with `(проверить: ГГГГ-ММ-ДД)` when it has its own date. A condition fires on its date or
     when its claim is contradicted, replaced, withdrawn or stale.
   `bin/strat step signoff.decision --out decisions.md`
2. **Memo.** Copy `knowledge/templates/memo.md` to `memo.md`: one page for the recipient in the
   brief, every line cited. `bin/strat step signoff.memo --out memo.md --next "Monitoring: review the decision on its check date"`
   (the step fails on an uncited line: fix and rerun).
3. **Report to the user** in Russian: where the memo and the full files are
   (`cases/<id>/memo.md`, `claims.md`), the check date, and the cost from `bin/strat cost`
   (CLI calls only; the IDE model's own usage is not included). Before this report, run
   `bin/strat report` to render `memo.html` and follow `skills/report/SKILL.md`.

## Later sessions at stage monitoring or revision

- **Every session at stage monitoring:** follow `skills/review/SKILL.md`. `bin/strat state`
  already lists what is due; `bin/strat review` gives the details and at most 3 questions.
- **The user brings new material** (a fresh export, a report, a competitor's change), or the
  stage is `revision`: follow `skills/revise/SKILL.md`. It starts with `bin/strat ingest <path>`.
- You never rewrite a decision on your own: you propose, the user says yes, then you change
  `decisions.md` and the documents.
