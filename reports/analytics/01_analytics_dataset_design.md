# 01 — Analytics Dataset Design for Python EDA & Power BI (Single Flat CSV)

**Status:** design proposal only. No implementation, no analytical CSV export, no source code, raw CSV/JSONL, manifest, database or prior report modified, no scraping and no HTTP requests performed.
**Date:** 2026-11-18.
**Evidence basis:** counts previously verified in this report from `data/*.csv` (5 files), `state/*.jsonl` (3 files), `src/movie_data_collector/*.py`, `pyproject.toml`, and prior audit/architecture reports. This focused revision re-checked the row-51 sequel-number false positive and the ticket-evidence fields in the raw files; it does not change source data or create any output.

---

## 1. Objective and analytical scope

### 1.1 Objective

Design **exactly one flat analytical CSV** that can be produced from the existing raw scraper outputs, explored with Pandas/NumPy, and imported directly into Power BI.

The project workflow is:

`Raw scraper data → Python cleaning and transformation → One analytical CSV → Power BI`

This is a CSV-based data visualization exercise, **not** a database or production data-platform project. The design must therefore be simple enough to build in a few scripts, but strict enough that a dashboard cannot silently present a conflicting, unverified, candidate-held or wrongly-matched revenue as a fact.

### 1.2 Scope decisions

| In scope | Out of scope |
|---|---|
| One movie-level analytical CSV with one row per `movie_id` | A database, warehouse, lakehouse or production architecture |
| Pandas/NumPy analysis of a single typed DataFrame | Multiple final analytical CSV exports |
| Descriptive movie, year, genre and director analysis | Revenue prediction, ML, ROI, ratings/budget analysis |
| Source-separated exploratory DTP/BOV revenue comparison | Official revenue conclusions while scope is unverified |
| Match and data-quality diagnostics | Ticket attendance conclusions from unverified candidates |
| A flat Power BI table with no analytical relationships | Empty or speculative screening/ticket fact tables |

### 1.3 Relationship to the prior design

This revision **replaces the previous five-table analytical design** with one movie-grain table. Raw source files and historical audit reports remain unchanged. The canonical-data-model report may continue to describe a future normalized system of record, but this project does **not** implement it.

The following remain true:

- One source of truth for analysis: `data/analytics/movie_analytics.csv`.
- One row per movie; no duplicate movie rows.
- No relationship model is required in Power BI.
- Internal Python DataFrames are allowed; only the final export is restricted to one CSV.

---

## 2. Verified source facts and limits

### 2.1 Exact build inputs

Only the following files are actual inputs to the analytics build.

| Class | File | Rows | Build use | `input_hash_before_build` |
|---|---|---:|---|---|
| Required | `data/movies.csv` | 92 | Master movie list, DTP URL, metadata, stored BOV URL/title and revenue strings. | **Always** |
| Required | `data/collection_log.csv` | 92 | Raw matcher status, `match_score` and `match_reason`. | **Always** |
| Required | `data/tickets_sold_web.csv` | 92 | Ticket candidate rows, status and evidence URLs. | **Always** |
| Required | `state/boxoffice_matches.jsonl` | 92 | BOV candidate context used to validate/quarantine mappings and record BOV evidence availability. | **Always** |
| Build metadata | `state/analytics_movie_id_map.json` | variable | Persistent `movie_id` mapping when present; absent on the first build. | **When present and read** |

`state/analytics_movie_id_map.json` is build metadata, not an analytical CSV, not a raw scraper output and not imported into Power BI.

### 2.2 Audit-only and deprecated files

| File | Rows | Role | Build use |
|---|---:|---|---|
| `state/doanhthuphim_movies.jsonl` | 92 | Raw DTP link text in `_dtp_raw`; no persisted DTP detail body. | Audit cross-check only; excluded from build values. |
| `state/web_tickets_progress.jsonl` | 92 | Typed mirror of the web ticket evidence. | Audit cross-check only; excluded from build values. |
| `data/unmatched_movies.csv` | 11 | Historical `not_found`/`needs_review` subset. | Consistency check only; excluded from build values. |
| `data/full_export.csv` | 92 | Deprecated key-less review sheet with `revenue = bov_raw or dtp_raw`. | **Excluded** from the build. |

Audit-only and deprecated files are not build inputs and must not contribute values to `movie_analytics.csv`.

### 2.3 Input hashing lifecycle

| Field | Exact meaning |
|---|---|
| `input_hash_before_build` | A mapping of file path → SHA-256 computed at the start of the build, immediately after each actual input is read. It always includes the four Required files from §2.1. If `state/analytics_movie_id_map.json` exists and is read, its pre-build hash is also recorded here. |
| `mapping_hash_after_build` | A single SHA-256 of `state/analytics_movie_id_map.json` after successful mapping validation/persistence, recorded only when that file exists after the build. It is a separate field, not a replacement for the mapping's `input_hash_before_build` entry. |

Rules:

1. The four Required raw input files must always be hashed before the build uses them. A missing hash for any one is a validation failure.
2. A missing mapping JSON on the first build is expected and is **not** a hashing failure; no mapping entry appears in `input_hash_before_build` in that case.
3. Raw input files must not change during the build. Re-hash them at the end and require equality with their `input_hash_before_build` values.
4. The mapping JSON may legitimately change when new `movie_id` values are assigned or mapping metadata is updated. Its pre-build and post-build hashes are **not** required to match.
5. Do not write a new/updated mapping JSON until the analytical DataFrame has passed every pre-export validation in §6. In-memory `movie_id` assignment is not persistence.
6. After those validations pass, persist the mapping JSON, verify persistence, and then record `mapping_hash_after_build`; record it after an unchanged successful build too, even when it equals the pre-build mapping hash.
7. If any transformation or pre-export validation fails, do not persist a new/updated mapping and do not overwrite the analytical CSV. If mapping validation or persistence fails, abort before exporting `movie_analytics.csv`; do not overwrite an existing analytical CSV.
8. Audit-only and deprecated files are not build inputs and are excluded from both hash fields.

This is a local validation-report convention only. No database, external manifest service, warehouse or additional architecture is introduced.

### 2.4 Verified counts to preserve

| Fact | Verified count | Treatment in the flat CSV |
|---|---:|---|
| Movies | 92 | `movie_analytics.csv` must contain exactly 92 rows. |
| `matched` / `needs_review` / `not_found` | 81 / 1 / 10 | `bov_match_status` is the **diagnostic matcher result**, not proof of a valid movie identity; all movies remain in the base universe. |
| DTP revenue observations | 92 | `dtp_revenue_vnd` populated for all 92; raw string retained separately. |
| BOV URLs | 82 | 79 valid stored BOV revenues + 1 quarantined false-positive revenue + 1 accepted-without-revenue + 1 candidate. |
| Stored BOV revenue observations | 80 | 80 revenues were stored under `matched` mappings: 79 valid mappings populate `bov_revenue_vnd`; 1 known false positive (line 51) is quarantined into `bov_quarantined_revenue_*`. |
| Valid revenue comparison rows | 79 | `include_revenue_comparison=1` for 79 only; all remain `insufficient_evidence`. |
| Quarantined false-positive mapping | 1 | Line 51, `Chị Mười Ba: 3 Ngày Sinh Tử`; BOV value preserved in `bov_quarantined_revenue_raw` / `_vnd`, never in `bov_revenue_vnd`. |
| Candidate-held BOV revenue observation | 1 | Line 84; `bov_candidate_revenue_vnd` populated for 1 only; never copied into `bov_revenue_vnd`. |
| Magnitude gap warnings | 21 | `magnitude_gap_warning=1` for 21 rows: 20 valid comparisons + 1 candidate-held warning-only row. Line 51 is excluded by mapping state; rows without usable BOV revenue have no warning. |
| Extreme gaps | 6 | Retained as warnings, not interpretations. |
| Confirmed revenue conflicts | 0 | `revenue_conflict_flag=0` for all 92 until all gates pass. |
| Verified cinema admissions | 0 | `ticket_verified_admissions` NULL for all 92; no ticket total is asserted. |
| Web ticket candidates | 16 | 5 `found`, 11 `needs_review`, 76 movies with no candidate; all unverified. |
| Pending review workflow rows | 6 | 5 high-priority `matched` rows (including line 51 false positive) + 1 `needs_review` candidate. No human review decision has been recorded. |
| Human-confirmed / human-rejected mappings | 0 / 0 | `mapping_human_reviewed=0` for all 92; no review result is invented. |
| Missing directors | 3 | `has_missing_core_data=1` for 3 rows. |
| Lower-bound DTP revenues | 2 | Flagged in `dtp_revenue_quality`; excluded from means unless explicitly opted in. |

### 2.5 Source constraints

- `utils.parse_money_vnd()` is a heuristic parser. It cannot recover revenue scope and treats `hơn X` as `X`; the analytical build must preserve a `lower_bound` quality label instead.
- `utils.normalize_title()` maps digits to Vietnamese number words and can collapse sequel numbers. It is a matching heuristic only, never an analytical identity key. Line 51 (`Chị Mười Ba: 3 Ngày Sinh Tử`) was auto-matched at 100.0 to `Chị Mười Ba 2: 3 Ngày Sinh Tử`; this is a known sequel-number false positive and must be quarantined from revenue comparison.
- `full_export.py` uses `revenue = bov_raw or dtp_raw`, an undocumented BOV-over-DTP preference. The flat design explicitly rejects that rule.
- BOV raw detail text was never persisted (`_bov_detail_raw=null` in all state rows), so BOV scope and label text cannot be audited locally.
- No raw file contains a full release date or duration. Those fields are therefore not populated from raw data.

---

## 3. Single analytical output

### 3.1 File and grain

**Output file:** `data/analytics/movie_analytics.csv`

**Grain:** one row per movie.

**Primary key:** `movie_id` (TEXT, e.g. `M0001`), never null and unique.

**Validation contract:**

- Row count = **92**.
- `movie_id` is non-null; `COUNT(DISTINCT movie_id)` = **92**.
- No duplicate `source_url_dtp`.
- Column set and order match §3.3–§3.7.
- No candidate-held BOV value appears in `bov_revenue_vnd`.
- No quarantined false-positive BOV value appears in `bov_revenue_vnd` or in any `include_revenue_comparison=1` row.
- `include_revenue_comparison=1` for exactly **79** rows; stored BOV revenue rows = 80, quarantined false positives = 1, candidate-held = 1.
- No human review decision is fabricated: `mapping_human_reviewed=0` and reviewer fields are null today.
- No official revenue field is exported.
- No ticket count is presented as verified cinema admissions.
- These are **pre-export gates**: they must pass before the mapping JSON is persisted and before `movie_analytics.csv` is written (§6).

### 3.2 Column groups

| Group | Purpose |
|---|---|
| A. Movie identity and metadata | Keys, titles, year, genre, director and lineage. |
| B. Matching information | Matcher outcome, score, BOV URL and review workflow state. |
| C. Revenue by source | DTP, accepted BOV and candidate BOV kept in separate columns with quality/eligibility flags. |
| D. Ticket information | Safe movie-level counts and evidence URLs only; no fabricated admissions. |
| E. Data quality | Distinct warning, review, missing-data and overall status flags. |

### 3.3 Group A — Movie identity and metadata

| Column | Type | Source / derivation | Null policy and notes |
|---|---|---|---|
| `movie_id` | string PK | Stable ID from §8.1 | Never null; unique; no duplicate movie rows. |
| `canonical_title` | string | `movies.csv.movie_name` | Verbatim DTP display title; never renamed or translated. |
| `original_title_raw` | string (nullable) | `movies.csv.original_title` | Verbatim fragment only; 2 rows populated, both fragments. |
| `release_year` | Int16 (nullable) | `movies.csv.release_year` | 92 populated; year-only precision. |
| `genre_raw` | string (nullable) | `movies.csv.genre` | Verbatim multi-value string; 92 populated; 62 distinct strings. |
| `genre_token_path` | string (nullable) | Derived from `genre_raw` | Pipe-delimited token list for Power BI token handling; grouping aid only. |
| `genre_grouped` | string (nullable) | Human vocabulary | NULL for all 92 today; not a verified fact until approved. |
| `director_raw` | string (nullable) | `movies.csv.director` | Verbatim; NULL for 3 rows. |
| `director_norm_key` | string (nullable) | Derived from `director_raw` | Casefold + accent/`đ` strip + whitespace collapse; grouping aid only. |
| `source_url_dtp` | string | `movies.csv.source_url_doanhthuphim` | Verbatim lineage URL; 92 unique. |
| `raw_source_row_dtp` | int | CSV line number | 2–93; supports raw-value lookup. |

`release_date` and `duration` are **not columns** in `movie_analytics.csv`: no full release date or supported duration exists in the raw data, so no placeholder is invented. See §10.

### 3.4 Group B — Matching information

| Column | Type | Source / derivation | Null policy and notes |
|---|---|---|---|
| `bov_match_status` | enum | `collection_log.csv.match_status` | `matched` (81) / `needs_review` (1) / `not_found` (10) / `unknown`. **Diagnostic matcher result only**; not proof of a valid identity and not a human review decision. |
| `match_score` | float (nullable) | `collection_log.csv.match_score` | Fuzzy similarity only; never a film rating or identity proof. |
| `match_reason` | enum (nullable) | `collection_log.csv.match_reason` | `auto` / `below_threshold` / `no_candidates` / `ambiguous_or_low_confidence`. |
| `bov_url` | string (nullable) | `movies.csv.source_url_bovn` | Populated for stored and candidate mappings; NULL for 10 `not_found`. URL alone does not establish identity. |
| `bov_title_raw` | string (nullable) | `movies.csv.title_bovn` | Stored BOV mapping title; NULL when no BOV mapping. May contain a false-positive title (line 51). |
| `mapping_validation_status` | enum | Rule engine + review evidence | `matcher_accepted` (80) / `known_false_positive_quarantined` (1) / `candidate_held` (1) / `no_mapping` (10) / `human_confirmed` (0) / `human_rejected` (0). Controls identity eligibility. |
| `mapping_validation_reason` | enum (nullable) | Review evidence | `sequel_number_error` for line 51; `different_subtitle` for line 84; NULL otherwise. |
| `mapping_human_reviewed` | int (0/1) | Review evidence | **0 for all 92 today**. Distinguishes human-reviewed mappings from matcher-only results. |
| `mapping_reviewed_at` | datetime (nullable) | Review evidence | NULL for all 92; never synthesized from collection time. |
| `mapping_reviewer` | string (nullable) | Review evidence | NULL for all 92; no reviewer is invented. |
| `review_status` | enum | Workflow state | `auto_accepted` (76) / `pending` (6) / `human_confirmed` (0) / `rejected` (0) / `not_applicable` (10). No `none`. Line 51 remains `pending`, not `rejected`. |
| `review_priority` | enum | Audit priority list | `high` for CSV lines 51, 32, 84, 78, 93, 91; else `normal`. Risk flag, not a duplicate status or review decision. |

### 3.5 Group C — Revenue by source

| Column | Type | Source / derivation | Null policy and notes |
|---|---|---|---|
| `dtp_revenue_raw` | string | `movies.csv.revenue_doanhthuphim` | Exact raw string; never overwritten. |
| `dtp_revenue_vnd` | Int64 | Quality-aware parser | Populated for 92/92; rounded `tỷ` values remain rounded. |
| `dtp_revenue_quality` | enum | Derived | `rounded` (90) / `lower_bound` (2). Never `exact` for DTP display strings. |
| `bov_revenue_raw` | string (nullable) | `movies.csv.revenue_bovn` | Valid stored BOV raw string only; NULL for quarantined false positive, candidate-held row and no-revenue rows. |
| `bov_revenue_vnd` | Int64 (nullable) | Quality-aware parser | Populated for **79 valid stored** rows only. |
| `bov_revenue_quality` | enum (nullable) | Derived | `exact` for parsed valid BOV strings; NULL when `bov_revenue_vnd` is NULL. Precision does not prove scope. |
| `bov_quarantined_revenue_raw` | string (nullable) | Line 51 BOV value | Populated for **1** known false positive only; audit retention, not accepted revenue. |
| `bov_quarantined_revenue_vnd` | Int64 (nullable) | Quarantined parser | Populated for line 51 only; excluded from gap-warning calculation, `revenue_gap_pct`, scatter plots and KPIs. |
| `bov_candidate_revenue_raw` | string (nullable) | Candidate BOV value | Populated for line 84 only; exact raw string retained for review. |
| `bov_candidate_revenue_vnd` | Int64 (nullable) | Candidate parser | Populated for **1** row only; never copied into `bov_revenue_vnd` or used in comparisons. May be used internally for a warning-only numerical gap. |
| `revenue_gap_pct` | float (nullable) | Derived | Populated only when `include_revenue_comparison=1` (**79** valid comparisons). NULL for candidate, quarantined and all ineligible rows. |
| `magnitude_gap_warning` | int (0/1) | Rule in §4.3 | 21 rows = 1 (20 valid comparisons + 1 candidate-held warning). Quarantined line 51 is excluded; no usable BOV revenue means no warning. |
| `revenue_conflict_flag` | int (0/1) | Derived | 0 for all 92 today; 1 only after all comparability/evidence gates pass and values disagree beyond tolerance. |
| `revenue_comparability_class` | enum | Derived per §4 | `insufficient_evidence` (79) / `not_applicable` (13) / three other classes at 0. |
| `comparability_reason` | enum (nullable) | Derived | `scope_unknown` (79) / `no_bov_mapping` (10) / `no_bov_revenue` (1) / `candidate_held` (1) / `mapping_quarantined_false_positive` (1). |
| `revenue_scope_verified` | int (0/1) | Derived | 0 for all 92 today. |
| `bov_evidence_available` | int (0/1) | State JSONL | 0 for all stored BOV rows; raw BOV detail body was not persisted. |
| `include_revenue_comparison` | int (0/1) | Rule engine | 1 for **79** valid, active, non-null BOV observations; 0 for quarantined, candidate and ineligible rows. |
| `include_revenue_eda` | int (0/1) | Rule engine | 1 for DTP-parseable rows (92 today); governs DTP-only exploratory charts. |
| `revenue_eda_basis` | enum (nullable) | Derived | `dtp_rounded_numeric_agreement` / `dtp_rounded_single_source` / `dtp_lower_bound`; never claims corroboration. |

**No `revenue_official_vnd` column is exported.** Official revenue remains blocked at 0/92, and no preferred, inferred or winner-takes-all revenue value is created. Exploratory revenue charts use `dtp_revenue_vnd` filtered by `include_revenue_eda=1`; they do not use a collapsed EDA amount column. The accepted/quarantined/candidate-held partition used to derive these fields comes from the optional per-movie `revenue_review` metadata in §8.1, keyed by stable `movie_id`; matcher status alone is not a substitute.

### 3.6 Group D — Ticket information

| Column | Type | Source / derivation | Null policy and notes |
|---|---|---|---|
| `ticket_candidate_count` | int | Deduplicated candidates linked by DTP URL | 1 for 16 movies, 0 for 76 today; counts evidence rows, not admissions. |
| `ticket_found_count` | int | Deduplicated candidates with `ticket_status='found'` | 1 for 5 movies, 0 otherwise. Heuristic candidate only. |
| `ticket_needs_review_count` | int | Deduplicated candidates with `ticket_status='needs_review'` | 1 for 11 movies, 0 otherwise. Includes quarantined context rows. |
| `ticket_verified_admissions` | Int64 (nullable) | Verified final admissions only | NULL for all 92. NULL means "no verified value", not zero admissions. |
| `ticket_data_status` | enum | Derived from candidate counts | `unverified_candidates` (16) / `no_candidates` (76). |
| `ticket_context_status` | enum | Context rule in §5 | `cinema_candidate_unverified` (15) / `event_attendance_quarantined` (1, line 49) / `no_candidate` (76). |
| `ticket_evidence_urls` | string (nullable) | Deduplicated raw source URLs | Pipe-separated, sorted raw URLs for inspection only; no ticket counts are summed. |

Individual ticket snippets, `published_at`, RSS-redirect flags and event-attendance context remain in the raw source and audit-only state files for inspection. They are not duplicated into the flat CSV as metrics.

### 3.7 Group E — Data quality

| Column | Type | Source / derivation | Null policy and notes |
|---|---|---|---|
| `has_missing_core_data` | int (0/1) | Derived | 1 when `canonical_title`, `release_year`, `genre_raw` or `director_raw` is missing; 3 rows today (director). |
| `has_revenue_gap_warning` | int (0/1) | Dashboard roll-up of `magnitude_gap_warning` | 21 rows today (20 valid + 1 candidate); semantically a quality warning, not a conflict. |
| `has_pending_review` | int (0/1) | Derived | 1 for 6 rows with `review_status='pending'`. |
| `data_quality_status` | enum | Precedence rule | `pending_review` > `revenue_gap_warning` > `missing_core_data` > `no_bov_match` > `ok`. Exact distribution is build-derived; underlying flag counts are fixed above. |

`magnitude_gap_warning` is the numerical calculation; `has_revenue_gap_warning` is the report-facing roll-up. They coincide today but are not the same concept. Neither sets `revenue_conflict_flag`.

---

## 4. Revenue policy

### 4.1 Source separation

- DTP and BOV values remain in separate columns. **Never collapse them into one preferred revenue field.**
- `bov_revenue_vnd` contains only the 79 BOV values attached to valid stored mappings.
- `bov_quarantined_revenue_*` contains only the known false-positive value from line 51; it is retained for audit, never as accepted revenue.
- `bov_candidate_revenue_vnd` contains the one pending candidate value only.
- No automatic BOV-over-DTP rule exists.
- DTP + BOV are never summed.

### 4.2 Comparison eligibility

A BOV value may enter `include_revenue_comparison=1` only when **all** of the following are true:

1. `bov_match_status='matched'` — it came from the matcher's diagnostic result.
2. `mapping_validation_status IN ('matcher_accepted','human_confirmed')` — it is not quarantined, candidate-held, rejected or unmapped.
3. `mapping_validation_status != 'known_false_positive_quarantined'` — a known false positive is never a valid identity.
4. `bov_revenue_vnd IS NOT NULL` — a valid stored BOV value exists.
5. `dtp_revenue_vnd IS NOT NULL`.
6. The source observation is not `candidate_held`.

`bov_match_status='matched'` alone is **not** sufficient. `mapping_human_reviewed=0` is allowed for a diagnostic comparison, but it means "matcher-only", not "verified identity". Line 51 is explicitly quarantined with `mapping_validation_status='known_false_positive_quarantined'`, `mapping_validation_reason='sequel_number_error'`, `review_status='pending'`, `mapping_human_reviewed=0`, and raw BOV values in `bov_quarantined_revenue_*`; no human rejection is invented.

This resolves to **79 valid revenue comparison rows**. The four remaining high-priority `matched` rows (lines 32, 78, 93, 91) are included and flagged `review_priority='high'`. The candidate-held row and the quarantined false-positive row are excluded. All 79 remain `revenue_comparability_class='insufficient_evidence'` with reason `scope_unknown`; none is verified or fully comparable.

#### Count reconciliation

| Layer | Count | Meaning |
|---|---:|---|
| Diagnostic matcher `matched` results | 81 | Raw matcher output; includes line 51 false positive and line 34 with no BOV revenue. |
| Stored BOV revenue observations | 80 | BOV revenue strings stored under `matched`; 79 valid + 1 quarantined false positive. |
| Valid revenue comparison rows | **79** | `include_revenue_comparison=1`; only these may appear in the diagnostic scatter. |
| Quarantined false-positive mappings | 1 | Line 51; pending, not rejected, with BOV value preserved outside accepted fields. |
| Candidate-held mappings | 1 | Line 84; `bov_candidate_revenue_*` only. |
| Pending review workflow rows | 6 | Includes line 51 and line 84; workflow state, not a human decision. |
| Human-confirmed / human-rejected mappings | 0 / 0 | No review result is fabricated. |

### 4.3 Gap warning vs confirmed conflict

#### Calculation rule

For rows where a gap is calculated:

`gap_pct = abs(dtp_revenue_vnd - bov_numeric_vnd) / dtp_revenue_vnd × 100`

- `dtp_revenue_vnd` is the DTP reference value, even though it is a rounded display figure.
- `bov_numeric_vnd` is the numeric value from the source-specific BOV column allowed for that mapping state.
- `magnitude_gap_warning=1` when `gap_pct > 10`; otherwise it is `0`.
- `revenue_gap_pct` is exported only when `include_revenue_comparison=1`.
- A warning is numerical only. It never sets `revenue_conflict_flag`.

#### Scope by mapping state

| Mapping state | Gap calculation | `magnitude_gap_warning` | `revenue_gap_pct` | Comparison eligibility |
|---|---|---|---|---|
| Valid accepted BOV mapping (`mapping_validation_status='matcher_accepted'` or `human_confirmed`, non-null `bov_revenue_vnd`) | Calculate from `dtp_revenue_vnd` and `bov_revenue_vnd`. | 1 when `gap_pct > 10`. | Populated for all 79 eligible rows, including warning and non-warning rows. | Eligible. |
| Candidate-held BOV mapping (line 84) | May calculate an internal warning-only gap from `dtp_revenue_vnd` and `bov_candidate_revenue_vnd`. | May be 1. | **Always NULL**; the internal warning-only percentage is not exported. | Never eligible; excluded from scatter and valid count. |
| Quarantined false-positive mapping (line 51) | **No gap calculation.** Preserve raw and parsed BOV values in `bov_quarantined_revenue_raw` / `_vnd` only. | **0** by exclusion rule. | NULL. | Never eligible; excluded from scatter, revenue KPIs, top-grossing selection and valid comparison count. Mapping quarantine/review status remains visible in data-quality reporting. |
| No usable BOV revenue | No calculation. | 0. | NULL. | Not eligible. |

#### Verified count reconciliation

| Gap category | Count |
|---|---:|
| Valid comparison rows with `magnitude_gap_warning=1` | 20 |
| Candidate-held row with warning-only gap | 1 |
| Quarantined false-positive rows included in gap calculation | 0 |
| Total `magnitude_gap_warning=1` rows | **21** |
| Valid revenue comparison rows (`include_revenue_comparison=1`) | 79 |
| Confirmed revenue conflicts (`revenue_conflict_flag=1`) | 0 |

These counts are supported by the current raw revenue strings using the DTP-referenced formula above. Line 51 is excluded by mapping state regardless of its numerical proximity.

- `revenue_conflict_flag=0` for all 92 until every comparability/evidence gate passes and values disagree beyond tolerance.
- Numerical agreement below 10% is labelled `dtp_rounded_numeric_agreement`; it is **not** corroboration. BOV raw text is unavailable and both scopes remain unknown.

### 4.4 Official and exploratory revenue

- Official revenue is blocked: there is no official revenue column and no value is fabricated.
- Exploratory charts use `dtp_revenue_vnd` with `include_revenue_eda=1` and an always-visible exploratory/unverified-scope label.
- High-priority rows remain eligible for DTP-only exploratory values. The four valid high-priority `matched` rows may show their BOV figures only in the diagnostic scatter, flagged `review_priority='high'`; the quarantined line 51 BOV value is never used in the scatter, exploratory selection or top-grossing values.
- Lower-bound DTP rows are displayed with `≥` and excluded from means unless a separate sensitivity view is explicitly requested.

---

## 5. Ticket candidate policy

### 5.1 Candidate link to `movie_id`

A ticket candidate is linked only through an exact `source_url_doanhthuphim` match to the persistent `movie_id` mapping. No positional join, fuzzy title join or `title_bovn` join is permitted. If a populated candidate row has no exact DTP URL match, the build aborts with `TICKET_LINK_UNRESOLVED`; it must not create a new movie row or attach the candidate to a different film.

### 5.2 Deduplication keys

There is currently one populated ticket row per movie, but the rule must remain safe if duplicates appear:

1. **Primary dedup key:** `(movie_id, source_url_normalized, source_title_normalized)`.
2. `source_url_normalized` lowercases the host, removes fragments and tracking parameters, and ignores trailing slashes. Google News RSS URLs are kept intact because their destination cannot be resolved offline.
3. `source_title_normalized` casefolds, strips accents/`đ`, collapses whitespace and preserves punctuation needed to distinguish titles.
4. If the same primary key has multiple numeric extracts, keep separate candidates only when `(tickets_display, ticket_status)` differs; otherwise collapse them as duplicates.
5. Exact duplicate rows collapse to one candidate and one evidence URL.

Under the current raw data this key yields 16 distinct candidates; no count changes.

### 5.3 Movie-level aggregation

For each `movie_id`, the build aggregates the deduplicated candidate set:

- `ticket_candidate_count` = number of deduplicated candidates with evidence.
- `ticket_found_count` = number of those candidates with `ticket_status='found'`.
- `ticket_needs_review_count` = number with `ticket_status='needs_review'`.
- `ticket_data_status` = `unverified_candidates` when `ticket_candidate_count > 0`, else `no_candidates`.
- `ticket_verified_admissions` stays NULL unless explicit verified final evidence exists; none exists today.

Ticket numbers are **never summed**, averaged, compared across movies or promoted to final admissions. Multiple candidates for one movie remain separate evidence items; their numeric values are not combined.

### 5.4 Evidence URL serialization

For each movie, collect the raw `source_url` strings of the deduplicated candidates, remove duplicates by the normalized URL rule, sort lexicographically, and join with `|` into `ticket_evidence_urls`. The serialized string is evidence navigation only, not a ticket metric.

### 5.5 Context quarantine

- `source_status='found'` is a search heuristic, not verified cinema admissions.
- Milestones, event attendance, streaming views and unrelated headlines are never summed as admissions.
- The `Tài` row (CSV line 49) is known event attendance from an unrelated artist headline. It remains one of the 11 `needs_review` candidates for audit count purposes, but is marked `ticket_context_status='event_attendance_quarantined'` and excluded from any cinema-admission interpretation.
- All other populated candidates are `cinema_candidate_unverified`; movies without candidates are `no_candidate`.
- No screening metric is created; screening data is 100% empty.

---

## 6. Python processing design

All transformations are pure Python functions producing one final in-memory DataFrame. Mapping persistence and CSV export are explicit gated write steps. Multiple internal DataFrames are allowed; no intermediate analytical CSVs are exported.

| # | Stage | Inputs | Internal output | Validation |
|---:|---|---|---|---|
| 1 | Load exact build inputs and validate existing mapping when present | 4 required files from §2.1 + `state/analytics_movie_id_map.json` when present | Raw DataFrames + validated mapping object (or explicit first-build absence) + `input_hash_before_build` | Row counts 92/92/92/92; CSV UTF-8 with BOM; JSONL parses line by line; all 4 required files hashed; mapping hashed if present; absent mapping on first build allowed; existing mapping schema/version, field validity, ID uniqueness and reuse rules pass before ID assignment. |
| 2 | Inspect schemas and types | Raw frames | Typed raw frames | Expected raw columns; cast `release_year`, `match_score`, money and ticket fields; literal `"nan"` → NULL. |
| 3 | Clean and normalize | Typed raw frames | Normalized working columns | Raw strings preserved in `*_raw`; derived keys/flags never overwrite source values. |
| 4 | Build/reuse/assign `movie_id` in memory | DTP URLs + identity metadata + §8.1 mapping | In-memory `movie_id` per DTP URL + in-memory mapping candidate | First-build deterministic seed; later builds load and reuse; new movies get next free ordinal; never renumber or reuse IDs; no mapping JSON is written in this stage. |
| 5 | Join at movie level | Working frames | One 92-row movie DataFrame | One row per DTP URL; revenue, matcher and ticket sources joined by exact DTP URL; no fan-out. |
| 6 | Aggregate ticket candidates | `tickets_sold_web.csv` working rows | Ticket summary columns | Exact URL link; dedup by §5.2; 16 candidates, 5 `found`, 11 `needs_review`; admissions remain NULL; no ticket values are summed. |
| 7 | Preserve revenue sources | DTP/BOV raw values | Separate DTP, valid BOV, quarantined BOV and candidate BOV columns | 92 DTP; 79 valid BOV; 1 quarantined false positive; 1 candidate field; no cross-copy. |
| 8 | Apply matching and revenue eligibility rules | Movie DataFrame + matcher fields | Eligibility flags | 79 comparison-eligible; 80 stored BOV revenues reconciled; line 51 excluded; `revenue_gap_pct` NULL except valid comparisons; candidate warning gap stays internal. |
| 9 | Generate quality flags | Eligibility outputs | Flag columns | 21 gap warnings = 20 valid + 1 candidate-only; line 51 excluded from gap calculation; 0 conflicts; 6 pending workflow rows; 0 human-reviewed maps; 3 missing-core-data rows. |
| 10 | Run all pre-export validations | Validated DataFrame + in-memory mapping candidate | Pass/fail export gate | Exactly 92 rows; unique, non-null `movie_id`; unique `source_url_dtp`; §3.1 schema/order; revenue segregation and eligibility (80 stored = 79 valid + 1 quarantined, 1 candidate, 79 comparisons, no cross-copy, scoped warning counts); ticket aggregation (16/5/11, dedup, no sums, admissions NULL); all required §2.4 counts reproduced. Failure blocks mapping persistence and CSV overwrite. |
| 11 | Persist mapping JSON | In-memory mapping candidate after stage 10 pass | `state/analytics_movie_id_map.json` | Write only after all pre-export validations pass; no write on transformation/pre-export validation failure; never renumber or reuse previously assigned IDs. |
| 12 | Verify mapping persistence and calculate `mapping_hash_after_build` | Persisted mapping JSON | Verified mapping object + post-build hash | Re-read and validate the persisted mapping; record separate `mapping_hash_after_build`; pre-build and post-build mapping hashes need not match; persistence failure blocks CSV export. |
| 13 | Export one CSV only after successful mapping persistence | Validated DataFrame | `data/analytics/movie_analytics.csv` | UTF-8 without BOM; typed values written as integers/floats/strings (no date columns today); empty as empty; one flat CSV, one row per `movie_id`; export failure is reported clearly. |
| 14 | Re-read and validate exported CSV | Exported CSV | Post-export validation report | Schema/order match §3; row count and PK uniqueness; counts in §2.4 reproduced; post-export failure is reported and never silently described as success. |
| 15 | Re-hash required raw inputs | 4 required files from §2.1 | Final hash check | SHA-256 values equal their `input_hash_before_build`; mismatch is reported clearly; mapping hash remains recorded separately in `mapping_hash_after_build`. |

Failure gates:

- Any transformation or pre-export validation failure (stages 1–10): do not persist a new/updated mapping JSON and do not overwrite `movie_analytics.csv`.
- Mapping validation or persistence failure (stages 1, 11–12): do not export or overwrite the analytical CSV; report the failure.
- CSV export or post-export validation failure (stages 13–14): report the failure clearly; do not silently claim a successful build.
- Raw-input re-hash mismatch (stage 15): report the failure clearly; do not silently claim the build succeeded.
- `input_hash_before_build` remains the start-of-build snapshot; `mapping_hash_after_build` is calculated only after successful mapping persistence. The two mapping hashes are not required to match.

Recommended module structure (future implementation only): `analytics/schema.py`, `analytics/load_raw.py`, `analytics/clean.py`, `analytics/ids.py`, `analytics/tickets.py`, `analytics/revenue.py`, `analytics/build_flat.py`, `analytics/validate.py`. No database.

---

## 7. Power BI design

### 7.1 Model

Import **only** `data/analytics/movie_analytics.csv`.

- Single table; no relationships between analytical tables.
- All KPIs come from the one movie-level table.
- Slicers use columns in that table: `release_year`, `bov_match_status`, `mapping_validation_status`, `review_status`, `review_priority`, `genre_grouped`, `director_norm_key`, `data_quality_status`.
- Genre token charts may use a Power Query split of `genre_token_path` derived from the same single source. This is a report-local transformation, not a second exported analytical CSV and not a relationship model.

### 7.2 Visual-level revenue warning rule

1. Any visual using `dtp_revenue_vnd` for exploratory analysis must always show **"Exploratory — revenue scope unverified"**.
2. No official-revenue visual exists today; the official KPI is 0.
3. A visual mixing any future official field with exploratory DTP values must distinguish the tiers and retain the exploratory warning.
4. No percentage or majority threshold may suppress the warning while unverified values remain visible.
5. The rule applies per visual/data selection, including slicers and filters, not merely at dataset level.

### 7.3 Dashboard pages

#### Page 1 — Movie overview

- **KPI cards:** Movies (92), Matched BOV (81), Matcher needs review (1), Not found (10), Pending workflow (6).
- **Visuals:** title table (`canonical_title`, `release_year`, `genre_raw`, `director_raw`, `bov_match_status`, `mapping_validation_status`, `review_status`); status donut; search slicer.
- **Limitations:** "All available DTP records; not a designed sample. `match_score` is fuzzy similarity, not a rating. Pending workflow is not a recorded human decision."

#### Page 2 — Release-year distribution

- **KPI cards:** Movies, Median year (2024), 2026-labelled movies (21).
- **Visuals:** year histogram; year × `bov_match_status` stacked column.
- **Limitations:** "Year only; no verified month/day."

#### Page 3 — Genre and director profile

- **KPI cards:** Distinct raw genre strings (62), Distinct directors (50), Missing directors (3).
- **Visuals:** genre token frequency from `genre_token_path`; director counts from `director_raw`/`director_norm_key`; optional exploratory average of `dtp_revenue_vnd` with warning.
- **Limitations:** "Raw multi-value genres and unnormalized director names; token-level counts are non-additive with revenue; grouping keys are aids, not verified identities."

#### Page 4 — Data quality and matching

- **KPI cards:** Gap warnings (21 = 20 valid + 1 candidate-only), Confirmed conflicts (0), Valid comparisons (79), Stored BOV revenues (80), Quarantined false positives (1), Candidate-held revenue (1), Pending workflow (6), Unverified ticket candidates (16), Verified admissions (0).
- **Visuals:** flag matrix (`magnitude_gap_warning` × `review_status` × `mapping_validation_status`); table of gap rows showing `dtp_revenue_raw`, `bov_revenue_raw`, `bov_candidate_revenue_raw` and `revenue_gap_pct` side by side, with the candidate row visibly marked as warning-only and `revenue_gap_pct=NULL`; separate audit table for line 51 using `bov_quarantined_revenue_raw`, `mapping_validation_reason` and `bov_url`; ticket evidence table via `ticket_evidence_urls` with `ticket_context_status`.
- **Limitations:** "20 gaps are valid comparison warnings; 1 is candidate-only with `revenue_gap_pct=NULL`. Gaps are numerical warnings, not confirmed conflicts. Line 51 is a known sequel-number false positive: pending, quarantined and excluded from gap calculation, not a valid comparison. `bov_match_status='matched'` is a diagnostic result, not identity proof. BOV page text was not persisted. Ticket 'found' means a search candidate; event attendance is quarantined; no ticket counts are summed."

#### Page 5 — Exploratory DTP/BOV revenue comparison

- **KPI cards:** DTP rows with exploratory revenue (92), Valid comparison pairs (79), Stored BOV revenues (80), Quarantined false positives (1), Candidate-held BOV rows (1), Gap warnings (21 = 20 valid + 1 candidate-only), Confirmed conflicts (0).
- **Visuals:** histogram of `dtp_revenue_vnd` filtered by `include_revenue_eda=1`; diagnostic scatter of `dtp_revenue_vnd` vs `bov_revenue_vnd` filtered by `include_revenue_comparison=1` with a 10% reference band.
- **Scatter rules:** exactly **79** valid, active, non-null BOV observations; includes the 4 remaining high-priority `matched` rows visibly identified by `review_priority='high'`; excludes the known false-positive row 51 and the candidate-held row 84; all 79 remain `insufficient_evidence`; never labelled verified or fully comparable.
- **Limitations:** "Rounded DTP figures; numeric agreement does not prove shared scope or period; the candidate-only warning is not a valid comparison and has `revenue_gap_pct=NULL`; line 51 is quarantined and appears only in the data-quality audit table; candidate and high-priority BOV values are excluded from exploratory/top-grossing selection; ≥ values are lower bounds; no sum across sources."

**Explicitly excluded dashboard pages:** official revenue conclusions, ticket attendance, screening efficiency, time-series revenue trends and forecasting.

---

## 8. Data lineage and reproducibility

### 8.1 Stable `movie_id` and persistent mapping artifact

#### Artifact

- **Recommended path:** `state/analytics_movie_id_map.json`.
- **Role:** build metadata only. It is **not** an analytical CSV and must **not** be imported into Power BI.
- **Encoding/format:** UTF-8 JSON. Top-level object only.

#### Hash handling

- On later builds, the file is read as a build input and its pre-build hash is included in `input_hash_before_build` (§2.3).
- On a first build the file may be absent; this is expected and not a validation error.
- `movie_id` values may be built, reused or assigned in memory before persistence; this does not write the JSON file.
- Write a new/updated mapping only after the analytical DataFrame has passed every §6 pre-export validation.
- After successful persistence is verified, record `mapping_hash_after_build`; record it after an unchanged successful build too.
- The mapping may legitimately change during a build; its pre-build and post-build hashes are not required to match.
- Mapping validation or persistence failure aborts the build before `movie_analytics.csv` is exported or overwritten.

#### Persistence order

The mapping JSON is build metadata and is persisted only after the DataFrame is validated. The exact order is:

1. Load and validate the existing mapping, if present (§6 stage 1).
2. Build, reuse or assign `movie_id` values in memory (§6 stage 4).
3. Build the movie-level DataFrame (§6 stage 5).
4. Complete revenue, ticket, matching and data-quality transformations (§6 stages 6–9).
5. Run all pre-export validations (§6 stage 10).
6. Only after all pre-export validations pass, persist `state/analytics_movie_id_map.json` (§6 stage 11).
7. Verify mapping persistence and calculate `mapping_hash_after_build` (§6 stage 12).
8. Only after successful mapping persistence, export `data/analytics/movie_analytics.csv` (§6 stage 13).
9. Re-read and validate the exported CSV (§6 stage 14).
10. Re-hash the four required raw inputs and verify they are unchanged (§6 stage 15).

This order prevents a partially transformed or invalid DataFrame from freezing new IDs into persistent metadata.

#### Schema

```json
{
  "schema_version": "1.0",
  "generated_at": "ISO-8601 datetime of last successful write",
  "source_anchor": "source_url_doanhthuphim",
  "id_prefix": "M",
  "movies": [
    {
      "movie_id": "M0001",
      "source_url_dtp": "https://...",
      "canonical_title": "verbatim movie_name",
      "release_year": 2024,
      "director_raw": "verbatim director or null",
      "url_history": [
        {
          "source_url_dtp": "current_or_prior DTP URL",
          "first_seen_at": "ISO-8601",
          "last_seen_at": "ISO-8601",
          "verification": "initial_seed | identity_match | reviewer_alias",
          "approved_by": "reviewer name or null",
          "approved_at": "ISO-8601 or null"
        }
      ],
      "status": "active | retired",
      "created_at": "ISO-8601",
      "last_seen_at": "ISO-8601",
      "notes": "optional short note",
      "revenue_review": {
        "decision": "accepted | quarantined | candidate_held | pending",
        "reason": "short reviewer explanation or null",
        "reviewed_at": "ISO-8601 or null",
        "reviewer": "reviewer name or null"
      }
    }
  ]
}
```

Field rules:

- `movie_id` is `M` + 4 zero-padded digits, unique across `movies`, never reused.
- `source_url_dtp` is the current primary DTP URL for an active row; it must match a row in `data/movies.csv` for current builds.
- `canonical_title`, `release_year`, `director_raw` are copied from the current raw row at mapping time to support identity checks on URL changes.
- `url_history` entries are objects with URL, first/last-seen timestamps and a `verification` value; it always contains the current `source_url_dtp` as the last element. Prior URLs are appended when identity-matched or reviewer-approved.
- `status='retired'` means the movie no longer appears in a current raw snapshot but its `movie_id` is preserved forever.
- `revenue_review` is optional persistent build metadata attached to the enclosing stable `movie_id`; the movie is identified by its exact `source_url_dtp`, never by CSV row position. It may be omitted or `null`; both mean no review metadata and must not be interpreted as `accepted`. When present as an object, all four fields are required: `decision` must be one of `accepted`, `quarantined`, `candidate_held` or `pending`; `reason` must be a non-empty string for `quarantined` and `candidate_held`; `reviewed_at` and `reviewer` are nullable strings, and `reviewed_at` must be a valid ISO-8601 timestamp when populated. A non-object value, missing field, unknown field or invalid value/type is rejected.
- `revenue_review.decision` is an explicit BOV revenue-classification decision, distinct from the `mapping_validation_status` / `mapping_validation_reason` identity diagnostics exported in `movie_analytics.csv`. It is build metadata, not a Power BI output column, and it is not a human-review result for movie identity. Revenue processing will consume it by the stable `movie_id`: `accepted` may populate accepted BOV revenue fields, `quarantined` and `candidate_held` populate only their separate audit fields and stay out of valid comparisons, and `pending` or absent metadata is not an accepted classification.

#### First build

1. Load `data/movies.csv` and derive the identity tuple `(source_url_dtp, canonical_title, release_year, director_raw)`.
2. Sort by `source_url_dtp` ascending.
3. Assign `M0001`..`M0092` in that order **in memory** with `status='active'` for all rows. The missing pre-build file is allowed. Write `state/analytics_movie_id_map.json` only after §6 stage 10 passes; `mapping_hash_after_build` is recorded after persistence is verified.

#### Reuse on subsequent builds

1. Load and validate the mapping file before any ID assignment; do not write it in this step.
2. Verify the schema/version, required fields, uniqueness of `movie_id` and `source_url_dtp`, valid `movie_id` format (`^M\d{4}$`), and no retired `movie_id` reused.
3. Build a set of current DTP URLs from `data/movies.csv`. Every current URL that appears in the mapping must resolve to a unique `movie_id`; every mapped active `source_url_dtp` must correspond to a current raw row **or** be intentionally retired only by a documented operator action (not performed by this design). In normal incremental builds, mismatches are treated as URL changes or missing rows per rules below.
4. Reuse the existing `movie_id` in memory for every unchanged current URL.

#### Assigning new IDs without renumbering

- For current URLs not present in the mapping, append new in-memory rows with the next free ordinal after the current maximum numeric suffix.
- Never renumber existing IDs.
- Never reuse a retired or missing ID.
- Persistence happens only at §6 stage 11, after all pre-export validations pass.

#### URL-change handling and identity verification

When a current raw row’s `source_url_dtp` is absent from the mapping’s active URL set, or a mapping points to a URL not present in current raw data:

- **Allowed keep-ID cases:** keep the existing `movie_id` only when identity is verified by one of these explicit checks:
  - current raw `canonical_title` and `release_year` and `director_raw` match the mapped identity fields after the same normalization used for reporting; **or**
  - the mapping already records a `url_history` entry with `verification='reviewer_alias'` for that `movie_id` and the current URL matches that approved replacement.
- If the replacement is ambiguous (multiple possible source rows, or identity fields conflict), the build **aborts** with `ID_MAPPING_UNRESOLVED`. Do not guess.
- When a verified URL change is accepted, set the new URL as `source_url_dtp`, append it to `url_history`, and update `last_seen_at`/identity snapshots.

#### Duplicate identity and duplicate URL handling

- Duplicate `source_url_dtp` values inside `data/movies.csv` → abort with `ID_MAPPING_INVALID`.
- Two mapping entries sharing the same `source_url_dtp` → abort with `ID_MAPPING_INVALID`.
- Two mapping entries claiming different `movie_id`s for the same logical identity without an approved alias → abort with `ID_MAPPING_INVALID`.
- Two distinct current raw movies that would collide on `movie_id` assignment → impossible if anchored by URL; URL collisions are caught above.

#### Failure gates

The mapping JSON must not be persisted before the analytical DataFrame passes all pre-export validations (§6 stages 1–10).

| Failure point | Required behavior |
|---|---|
| Existing mapping missing after a prior successful build, unreadable, invalid JSON, invalid schema/version, duplicate/invalid IDs, ambiguous URL/identity, `ID_MAPPING_UNRESOLVED` or `ID_MAPPING_INVALID` | Abort before ID persistence and before CSV export; do not silently rebuild or reseed IDs. |
| Any transformation or pre-export validation failure (§6 stages 1–10), including row count, `movie_id` uniqueness/non-null, `source_url_dtp` uniqueness, revenue segregation/eligibility, ticket aggregation, schema/order or count checks | Do not persist a new/updated mapping JSON and do not overwrite `movie_analytics.csv`. |
| Mapping persistence failure, including failed write or failed post-write verification (§6 stages 11–12) | Do not export or overwrite `movie_analytics.csv`; report the failure clearly. |
| CSV export or post-export validation failure (§6 stages 13–14) | Report the failure clearly; do not silently claim a successful build. |
| Any ID decision | Never renumber or reuse previously assigned IDs. |

`input_hash_before_build` remains the pre-build snapshot; `mapping_hash_after_build` is the separate post-success hash. They are not required to match.

Operator recovery is manual: fix or regenerate the mapping only outside this automated build path, and document the reason. Re-seeding is forbidden once exports have been published.

### 8.2 Preserved raw values

- DTP/BOV strings are retained in `dtp_revenue_raw`, `bov_revenue_raw`, `bov_quarantined_revenue_raw` and `bov_candidate_revenue_raw`.
- Original titles, genres and director strings are retained verbatim.
- Match score and reason are carried through from the collection log.
- BOV candidate URL/revenue and the quarantined line 51 BOV revenue remain visible as audit evidence, not as accepted values.
- Ticket evidence URLs are retained only as deduplicated reference links; numeric snippets are not copied as admissions.
- No raw file is written by the build.

### 8.3 Exclusion audit

- Exclusions are per analysis, expressed through `include_*`, `mapping_validation_status` and `data_quality_status` flags.
- No movie row is deleted because one optional field or a suspect mapping exists.
- Candidate-held and quarantined false-positive revenues are exclusions from accepted BOV analysis, not deletions of evidence.
- Quarantine is reversible only by a recorded human review; the design never invents a reviewed result.

---

## 9. Implementation roadmap

| Priority | Task | Deliverable |
|---|---|---|
| **P0** | Freeze raw inputs; implement load, schema and profile stages | Reproduced counts and validation report. |
| **P0** | Implement stable `movie_id` mapping with fail-safe | One ID per movie; no renumbering. |
| **P0** | Build the flat 92-row DataFrame and export `movie_analytics.csv` | Exactly one analytical CSV. |
| **P1** | Implement revenue, matching and ticket eligibility flags | Correct separation of DTP, accepted BOV and candidate BOV. |
| **P1** | Add Power BI report using the single table | Five supported pages; no relationships. |
| **P2** | Human review of 6 pending rows (including line 51 false positive) and 21 gap warnings | Updated `mapping_validation_status`, reviewer fields and `review_status`; only then reconsider official revenue. |
| **P3** | Add verified dates, duration or tickets only from supported evidence | Schema change through a documented policy version. |

---

## 10. Open questions and unresolved design issues

1. **Target revenue scope:** lifetime cumulative vs cumulative-to-date remains undefined; official revenue stays blocked.
2. **Duration source:** no supported duration exists in current raw data; field is intentionally omitted.
3. **Release date source:** no full date exists; `release_date` is intentionally omitted.
4. **Genre token handling:** Power Query split of `genre_token_path` is acceptable for reports, but must not be exported as a second analytical CSV.
5. **Review transitions:** reviewer identity and evidence requirements for `human_confirmed` / `rejected` need human approval.
6. **Release identity rule:** re-release vs separate movie for the 13 weak year disagreements remains open.
7. **Lower-bound display:** approve `≥` display and exclusion from means.
8. **Licensing:** confirm retention of source URLs and candidate snippets in the flat CSV is acceptable for the intended personal/non-commercial dashboard.
9. **Line 51 review:** a human must confirm or reject the quarantined sequel-number mapping; until then it remains pending with no valid BOV comparison.

---

## 11. Verification summary for this design task

- Verified counts preserved/reconciled: 92 movies; 81/1/10 diagnostic match statuses; 92 DTP revenues; 80 stored BOV revenues (79 valid + 1 quarantined false positive); 1 candidate-held BOV revenue; 79 valid comparison rows; 21 gap warnings (20 valid + 1 candidate-only; line 51 excluded); 0 confirmed conflicts; 0 verified admissions; 16 deduplicated unverified ticket candidates; 6 pending workflow rows; 0 human-reviewed mappings.
- Output count: exactly one analytical CSV, `data/analytics/movie_analytics.csv`, with one row per `movie_id`.
- Hash lifecycle is explicit: `input_hash_before_build` covers all 4 Required inputs and the mapping JSON when read; `mapping_hash_after_build` is a separate post-success hash and need not equal the mapping's pre-build hash.
- Persistence order is explicit: `movie_id` values are assigned in memory; the mapping JSON is written only after all §6 pre-export validations pass; persistence is verified and hashed; only then is `movie_analytics.csv` exported, re-read/validated, followed by raw-input re-hashing.
- No obsolete child analytical exports remain in the design.
- No Power BI relationship model remains.
- Revenue sources are separate; candidate and quarantined false-positive values are segregated; no preferred or official revenue value is exported.
- Ticket values are summaries and evidence references only; dedup, context quarantine and no-summing rules are explicit.
- Visual-level warning rules and diagnostic-scatter restrictions are retained; the scatter now uses 79 valid rows.
- No database, warehouse or production architecture is introduced.

### 11.1 Changes in this revision

| # | Area | Before | Now |
|---:|---|---|---|
| 1 | Analytical outputs | Five CSVs with child tables and relationships | One flat CSV: `movie_analytics.csv`, 92 rows, one row per `movie_id`. |
| 2 | Grain | Mixed movie/observation/issue grains | Single movie grain; no duplicate movie rows. |
| 3 | Revenue | Official and exploratory amount fields plus observation table | Separate DTP, accepted BOV and candidate BOV columns; no official or preferred field. |
| 4 | Candidate value | Held in a child observation table | `bov_candidate_revenue_vnd` on the movie row, never in accepted BOV revenue. |
| 5 | Tickets | Observation-level table | Safe movie-level counts plus evidence URLs; admissions remain NULL. |
| 6 | Genres | Exploded child table | `genre_raw` plus `genre_token_path`; token handling is report-local only. |
| 7 | Review queue | Separate issue table | Flags and status columns on the movie row. |
| 8 | Power BI | One central table plus four child tables | One imported table, no relationships. |
| 9 | Python workflow | Multiple analytical DataFrames exported | Multiple internal DataFrames allowed; exactly one final CSV exported. |
| 10 | Architecture | Metadata sidecar described as an additional artifact | ID mapping state retained as build metadata only; not an analytical export and not imported into Power BI. |
| 11 | ID mapping | "Existing ID mapping design" without a concrete artifact or hash scope | §8.1 specifies `state/analytics_movie_id_map.json`, full schema, first-build/reuse/new-ID rules, URL verification, duplicate handling and fail-safe codes; §2.1–§2.3 define exact build inputs and hash every actual input. |
| 12 | False-positive mapping | Row 51 was counted among 80 accepted BOV comparisons | §4.2 quarantines the known sequel-number error: 80 stored BOV revenues = 79 valid comparisons + 1 quarantined; new mapping-validation columns preserve the raw BOV value without inventing a human rejection. |
| 13 | Ticket aggregation | Counts described without link, dedup or context rules | §5 and §6 define exact DTP-URL linking, dedup keys, movie-level counts, URL serialization, event-attendance quarantine and a no-summing rule; one row per movie is unchanged. |
| 14 | Input hashing | Ambiguous whether the mutable mapping JSON had to keep the same hash across a build | §2.3, §6 and §8.1 define `input_hash_before_build` and `mapping_hash_after_build`: required raw files always hashed; mapping pre-hash when read; first-build absence allowed; mapping may change; post-hash recorded separately; mapping failure blocks CSV export. |
| 15 | Revenue gap warning | "Any BOV string" was too broad for quarantined and candidate values | §3.5, §4.3, §6 and §7 define the DTP-referenced `>10%` rule and scope table: 20 valid warnings, 1 candidate-only warning with `revenue_gap_pct=NULL`, line 51 excluded, 21 total, 79 valid comparisons, 0 conflicts. |
| 16 | Mapping persistence order | Mapping state could be written before full DataFrame validation | §6 and §8.1 require in-memory ID assignment, a full pre-export validation gate, mapping persistence and `mapping_hash_after_build`, then CSV export, post-export validation and raw-input re-hash; transformation/pre-export failure blocks persistence and CSV overwrite, mapping failure blocks export, and CSV failure is reported clearly. |
