---
name: Power BI Engineering
description: "Create, inspect, refactor, and validate professional Power BI projects using PBIP, PBIR, TMDL, Power Query M, DAX, and Microsoft-documented validation workflows."
---

# Power BI Engineering

Use this skill for Power BI development and review tasks involving Power BI Desktop projects, semantic models, report definitions, Power Query, DAX, and validation.

Before starting, read `references/official-resources.md`. Treat official Microsoft documentation and published schemas as the source of truth.

## Non-negotiable rules

- Inspect existing projects and files before making changes.
- Preserve source data. Never overwrite user data without explicit permission.
- Work incrementally. Change only the files needed for the requested task.
- Avoid unnecessary dependencies.
- Never generate a fake `.pbix` by renaming or copying another format. A PBIP project is not a PBIX file.
- Never claim that Power BI Desktop validation or PBIX export happened unless it actually did.
- Clearly separate static validation from Power BI Desktop runtime validation.
- Report the exact files created and modified.
- Do not commit or push unless explicitly requested.

## 1. Power BI project architecture

### PBIP project structure

A typical Power BI Desktop project has a top-level `.pbip` file, a semantic model folder, and a report folder:

```text
ProjectName/
├── ProjectName.pbip
├── ProjectName.SemanticModel/
│   ├── definition.pbism
│   └── definition/
│       ├── model.tmdl
│       ├── tables/
│       ├── relationships.tmdl
│       └── ...
└── ProjectName.Report/
    ├── definition.pbir
    └── definition/
        ├── report.json
        ├── pages/
        │   └── <page-id>/
        │       ├── page.json
        │       └── visuals/
        │           └── <visual-id>/
        │               └── visual.json
        └── ...
```

Use the documented schema and version identifiers for `.pbip`, `definition.pbism`, `definition.pbir`, `report.json`, `page.json`, and `visual.json`. Do not mix PBIR and PBIR-Legacy file structures.

### Report and semantic model separation

- The semantic model owns source queries, tables, columns, relationships, calculated objects, and measures.
- The report owns pages, visuals, filters, bookmarks, themes, tooltips, and field bindings.
- Reports reference semantic model fields. They should not redefine business logic that belongs in the model.
- Keep model changes and report changes isolated unless a field rename or measure change requires both.

### Project references and metadata

- The `.pbip` file links the report and semantic model folders and declares project properties.
- `definition.pbir` binds a report to a semantic model with either `byPath` or `byConnection`.
  - `byPath` uses a relative path with forward slashes and is appropriate for local PBIP projects.
  - `byConnection` targets a Fabric semantic model and is appropriate for service-hosted reports.
- `definition.pbism` declares the semantic model definition format and version.
- PBIR JSON files use `$schema` identifiers. Validate against the schema version that the file declares, not a newer or invented one.
- Use stable, unique identifiers for pages, visuals, tables, columns, and measures.
- Keep folder names and object names consistent with their declared identifiers where the format expects it.

## 2. Power Query M

### CSV ingestion

- Use `File.Contents` plus `Csv.Document` with explicit delimiter, encoding, quote style, and column handling.
- Promote headers only after confirming the header row is correct.
- Avoid hard-coded absolute local paths in portable project files. Use a documented relative path strategy and document refresh requirements.
- Preserve original source columns when they are needed for traceability.

### Data type conversion

- Apply explicit types with `Table.TransformColumnTypes`.
- Use an explicit culture where number or date interpretation could be locale-dependent.
- Validate that key numeric, date, and integer columns actually parsed to the intended types.
- Do not rely on automatic type detection for production models.

### Locale and currency handling

- Normalize currency symbols, non-breaking spaces, thousands separators, decimal commas, and suffixes such as billions or millions before conversion.
- Use a deterministic conversion path: remove formatting characters, normalize the decimal separator, then call `Number.FromText` with an explicit culture.
- Scale suffix-based values explicitly, for example billions by `1000000000`.
- Preserve the original display value if auditing or reconciliation requires it.
- Never guess a missing or ambiguous value.

### Data validation

- Check expected row counts, required columns, blank values, duplicate keys, invalid dates, negative values where impossible, and parse errors.
- Add an explicit error or validation column when errors need to be visible, or raise an error when strict failure is appropriate.
- Use `Table.SelectRowsWithErrors`, `try ... otherwise`, and controlled `error` statements deliberately.
- Make validation failures visible instead of silently dropping rows.

### Error handling

- Wrap fragile text parsing with `try` and expose the failure reason.
- Keep raw, staged, and final queries separate so errors can be traced.
- Do not swallow errors with `otherwise null` unless a null is an explicitly acceptable business outcome.
- Validate that final queries return the expected shape before loading them into the model.

### Query dependencies

- Build a clear dependency chain: source, raw, staged, typed, validated, final.
- Disable load for staging queries where appropriate.
- Avoid circular references and unnecessarily duplicated source reads.
- Give queries stable names that do not depend on display labels.
- Consider query folding for database sources, but never assume folding after custom functions or unsupported transforms.

## 3. Data modeling

### Fact and dimension tables

- Classify tables by role: fact tables store events or measurements; dimension tables describe entities used for filtering and grouping.
- Store numeric business measurements in fact tables.
- Store descriptive attributes in dimension tables.
- Keep fact tables at a consistent grain.
- Avoid mixing fact and dimension roles in one table unless the design is intentionally small and documented.

### Star schema

- Prefer a star schema: dimensions surround one or more fact tables.
- Use surrogate keys when natural keys are unstable, large, or unsuitable for modeling.
- Normalize denormalized source data in Power Query when useful.
- Document any deliberate denormalization.

### Relationships and cardinality

- Use one-to-many relationships from dimension to fact in most models.
- Set filter direction to single unless a specific, tested requirement needs bidirectional filtering.
- Avoid ambiguous relationship paths.
- Use inactive relationships with `USERELATIONSHIP` when the same dimension plays multiple roles.
- Validate that relationship columns have compatible types and no unmatched keys where integrity is expected.

### Date tables

- Use a dedicated date table for time-based analysis.
- Ensure a contiguous date range covering all facts.
- Mark the table as a date table in Power BI when appropriate.
- Include year, quarter, month, day, and sort columns.
- Time intelligence functions depend on a proper date table and contiguous dates.

### Column types and formatting

- Set correct data types for every column used in relationships, sorting, aggregation, or time intelligence.
- Configure format strings for currency, percentages, counts, and dates.
- Set `summarizeBy` deliberately; numeric keys should usually not be summed.
- Hide technical columns such as keys, helper columns, and raw parsing fields from report view.
- Preserve original names in hidden columns when users need traceability.

### Hidden technical columns

- Hide columns that exist only for relationships, sorting, tokenization, or parsing.
- Do not hide columns that report authors need for legitimate analysis.
- Document helper tables and their intended use, especially disconnected tables used with `PATHCONTAINS`, `TREATAS`, or slicer logic.
- Ensure helper tables do not multiply fact rows or duplicate KPI values.

## 4. DAX engineering

### Measures versus calculated columns

- Prefer measures for aggregations and business logic that responds to filter context.
- Use calculated columns only for row-level attributes that must be stored in the model.
- Avoid calculated columns for values that can be computed by a measure.
- Keep base measures and presentation measures separate when formulas become complex.

### Filter context and row context

- Understand that measures evaluate in filter context and iterators introduce row context.
- Use `CALCULATE` to modify filter context.
- Use `FILTER` when row-by-row conditions are required.
- Use `ALL`, `REMOVEFILTERS`, `ALLEXCEPT`, and `KEEPFILTERS` deliberately and test their impact on visuals.
- Use `ALLSELECTED` when rankings or shares should respect user selections.

### Time intelligence

- Use a proper date table before applying `TOTALYTD`, `DATEADD`, `SAMEPERIODLASTYEAR`, or similar functions.
- Account for incomplete current periods.
- Use explicit date logic instead of time intelligence functions when business calendars are nonstandard.

### Ranking and Top N

- Use `RANKX` with a deliberate tie-breaker and deterministic sort order.
- Use `TOPN` for Top N selection, then calculate values over the selected set.
- Avoid relying on visual-level Top N alone when the logic must be reusable in measures.
- Test ranking behavior with ties, blanks, slicers, and cross-filtering.

### Safe division

- Use `DIVIDE` for ratios and shares.
- Provide an explicit alternate result when blank is not appropriate.
- Never divide directly with `/` when the denominator can be zero or blank unless that behavior is intentional and tested.

### KPI and analytical measures

- Create explicit measures for totals, averages, distinct counts, shares, rankings, and derived rates.
- Use `COUNTROWS`, `DISTINCTCOUNT`, `SUM`, and `SUMX` according to the required grain.
- Check that averages use the intended denominator.
- Ensure measures do not double count when disconnected helper tables or multi-value columns are involved.
- Use variables for readability and repeated expressions.

### Measure naming and formatting

- Use clear names such as `Total Revenue VND`, not ambiguous labels.
- Apply format strings, descriptions, display folders, and consistent units.
- Keep measure names stable because visual bindings reference them.
- Avoid implicit measures where explicit measures exist.

## 5. Report design

### Executive dashboards

- Start with a small set of KPI cards: totals, averages, rates, and the most important comparison.
- Add only the charts needed to answer executive questions.
- Keep the first page readable at a glance.
- Surface caveats and data-quality notes where users will see them.

### Analytical report pages

- Use dedicated pages for deep dives such as time trends, category analysis, and rankings.
- Provide enough context through titles, subtitles, slicers, and captions.
- Use consistent measures across pages so numbers reconcile.

### KPI cards

- Bind cards to explicit measures.
- Avoid duplicated KPI cards unless they show genuinely different metrics.
- Use conditional formatting sparingly and consistently.
- Include units and caveats in titles or labels.

### Slicers

- Use slicers for the most common filters: date, category, geography, status, and other key dimensions.
- Sync slicers across pages when users expect continuity.
- Avoid too many slicers on one page.
- Test slicer interactions with all dependent visuals and measures.

### Charts and tables

- Match visual type to the question: trend, comparison, distribution, composition, or detail.
- Use bar or column charts for categorical comparisons.
- Use line charts for time series.
- Use tables or matrices for detailed records.
- Use Top N visuals with explicit sorting.
- Avoid pie charts with many categories.
- Verify sort order, data labels, axis formatting, and tooltip fields.

### Drill-through and tooltips

- Use drill-through pages for entity-level detail.
- Keep drill-through filters explicit and test them from the source visual.
- Use tooltip pages to add context without cluttering the main canvas.
- Add a clear back button or navigation where users need it.

### Layout, color, and typography

- Use a consistent grid, margins, alignment, and spacing.
- Choose an accessible color palette with sufficient contrast.
- Use a small number of fonts and consistent font sizes.
- Use titles that state the insight or metric, not generic labels.
- Keep visual sizes and positions within page bounds.
- Avoid overlaps and check z-order.
- Assign sensible tab order and names for accessibility.

### Responsive visual positioning

- Use the declared page width and height.
- Verify every visual has valid `x`, `y`, `width`, `height`, and `z` values.
- Keep visuals inside the canvas and aligned to the grid.
- If mobile layout is required, validate it separately; do not assume desktop layout adapts correctly.

## 6. TMDL and PBIR correctness

### Follow actual specifications

- Use Microsoft TMDL grammar and Tabular Object Model property rules for semantic model files.
- Use published PBIR JSON schemas for report files.
- Use the schema version declared by each file.
- Do not copy examples from unsupported or unrelated versions.

### Never invent unsupported properties

- Do not add properties, objects, or structural levels that are not documented for that context.
- A property being valid on one TMDL object does not mean it is valid on another.
- Treat `lineageTag`, `annotation`, `expression`, `sourceColumn`, `formatString`, and similar properties according to the exact object where they appear.
- If uncertain, check the TMDL object reference or validate with a supported parser.

### Respect property context and indentation

- TMDL uses whitespace indentation to express object hierarchy.
- Use tabs consistently where the format expects them.
- Place object properties under the correct object declaration.
- Keep multi-line DAX and M expressions in the correct expression blocks.
- Quote object names containing spaces, dots, colons, equals signs, or single quotes according to TMDL rules.

### Verify object references and identifiers

- Check that every relationship column, hierarchy level, sort-by column, and visual binding references an existing object.
- Check that PBIR `queryRef` values and source entities resolve to model tables, columns, and measures.
- Use unique identifiers for tables, columns, measures, pages, and visuals.
- Use valid GUIDs for lineage tags where required.
- Ensure page and visual folder identifiers match their JSON `name` values when expected.

### Do not trust syntax validation alone

- Valid JSON only proves that a PBIR file parses as JSON. It does not prove that the file is valid PBIR.
- JSON schema validation does not prove that visual fields resolve against the semantic model.
- TMDL that looks structurally plausible can still fail in Power BI Desktop because a property is unsupported in its object context.
- Cross-file validation is required for a trustworthy project.

## 7. Validation workflow

Before declaring a Power BI project complete, perform the following checks.

1. **Inspect all generated files.**
   - List the project tree and read the files that were created or changed.
   - Confirm that no unintended files were modified.

2. **Validate JSON syntax.**
   - Parse every JSON file.
   - Validate against the declared `$schema` when a supported validator is available.
   - Confirm schema versions are consistent with the documented format.

3. **Validate TMDL with an appropriate parser whenever available.**
   - Prefer Power BI Desktop, Tabular Editor, AMO/TOM, or another supported TMDL validation mechanism.
   - If no parser is available, perform static inspection only and say so explicitly.
   - Check indentation, object hierarchy, property context, and quoted names.

4. **Validate DAX references and measure dependencies.**
   - Confirm all referenced tables, columns, and measures exist.
   - Confirm no measure depends on a missing or misspelled object.
   - Review `CALCULATE`, `FILTER`, `ALL`, `REMOVEFILTERS`, `DIVIDE`, and time intelligence usage.

5. **Validate Power Query expressions.**
   - Confirm source paths and encodings.
   - Confirm data types, locale handling, currency parsing, and error paths.
   - Confirm row counts and validation checks.
   - Evaluate refresh behavior when a supported engine is available.

6. **Check report visual references and semantic model bindings.**
   - Confirm every visual has a valid position, visual type, and unique name.
   - Confirm every field, measure, sort field, filter, and tooltip binding resolves.
   - Confirm theme and resource package paths exist.
   - Confirm `definition.pbir` points to the intended semantic model.

7. **Check source data integrity.**
   - Confirm the source file is the correct one and has not been altered.
   - Confirm row count, column names, encodings, missing values, duplicates, and expected value ranges.
   - Reconcile key aggregates independently.

8. **Run Power BI Desktop runtime validation when available.**
   - Open the PBIP or PBIR in Windows Power BI Desktop.
   - Refresh the model.
   - Confirm no load, refresh, DAX, Power Query, or visual errors.
   - Confirm each page renders and measures reconcile.

9. **Clearly distinguish validation levels.**
   - State exactly which static checks passed.
   - State exactly which runtime checks could not be performed.
   - Never claim a PBIX was generated if only a PBIP project exists.

## 8. Documentation and references

- Consult `references/official-resources.md` for official Microsoft documentation links.
- Use official Microsoft Learn pages and Microsoft-maintained schema repositories.
- Do not invent documentation URLs.
- Keep version-specific behavior tied to the matching documentation version.
- Document assumptions, data caveats, refresh instructions, and validation limitations in the project README when appropriate.

## 9. Operating rules

- Inspect before changing anything.
- Preserve datasets and user files.
- Avoid installing dependencies unless the user explicitly allows it.
- Prefer incremental, reviewable edits.
- Never overwrite user data without permission.
- Never fabricate data, mappings, measures, or validation results.
- Never create a fake PBIX.
- Report exact created and modified files.
- Do not commit or push unless explicitly requested.
