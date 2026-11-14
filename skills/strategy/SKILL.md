---
name: strategy
description: Use at stage strategy, after Gate 2. Writes, in sequence and without stopping, the product strategy, the communication strategy derived from it, the promise check, and the verification plan; then hands over to Gate 3.
---

# Strategy

Write the four parts in order, each about one page, each from its template, every line cited.
Do not stop between them: the next gate is after all four.

## 1. Product strategy -> product.md

Follow `knowledge/product-strategy.md` and `knowledge/templates/product.md`. It follows from
the option chosen at Gate 2 (the "Рекомендация" section of `options.md`). New numbers you
estimate are `forecast` claims.

`bin/strat step strategy.product --out product.md`

## 2. Communication strategy -> comms.md

Follow `knowledge/comms-strategy.md` and `knowledge/templates/comms.md`. Derive it from
`product.md`: the same audience, a barrier backed by a claim, one key message, its proof.

## 3. Promise check (inside comms.md)

List every promise the message and channels make in the "Проверка обещаний" table. Each maps
to a capability in `product.md` or to a claim. Remove or rewrite every promise marked "нет"
before you log the step.

`bin/strat step strategy.comms --out comms.md`

## 4. Verification plan -> verification.md

Follow `knowledge/verification-plan.md` and `knowledge/templates/verification.md`: the expected
change with its baseline claim, the comparison, the observation period, unwanted effects, the
review conditions.

`bin/strat step strategy.verification --out verification.md --next "Gate 3: sign-off (skills/signoff)"`

## 5. Consistency pass

Before Gate 3, read the three files together: does the communication promise only what the
product does; does the verification measure what the product strategy expects; does everything
follow from the chosen option? Fix and re-log the changed file with a new step id
(`strategy.fix.<n>`). Then continue with `skills/signoff/SKILL.md`.
