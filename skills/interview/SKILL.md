---
name: interview
description: Use when an open research question needs the voice of users - to write an interview guide from plan.md, to analyse an interview transcript the user supplies, or to run a model respondent (persona) to sharpen hypotheses before real interviews. Model respondents are always synthetic, never facts.
---

# Interview

Three jobs, all leading to claims with a source and a type:

| Job | Command | Source it makes | Claim types it can back |
|---|---|---|---|
| Guide from open questions | you write `interviews/guide_<n>.md` | none (not a finding) | - |
| Real transcript | `bin/strat interview add <file> --mask "<names>" --step <id>` | `interview`, masked | fact (what was said), hypothesis, gap |
| Model respondent | `bin/strat interview persona <persona-file> --guide <guide> --step <id>` | `interview`, synthetic | `synthetic` only |

## 1. Guide -> interviews/guide_<n>.md

- Take the open questions (`- [ ]`) in `plan.md` that are about users: why they come, pay,
  leave, choose a competitor. A question that a table or a web page can answer does not go into
  an interview.
- The file, in Russian:
  1. `# Гайд интервью <n>: <тема>`
  2. The consent line, before any question:
     `> Согласие: перед началом спросить согласие на запись и обработку ответов; имена, телефоны и почту в запись не вносить.`
     The CLI refuses a guide without a `> Согласие:` line before the first question.
  3. `Цель:` which plan questions (Q1, Q2) it serves.
  4. `## Вопросы` - 5 to 8 numbered questions (`1. ...`), the CLI reads only numbered lines.
- Questions are non-leading: about past behaviour and real episodes, not opinions or the future.
  - Bad: «Вам ведь не понравилось повышение цены?» Good: «Вспомните, когда вы последний раз
    меняли тариф. Что тогда происходило?»
  - One thing per question; no product names you want them to praise; no "would you buy".
  - End with «Что я не спросил, а стоило?»
- Log: `bin/strat step interview.guide<n> --out interviews/guide_<n>.md`

## 2. Real transcript (text, or audio through skills/media)

- Consent first. Ask once, in Russian: «Респондент дал согласие на запись и её обработку?»
  Without a yes, do not register the transcript.
- Audio or video: run the `media` skill first (`bin/strat media ...`), then register the
  resulting text with `interview add` so it is masked; the timestamped media transcript is not
  masked by the script, so check it by eye and never quote personal data from it.
- Read the raw file once, list the people's names in it, and pass them with `--mask`:
  `bin/strat interview add materials/call_3.txt --mask "Мария Соколова, Олег" --step interview.add.3`
  The script masks e-mails and phone numbers itself, and the names you give it; it writes the
  masked copy to `interviews/<name>.md` and registers that, never the raw file. `strat source
  add` of a file named like a transcript (interview, интервью, transcript, транскрипт) takes the
  same path. If the raw file was already in the case, tell the user to delete it.
- Read the masked copy. If a name, an address or an employer is still there, run again with a
  longer `--mask` list.
- Claims: quote the respondent's words exactly. `--where` is free text for a text transcript
  («реплика 4»), a timestamp for a media transcript.
  - What a person says about themselves («я отключила подписку после первого списания») can be
    a `fact` about what this respondent said; put «респондент 1 говорит» in the text.
  - A generalisation from a few people is a `hypothesis`, never a fact about all users: five
    interviews do not give a share or a percentage.
- Refer to people by role and number («респондент 3, ушёл в августе»), never by name.

## 3. Model respondents (personas)

Use them to test a guide and to find hypotheses worth checking with real people, never to
answer a research question.

1. Write a persona file, in Russian, invented: `interviews/personas/<name>.md` with 4-6 lines
   (age band, situation, why they came, what they pay for, habits). Build it from claims you
   already have (a segment in the cohort table), not from imagination alone, and say which.
   No real person, no real names.
2. Run it:
   `bin/strat interview persona interviews/personas/mama.md --guide interviews/guide_1.md --questions 5 --step interview.persona.mama`
   - The peer model (`config/routes.yaml`, `persona:`) answers each question in turn, with the
     earlier answers in context. Each answer is its own logged step with its price; a stop on
     question N (exit 2) is resumed by running the same command again.
   - The session goes to `interviews/persona_<name>.md`; it starts with the banner «ВНИМАНИЕ:
     это имитация респондента языковой моделью ..., а не ответы реального человека».
3. No peer key (exit 3): run the native subagent from `agents/persona.md` with a fresh context.
   Give it the persona file, the guide and the output path; it writes the same `## Q<n>`
   blocks. Then import:
   `bin/strat interview add <file> --persona mama --step interview.persona.mama`
   It is stored as synthetic and marked same-vendor: the model that wrote your hypotheses also
   played the respondent, so agreement between them proves even less. Say so to the user.
4. Claims from a session are `--type synthetic`, `--where Q<n>`, the quote from that block;
   the text says «модельный респондент <name> говорит ...». The CLI refuses any other type for
   a claim citing a persona source, and refuses a `fact` whose `--supports` reaches a synthetic
   claim, directly or through a hypothesis.
5. What a session is good for: a hypothesis built on synthetic claims (`--type hypothesis
   --supports C0xx`) that names how a real interview or data would check it; a guide question
   that confused the respondent and needs rewording. It never changes a ranking in `table.md`
   on its own.

## Tell the user (in Russian)

- After a guide: the questions, which plan questions they serve, and the consent line.
- After a transcript: how many phones, e-mails and names were masked, and that names the script
  did not know were checked by you.
- After a persona session: «Это ответы модели, которая играет вымышленного пользователя, а не
  реального человека. Я использую их только как гипотезы для проверки на настоящих интервью.»
  Plus the cost from the command output (`bin/strat cost` shows it by stage).
