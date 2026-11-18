# 06 — Executive Summary

**Audit date:** 2026-11-18 · **Scope:** all local files in `movie-data-scraper` (26 files, 5 data CSVs, 3 state JSONL files, source code). Read-only; no scraping or HTTP requests performed. No original data was modified.

## Headline findings

- The collection covers **92 movies**. Every dataset has a stable DTP URL key with **0 duplicate keys, 0 exact duplicate rows and 0 duplicate normalized titles**. Structure is good; content trustworthiness is not.
- **42/92 records (45.7%)** have at least one *core* quality issue (uncertain match, >10% revenue conflict, missing BOV revenue, missing director, or uncertain ticket evidence). Under a broad definition that also counts the effectively unpopulated `original_title` field, 91/92 (98.9%) have an issue — but that figure is driven by one optional field.
- **21/81 (25.9%)** of matched movies have DTP vs BOV revenue differing by more than 10%, including **6 extreme cases** (5 where BOV is roughly 900×–4,350× smaller than DTP, 1 where BOV is 14.4× larger). `full_export.csv` uses the BOV figure in every case, so the final export inherits all of them.
- Match statuses: **81 matched (88.0%), 1 needs_review (1.1%), 10 not_found (10.9%)**. At least one auto-accepted match is a probable false positive (row 51), and several others are suspicious.
- Ticket counts: **0/92** official counts from BOV; only **5/92** heuristic web-derived figures in the export, based on news headlines/snippets (2 of them at the minimum acceptance confidence of 55). Screening counts are **0/92 everywhere**.
- `full_export.csv` drops all source URLs, both raw revenue fields, match status and match score. It is **not a reliable analytical dataset**.

## Explicit answers to the required questions

**1. Is the dataset clean?**
No. Structurally tidy (no duplicate keys, no malformed URLs, no invalid years), but materially unclean: 45.7% of rows carry a core issue, two columns are 100% empty across all datasets, revenues conflict across sources, and at least one match is likely wrong.

**2. What percentage of records have significant quality issues?**
**45.7% (42/92)** under the core definition. Contributing issues (overlapping): revenue conflict 21, uncertain ticket evidence 11, missing BOV revenue 11, `not_found` 10, missing director 3, `needs_review` 1. A broad definition including missing `original_title` yields 98.9% (91/92) — reported for transparency, but it overstates unusability because that field is 97.8% empty by construction.

**3. Which columns have the highest missing-value rates?**
- `tickets_sold` and `screening_count`: **100%** missing in `movies.csv`, `unmatched_movies.csv` and `full_export.csv`.
- `original_title`: **97.83%** (90/92).
- In `full_export.csv`: `to_review_screening_count` **100%**, `tickets_sold` **94.57%**, `to_review_match` 98.91%, `to_review_director` 96.74%, `to_review_tickets_sold` 88.04%.
- In `tickets_sold_web.csv`: all 16 evidence columns **82.61%** missing and `error` **100%** empty.
- Highest non-trivial rates among otherwise-populated fields: `revenue_bovn` 11.96%, `title_bovn`/`source_url_bovn` 10.87%, `director` 3.26%.

**4. Are there duplicate or potentially incorrectly matched movies?**
No exact duplicates or duplicate normalized titles exist. **Potential incorrect matches do exist:**
- Row 51 `Chị Mười Ba: 3 Ngày Sinh Tử` → BOV `Chị Mười Ba 2: 3 Ngày Sinh Tử`, auto-accepted at score 100 — a confirmed blind spot in the sequel-number penalty (both strings yield sequel digit "3" because the code takes the last number).
- Row 32 `Em Chưa 18` (2017) → BOV page dated 2025-06-24, score 94, plus a 99.96% revenue conflict.
- Row 84 `Kính Vạn Hoa: Phim Điện Ảnh` → `Kính Vạn Hoa: Bắt Đền Con Ma`, score 83.25 — correctly flagged `needs_review`, but its BOV revenue still feeds the export.
- Row 78 `Cô Ba Sài Gòn` → BOV slug `co-ba-sai-gon-2`, possible duplicate page.
- Rows 7, 10, 42, 47, 49, 80 differ only in punctuation/case/alternate-title form and appear benign.

**5. Are the revenue and ticket count fields trustworthy?**
**Revenue: partially.** DTP values are rounded but internally consistent (92/92); BOV values are precise and agree with DTP within 10% for 60/81 matched rows, but **21 conflict** and **6 are extreme**. Without the raw BOV page text (not persisted locally), the cause cannot be confirmed. `full_export.revenue` is **not trustworthy** because it silently prefers BOV in all 81 cases.
**Ticket counts: no.** Official counts are 100% missing. The 5 exported values are point-in-time news-snippet figures (`tickets_basis='cumulative'` is assigned by keyword cues, not verified final totals); 3 of 5 evidence URLs are Google News RSS redirects. Eleven additional candidates are correctly quarantined as `needs_review`. Screening counts are entirely absent.

**6. Is `full_export.csv` suitable for analysis?**
No. It is a key-less, positional merge that mixes two revenue formats and sources, prefers conflicting BOV figures, retains only 5 ticket values without their evidence, has a 100%-empty screening column, and drops match status, score, reason and all source URLs. Use `movies.csv` + `collection_log.csv` + `tickets_sold_web.csv` joined on `source_url_doanhthuphim` as a more faithful base (still requiring cleaning).

**7. What important data should be added?**
Priority order: (P0) stable movie ID and URLs; numeric revenue with `source`/`scope`/`as_of_date` and raw text; match + human-review flags; full ISO release date. (P1) true original/alternate titles, evidenced ticket counts, screening counts, normalized genre, runtime, language/country, normalized director. (P2) IMDb/TMDb ratings and vote counts, budget, distributor, worldwide revenue, daily/weekly revenue and ticket history, cast. Ratings must be stored with an explicit scale and never be confused with the fuzzy `match_score`. See report 04.

**8. What should be cleaned first?**
1. Reconcile the 21 revenue conflicts and resolve the 6 extreme cases; store both sources with numeric parsing and scope labels rather than choosing one silently.
2. Manually review rows 51, 32, 84, 78, 93, 91.
3. Add `review_status`/`reviewed_at` and restore `match_score`/`match_reason` to the analytical table.
4. Parse release dates and normalize genre/director; populate real alternate titles.
5. Rebuild `full_export.csv` with keys and typed columns (or retire it).

**9. What should be collected next?**
First, **do not collect more sources**: re-extract the BOV revenue block with the raw page text retained so scope can be verified (no new source website assumptions). Then collect full release dates and alternate titles from the existing DTP/BOV pages (respecting terms and rate limits), legitimate public ticket/screening figures if available, and normalized metadata (runtime, country, language) from TMDb with attribution. Ratings/budget only after the P0 issues are closed.

**10. What is the recommended final dataset structure?**
A **canonical movie table** (one row per film, keyed by `movie_id` with `source_url_doanhthuphim` and `source_url_bovn`), plus small satellite tables:
- `movie_alias(movie_id, title, language, title_type, source)`
- `revenue_observation(movie_id, source, amount_vnd, raw_value, scope[cumulative/daily/weekly], as_of_date, source_url, evidence_snippet)`
- `ticket_observation(movie_id, source, count, scope, as_of_date, source_url, snippet, confidence, status)`
- `screening_observation(movie_id, source, count, scope, as_of_date, source_url)`
- `match_review(movie_id, match_status, match_score, match_reason, review_status, reviewer, reviewed_at)`
- `movie_attribute(movie_id, release_date, genre_code, director_id, runtime_min, language, country, ...)`

Keep raw values and URLs alongside parsed values; never overwrite a missing value with an estimate.

---

## Prioritized action plan

### P0 — Critical (block all analysis)
1. Quarantine the 6 extreme revenue conflicts; re-extract and verify BOV revenue scope, persisting raw page evidence. *(Affects `full_export.revenue` for 6 rows; 21 rows need reconciliation.)*
2. Manually review matches at rows 51, 32, 84, 78, 93, 91; fix the `_sequel_digits()` last-number bug in `matching.py`.
3. Add `review_status`, `reviewed_at`, `reviewer`; restore `match_score`/`match_reason` to the analytical output.
4. Rebuild the export with an explicit key, separate numeric revenue fields, source labels and typed release dates; stop using the current `full_export.csv` for analysis.

### P1 — Important
5. Populate real original/alternate titles (currently 2/92 and invalid).
6. Add ISO release date and normalize genre (62 raw strings) and director (50 raw strings).
7. Add evidenced ticket counts with scope/as-of/source; keep `screening_count` empty until legitimately available.
8. Enrich runtime, original language and production country from TMDb with attribution.

### P2 — Optional
9. IMDb/TMDb ratings + vote counts (explicit scale, source, as-of date).
10. Budget, distributor, domestic vs worldwide revenue split, daily/weekly history, cast.
11. Only then evaluate modelling; require a documented sampling frame, sufficient sample size and a held-out evaluation design.

---

## Confirmed problems / potential problems / evidence limitations

**Confirmed**
- 0 duplicates; 92 movies; status counts 81/1/10.
- `tickets_sold` and `screening_count` 100% empty; `original_title` 97.83% empty.
- 21 revenue conflicts >10%, 6 extreme; `full_export` always prefers BOV.
- Row 51 auto-matched to a different sequel number at score 100; `_sequel_digits()` takes the last number in both strings.
- Row 84 `needs_review` match supplies revenue to the export; no human-review fields exist.
- `full_export.csv` drops 7 source/provenance columns; joins are positional.
- BOV raw page text is never persisted (`_bov_detail_raw` empty in all 92 state records).

**Potential (needs live verification, which was out of scope)**
- Whether the small BOV revenue figures are daily/weekly values, per-screening prices, stale snapshots or genuinely different-scope totals.
- Whether rows 32, 78, 93 and 91 point to the wrong BOV page/release.
- Whether any of the 10 `not_found` movies genuinely have a BOV page (absence was not independently checked).
- Whether the 5 accepted web ticket figures are final cumulative totals.

**Limitations caused by unavailable evidence**
- No HTTP access was permitted, so website completeness (all "Show more" records collected), current page content and source terms compliance could not be verified.
- No rating, runtime, budget, release date, country, language, cast, distributor or screening-count data exists locally, so no analysis of those dimensions is possible.
- `pandas`/`rapidfuzz` are not installed; profiling used stdlib re-implementations of the project's own parsing/normalization logic. Fuzzy scores were read from stored `collection_log.csv`, not recomputed.

---

## Final verdict

**NOT READY FOR ANALYSIS.**

Justification: 45.7% of the 92 records have at least one core quality issue; 25.9% of matched movies have conflicting revenue and the final export actively propagates the conflicting source; at least one auto-accepted match is a probable false positive; tickets and screenings are effectively absent (5/92 and 0/92); and the designated final dataset has no key, no provenance and mixed units. A screened subset of ~50 records passes the narrow core-issue screen and may be used for *exploratory, descriptive DTP-revenue analysis only* after documenting the exclusions. It is not sufficient for dashboards, statistical inference, machine learning or revenue prediction.
