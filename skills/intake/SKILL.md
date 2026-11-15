---
name: intake
description: Use when a product lead brings a decision question and there is no active case, or the case is at stage intake. Turns a vague request plus materials into a brief, asking at most 5 questions (quick) or 10 (deep).
---

# Intake

Goal: a brief the user recognises, with every unknown made visible as an assumption. Ask only
what changes the plan.

## 1. Is it a decision task?

A decision task names (or implies) a choice about a product: what to do about a metric, whether
to launch or stop something, how to position it. If the message is a general question, answer
it normally and do not create a case.

## 2. Create the case and register materials

```
bin/strat new <short-latin-id> --title "<название по-русски>"
bin/strat source add <path> --step intake.source.<n>       # once per file
```

- Register every file the user points to (a folder: every file in it). Files outside the case
  are copied into `materials/`; the originals are never changed.
- A saved web page (`.html`) goes through `bin/strat read <file> --step intake.read.<n>`.
- Read each snapshot (`sources/Sxxx.md`) far enough to know what it covers; follow
  `skills/materials/SKILL.md` for tables, documents, slides and PDFs.
- Classify the case with `knowledge/case-types.md`.

## 3. Ask (one message, then stop and wait)

Quick mode (default): one message in Russian with at most 5 numbered questions. Each question:

- is about something the materials do not answer and that changes the options or the plan
  (the decision itself, the goal metric, the recipient, the deadline, hard constraints);
- carries a default: "если не ответите, считаю, что ...".

Deep mode: when the user asks for it, or when more than 5 of these are unknown. One question per
message, at most 10 in total, each with a default.

Do not ask what you can read in the materials. Do not ask about method. Free-text answers are
fine; "не знаю" means the default.

Before you send the questions, record them so a new chat can pick up the answers:

```
bin/strat step intake.questions --next "Waiting for answers to intake questions: 1) <short> 2) <short> ... Defaults: <short>"
```

Then send the questions and **end your turn**. Do not fill in the defaults yourself and go on:
the CLI refuses to move to the plan until the answers are logged. In the next turn, after the
user replied (or said to take the defaults), log what they said first:

```
bin/strat step intake.answers --note "<the user's answers in a few words, or: defaults>"
```

## 4. Write the brief

- Copy `knowledge/templates/brief.md` to `cases/<id>/brief.md` and fill every section in
  Russian.
- Record what the user told you as claims before you use it:
  - a statement from the user's message or answers: `--type assumption`, text starting
    "По словам пользователя, ..." (it has no source document);
  - every default the user did not override: `--type assumption`;
  - a figure you read in a material: `--type fact` with its quote (`knowledge/claims.md`).
- Cite those claims in the brief's "Допущения" section.

Then log the step and move on:

```
bin/strat step intake.brief --out brief.md --stage plan --next "Plan: draft options, decision table, research questions (skills/plan)"
```

Continue with `skills/plan/SKILL.md` in the same turn; intake is not a gate.
