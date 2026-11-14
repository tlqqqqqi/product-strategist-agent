---
name: review
description: Use at the start of a session when the case is at stage monitoring, or when the user asks whether the decision still holds. Reports due checks, fired review conditions, stale and contradicted load-bearing claims, and asks the user at most 3 questions.
---

# Review

After sign-off the decision lives in `decisions.md`. There is no daemon: the review happens when
a session starts. `bin/strat state` (and the session-start hook) lists due items at stage
`monitoring`; this skill turns them into a short report and at most 3 questions.

## Steps

1. `bin/strat review` (add `--json` if you want the structure). It prints:
   - **due** - the check date of the live decision once it has passed; review conditions that
     fired (their own date passed, or the claim they watch is contradicted, replaced, withdrawn
     or stale); a check date that is missing or not `ГГГГ-ММ-ДД`.
   - **contradicted load-bearing claims** - a decision, a strategy or the recommendation rests
     on a claim that newer material contradicts (a recorded `contradiction` judgment with
     answer yes). Each comes with the conclusions resting on it and the document lines that
     cite them.
   - **stale load-bearing claims** - past their shelf life (`config/shelf-life.yaml`).
   - **questions** - at most 3, most important first: contradictions, fired conditions, the
     check date, stale claims.
2. Nothing due and no questions: tell the user in one or two lines (Russian) that the decision
   stands and when the next check is. Stop.
3. Otherwise report in Russian, short:
   - what is due or changed, with claim ids;
   - for a contradiction: the old figure, the new one, and which conclusions and lines depend on
     it (`bin/strat impact <id>` for the full list);
   - then ask the questions from the output, translated, no more than 3. Each question offers
     concrete answers (revise / keep and record why / bring newer data).
4. Wait for the answers. Then:
   - **Revise** -> `skills/revise/SKILL.md`, from step 4 (the claims are already there).
   - **Keep the decision** -> add a line to "История" in `decisions.md` with the date and the
     reason, cite the claims; if the user names a new check date, change `Дата проверки`.
     `bin/strat step review.<ГГГГ-ММ-ДД> --out decisions.md --next "Monitoring: next check <date>"`
   - **Stale claim** -> as in `knowledge/claims.md`: newer data (`bin/strat claim confirm`),
     use as history (re-add with `--historical`), or record a gap. Never change `as_of` to pass
     a check.
   - **Bring newer data** -> the user brings a file: `skills/revise/SKILL.md`.

## Rules

- At most 3 questions per session, even when more is due; the rest waits for the next review.
- A model's contradiction judgment is its assessment; say so when you report it.
- You do not change `decisions.md`, the options or the strategies without the user's yes.
