---
name: unslop
description: Use before you show the user any Russian text you wrote - a chat message, a gate summary, a case document (brief, options, product, comms, verification, decisions, memo). Cuts AI tells and decoding work from the text without changing its meaning or citations.
---

# Unslop

Edit Russian text to remove AI patterns and anything the reader has to decode. Scan for the
patterns below, then rewrite. Keep the meaning, the numbers and every claim id `[Cxxx]` exactly;
match the tone of a note to a product lead.

Adapted from `unslop` in pstack (MIT, Lauren Tan; https://github.com/backnotprop/pstack).
Rule numbers are the original ones; Russian rules are added from 34. A removed rule leaves a gap.

## Patterns to detect and fix

### Content

3. **Superficial participle phrases.** «подчёркивая…», «обеспечивая…», «отражая…»,
   «демонстрируя…». Delete, or state the fact with its claim.
5. **Vague attributions.** «Эксперты считают», «Исследования показывают», «Рынок ждёт». Name the
   source and cite its claim, or delete.

### Language

7. **AI vocabulary.** ключевой (as filler), важно отметить, является, играет роль, позволяет,
   обеспечивает, критически, комплексный, уникальный, экосистема (abstract), ландшафт,
   синергия, драйвер (abstract). Replace with plain words.
8. **Fancy ways to say "is".** «является», «выступает в качестве», «представляет собой». Use a
   dash or «это».
9. **"Not just X, but Y."** «не просто X, а Y», «не только X, но и Y» for effect. State the point.
10. **Rule of three.** Do not force ideas into groups of three. Use the natural number.
11. **Synonym cycling.** One name per thing: if it is «канал performance_ads», do not switch to
    «платный трафик», «реклама», «источник» in the next lines.
12. **False ranges.** «от X до Y» where X and Y are not on one scale. List the items.

### Style

13. **Dash overuse.** In Russian the dash is correct punctuation (subject and predicate, an
    omitted verb), keep those. Do not use it as an all-purpose joint between two thoughts: at
    most one dash per sentence; otherwise end the sentence or use a comma.
14. **Colon overuse.** A colon is fine before a list or an example, not as a mid-sentence
    joint («Решение: остановить…; онбординг: не трогаем»). Write a sentence.
15. **Boldface overuse.** Do not bold every name or metric.
16. **Inline-header lists.** A bold label and colon that restates the line («**Риск:** риск в
    том…») becomes prose. A bold lead-in that names the item and is followed by new detail is
    fine.
17. **Headings.** Sentence case, short, no colon.
18. **Decorative emojis.** None.
19. **Quotes.** Russian text uses «ёлочки», and „лапки“ inside them. Straight quotes only in
    code and commands.

### Communication

20. **Chatbot phrases.** «Отличный вопрос!», «Надеюсь, это поможет», «Конечно!», «Если что,
    пишите». Remove.
22. **Sycophantic tone.** «Вы абсолютно правы!» Answer directly.

### Filler

23. **Filler phrases.** «для того чтобы» becomes «чтобы», «в связи с тем что» becomes
    «потому что», «стоит отметить, что» and «следует подчеркнуть» are deleted.
24. **Excessive hedging.** «потенциально может, возможно, в какой-то степени» becomes «может».
25. **Generic conclusions.** «Перспективы выглядят многообещающе.» State the next step or the
    number.

### Jargon

26. **Abstract metaphor nouns.** точка роста, рычаг, вектор, фокус (as a noun for "priority"),
    north star, флайвил, воронка (outside an actual funnel), драйвер, боль (for a problem).
    Pick the concrete word.

### Plain speech

27. **Say what it does, not how it feels.** «канал работает неэффективно» becomes «семья из
    канала приносит 638 ₽, а её привлечение стоит 650 ₽». If a sentence could stand unchanged in
    another case's memo, it says nothing about this one: cut it.
28. **Shorten or split dense sentences.** One idea per sentence. A sentence with two «;» is
    three sentences.
29. **Active voice.** Name who acts: «команда остановит показ», not «показ будет остановлен» or
    an infinitive with no actor («остановить показ»). Passive is fine when the actor does not
    matter.
30. **Cut adverbs, or use the number.** «значительно вырос» becomes «вырос с 4 % до 7,6 %».
31. **Prefer the plain word.** «осуществлять» becomes «делать», «в рамках» becomes «в» or «при»,
    «данный» becomes «этот», «произвести оценку» becomes «оценить».
32. **Mannered prose.** Aphorisms, rhetorical fragments, figurative verbs («канал съедает
    бюджет»). Say what you mean.
33. **Over-compression.** Verbless fragments, symbol-speak and abbreviations the reader has to
    decode. «m1 < 60% → стоп» becomes «если первый месяц продлевают меньше 60 % семей, канал
    останавливаем». Write whole sentences.

### Russian text (added)

34. **Numbers in Russian format, one style.** Decimal comma (`7,6`), a space before `%` and the
    currency (`7,6 %`, `650 ₽`), a space in thousands (`9 612`). Never `7.6` in Russian text.
    Keep the precision the claim has; do not round a number a block copies from a claim.
35. **No arrows or comparison symbols in sentences.** `→`, `->`, `<`, `>`, `≥`, `≤`, `x` for
    "times" become words («с 90 % до 89 %», «меньше 60 %», «в 0,98 раза»). Tables and charts may
    keep them.
36. **Internal labels are not words.** Option numbers (`В4`), objection ids (`O012`), cohort
    shorthand (`m1`, `m2`), stage names (`holdout`, `A/B`) are explained the first time in plain
    words («первый месяц подписки», «контрольная группа без изменений»), or replaced.
    Claim ids `[Cxxx]` stay: they are links.
37. **Anglicisms that have a plain word.** креатив becomes «рекламное объявление», посадочная
    becomes «страница», холдаут becomes «контрольная группа», ретеншн becomes «удержание»,
    кейс (as "example") becomes «пример». Data names (a channel `performance_ads`, a column)
    keep their names.
38. **Bureaucratic Russian (канцелярит).** Chains of nouns in the genitive («проведение анализа
    оценки эффективности»), «на сегодняшний день», «имеет место». Use a verb.

## How to apply

1. Read the text once as its reader (the recipient in the brief) would.
2. Mark every pattern above; rewrite those sentences only.
3. Check that every number and every `[Cxxx]` is still there and still says the same thing.
   Do not add facts, drop caveats or change a recommendation while editing.
4. In `memo.md`, `bin/strat report` refuses rules 34 and 35 in prose lines (outside blocks and
   tables); fix the reported lines and rerun.
