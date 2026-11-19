# 02 — Python Implementation Plan for the Single-Flat-CSV Analytics Build

**Status:** design-only plan. No Python implementation code, test files, analytical CSV, mapping JSON or data modification is part of this task.  
**Date:** 2026-11-18.  
**Authoritative specification:** `reports/analytics/01_analytics_dataset_design.md`. This plan must not change, simplify or reinterpret that design.  
**Planned output:** exactly one analytical CSV, `data/analytics/movie_analytics.csv`.  
**Architecture boundary:** simple Python functions, Pandas/NumPy-compatible DataFrames, standard-library helpers, no database, no external service, no scraping, no new analytical exports.

---

## 1. Proposed minimal project structure

### 1.1 Physical layout

The analytics modules should live under the existing source package so no new top-level package or packaging configuration is needed:

```text
src/movie_data_collector/analytics/
    __init__.py
    schema.py
    load_raw.py
    clean.py
    ids.py
    tickets.py
    revenue.py
    build_flat.py
    validate.py
    run_build.py

tests/
    test_analytics_ids.py
    test_analytics_tickets.py
    test_analytics_revenue.py
    test_analytics_build.py
```

No new console script entry is proposed in `pyproject.toml` at this stage. The executable module can be invoked with `python -m movie_data_collector.analytics.run_build`.

### 1.2 File responsibilities

| File | Responsibility | Why necessary | Type |
|---|---|---|---|
| `src/movie_data_collector/analytics/__init__.py` | Package marker for the analytics subpackage. | Makes `movie_data_collector.analytics.*` importable without adding another top-level package. | Reusable module |
| `src/movie_data_collector/analytics/schema.py` | Central constants: build paths, final column order, expected raw columns, expected counts, enum values, known false-positive/candidate rules, mapping schema version. | The approved design fixes exact paths, schema and counts. Keeping them in one place prevents silent drift. It should import existing path constants from `src/movie_data_collector/config.py` and add only new analytics paths. | Reusable module / configuration constants |
| `src/movie_data_collector/analytics/load_raw.py` | Strict CSV/JSONL reading, SHA-256 hashing, schema checks, first-build mapping absence handling, raw bundle assembly. | Stage 1 and stage 15 of the approved design require exact inputs and hash traceability. | Reusable module |
| `src/movie_data_collector/analytics/clean.py` | Text normalization, missing-token coercion, revenue parsing with quality labels, genre token path creation, ticket URL/title normalization helpers. | Keeps raw values intact while producing safe derived keys and typed values. | Reusable module |
| `src/movie_data_collector/analytics/ids.py` | Validate existing mapping, build/reuse/assign IDs in memory, write mapping only after pre-export validation, verify persistence and compute `mapping_hash_after_build`. | Implements the stable ID lifecycle and its failure gates. | Reusable module |
| `src/movie_data_collector/analytics/tickets.py` | Exact DTP-URL linking, ticket candidate deduplication, movie-level aggregation, evidence URL serialization, event-attendance quarantine. | Implements §5 without summing tickets or claiming admissions. | Reusable module |
| `src/movie_data_collector/analytics/revenue.py` | Revenue parsing/segregation rules, mapping validation status, comparison eligibility, gap warnings, comparability flags. | Prevents accepted, candidate-held and quarantined BOV values from being mixed. | Reusable module |
| `src/movie_data_collector/analytics/build_flat.py` | Joins working frames at movie grain, adds matching columns, applies quality flags, orders final columns, exports the single CSV. | Produces the one final flat DataFrame in the approved schema. | Reusable module |
| `src/movie_data_collector/analytics/validate.py` | Pre-export validation, exported-CSV re-read validation, raw-input hash comparison, validation report formatting. | Centralizes all stop gates so the build cannot silently succeed after a failure. | Reusable module |
| `src/movie_data_collector/analytics/run_build.py` | Orchestrates the 15 approved stages, exposes `build` and `validate` commands, returns non-zero exit status on failure. | Single executable entry point without classes, services or frameworks. | Executable module |
| `tests/test_analytics_ids.py` | Unit tests for mapping validation, reuse, new IDs, URL/identity ambiguity, duplicate URLs and persistence failures. | Covers the highest-risk lifecycle rules. | Executable test module |
| `tests/test_analytics_tickets.py` | Unit tests for exact URL linking, dedup keys, aggregation and `Tài` event-attendance quarantine. | Prevents accidental admission claims. | Executable test module |
| `tests/test_analytics_revenue.py` | Unit tests for revenue segregation, line 51 quarantine, line 84 candidate exclusion, eligibility and gap calculations. | Protects the approved revenue policy. | Executable test module |
| `tests/test_analytics_build.py` | Full-build validation tests, CSV re-read checks, hash checks and no-overwrite failure tests. | Verifies the end-to-end contract using read-only raw inputs and temporary output paths. | Executable test module |

### 1.3 Explicitly not proposed

- No database, repository, service layer, ORM, dependency-injection framework or plugin system.
- No class hierarchy; plain dictionaries and DataFrames are sufficient.
- No additional analytical CSVs.
- No modification of `data/full_export.csv` or use of it as a build input.
- No scraping or network calls in the analytics package.
- No new third-party dependency.

---

## 2. End-to-end processing sequence

The sequence below mirrors §6 of the approved design. Transformations remain in memory until all pre-export validations pass.

### 2.1 Intermediate data names used in this plan

| Name | Meaning |
|---|---|
| `paths` | Dict of exact build/input/output paths from `schema.py`. |
| `raw_bundle` | Dict containing four raw frames/records, optional mapping document, and `input_hash_before_build`. |
| `typed_frames` | Raw frames after expected-column checks and type coercion. |
| `working_frames` | Frames with normalized derived columns; raw strings preserved in `*_raw`. |
| `mapping_candidate` | In-memory mapping document after ID reuse/assignment; not persisted yet. |
| `movie_frame` | 92-row movie-grain DataFrame after exact-URL joins. |
| `ticket_summary` | One row per `movie_id` with ticket counts and evidence strings. |
| `revenue_frame` | Revenue columns and derived eligibility/gap flags. |
| `quality_frame` | Data-quality flags and `data_quality_status`. |
| `final_frame` | Final DataFrame in exact approved column order. |
| `validation_reports` | In-memory report dicts printed or returned by the CLI; no additional CSV is written. |

### 2.2 Stages

| # | Stage | Input files | Main operations | Expected intermediate data | Output / validation result | Conditions that stop the build |
|---:|---|---|---|---|---|---|
| 1 | Load exact build inputs and validate existing mapping | `data/movies.csv`, `data/collection_log.csv`, `data/tickets_sold_web.csv`, `state/boxoffice_matches.jsonl`; `state/analytics_movie_id_map.json` if present | Hash each actual input; read CSV with UTF-8 BOM; parse JSONL line by line; load and validate mapping if present; allow absent mapping only on first build | `raw_bundle`, `input_hash_before_build`, validated mapping or explicit first-build absence | Four inputs available with 92/92/92/92 rows; mapping hash recorded when read | Missing required file; wrong row count; wrong encoding/schema; JSONL parse failure; malformed/invalid mapping when present; any required hash missing |
| 2 | Inspect schemas and types | `raw_bundle` | Verify required columns; cast `release_year`, `match_score`, money and ticket fields; convert literal `"nan"` to null | `typed_frames` | Typed frames with no unexpected source columns used for values | Missing or unexpected required raw column; unsafe type coercion for a required field |
| 3 | Clean and normalize | `typed_frames` | Preserve raw strings; create normalized grouping keys; parse DTP/BOV money with quality labels; build `genre_token_path`; normalize URLs/titles for ticket dedup | `working_frames` | Raw values unchanged; derived keys only in new columns | Any DTP revenue not parseable for a required DTP row; raw value overwritten by derived value; unsupported parser output |
| 4 | Build/reuse/assign `movie_id` in memory | DTP URLs, identity metadata, validated mapping | Reuse unchanged IDs; seed first build; assign new IDs from next free ordinal; handle verified URL changes; detect duplicate/invalid identities | `mapping_candidate`, `id_rows` | One non-null `movie_id` per DTP URL; no renumbering or reuse; no file write | Duplicate source URL; duplicate identity; invalid mapping; ambiguous URL/identity change; `ID_MAPPING_INVALID`; `ID_MAPPING_UNRESOLVED`; any attempt to persist early |
| 5 | Join at movie level | `working_frames`, `id_rows` | Join movies, collection log and BOV context by exact `source_url_doanhthuphim`; do not use position, fuzzy title or BOV title | `movie_frame` | One 92-row movie DataFrame; no fan-out | Row count not 92; duplicate DTP URL; join fan-out; missing exact URL match for a required source row |
| 6 | Aggregate ticket candidates | `data/tickets_sold_web.csv` working rows, `movie_frame` | Link populated candidates by exact DTP URL; deduplicate by approved key; aggregate counts; quarantine `Tài`; serialize evidence URLs; leave admissions NULL | `ticket_summary` | 16 candidates, 5 `found`, 11 `needs_review`, 76 no-candidate movies; no sums | `TICKET_LINK_UNRESOLVED`; duplicated candidate collapses incorrectly; ticket numbers summed; admissions populated; context quarantine missing; counts inconsistent |
| 7 | Preserve revenue sources | `movie_frame` | Keep DTP, valid BOV, quarantined BOV and candidate BOV strings/numbers in separate columns; reconcile stored BOV observations | `revenue_frame` | 92 DTP; 80 stored BOV = 79 valid + 1 quarantined; 1 candidate; no cross-copy | Candidate value in `bov_revenue_vnd`; line 51 value in accepted BOV fields; stored BOV count mismatch; collapsed preferred revenue field |
| 8 | Apply matching and revenue eligibility | `revenue_frame`, matcher fields, review rules | Derive `mapping_validation_status`, review fields, `include_revenue_comparison`, `comparability_reason`, `revenue_gap_pct` and scoped `magnitude_gap_warning` | Eligible `final_frame` skeleton | 79 comparison rows; line 51 and line 84 excluded; all eligible rows `insufficient_evidence`; `revenue_gap_pct` only for eligible rows | Eligible count not 79; known false positive/candidate eligible; candidate percentage exported; human review invented; formula denominator not DTP |
| 9 | Generate quality flags | Eligible frame | Derive missing-core, revenue-warning roll-up, pending-review and `data_quality_status` using approved precedence | `quality_frame` | 21 warnings = 20 valid + 1 candidate-only; 0 conflicts; 6 pending workflow rows; 3 missing-core rows; 0 human-reviewed maps | Warning count mismatch; line 51 included in gap calculation; `revenue_conflict_flag=1`; review outcome fabricated; pending count mismatch |
| 10 | Run all pre-export validations | `final_frame`, `mapping_candidate`, `expected_counts` | Check row count, PK, DTP URL uniqueness, schema/order, revenue segregation, ticket aggregation, all §2.4 counts and §3.1 contract | Pass/fail gate | All §3.1 contract items pass before any write | Any failed check; stop before mapping persistence and before CSV export; do not overwrite an existing CSV |
| 11 | Persist mapping JSON | `mapping_candidate`, `paths['id_map']` | Write `state/analytics_movie_id_map.json` only after stage 10 passes | Persisted mapping file | Mapping write occurs after validation, never before | Mapping write failure; validation failure; any attempt to renumber or reseed IDs |
| 12 | Verify mapping persistence and hash | Persisted mapping file, `mapping_candidate` | Re-read mapping; validate schema/content; compute `mapping_hash_after_build` | Verified mapping object, post-build hash | `mapping_hash_after_build` recorded separately; equality with pre-build hash not required | Re-read failure; content mismatch; schema invalid; persistence verification failure; stop before CSV export |
| 13 | Export one CSV | Validated `final_frame`, `paths['output_csv']` | Write only `data/analytics/movie_analytics.csv`; UTF-8 without BOM; empty as empty; exact column order | Analytical CSV | One flat CSV, 92 rows, one row per `movie_id` | Export failure; wrong path; extra analytical export attempted; do not silently claim success |
| 14 | Re-read and validate exported CSV | Exported CSV, approved schema and counts | Re-read file; compare schema/order, row count, PK uniqueness, values and counts with expected frame/report | Post-export validation report | Exported CSV reproduces approved counts and schema | Schema/order mismatch; row/PK/count mismatch; value drift; report failure clearly |
| 15 | Re-hash required raw inputs | Four required raw input files, `input_hash_before_build` | Recompute SHA-256 and compare with start-of-build values | Final hash check report | All four raw hashes unchanged; mapping hash remains separate | Any raw input hash change; report failure clearly; do not claim a successful build |

### 2.3 Write-order guarantee

The implementation must preserve this exact order:

1. validate existing mapping, if present;
2. assign IDs in memory;
3. build the movie DataFrame;
4. complete transformations;
5. run all pre-export validations;
6. persist mapping JSON;
7. verify persistence and calculate `mapping_hash_after_build`;
8. export `movie_analytics.csv`;
9. re-read and validate CSV;
10. re-hash raw inputs.

No stage may reorder these gates.

---

## 3. Function interface specifications

The following are interfaces only, not implementation code. Report objects are plain dictionaries. The design does not require custom classes.

### 3.1 `schema.py`

| Function | Parameters | Return | Responsibility | Validation / error conditions |
|---|---|---|---|---|
| `build_paths` | none | `dict[str, Path]` with keys for four required inputs, mapping JSON and output CSV | Provide the exact paths from the approved design using existing `config.py` constants where available | Must not include audit-only or deprecated files as build inputs |
| `final_columns` | none | `list[str]` | Return the approved final column names in exact order | Must match §3.3–§3.7; must not include `revenue_official_vnd`, release date or duration |
| `expected_raw_columns` | none | `dict[str, list[str]]` | Return required column sets for each raw input | Fails validation if any required column is missing |
| `expected_counts` | none | `dict[str, int]` | Return approved counts from §2.4 and §3.1 | Must include 92 rows, 79 comparisons, 80 stored BOV, 21 warnings, 16 ticket candidates, 5 found, 11 needs review, 6 pending, 3 missing-core |
| `known_mapping_rules` | none | `dict` | Return explicit, reviewable rules for line 51 quarantine and line 84 candidate-held status | Must not infer review from fuzzy scores; changes require design review |
| `mapping_schema_version` | none | `str` | Return approved mapping schema version | Used by mapping validation |

### 3.2 `load_raw.py`

| Function | Parameters | Return | Responsibility | Validation / error conditions |
|---|---|---|---|---|
| `file_sha256` | `path: Path` | `str` | Compute SHA-256 for a file in chunks | Missing or unreadable file is an error |
| `read_csv_strict` | `path: Path`, `expected_columns: list[str]`, `row_count: int` | `DataFrame` | Read CSV with UTF-8 BOM and verify schema/row count | Missing column, wrong count or decode failure stops build |
| `read_jsonl_strict` | `path: Path`, `row_count: int` | `list[dict]` | Parse JSONL line by line and verify record count | Invalid JSON line or wrong count stops build |
| `load_raw_bundle` | `paths: dict[str, Path]`, `allow_missing_mapping: bool` | `dict` containing raw frames/records, optional mapping document and `input_hash_before_build` | Orchestrate stage 1; hash all four required inputs; hash mapping when present | Missing required file, bad schema, JSONL error or invalid mapping stops build; missing mapping allowed only when first build is explicitly permitted |

### 3.3 `clean.py`

| Function | Parameters | Return | Responsibility | Validation / error conditions |
|---|---|---|---|---|
| `coerce_missing_tokens` | `frame: DataFrame` | `DataFrame` | Convert literal `"nan"`, empty strings and configured null tokens to pandas null without changing meaningful text | Must not convert valid string `"nan"` content if it is genuine title text; rule should be column-aware where needed |
| `normalize_grouping_key` | `value: str \| None` | `str \| None` | Casefold, strip accents/`đ`, collapse whitespace for grouping keys | Used only for grouping; never overwrites raw title/director |
| `normalize_ticket_title` | `value: str \| None` | `str \| None` | Normalize source title for ticket dedup, preserving punctuation needed to distinguish titles | Must not collapse distinct headlines into one key |
| `normalize_ticket_url` | `url: str \| None` | `str \| None` | Lowercase host, remove fragments/tracking parameters and trailing slashes; keep Google News RSS URLs intact | Must not resolve or fetch URLs |
| `parse_revenue_with_quality` | `raw: str \| None`, `source: str` | `tuple[int \| None, str \| None]` | Parse VND-like strings and return numeric value plus `rounded`, `lower_bound` or `exact` quality as appropriate; detect `hơn X` as lower bound | Unparseable DTP required value stops build; must not claim DTP `exact` |
| `split_genre_tokens` | `genre_raw: str \| None` | `list[str]` | Split raw genre string into tokens for `genre_token_path` | Must preserve raw genre string; no second exported table |

### 3.4 `ids.py`

| Function | Parameters | Return | Responsibility | Validation / error conditions |
|---|---|---|---|---|
| `load_and_validate_mapping` | `mapping_doc: dict \| None`, `current_rows: list[dict]`, `allow_missing: bool` | `dict` validated mapping structure, including empty first-build marker | Validate schema version, required fields, `M\d{4}` format, unique IDs/URLs, no retired ID reuse and active URL reconciliation | Missing mapping invalid unless `allow_missing`; duplicate/invalid/ambiguous mapping stops with documented error |
| `assign_ids_in_memory` | `current_rows: list[dict]`, `mapping: dict` | `tuple[list[dict], dict]` of rows with IDs and in-memory mapping candidate | Reuse existing IDs, seed first build, add new IDs from next free ordinal, handle verified URL changes | No persistence; no renumber/reuse; ambiguous identity/URL stops build |
| `resolve_identity_change` | `current_row: dict`, `candidate_rows: list[dict]` | `dict \| None` | Apply identity verification by title + year + director or approved reviewer alias | Ambiguous or conflicting identity returns failure; no guessing |
| `persist_mapping` | `mapping_candidate: dict`, `path: Path` | `None` | Write mapping JSON only after pre-export validation passes | Write failure stops build; must not export CSV |
| `verify_mapping_and_hash` | `path: Path`, `expected_doc: dict` | `str` | Re-read and validate persisted mapping; compute `mapping_hash_after_build` | Re-read/content/schema failure stops build; pre-build and post-build hashes need not match |

### 3.5 `tickets.py`

| Function | Parameters | Return | Responsibility | Validation / error conditions |
|---|---|---|---|---|
| `link_tickets_to_movies` | `tickets: DataFrame`, `movie_id_by_dtp_url: dict[str, str]` | `DataFrame` with `movie_id` added | Link each populated ticket candidate by exact `source_url_doanhthuphim` | Unresolved populated candidate stops with `TICKET_LINK_UNRESOLVED`; no fuzzy/title/positional join |
| `deduplicate_ticket_candidates` | `linked: DataFrame` | `DataFrame` | Apply approved primary key `(movie_id, source_url_normalized, source_title_normalized)` and secondary `(tickets_display, ticket_status)` rule | Exact duplicates collapse; distinct evidence preserved; no numeric summing |
| `classify_ticket_context` | `row: dict` | `str` | Return `cinema_candidate_unverified`, `event_attendance_quarantined` or `no_candidate` | `Tài` line 49 must be event-attendance quarantined and still counted in needs-review |
| `aggregate_ticket_summary` | `deduped: DataFrame`, `all_movie_ids: list[str]` | `DataFrame` one row per `movie_id` | Compute candidate, found and needs-review counts; data status; context status; evidence URLs; admissions NULL | Counts must reproduce 16/5/11/76; no admission inference or ticket values summed |
| `serialize_evidence_urls` | `urls: list[str]` | `str \| None` | Deduplicate by normalized URL, sort lexicographically and join raw URLs with `\|` | Evidence string is navigation only, not a metric |

### 3.6 `revenue.py`

| Function | Parameters | Return | Responsibility | Validation / error conditions |
|---|---|---|---|---|
| `parse_revenue_columns` | `frame: DataFrame` | `DataFrame` | Parse DTP, valid BOV, quarantined BOV and candidate BOV values into separate raw/numeric/quality columns | No cross-copy; line 51 only in quarantine; line 84 only in candidate fields |
| `derive_mapping_validation` | `row: dict`, `rules: dict` | `tuple[str, str \| None]` | Return `mapping_validation_status` and `mapping_validation_reason` | Line 51 must be `known_false_positive_quarantined` / `sequel_number_error`; line 84 `candidate_held` / `different_subtitle`; no human review invented |
| `derive_review_fields` | `row: dict`, `rules: dict` | `tuple[str, str]` | Return `review_status` and `review_priority` from workflow rules | Line 51 remains `pending`; high-priority lines are 51, 32, 84, 78, 93, 91; `human_confirmed`/`rejected` not fabricated |
| `compute_gap_pct` | `dtp_vnd: int \| None`, `bov_vnd: int \| None` | `float \| None` | Calculate `abs(dtp - bov) / dtp × 100` using DTP as denominator | NULL when denominator or BOV value unusable; never use `max(dtp, bov)` |
| `apply_revenue_eligibility` | `frame: DataFrame` | `DataFrame` | Set accepted BOV fields, candidate/quarantine exclusions, `include_revenue_comparison`, `revenue_gap_pct`, `magnitude_gap_warning`, comparability class/reason and `bov_evidence_available` | 79 eligible rows; candidate may have warning-only internal gap with exported `revenue_gap_pct=NULL`; line 51 excluded from gap calculation; `revenue_conflict_flag=0` |
| `derive_revenue_eda_basis` | `row: dict` | `str \| None` | Set `dtp_rounded_numeric_agreement`, `dtp_rounded_single_source` or `dtp_lower_bound` | Must never claim corroboration or official revenue |

### 3.7 `build_flat.py`

| Function | Parameters | Return | Responsibility | Validation / error conditions |
|---|---|---|---|---|
| `build_movie_frame` | `raw_bundle: dict`, `id_rows: list[dict]` | `DataFrame` | Build the 92-row movie-grain base frame with Group A identity/metadata columns | Duplicate DTP URL, wrong count or fan-out stops build |
| `add_matching_columns` | `frame: DataFrame`, `collection_log: DataFrame` | `DataFrame` | Add Group B columns from collection log and derived mapping/review fields | Exact DTP URL join; matcher status remains diagnostic only |
| `merge_ticket_and_revenue` | `frame: DataFrame`, `ticket_summary: DataFrame`, `revenue_frame: DataFrame` | `DataFrame` | Attach Groups C and D without changing grain | No row multiplication; no ticket totals; no preferred revenue |
| `add_quality_flags` | `frame: DataFrame` | `DataFrame` | Add Group E flags and `data_quality_status` precedence | Warnings/conflicts/pending flags must follow approved rules |
| `order_final_columns` | `frame: DataFrame`, `columns: list[str]` | `DataFrame` | Enforce exact approved schema and order | Missing, extra or reordered column stops build |
| `export_csv` | `frame: DataFrame`, `path: Path` | `None` | Write the single analytical CSV with UTF-8 without BOM | Wrong path, write failure or attempted second analytical export stops/reports failure |

### 3.8 `validate.py`

| Function | Parameters | Return | Responsibility | Validation / error conditions |
|---|---|---|---|---|
| `validate_pre_export` | `final_frame: DataFrame`, `mapping_candidate: dict`, `expected: dict` | report `dict` | Run all §3.1 contract checks, §2.4 counts, revenue segregation, ticket aggregation and grain checks | Any failure blocks mapping persistence and CSV overwrite |
| `validate_exported_csv` | `csv_path: Path`, `expected_columns: list[str]`, `expected_counts: dict`, `expected_frame: DataFrame \| None` | report `dict` | Re-read exported CSV and verify schema/order, row count, PK uniqueness and counts/values | Any mismatch is reported; build is not called successful |
| `verify_raw_input_hashes` | `paths: dict[str, Path]`, `before: dict[str, str]` | report `dict` | Re-hash the four required inputs and compare with `input_hash_before_build` | Any mismatch is reported; no silent success |
| `format_report` | `report: dict` | `str` | Render validation results for stdout/logging | Must not write an additional analytical CSV or manifest file |

### 3.9 `run_build.py`

| Function | Parameters | Return | Responsibility | Validation / error conditions |
|---|---|---|---|---|
| `run_build` | `paths: dict[str, Path]` | final report `dict` | Execute stages 1–15 in order and stop at the first failed gate | Must never persist mapping before stage 10; must never export before successful mapping persistence |
| `validate_existing_output` | `paths: dict[str, Path]` | report `dict` | Read-only standalone validation of the exported CSV; recomputes current raw hashes for report only | Must not write mapping or CSV; must not claim “unchanged since build” without a supplied baseline |
| `main` | `argv: list[str] \| None` | `int` | Parse `build` / `validate` commands, print reports, return exit status | Non-zero on any failure; no vague success message after partial failure |

---

## 4. Dependencies

### 4.1 Required and already available

| Dependency | Status | Use in this plan |
|---|---|---|
| Python `>=3.13` | Declared in `pyproject.toml` | Runtime baseline |
| `pandas>=3.1.1` | Declared in `pyproject.toml` | CSV reading/writing, DataFrame transformations, nullable integer types, joins and validation |
| Standard library `pathlib` | Built in | Path handling |
| Standard library `hashlib` | Built in | SHA-256 hashing |
| Standard library `json` | Built in | Mapping JSON and JSONL parsing |
| Standard library `csv` / Pandas I/O | Built in / declared | CSV handling |
| Standard library `re`, `unicodedata` | Built in | Text normalization and token handling |
| Standard library `argparse` | Built in | CLI parsing |
| Standard library `unittest` | Built in | Tests; avoids adding pytest |
| Standard library `datetime`, `tempfile` | Built in | Mapping timestamps and isolated test outputs |

### 4.2 Not required for analytics

| Dependency | Reason |
|---|---|
| `playwright` | Required by scraper only; analytics must not scrape or fetch |
| `rapidfuzz` | Matching is already recorded in raw inputs; analytics must not perform fuzzy identity matching |
| `numpy` | The design permits NumPy, but the current `pyproject.toml` does not declare it directly. This plan avoids direct NumPy imports; if later needed, dependency approval should be requested before adding it. |
| `pytest` | Not declared; `unittest` is sufficient and avoids environment changes |

### 4.3 Existing project code reuse

- Reuse existing read-only path constants from `src/movie_data_collector/config.py` where they already match the approved inputs.
- Do not import or execute scraping modules from the analytics package.
- Do not reuse `full_export.py` logic: its `revenue = bov_raw or dtp_raw` rule and `max(dtp, bov)` conflict denominator are explicitly rejected by the design.
- `utils.parse_money_vnd()` may be used as a low-level parser helper only if wrapped by `clean.parse_revenue_with_quality()` to add lower-bound detection and approved quality labels.

---

## 5. Testing and validation strategy

### 5.1 Unit tests vs full-build validation

- **Unit tests** use small synthetic DataFrames/dicts and temporary paths. They test one rule at a time and must not write the real mapping JSON or analytical CSV.
- **Full-build validation** uses the current four required raw inputs read-only. It may write only to temporary output paths during tests and must clean up. It reproduces the approved counts and validates export/re-read behavior without touching real `state/analytics_movie_id_map.json` or `data/analytics/movie_analytics.csv`.
- **Failure-injection tests** substitute failing writers or invalid fixtures to prove no overwrite/no silent success behavior.

### 5.2 Required test coverage

| # | Type | Test area | Scenario / setup | Expected result |
|---:|---|---|---|---|
| 1 | Unit + full-build | Required inputs and schemas | Provide all four required inputs; omit one; alter a required column | Valid set loads; missing file or column stops with clear error; audit-only/deprecated files are not required |
| 2 | Unit | Missing or duplicate movie IDs | Mapping with null ID or duplicate ID | Validation fails; no ID assignment accepted |
| 3 | Unit | Stable ID reuse | Same 92 DTP URLs on two builds with existing mapping | All IDs reused unchanged; no JSON write occurs until validation gate |
| 4 | Unit | New ID without renumbering | Add one new DTP URL to existing mapping | Existing IDs unchanged; new ID is next free ordinal; retired/missing IDs not reused |
| 5 | Unit | Ambiguous URL/identity change | URL changes with conflicting title/year/director or multiple candidates | Build stops with `ID_MAPPING_UNRESOLVED`; no guessed ID |
| 6 | Unit | Duplicate source URLs | Two raw movies share `source_url_doanhthuphim`; two mapping entries share URL | Stops with duplicate-URL failure before persistence |
| 7 | Unit | Exact URL ticket linking | Populated ticket row URL matches one movie; another uses similar but non-identical URL | Exact match links; non-identical unresolved populated row stops with `TICKET_LINK_UNRESOLVED`; no title join |
| 8 | Unit | Ticket dedup and aggregation | Duplicate evidence rows plus distinct evidence rows for one movie | Dedup key collapses exact duplicates; counts reflect unique candidates; no numeric ticket values summed |
| 9 | Unit | `Tài` event attendance | Line 49 `Tài` candidate | Counts as one `needs_review` candidate but has `ticket_context_status='event_attendance_quarantined'`; no admission interpretation |
| 10 | Unit | DTP/BOV revenue separation | Row with both revenue strings; row with candidate BOV | DTP and BOV remain separate; candidate BOV never copied to `bov_revenue_vnd`; no preferred revenue column |
| 11 | Unit | Quarantined sequel false positive | Line 51 `Chị Mười Ba: 3 Ngày Sinh Tử` with BOV `Chị Mười Ba 2: 3 Ngày Sinh Tử` | `known_false_positive_quarantined`, `sequel_number_error`, pending; BOV only in quarantine columns; excluded from gap and comparisons |
| 12 | Unit | Candidate-held BOV exclusion | Line 84 `Kính Vạn Hoa: Phim Điện Ảnh` | `candidate_held`, `different_subtitle`; candidate revenue only in candidate columns; `revenue_gap_pct=NULL`; not in scatter/count |
| 13 | Unit | Eligibility and gap calculation | Valid accepted BOV rows with gaps below/above 10%; candidate row above 10%; line 51 | Valid rows populate `revenue_gap_pct`; warning when `>10` using DTP denominator; candidate warning-only with NULL percentage; line 51 no gap; conflicts remain 0 |
| 14 | Full-build validation | Exactly 92 unique movie rows | Run build validations against current raw inputs | 92 rows, 92 unique non-null `movie_id`, 92 unique `source_url_dtp` |
| 15 | Full-build validation | CSV export and re-read | Export to temp path, then re-read | Column order, schema, row count, PK and counts match expected frame |
| 16 | Full-build validation | Raw input hash consistency | Hash at start; mutate a copied required input before final hash check | Unchanged inputs pass; changed input fails and is reported; mapping hash remains separate |
| 17 | Unit + failure injection | Persistence/export failure behavior | Force pre-export validation failure, mapping write failure and CSV export failure | No mapping write on pre-export failure; no CSV export/overwrite on mapping failure; export failure reported clearly; no silent success |

### 5.3 Additional validation checks included in full-build validation

- First build with missing mapping JSON is allowed; later missing mapping is not.
- `mapping_hash_after_build` is recorded only after successful persistence.
- Mapping pre-build and post-build hashes may differ and are not required to match.
- `include_revenue_comparison=1` exactly 79 rows.
- `magnitude_gap_warning=1` exactly 21 rows = 20 valid + 1 candidate-only.
- `revenue_conflict_flag=0` for all rows.
- `ticket_verified_admissions` NULL for all rows.
- `mapping_human_reviewed=0` with reviewer fields NULL.
- No official revenue column, release date or duration column appears.

---

## 6. Execution workflow

These commands are proposed only and must not be run as part of this planning task.

### 6.1 Run tests

```bash
uv run python -m unittest discover -s tests -p "test_*.py" -v
```

### 6.2 Build the analytical CSV

```bash
uv run python -m movie_data_collector.analytics.run_build build
```

Expected behavior:

- performs stages 1–15 in order;
- prints a validation summary;
- returns non-zero status on any stop condition;
- writes only `data/analytics/movie_analytics.csv` and the approved mapping JSON after the correct gates.

### 6.3 Validate the exported CSV

```bash
uv run python -m movie_data_collector.analytics.run_build validate
```

Expected behavior:

- read-only with respect to mapping JSON and analytical CSV;
- re-checks exported CSV structure/counts;
- recomputes current raw-input hashes for reporting, but does not claim a comparison against the build-start baseline;
- prints a clear validation report;
- returns non-zero status if the CSV cannot be validated.

**Review point:** the approved design specifies post-export validation as part of the build but does not define a separate standalone `validate` command. The proposed read-only command is the minimal practical interpretation and should be confirmed before implementation.

---

## 7. Assumptions and unresolved issues

These are carried forward from the approved design or identified as implementation-planning clarifications. No unilateral design change is made here.

1. **Revenue scope remains unknown.** Lifetime cumulative vs cumulative-to-date is unresolved; official revenue stays blocked.
2. **`release_date` and `duration` remain omitted.** No supported raw source exists.
3. **`genre_grouped` remains NULL.** No approved human vocabulary exists yet.
4. **Review transitions are not implemented.** Reviewer identity, evidence requirements and approval workflow for `human_confirmed` / `human_rejected` need human approval.
5. **Line 51 remains quarantined and pending.** A human must confirm or reject the sequel-number mapping before any design change.
6. **Line 84 remains candidate-held.** It must not become accepted BOV revenue without review.
7. **Ticket admissions remain unverified.** The 16 candidates are evidence rows, not admissions; line 49 is event attendance.
8. **Lower-bound display needs approval.** The `≥` display and exclusion from means are specified but still listed as open in the design.
9. **Licensing approval is needed** for retaining source URLs and candidate snippets in the personal/non-commercial dashboard.
10. **NumPy is not directly declared.** This plan avoids direct NumPy imports; adding NumPy as an explicit dependency requires approval.
11. **Standalone `validate` command semantics need confirmation.** This plan proposes read-only validation only; design §6 mandates post-export validation inside the build. A standalone command cannot prove raw inputs were unchanged since build because the design does not define a persisted baseline, and this plan does not add one.
12. **Known-rule encoding must remain explicit.** Line 51 and line 84 rules should be reviewable constants in `schema.py`, not inferred by fuzzy logic. Any change needs design review.
13. **No new columns may be added.** If implementation reveals a need for a new field, stop and request review rather than silently extending the schema.

---

## 8. Checklist mapping this plan back to the approved design

| Design section | Approved requirement | Plan coverage |
|---|---|---|
| §1 | One flat CSV, simple project, no database | §1 structure, §2 export stage, §4 dependencies |
| §2.1 | Four exact required build inputs | `schema.build_paths`, `load_raw.load_raw_bundle`, test 1 |
| §2.1 | Mapping JSON is build metadata, not analytical input/export | `ids.py`, persistence order, §1 exclusions |
| §2.2 | Audit-only and deprecated files excluded | `schema.build_paths`, test 1 |
| §2.3 | `input_hash_before_build` covers all actual inputs read at start | `file_sha256`, `load_raw_bundle`, stage 1, test 16 |
| §2.3 | First-build mapping absence allowed; later absence invalid | `load_and_validate_mapping`, stages 1/11, test 3 |
| §2.3 | Raw inputs unchanged during build; mapping may change | `verify_raw_input_hashes`, stages 12/15, tests 3/16 |
| §2.3 | `mapping_hash_after_build` separate from pre-build hash | `verify_mapping_and_hash`, stage 12, §5.3 |
| §2.4 | Preserve all verified counts | `expected_counts`, `validate_pre_export`, full-build validation |
| §2.5 | Do not reuse rejected heuristics from `full_export.py` | §4.3, revenue functions, test 10/13 |
| §3.1 | 92 rows, unique non-null `movie_id`, unique DTP URL, exact schema | `validate_pre_export`, `validate_exported_csv`, tests 14/15 |
| §3.3–§3.7 | Exact columns and raw-value preservation | `final_columns`, `order_final_columns`, build functions |
| §4.1 | Separate DTP, accepted BOV, quarantined BOV, candidate BOV | `parse_revenue_columns`, `apply_revenue_eligibility`, test 10 |
| §4.2 | 79 valid comparisons; line 51 and line 84 excluded | `apply_revenue_eligibility`, tests 11/12/13 |
| §4.3 | DTP-referenced gap formula, `>10%`, candidate warning-only, no line 51 gap | `compute_gap_pct`, `apply_revenue_eligibility`, test 13 |
| §4.4 | No official revenue value or column | `final_columns`, schema check, test 10 |
| §5.1 | Exact DTP-URL ticket linking only | `link_tickets_to_movies`, test 7 |
| §5.2 | Ticket dedup keys and URL/title normalization | `deduplicate_ticket_candidates`, `normalize_ticket_*`, test 8 |
| §5.3 | Aggregate counts only; no admitted totals | `aggregate_ticket_summary`, tests 8/9 |
| §5.4 | Deduped, sorted, pipe-separated evidence URLs | `serialize_evidence_urls`, test 8 |
| §5.5 | `Tài` event-attendance quarantine | `classify_ticket_context`, test 9 |
| §6 stages 1–10 | Transform and validate before any write | §2.2, `run_build`, `validate_pre_export`, test 17 |
| §6 stages 11–12 | Persist mapping and verify/hash only after pre-export validation passes | `ids.py`, stages 11–12, test 17 |
| §6 stages 13–15 | Export CSV, re-read, re-hash raw inputs | `export_csv`, `validate_exported_csv`, `verify_raw_input_hashes`, tests 15/16 |
| §6 failure gates | No persistence/export on validation failure; clear failure reporting | `run_build`, test 17 |
| §7 | Power BI imports only the one CSV | §1 exclusions, `export_csv` |
| §8.1 | Stable ID schema, reuse, new IDs, URL-change verification, duplicate handling | `ids.py`, tests 2–6 |
| §8.2 | Preserved raw values and evidence URLs | `clean.py`, `tickets.py`, `revenue.py` |
| §8.3 | Exclusions expressed as flags, not deleted rows | `apply_revenue_eligibility`, `add_quality_flags` |
| §10 | Open issues remain documented | §7 |
| §11 | Verification summary and correction log | §5.3 and this checklist |
