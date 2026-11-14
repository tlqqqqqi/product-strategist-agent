---
name: signoff
description: Use at stage gate3 or monitoring. Presents the strategies for sign-off at Gate 3; after an explicit yes writes the decision record and the one-page memo.
---

# Sign-off

## Gate 3

1. `bin/strat gate check 3`; fix and rerun until it passes (the stage becomes `gate3`).
2. Present in Russian, short: the product direction and refusals, the key message and its
   proof, the promise check result, the expected change and when it will be measured.
3. Ask for sign-off: "Подписываете стратегию? После подписи я запишу решение и подготовлю
   записку." Stop and wait.

- An explicit yes: `bin/strat gate approve 3`, then "After sign-off" below.
- A correction: `bin/strat step signoff.revise.<n> --stage strategy`, change the files, rerun
  `bin/strat gate check 3`, present again.

## After sign-off

1. **Decision record.** Copy `knowledge/templates/decision-record.md` to `decisions.md` (or add
   a new "Решение" section if it exists). Fill the chosen option, the owner (a role), the metrics
   and review conditions from `verification.md`, the check date, and the load-bearing claims.
   `bin/strat step signoff.decision --out decisions.md`
2. **Memo.** Copy `knowledge/templates/memo.md` to `memo.md`: one page for the recipient in the
   brief, every line cited. `bin/strat step signoff.memo --out memo.md --next "Monitoring: review the decision on its check date"`
   (the step fails on an uncited line: fix and rerun).
3. **Report to the user** in Russian: where the memo and the full files are
   (`cases/<id>/memo.md`, `claims.md`), the check date, and the cost from `bin/strat cost`
   (CLI calls only; the IDE model's own usage is not included). Before this report, run
   `bin/strat report` to render `memo.html` and follow `skills/report/SKILL.md`.

## Later sessions at stage monitoring

Say where the case stands and when the check date is. Automatic review of due items and
revision on new material are not available in this version; if the user brings new material,
register it, add claims, and tell the user which conclusions it touches
(`bin/strat claim list --load-bearing`).
