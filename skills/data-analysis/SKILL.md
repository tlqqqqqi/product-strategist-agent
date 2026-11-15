---
name: data-analysis
description: Use when a figure needs a calculation (a difference, a share, a growth rate, a sum) or when figures from tables are compared. Writes a short reproducible script in analysis/, checks units, periods, gaps and definitions, registers the output as a source and cites it; `bin/strat analysis check` reruns the script and refuses figures that no longer reproduce.
---

# Data analysis

A figure that needs a calculation goes through a script, never by eye. The script is short,
reads the table itself, and prints each figure with its unit and period. Its output is a
source like any other, so a claim quotes it and anyone can rerun it.

## When

- A difference, share, growth rate, sum or average of table values.
- Two figures from different rows, sheets or files are compared or combined.
- A figure comes from a column with empty cells.

Reading one cell as it stands needs no script: cite the table directly (`skills/materials/SKILL.md`).

## Before writing the script: five checks

Write the answers into the script as comments. A figure that fails one is not quoted until it
is fixed or the problem is stated in the claim text.

1. **Unit.** RUB or thousand RUB; % or percentage points; users or thousand users. The column
   name and the definitions sheet usually say. A difference of two percentages is in p.p.
2. **Period.** Month, quarter or year; a value per period or cumulative; the date it is as of.
   A monthly churn rate and a quarterly one are different quantities.
3. **Gaps.** The snapshot header lists empty cells per column (`empty cells: D 1`). An empty
   cell is unknown, not zero. The script prints every empty cell it reads as a `GAP` line.
4. **Denominator.** A share or a rate of what: all users, payers of the previous month, a
   cohort? Say it in the claim text.
5. **Same definition.** Figures you compare must be counted the same way. Read the
   definitions sheet (in the sample case, sheet `about`): there `monthly.paying_users` counts
   promo users only from their first charge in August 2026, so the August rise in payers is not
   organic growth, and `monthly.churn_pct` leaves out promo users who never paid.

## Steps

1. Register the material if it is not yet a source: `bin/strat source add materials/<file>`.
   Read its snapshot header and the definitions sheet.
2. Write `cases/<case>/analysis/q<N>_<name>.py` (N = the plan's question):

   ```python
   # Q2: how many promo-cohort payers were lost between August and October 2026.
   # unit: users; period: month (2026-08, 2026-10); gaps: column D has 1, not in the promo row;
   # denominator: May 2026 cohort of the promo channel; definition: `about` sheet, cohorts.*
   from strat.analysis import load, figure, diff, pct_change

   t = load("materials/metrics.xlsx", "cohorts")      # or load("S001", "cohorts")
   promo = {"channel": "promo_3_months_free"}
   aug = figure("promo_paid_aug", t.value("paid_users_2026_08", promo), "users", "2026-08")
   oct_ = figure("promo_paid_oct", t.value("paid_users_2026_10", promo), "users", "2026-10")
   diff(oct_, aug, "promo_paid_change")
   pct_change(oct_, aug, "promo_paid_change_pct")
   ```

3. Run it and save the output next to it:

   ```
   .venv/bin/python cases/<case>/analysis/q<N>_<name>.py > cases/<case>/analysis/q<N>_<name>.txt
   ```

   Read the output. `GAP` lines name the empty cells the script read. A `MISMATCH` error means
   two figures had different units or periods: convert one explicitly (for example
   `figure("revenue_rub", rev_k * 1000, "RUB", "2026-10")`) or do not combine them.
4. Register the output and check that it reproduces:

   ```
   bin/strat source add analysis/q<N>_<name>.txt --step research.q<N>.analysis.<k>
   bin/strat analysis check <S id>
   ```

   Exit 1 names each figure that does not reproduce, or the script error. Fix the script,
   rerun it, register the new output, and replace the claims that cited the old one
   (`bin/strat claim replace`).
5. Cite a figure: `--source <S id> --where <figure name> --quote "<name> = <value> <unit>"`,
   copied from the `FIGURE` line, with `--as-of` the end of the figure's period and
   `--historical` when the period is closed history. The claim text (in Russian) names the
   unit, the period and the denominator, and says when the figure rests on a column with gaps.
   Example: "С августа по октябрь 2026 платящих из майской когорты акции стало на 2700 меньше
   (4550 -> 1850, -59,3%)".
6. Before gate 2, and after new material arrives: `bin/strat analysis check --all`. It reruns
   every analysis script and reports conclusions whose supporting figures are one quantity at
   different scales (RUB vs thousand RUB) or the same unit over different periods (a month vs a
   quarter).

## Helper reference (`strat.analysis`)

| Call | Does |
|---|---|
| `load(ref, sheet)` | A table from a file in the case (`materials/x.xlsx`) or a source id (`S001`); a csv's sheet is the file name without extension |
| `t.value(column, {"col": "key"})` | The one number on the matching row; `None` and a `GAP` line if empty |
| `t.numbers(column, where=None)` | Numbers of matching rows; empty cells left out and printed as `GAP` |
| `t.rows`, `t.columns` | Raw rows as dicts, header names |
| `figure(name, value, unit, period)` | Prints `FIGURE name = value unit \| period P`; period forms: `2026-10`, `2026-Q3`, `2026`, `2026-W40`, `2026-10-15`, `A..B` |
| `diff(new, old, name)` | new - old in the same unit (p.p. for %) |
| `pct_change(new, old, name)` | Relative change in % |
| `share(part, whole, name)` | part / whole in %, same period required |

Units are normalized (`₽`, `руб` -> `RUB`; `тыс. ₽` -> `thousand RUB`; `п.п.` -> `p.p.`); an
unknown unit is compared as written. The unit label is all the helper sees: a change already in
percentage points must be declared `p.p.`, not `%`, or `diff` will treat it as a rate.

## Limits (tell the user when they matter)

- The check compares the `FIGURE` lines only; anything else the script prints is not checked.
- The conclusion check sees only figures that come from analysis outputs. A figure quoted
  straight from a table is not unit-checked: run it through a one-line script if it is combined
  with others.
- A script that loads a source id (`S001`) reads the frozen snapshot; one that loads
  `materials/...` reads the current file, so the check notices when the file changed.
