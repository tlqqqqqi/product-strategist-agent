---
name: materials
description: Use when reading the user's files - tables, Word, PowerPoint, PDF, images. How to convert them, read the snapshot, and turn what is in them into claims with the right where.
---

# Materials

Convert first, then read the snapshot; open the original only to check a doubtful value.

```
bin/strat source add materials/<file> --step <id>     # prints the S id; snapshot in sources/
```

| Kind | Snapshot | `--where` |
|---|---|---|
| xlsx, csv | one CSV block per sheet: header, row count, empty cells per column | `sheet!B2:B7` (a csv's sheet is the file name without extension) |
| docx | headings in order, paragraphs numbered `[pN]`, tables as rows | a heading (`О продукте`, or `Раздел > Подраздел`) or `paragraph N` |
| pptx | per slide: title, text, tables, speaker notes | `slide 7` |
| pdf | text per page; pages without text are flagged | `page 12` |
| html | page text | the section heading |
| image | none | read the image yourself; `where` names the region |

The CLI checks that the quote occurs inside the region `--where` names. Cell coordinates count
the header as row 1, as in the spreadsheet.

## Tables

- Before using a figure, state its unit, its period and the number of empty cells in its column
  (the snapshot lists them). A figure from a column with gaps says so.
- A figure that needs a calculation goes through a script in `analysis/`, never by eye (see
  `skills/data-analysis/SKILL.md`).
- Watch for mixed periods (month vs quarter), cumulative vs monthly values, and percentages vs
  percentage points.

## Slides and documents

- A statement on a slide or in a document is its author's claim, not a fact about the world,
  unless it carries its own source. Record who says it: "По данным команды продукта, ...".
- Speaker notes often hold the caveats (`notes:` lines). Read them.

## Charts, pictures, scans

- Charts and pictures inside files are not in the text snapshot. Say so to the user, and read
  the image if the figure matters.
- A page flagged "no text layer" is a scan: read it as an image and mark the claim text
  "(прочитано с изображения)".
