# MovieAnalytics — Power BI Project (PBIP)

This directory contains a source-controlled Power BI Project (PBIP) built from the finalized
78-row dataset at `data/processed/checkpoint3.csv`.

The project is **report source only**. It uses the documented plain-text PBIP/PBIR/TMDL formats and
does **not** contain a `.pbix` file. Power BI Desktop is required to open, refresh, validate at
runtime, and optionally save a `.pbix`.

## Source data

| Item | Value |
|---|---|
| Source file | `data/processed/checkpoint3.csv` |
| Rows | 78 |
| Columns | `movie_name`, `release_year`, `genre`, `director`, `revenue`, `tickets_sold` |
| SHA-256 | `9de3cb115f4e8b8833508b98363f9163e261dd3f756b10d35007ee796ab5c51a` |
| Encoding | UTF-8 with BOM, CRLF line endings |
| Revenue formats | Exact VND (`714,030,584,098₫`) and `tỷ đồng` (`147,5 tỷ đồng`) |

The semantic model reads the source using the relative path
`../../../data/processed/checkpoint3.csv` from the
`MovieAnalytics.SemanticModel/` folder. Keep the folder layout intact, or update both M partitions
before refreshing.

## Folder structure

```text
reports/powerbi_checkpoint3/
├── MovieAnalytics.pbip
├── README.md
├── .gitignore
├── MovieAnalytics.Report/
│   ├── .platform
│   ├── definition.pbir
│   ├── definition/
│   │   ├── version.json
│   │   ├── report.json
│   │   └── pages/
│   │       ├── pages.json
│   │       ├── ExecutiveOverview/
│   │       ├── RevenueAnalysis/
│   │       ├── MovieGenreAnalysis/
│   │       └── TicketAnalysis/
│   └── StaticResources/SharedResources/
│       ├── BaseThemes/CY24SU10.json
│       └── BuiltInThemes/MovieAnalyticsTheme.json
└── MovieAnalytics.SemanticModel/
    ├── .platform
    ├── definition.pbism
    ├── .pbi/editorSettings.json
    └── definition/
        ├── database.tmdl
        ├── model.tmdl
        └── tables/
            ├── Movies.tmdl
            └── Genre Tokens.tmdl
```

## How to open in Power BI Desktop

1. Use Power BI Desktop on Windows ( recent versions that support PBIP/PBIR and TMDL ).
2. Open `MovieAnalytics.pbip` directly. If Desktop asks for a project, select
   `MovieAnalytics.Report/definition.pbir` instead.
3. Confirm the semantic model resolves to `../MovieAnalytics.SemanticModel`.
4. Refresh the model. If Desktop cannot resolve the relative CSV path, open
   Power Query, edit the `SourcePath` step in both `Movies` and `Genre Tokens`, and point it to the
   absolute path of `data/processed/checkpoint3.csv`.
5. Review each page and visual.
6. Only after successful validation, use **File → Save As** in Desktop to create a `.pbix` if a
   binary deliverable is required.

## Semantic model

`Movies` maps the six CSV columns to:

| CSV column | Model column | Type |
|---|---|---|
| `movie_name` | `Movie Name` | Text |
| `release_year` | `Release Year` | Whole number |
| `genre` | `Genre` | Text |
| `director` | `Director` | Text |
| `revenue` | `Revenue VND` | Decimal number |
| `tickets_sold` | `Tickets Sold` | Whole number |

`Genre Tokens` is a disconnected helper table created by splitting `Movies[Genre]` on the only
delimiter present in the source (`,`), trimming each token, removing blanks, and de-duplicating.
It produces 29 genre tokens. Combined genre strings are never counted as a single genre in genre
charts or the genre slicer. There is no relationship or bridge table between `Genre Tokens` and
`Movies`. Each report page has its own Genre slicer; these four slicers are separate and are not
synchronized across pages.

Power Query behavior:

- Validates the exact six-column schema and raises an error on mismatch.
- Validates that exactly 78 rows are present and raises an error otherwise.
- Validates that no cell is null or blank.
- Parses exact VND strings by removing `₫` and all thousands separators.
- Parses `tỷ` / `tỷ đồng` values by treating a comma as a decimal separator and multiplying by
  `1,000,000,000`.
- Uses `en-US` number parsing explicitly so results do not depend on the Desktop locale.
- Raises an error for any revenue or integer value it cannot parse; it does not invent values.
- Validates that `tickets_sold` is a positive whole number.

### DAX measures

Required measures are implemented in `Movies.tmdl`:

- `Total Movies`
- `Total Revenue VND`
- `Total Estimated Tickets`
- `Average Revenue per Movie`
- `Average Estimated Tickets per Movie`
- `Average Revenue per Estimated Ticket`
- `Revenue by Year`
- `Movies by Year`
- `Estimated Tickets by Year`
- `Revenue Share %`
- `Movie Share %`
- `Rank by Revenue`
- `Rank by Estimated Tickets`

Supporting measures: `__Movie In Genre Selection`, `Top 10 Revenue Value`, and
`Top 10 Ticket Value`.

`__Movie In Genre Selection` applies the disconnected `Genre Tokens` slicer per movie by converting
the comma-delimited genre string to a pipe-delimited path and testing `PATHCONTAINS`. KPI measures
iterate the 78-row `Movies` table exactly once, so genre splitting never duplicates movie counts,
revenue, or tickets.

Genre multi-select uses union/OR semantics: a movie qualifies when at least one selected token
matches its genre string. A movie that matches several selected genres is still iterated once, so
its revenue, tickets, and movie count are contributed exactly once.

`Rank by Revenue` and `Rank by Estimated Tickets` return `BLANK()` for movies that do not match the
active Genre Tokens selection. Their `RANKX` candidate set is
`FILTER(ALLSELECTED('Movies'[Movie Name]), CALCULATE([__Movie In Genre Selection]) = 1)`, so
nonmatching movies cannot receive a rank that passes the five Top 10 visual filters. Applying
`ALLSELECTED` only to `Movies[Movie Name]` preserves the active Release Year and Director filter
context.

Eleven visuals that display `Movies` columns directly (movie, director, year, or scatter details)
use a supported Advanced visual-level filter `Total Movies > 0`. This removes rows or groups with
no genre-matching movies because the disconnected `Genre Tokens` table cannot physically filter
the `Movies` table. The five Top 10 visuals rely on their existing rank filters and do not use this
additional filter.

## Report pages

1. **Executive Overview** — KPI cards, revenue/movie trends by year, top-10 revenue bar, top-10 revenue table.
2. **Revenue Analysis** — revenue trend, average revenue by year, revenue-share pie, top-10 revenue ranking, revenue-share table, revenue-per-ticket card.
3. **Movie & Genre Analysis** — year/genre/director slicers, top-10 revenue ranking, rank/share table, movies-by-genre and revenue-by-genre bars, director table, revenue-vs-ticket scatter.
4. **Ticket Analysis** — ticket KPI cards, top-10 tickets bar, tickets-by-year column, revenue-vs-ticket scatter, and the required ticket disclaimer.

All pages are 1280 × 720 widescreen and use `FitToPage`. Year and genre slicers are present on every
page. Visual tooltips include director, year, rank, and share fields where useful.

## Ticket disclaimer

The Ticket Analysis page includes this exact text:

> Ticket counts are a mixture of original, estimated, and manually entered values. They have not been independently verified as actual cinema admissions.

## Validation performed

Static validation only was performed in this environment:

- JSON files parse successfully and use documented PBIP/PBIR schema identifiers.
- Project, report, and semantic-model references are internally consistent.
- TMDL table, column, partition, and measure references are internally consistent.
- All visual field references point to existing model columns or measures.
- Revenue parsing rules were checked against the 70 exact-VND and 8 `tỷ đồng` source formats.
- Source CSV SHA-256 is unchanged.

Power BI Desktop runtime validation and `.pbix` export were **not** performed because Power BI
Desktop is not available in this Linux environment. Runtime refresh, visual rendering, and DAX
evaluation must be verified in Desktop before publishing.

## Scope

This project reads the source CSV only. It does not modify `checkpoint3.csv`, the scraper code,
the analytics code, or any existing visualization directories under `reports/`.
