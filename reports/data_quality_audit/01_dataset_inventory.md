# 01 — Dataset Inventory

**Audit scope:** read-only profiling of all files currently present in `movie-data-scraper`.
**Audit date:** 2026-11-18. **Data origin:** local files only; no HTTP requests and no source-website access were performed.
**Environment note:** `pandas` is not installed in this environment (no `.venv`, no `uv`, no `pip`), so all profiling was performed with the Python standard library (`csv`, `json`, `re`, `statistics`) using the same parsing rules as `src/movie_data_collector/utils.py`. No dataset file was modified.

---

## 1.1 Repository inventory

| Category | Count | Files |
|---|---:|---|
| **Total files (excluding `.git`)** | **26** | — |
| Data CSVs (`data/`) | 5 | `movies.csv`, `unmatched_movies.csv`, `collection_log.csv`, `tickets_sold_web.csv`, `full_export.csv` |
| State JSONL (`state/`) | 3 | `doanhthuphim_movies.jsonl`, `boxoffice_matches.jsonl`, `web_tickets_progress.jsonl` |
| Package modules (`src/movie_data_collector/`) | 10 | `__init__.py`, `cli.py`, `config.py`, `full_export.py`, `matching.py`, `pipeline.py`, `scrape_boxofficevietnam.py`, `scrape_doanhthuphim.py`, `search_tickets_web.py`, `utils.py` |
| Scripts (`scripts/`) | 2 | `inspect_sites.py`, `search_tickets_web.py` |
| Notebook | 1 | `src/main.ipynb` |
| Root config/docs | 5 | `AGENTS.md`, `README.md`, `.gitignore`, `pyproject.toml`, `uv.lock` |

`reports/data_quality_audit/` did not exist before this audit and was created only for these reports.

## 1.2 Dataset shapes and sizes

All CSVs are UTF-8 with BOM (`utf-8-sig`, as written by the pipeline).

| Dataset | Rows (excl. header) | Columns | File size (bytes) | Role |
|---|---:|---:|---:|---|
| `data/movies.csv` | 92 | 14 | 22,100 | Consolidated movie-level output (one row per collected DoanhThuPhim movie) |
| `data/unmatched_movies.csv` | 11 | 14 | 2,043 | Subset of `movies.csv`: `not_found` / `needs_review` / missing BOV URL |
| `data/collection_log.csv` | 92 | 8 | 15,553 | Projection of `movies.csv` plus match provenance (`match_score`, `match_reason`) |
| `data/tickets_sold_web.csv` | 92 | 19 | 37,743 | One row per movie: web-search evidence for ticket counts (RSS headlines/snippets) |
| `data/full_export.csv` | 92 | 13 | 19,361 | "Final" review-friendly merge of `movies.csv` + `tickets_sold_web.csv` |

State files (also local evidence, not requested as audit outputs but inspected for provenance):

| State file | Records | Size (bytes) | Notable content |
|---|---:|---:|---|
| `state/doanhthuphim_movies.jsonl` | 92 | 64,993 | Raw DTP link metadata in `_dtp_raw` |
| `state/boxoffice_matches.jsonl` | 92 | 187,203 | `match_score`, `match_reason`, `_bov_candidate` (82/92), `bov_release_info`, `bov_title` |
| `state/web_tickets_progress.jsonl` | 92 | 72,485 | `snippet` + `source_url` present in only 16/92; `error` empty in all |

## 1.3 Schemas and inferred types

Types are inferred from the stored values. **Important:** revenue, ticket and screening values are stored as *display strings*, not numbers.

### `movies.csv` (14 columns, 92 rows)

| Column | Non-null / rows | Distinct non-null | Inferred type | Notes |
|---|---:|---:|---|---|
| `movie_name` | 92/92 | 92 | string | Original DTP title; de-facto business key |
| `title_bovn` | 82/92 | 82 | string | Title from matched BOV page |
| `original_title` | 2/92 | 2 | string | Almost entirely empty; see §1.6 |
| `release_year` | 92/92 | 15 | 4-digit year string (2013–2026) | No full release date stored |
| `genre` | 92/92 | 62 | string | Comma-separated multi-value, not normalized |
| `director` | 89/92 | 50 | string | 3 missing |
| `revenue_doanhthuphim` | 92/92 | 83 | string ("714 tỷ", "66,5 tỷ", "hơn 21 tỷ") | Rounded, mixed casing/units |
| `revenue_bovn` | 81/92 | 81 | string ("714,030,584,098₫") | Precise VND with `₫`; 11 missing |
| `tickets_sold` | **0/92** | 0 | — | **Completely empty** (BOV ticket extraction yielded no value) |
| `screening_count` | **0/92** | 0 | — | **Completely empty** |
| `source_url_doanhthuphim` | 92/92 | 92 | URL | **Best primary-key candidate** |
| `source_url_bovn` | 82/92 | 82 | URL | 10 missing (all `not_found`) |
| `match_status` | 92/92 | 3 | enum: `matched` 81, `not_found` 10, `needs_review` 1 | |
| `collection_status` | 92/92 | 3 | enum: same distribution as `match_status` | Redundant with `match_status` in this snapshot |

### `unmatched_movies.csv` (14 columns, 11 rows)
Identical schema to `movies.csv`. Null rates: `title_bovn`, `original_title`, `revenue_bovn`, `source_url_bovn` = 10/11 each (the single populated row is the `needs_review` record); `tickets_sold`, `screening_count` = 11/11 empty.

### `collection_log.csv` (8 columns, 92 rows)

| Column | Non-null / rows | Type / values |
|---|---:|---|
| `movie_name` | 92/92 | string |
| `title_bovn` | 82/92 | string |
| `source_url_doanhthuphim` | 92/92 | URL |
| `source_url_bovn` | 82/92 | URL |
| `match_status` | 92/92 | enum |
| `collection_status` | 92/92 | enum |
| `match_score` | 92/92 | float (0–100; fuzzy-match confidence, **not** a movie rating) |
| `match_reason` | 92/92 | enum: `auto` 81, `below_threshold` 9, `no_candidates` 1, `ambiguous_or_low_confidence` 1 |

### `tickets_sold_web.csv` (19 columns, 92 rows)

| Column | Non-null / rows | Type / notes |
|---|---:|---|
| `movie_name`, `title_bovn`, `source_url_doanhthuphim` | 92, 82, 92 | string / URL (join keys) |
| `tickets_sold_web` | 16/92 | integer as string, 4,000–9,000,000 |
| `tickets_display`, `tickets_basis`, `confidence`, `source_title`, `source_url`, `source_name`, `published`, `snippet`, `search_backend`, `matched_query` | 16/92 each | Evidence fields; only populated when a candidate was found |
| `ticket_status` | 92/92 | enum: `found` 5, `needs_review` 11, `not_found` 76 |
| `search_queries` | 92/92 | pipe-separated query strings |
| `candidate_count` | 92/92 | integer 0–4 |
| `error` | **0/92** | **Completely empty** |
| `collected_at` | 92/92 | ISO-8601 UTC timestamp (all 2026-11-18) |

### `full_export.csv` (13 columns, 92 rows)

| Column | Non-null / rows | Type / notes |
|---|---:|---|
| `movie_name` | 92/92 | string; **only available join key**, but no explicit key column |
| `original_title` | 2/92 | string |
| `release_year` | 92/92 | 4-digit string |
| `genre`, `director` | 92, 89 | string |
| `revenue` | 92/92 | string; `BOV value if present else DTP value` (mixed units/formats) |
| `tickets_sold` | 5/92 | integer string; sourced from `tickets_sold_web` only when `ticket_status='found'` |
| `screening_count` | **0/92** | completely empty |
| `to_review_director` | 3/92 | provenance note with DTP URL |
| `to_review_revenue` | 21/92 | conflict / missing / uncertain-match notes |
| `to_review_tickets_sold` | 11/92 | unconfirmed ticket evidence notes |
| `to_review_screening_count` | **0/92** | completely empty |
| `to_review_match` | 1/92 | source URLs for the single `needs_review` match |

No rating, runtime, vote count, budget, release date (full), country, language, distributor or cast column exists in any dataset. `match_score` is the only numeric "score" field and measures fuzzy-string similarity.

## 1.4 Relationships between datasets

```
state/doanhthuphim_movies.jsonl ──(source_url_doanhthuphim)──┐
                                                             ├─> data/movies.csv ──> data/unmatched_movies.csv (filter)
state/boxoffice_matches.jsonl ──(same key, adds BOV fields)──┘         │
                                                                      ├─> data/collection_log.csv (projection + scores)
                                                                      └─> data/full_export.csv (merge)
state/web_tickets_progress.jsonl ──(source_url_doanhthuphim)──> data/tickets_sold_web.csv ──> data/full_export.csv
```

- All five CSVs have exactly **92 rows** except `unmatched_movies.csv` (**11 rows**, an exact subset of `movies.csv` by DTP URL).
- `movies.csv` and `collection_log.csv` are row-for-row identical in `movie_name` order and agree on `match_status`/`collection_status` for all 92 rows; `collection_log.csv` adds `match_score` and `match_reason`.
- `movies.csv` and `full_export.csv` are in the same `movie_name` order for all 92 rows; the merge is effectively **positional**, not key-based (see report 05).
- `tickets_sold_web.csv` joins to `movies.csv` on `source_url_doanhthuphim` for all 92/92 rows.

## 1.5 Keys and uniqueness

| Dataset | Exact duplicate rows | Duplicate `source_url_doanhthuphim` | Duplicate normalized `movie_name` |
|---|---:|---:|---:|
| `movies.csv` | 0 | 0 | 0 |
| `unmatched_movies.csv` | 0 | 0 | 0 |
| `collection_log.csv` | 0 | 0 | 0 |
| `tickets_sold_web.csv` | 0 | 0 | 0 |
| `full_export.csv` | 0 | n/a (no URL column) | 0 |

- **Primary key:** `source_url_doanhthuphim` (92 unique values, stable across four datasets). `movie_name` is also unique in this snapshot, but URLs are safer.
- **No `movie_id` column exists.** Joins across exports rely on the DTP URL or on row order.
- No normalized-title duplicates and no case of the *same* normalized title appearing with two different release years were found. This does **not** rule out semantically duplicate films with different titles (see report 02/03).

## 1.6 Overlapping information

- `unmatched_movies.csv` is a pure filter of `movies.csv` (11 of 92 rows; the same 11 rows flagged `not_found`/`needs_review`/no BOV URL).
- `collection_status` duplicates `match_status` exactly in this snapshot (both: 81/10/1).
- `movies.csv` holds two revenue representations for the same concept from two sources; `full_export.csv` collapses them into one `revenue` column and therefore **loses source and provenance**.
- `full_export.csv` columns present in `movies.csv` but **dropped**: `collection_status`, `match_status`, `revenue_bovn`, `revenue_doanhthuphim`, `source_url_bovn`, `source_url_doanhthuphim`, `title_bovn`.
- Columns added by `full_export.csv`: `revenue`, `to_review_director`, `to_review_revenue`, `to_review_tickets_sold`, `to_review_screening_count`, `to_review_match`.
- `original_title` is populated in only **2/92** rows: row 10 `Avengers: Hồi Kết (Endgame)` → `Endgame` (a fragment of the English title), and row 72 `Lật Mặt (Lật Mặt 1)` → `Lật Mặt 1` (a franchise numbering, not a translated/original-language title). The field is therefore not a reliable "original title" attribute.

**Bottom line:** the dataset family is one 92-movie master list replicated into four projections plus one web-evidence table. There are no duplicate keys, but the final export is a lossy, key-less view whose `revenue` column mixes two incompatible source formats.
