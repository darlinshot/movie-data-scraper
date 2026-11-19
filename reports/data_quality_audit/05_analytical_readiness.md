# 05 — Cross-Dataset Analysis & Analytical Readiness

## 5.1 Cross-dataset comparison

### `movies.csv` vs `full_export.csv`

| Aspect | Finding |
|---|---|
| Row count / order | Both 92 rows; `movie_name` order identical in all 92 positions |
| Join mechanism | **Positional**, not key-based: `build_full_export()` iterates `movies.to_dict("records")` in order and appends a row; the only common column is `movie_name` (never used as a join key) |
| Revenue | `full_export.revenue` = BOV string in **81/92** rows, DTP string in **11/92**; therefore it inherits all 21 >10% conflicts and all 6 extreme mismatches. Raw formats are mixed (`714 tỷ` vs `714,030,584,098₫`) |
| Tickets | 5 web-`found` values copied through; 11 web-`needs_review` values correctly withheld and placed in `to_review_tickets_sold` |
| Fields lost | `source_url_doanhthuphim`, `source_url_bovn`, `revenue_doanhthuphim`, `revenue_bovn`, `title_bovn`, `match_status`, `collection_status` |
| Fields added | `revenue`, `to_review_director`, `to_review_revenue`, `to_review_tickets_sold`, `to_review_screening_count`, `to_review_match` |
| Duplicate rows introduced | None (92 → 92) |

**Information loss:** the export cannot answer "which source does this revenue come from?", "was this match accepted or uncertain?", or "what page is this from?" without rejoining to `movies.csv` by row position or name. `to_review_revenue` covers the 21 conflicts and notes where revenue is missing or the match uncertain, but it is free text, not a structured flag.

### `movies.csv` vs `collection_log.csv`
- Same 92 rows in the same order; `movie_name`, `title_bovn`, both URLs, `match_status`, `collection_status` are identical in all rows (**0 disagreements**).
- `collection_log.csv` is the only CSV with `match_score` and `match_reason`. Dropping these from `movies.csv`/`full_export.csv` removes the ability to audit matching without the state files.

### `movies.csv` vs `unmatched_movies.csv`
- `unmatched_movies.csv` = exact 11-row subset (10 `not_found` + 1 `needs_review`); all 11 DTP URLs also exist in `movies.csv`. No extra or missing records; the filter in `pipeline.write_outputs()` is correctly implemented.
- The one `needs_review` row carries a BOV URL and BOV revenue into the unmatched file, which is appropriate but means "unmatched" here means "not reliably matched", not "no candidate".

### `tickets_sold_web.csv` vs `full_export.csv`
- 92 web-evidence rows join 92/92 to the master by `source_url_doanhthuphim`.
- 16 candidates found; 5 `found` copied into `full_export.tickets_sold`, 11 `needs_review` withheld with evidence notes. No `found` candidate was dropped, no `needs_review` candidate was wrongly promoted.
- However, `full_export.csv` does **not** retain the web evidence URL, snippet, confidence or basis for the 5 accepted values. A analyst must return to `tickets_sold_web.csv` (joining by movie name, since the export has no key) to verify them.
- `tickets_sold_web.csv.error` is empty in all 92 rows; absent search failures are indistinguishable from "no candidates".

### Is `full_export.csv` a reliable analytical dataset?

**No — not in its current form.** It is a convenient human-review sheet, not an analysis-ready table:
1. No primary key or source URL.
2. `revenue` mixes two sources, two precisions and two textual formats, and prefers the conflicting source.
3. `tickets_sold` is populated for 5/92 rows from heuristic news evidence with no retained provenance in the file.
4. `screening_count` and `to_review_screening_count` are 100% empty.
5. No match status, score or review flag — a probable false positive (row 51) and a `needs_review` match (row 84) look identical to clean rows.
6. `release_year` is a string; `genre` is an unnormalized comma-separated string; no full release date exists.
7. BOM prefix (`utf-8-sig`) requires explicit encoding handling in some tooling.

`movies.csv` + `collection_log.csv` + `tickets_sold_web.csv`, joined on `source_url_doanhthuphim`, form a more faithful (though still imperfect) analytical base than `full_export.csv`.

---

## 5.2 Analytical readiness by use case

| Use case | Verdict | What is available | What is missing / quality issues |
|---|---|---|---|
| **A. Exploratory Data Analysis (EDA)** | **PARTIALLY READY (with caveats)** | 92 named movies, release year, raw genre, director, two raw revenue strings, match provenance in adjacent files | Revenue must be parsed and source-labelled; 21 conflicts; tickets 5/92; no key in export; no date; small n. EDA limited to descriptive distributions of DTP revenue, year, genre frequency and match status |
| **B. Power BI dashboards** | **NOT READY** | Flat CSVs, one row per movie, status enum fields | No key/relationship, mixed-unit revenue string, string years, unnormalized genre, no date column for time intelligence, no review flags, mixed encodings. Would require a semantic model built from `movies.csv` + `collection_log.csv` + `tickets_sold_web.csv`, not the final export |
| **C. Statistical analysis** | **NOT READY** | One measured outcome (revenue) with two disagreeing measurements | Unknown sampling frame (all available DTP records, not a designed sample), n=92 heavily skewed to 2023–2026 (56/92), measurement error in 25.9% of matched revenues, no control variables (runtime, budget, rating, country) |
| **D. Machine Learning (general)** | **NOT READY** | 92 rows; genre/director/year as weak categorical features | n=92 is far too small for reliable generalisation; 97.8% missing original title, 94.6% missing tickets, 100% missing screenings; no rating/budget/runtime; target definition (which revenue?) unresolved; no train/validation design. Numeric columns alone do not make this ML-ready |
| **E. Movie revenue prediction** | **NOT READY** | Rounded DTP revenue for all 92; exact BOV revenue for 81 | Target unreliable (21 conflicts, 6 extreme); no budget, runtime, cast, rating, marketing spend or release-width features; no out-of-sample design; mixing domestic VND with worldwide concepts would be invalid |
| **F. Movie performance / box-office analysis** | **PARTIALLY READY (narrow scope)** | DTP ranking, matched BOV page presence, 5 web ticket figures, release years | Only domestic Vietnamese box office; no time series, no daily/weekly history, no admissions for almost all films, no screens; must exclude or manually resolve the 21 conflicts and the 11 uncertain matches before reporting |

## 5.3 Minimum conditions to reach "ready"

1. Build a single canonical movie table keyed by `movie_id`/DTP URL, preserving all source URLs and original titles.
2. Store revenue as numeric `amount_vnd` + `raw_value` + `source` + `scope` + `as_of_date`; resolve or flag the 21 conflicts and 6 extreme mismatches.
3. Add `review_status`/`reviewed_at` and resolve the six priority records in report 03 §3.9.
4. Add ISO release date and normalized genre/director fields.
5. Keep ticket counts separate with evidence and basis; leave `screening_count` empty until legitimately available (do not impute).
6. Retire `full_export.csv` as the analysis input, or rebuild it as a key-preserving, typed, source-labelled table.
