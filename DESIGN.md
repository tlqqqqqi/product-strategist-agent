# Design

Source of truth for the two pages a person sees: the memo (`config/memo.html`, rendered by
`bin/strat report`) and the replay (`demo/replay/index.html`). Approved by the owner on
2026-11-15 from previews of five directions. The approved reference page is
`design/reference.html`: open it in a browser; where it and this file disagree, this file wins.

Rules applied on top: the impeccable craft floor and slop list (local copy of
github.com/pbakaus/impeccable), the `design` skill's slop list, and diagram-design's chart rules
(one accent per chart, hairlines, 4 px grid). Copy in the pages is Russian; this file is English.

## Direction

A calm analyst tool, light and smooth. The palette and the pushable buttons come from the
owner's Himalai system (SberHack `DESIGN.md`); the type is Geologica at light weights with
slightly tight tracking, the precision of a financial dashboard. Rejected: a gradient band
(generic, not needed), a dark console (owner: bad), a mascot, an avatar or a named persona for
the agent (owner: childish), violet as the agent's colour.

Hierarchy on the memo: the decision (title and decision box) first, the numbers that carry it
second, the evidence (charts, decision table, risks) third. On the replay: the conversation
first, folded tool steps second, run metadata last.

## Tokens

Defined once as CSS custom properties on `:root`. Light theme only for now (dark is not
designed; do not ship an untested one).

| Role | Value | Use |
|---|---|---|
| `--page` | `#F5F8FF` | Page ground (blue-tinted, not cream) |
| `--surface` | `#FFFFFF` | Cards, the memo sheet, the replay panel, claim cards |
| `--surface-2` | `#F2F8FF` | Insets: stats strip, risk rows, gate card, citation chips, bar tracks |
| `--ink` | `#1A1F3B` | Headings, numbers, body (16.1:1 on surface) |
| `--muted` | `#56627A` | Captions, metadata, inactive controls (6.1:1) |
| `--hairline` | `#D3E1F2` | 1 px dividers and control borders |
| `--accent` | `#2563EB` | Primary button fill, links, the selected option, line-chart focal labels (5.2:1) |
| `--accent-mark` | `#3B82F6` | Non-text marks: the focal line segment and points, focus outline on messages |
| `--accent-press` | `#1D4ED8` | Primary button bottom edge; accent text on `--accent-soft` (AA) |
| `--accent-soft` | `#E3EDFF` | User bubble, decision box, selected rows and tabs, hover fills |
| `--neg` / `--neg-mark` / `--neg-soft` | `#C01D38` / `#F4455E` / `#FFE3E7` | Minus figures and decreases (text uses `--neg`) |
| `--pos` / `--pos-mark` / `--pos-soft` | `#157A3F` / `#22A55B` / `#DCF5E6` | Plus figures and increases; the "факт" label |
| `--violet` / `--lavender` | `#7C5CFF` / `#C7B8FF` | Bar charts only: focal bar / other bars (owner's choice; reads as data, not alarm) |
| `--warn` | `#A8470F` | Objection ids in risk rows, "допущение"/"пробел" labels (`#8A4B0F` on `#FFF1E0`) |
| `--sel` | `#C7DBFF` | Text selection |

Sign rule: a figure with a minus sign is `--neg`, a figure that reports an increase is `--pos`,
everything else is `--ink`. Levels (a churn of 6.8%) are not signed. Never colour alone: the
sign is always written.

## Type

One family for UI and text: **Geologica** (Google Fonts, full Cyrillic), weights 300-600.
**JetBrains Mono** 400/500 only for claim and objection ids, quotes in claim cards and dates in
metadata; never for figures. `font-variant-numeric: tabular-nums` on body.

| Style | Size / line height | Weight | Tracking |
|---|---|---|---|
| Memo title (h1) | 34 / 1.08 | 400 | -0.025em |
| Section (h2) | 21 / 1.3 | 500 | -0.015em |
| Key figure | 36 / 1.1 | 300 | -0.03em |
| Body | 15-16 / 1.55 | 350-400 | 0 |
| UI label, button | 14-15 / 1.3 | 500-600 | 0 |
| Caption, metadata | 13 / 1.4 | 400 | 0 |
| Smallest functional text | 12 | 400-500 | 0 |

Prose measure 65-75 characters. No eyebrow or kicker labels above headings; no numbered section
markers; headings never skip a level.

## Space, radius, elevation

- Spacing on a 4 px grid: 4, 8, 12, 16, 20, 24, 32, 48. Card padding 28 desktop, 16-20 phone;
  more space above a heading than below it.
- Radius by role: 6 (citation chips, small insets), 10 (buttons, options, decision box, risk
  rows, claim card quote), 16 (cards, bubbles with a 4 px tail corner), 20 (the replay panel),
  999 (filter chips, model pills, segmented controls).
- Elevation: `--shadow` `0 6px 20px rgba(59,130,246,.10), 0 1px 3px rgba(26,31,59,.06)` for
  cards; `--shadow-lg` `0 16px 40px rgba(59,130,246,.16), 0 2px 6px rgba(26,31,59,.08)` for the
  replay panel, the info panel and claim cards. Cards have no border. No glow, no inner
  shadows, no hard offset shadows.

## Motion

Product motion, 150-250 ms, `cubic-bezier(.16,1,.3,1)` for arrivals and `ease-out` for colour.
Only transform, opacity and clip-path animate; never height, padding or grid tracks.

- Info panel and claim card: opacity + 4-6 px rise (+ clip-path reveal for the panel), 200-220 ms.
- Fold chevron rotates 180°; info icon rotates 180° while open.
- Bars and funnel rows grow once from the left on load (`scaleX`, 900 ms, the one authored moment).
- Buttons: press scales to 0.96 in 100 ms.
- `prefers-reduced-motion`: all transitions off.

## Components

**Buttons.** Pushable: 1.5 px border `#C9D6E8` with a 4 px bottom edge, radius 10, weight 600.
Primary: `--accent` fill, `--accent-press` bottom edge, white label, one per view. States:
hover (soft fill; primary brightens), focus (2 px `--accent` ring, 2 px offset), active (scale
0.96), disabled (45% opacity, not-allowed). Labels name the action ("← Сообщение").

**Chips and pills.** Filter chips (claim types) and model pills: radius 999, 1.5 px hairline
border; selected is ink-filled with white text; hover is `--accent-soft`.

**Citation.** `C025` in JetBrains Mono 12 px on a `--surface-2` chip, radius 6; a gap or
assumption citation has a dashed hairline instead. Every citation is a link that opens the claim
card. Citations may sit inline in text, figures, table cells, risk rows and agent messages.

**Claim card.** Fixed-position card next to the citation (flips above when there is no room),
max 380 px: id, type label (факт green, вывод blue, допущение/пробел amber), the claim text,
"Источник:" link to the original file (download) and to its text snapshot, "Место:", the quote
in mono on `--surface-2`. A gap says "Данных нет: это известное неизвестное, а не факт." Closes
on Esc, outside click, scroll and ×; focus returns to the citation.

**Memo.**
- Header: title (the decision in words), one line of context, the decision box (`--accent-soft`,
  "Решение." in `--accent-press`), a metadata strip (check date, counts of facts, assumptions,
  accepted risks).
- Claim-type filter: chips that dim (opacity .32) everything not resting on that type; hidden
  without JS.
- Key figures ("Почему"): rows of figure + sentence + citation + one muted explanation line,
  divided by hairlines. Not hero-metric cards.
- Charts (the `strat report` blocks): bars and funnel as HTML rows (label, track on
  `--surface-2`, fill, value); line as SVG for marks only with values and x labels in HTML
  below; a dashed muted marker with a small label for an event (price change); one focal
  element per chart. Caption above with unit and citation.
- Decision table: hairline rows, muted 13 px header, the chosen option on `--accent-soft`;
  cells keep citations; no side stripes.
- Accepted risks: `--surface-2` rows with the objection id in `--warn` mono.

**Replay.**
- Top bar: model pills (scroll horizontally on phone) and the info button (i) on the right.
- Info panel: overlays the chat under the top bar (does not push content): gates 1-3 and what a
  claim is.
- Stats strip: date, active minutes, tokens and cache (or $ when priced), steps.
- User message: right-aligned `--accent-soft` bubble, radius 16 with a 4 px bottom-right corner;
  materials named in it become file chips (file icon + name) that link to the files.
- Tool steps: one muted summary line with a chevron ("Создал кейс, зарегистрировал 3 источника,
  прочитал 4 файла ⌄"), as in claude.ai; open, a rounded card of rows, each row one step with
  its command or file in mono; closed by default.
- Agent message: plain text, no bubble, no avatar, no name; figures signed and coloured, inline
  citations open claim cards.
- Question window: tabs (one per question), the question, options as rows with a radio dot; the
  chosen answer on `--accent-soft` with an `--accent-mark` border.
- Gate card: `--surface-2`, "Gate N · …" title (a paragraph, not a heading), the question, the
  answer buttons (primary + secondary).
- Bottom bar: "← Сообщение", position "7 из 21", play/pause, "Сообщение →"; prev/next jump
  between messages (user, agent, question, gate), never tool steps; disabled at the ends.

## Browser surfaces

Selection `--sel`; caret `--accent`; thin scrollbar in `--hairline`; focus ring 2 px
`--accent` with 2 px offset on every control; link underline offset 3 px; tabular figures.

## Accessibility

Text AA (4.5:1, large 3:1) measured, not assumed; nothing under 12 px; touch targets at least
32 px high with 44 px hit area on phone; colour never the only signal (signs, labels); the
filter and cards work by keyboard; the page reads in full without JS (each citation stays a link to its
claim's anchor on the page, the filter chips stay hidden).

## Responsive

One column below 980 px; figures stack (figure above its sentence) below 560 px; bar and funnel
labels move above the track below 560 px; the decision table scrolls horizontally inside its
wrapper; no horizontal page scroll at 360 px.
