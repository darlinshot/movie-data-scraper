# 02 — Data Quality Report

Read-only assessment of the five datasets. Row numbers below are **CSV line numbers including the header** (i.e. data row 1 = CSV line 2). Parsing rules mirror `src/movie_data_collector/utils.py`.

**Definitions used here**
- "Missing" = empty string, whitespace-only, or literal `nan`/`none`/`null`/`n/a`/`na`. No such null-placeholder strings beyond true blanks were found (one exception noted in §2.4).
- "Core issue" (for the aggregate rate) = at least one of: non-`matched` match status; >10% revenue conflict between DTP and BOV; missing BOV revenue; missing director; web ticket candidate flagged `needs_review`. **`original_title` missingness is excluded from the core rate** because it is an optional enrichment field in this schema (97.8% missing globally).

---

## 2.A Completeness

### `movies.csv` (n = 92)

| Column | Missing | Missing % |
|---|---:|---:|
| `movie_name` | 0 | 0.00% |
| `title_bovn` | 10 | 10.87% |
| `original_title` | 90 | **97.83%** |
| `release_year` | 0 | 0.00% |
| `genre` | 0 | 0.00% |
| `director` | 3 | 3.26% |
| `revenue_doanhthuphim` | 0 | 0.00% |
| `revenue_bovn` | 11 | 11.96% |
| `tickets_sold` | 92 | **100.00%** |
| `screening_count` | 92 | **100.00%** |
| `source_url_doanhthuphim` | 0 | 0.00% |
| `source_url_bovn` | 10 | 10.87% |
| `match_status` | 0 | 0.00% |
| `collection_status` | 0 | 0.00% |

**Completely empty columns:** `tickets_sold`, `screening_count`.
**Completely empty rows:** none. **Records missing important identifiers:** 10 rows lack any BOV identity (`source_url_bovn` and `title_bovn`); all 92 have a DTP URL and movie name.

### `unmatched_movies.csv` (n = 11)
Same schema. Missing: `title_bovn`, `original_title`, `revenue_bovn`, `source_url_bovn` = 10/11 (90.91%) each; `tickets_sold` and `screening_count` = 11/11 (100%). The one populated BOV row is the `needs_review` record (row 84 in the master list).

### `collection_log.csv` (n = 92)
No completely empty columns and no missing `match_score`/`match_reason`. Only `title_bovn` / `source_url_bovn` missing in 10 rows (10.87%). This is the most complete provenance table.

### `tickets_sold_web.csv` (n = 92)

| Column | Missing | Missing % |
|---|---:|---:|
| `tickets_sold_web`, `tickets_display`, `tickets_basis`, `confidence`, `source_title`, `source_url`, `source_name`, `published`, `snippet`, `search_backend`, `matched_query` | 76 each | **82.61%** |
| `error` | 92 | **100.00%** |
| `ticket_status` | 0 | 0.00% |
| `search_queries`, `candidate_count`, `collected_at` | 0 | 0.00% |

Status distribution: `found` 5 (5.43%), `needs_review` 11 (11.96%), `not_found` 76 (82.61%). The `error` column is entirely empty even though `search_error` is a possible code path, so no search failures are recorded.

### `full_export.csv` (n = 92)

| Column | Missing | Missing % |
|---|---:|---:|
| `original_title` | 90 | 97.83% |
| `tickets_sold` | 87 | 94.57% |
| `screening_count` | 92 | 100.00% |
| `to_review_director` | 89 | 96.74% |
| `to_review_revenue` | 71 | 77.17% |
| `to_review_tickets_sold` | 81 | 88.04% |
| `to_review_screening_count` | 92 | 100.00% |
| `to_review_match` | 91 | 98.91% |
| `revenue`, `movie_name`, `release_year`, `genre` | 0 | 0.00% |

**Completely empty columns:** `screening_count`, `to_review_screening_count`.

### Cross-source completeness comparison

| Attribute | DTP side (master) | BOV side (matched) | Web ticket evidence |
|---|---:|---:|---:|
| Revenue | 92/92 (rounded, "tỷ") | 81/92 (exact VND) | n/a |
| Tickets sold | 0/92 | 0/92 | 16/92 (5 accepted, 11 uncertain) |
| Screenings | 0/92 | 0/92 | n/a |
| Release date (full) | 0/92 (year only) | 0/92 in CSV (`bov_release_info` exists only in state JSONL, and is polluted) | n/a |
| Original/alternate title | 2/92 | `bov_title` in state only, dropped from export | n/a |

**Finding:** revenue is the only attribute with reasonable coverage. Every other analytical attribute (tickets, screenings, release date, original title, rating, runtime) is absent or nearly absent.

---

## 2.B Uniqueness

- **Exact duplicate rows: 0** in all five datasets.
- **Duplicate `source_url_doanhthuphim`: 0** (92 unique). No duplicate `source_url_bovn` among the 82 present.
- **Duplicate normalized movie titles: 0** (normalization = lowercase, accent-stripped, `đ→d`, digits→Vietnamese words, punctuation removed — the same logic used by the matcher).
- **Same normalized title with different release years: 0.**
- **Duplicates across datasets:** `unmatched_movies.csv` is intentionally a subset (11 rows all present in `movies.csv`); the other three 92-row files are 1:1 projections, so no duplicates are introduced by merging (row counts stay at 92).
- **Potential semantically duplicate movies with different titles:** cannot be ruled out. Concrete candidates to review: row 38 `Quỷ Nhập Tràng 2` vs row 35 `Quỷ Nhập Tràng`; rows 16/20 (`Lật Mặt 6`, `Lật Mặt 8`) plus rows 72/73/74 (`Lật Mặt 1`, `2`, `Ba Chàng Khuyết`) are distinct franchise instalments, not duplicates. No merge or removal was performed.

---

## 2.C Validity

| Check | Result |
|---|---|
| Invalid data types in numeric columns | No numeric columns exist; all counts/amounts are strings. `tickets_sold_web` is stored as integer-like text. |
| Incorrect date format | No date column in any CSV; `release_year` is a clean 4-digit string in all 92 rows. `published` in `tickets_sold_web.csv` is valid ISO-8601 UTC for the 16 populated rows. |
| Invalid years | No values outside 1900–2099. Observed: 2007 (1), 2013 (1), 2014 (2), 2015 (3), 2016 (2), 2017 (2), 2018 (5), 2019 (7), 2020 (3), 2021 (3), 2022 (7), 2023 (9), 2024 (12), 2025 (14), 2026 (21). |
| Negative revenue / tickets / screenings | None (no negatives, no zeros in parsed revenue). |
| Invalid ratings / rating scale | **Not applicable — no rating column exists anywhere.** `match_score` is fuzzy-match confidence (0–100), not a film rating; treating it as one would be an error. |
| Malformed URLs | 0. All 92 DTP URLs, 82 BOV URLs and 16 web evidence URLs match `^https?://...$`. Structural oddity: row 78 uses BOV URL `/movie/co-ba-sai-gon-2/` (a `-2` slug for a 2017 film) — syntactically valid but suspicious (see report 03). |
| Unexpected categorical values | `match_status` ∈ {matched, not_found, needs_review}; `collection_status` identical; `ticket_status` ∈ {found, needs_review, not_found}; `tickets_basis` ∈ {cumulative, partial_or_uncertain}; `match_reason` ∈ {auto, below_threshold, no_candidates, ambiguous_or_low_confidence}. All documented in code. |
| Empty strings / whitespace-only | No whitespace-only values. `tickets_sold_web.csv.title_bovn` uses the literal string `"nan"` in 10 rows (an artifact of `pd.read_csv(...).where(pd.notna, None)` not being applied to that column downstream). `error` is an empty string in all 92 rows rather than null. |
| Mixed unit representations | Confirmed: `revenue_doanhthuphim` is rounded text ("714 tỷ", "hơn 21 tỷ", "8,7 Tỷ"); `revenue_bovn` is exact VND text ("714,030,584,098₫"). `full_export.revenue` mixes both formats in one column. |
| Other text quality | `genre` holds unnormalized comma-separated multi-values (62 distinct strings). `director` has trailing/embedded formatting in some records (e.g. row 13 BOV raw shows `Director:` blank). |

---

## 2.D Consistency

1. **Release date vs release year:** no CSV contains a full release date. In the state file, `bov_release_info` exists but is polluted with page boilerplate (login/menu text and "You may also like…" recommendation dates). Comparing the first 4-digit year in that field to `release_year`: 68 agree, **13 disagree**, 11 have no year. Examples of large gaps: row 32 `Em Chưa 18` 2017 vs 2025, row 91 `Dòng Máu Anh Hùng` 2007 vs 2025, row 43 `Siêu Lừa Gặp Siêu Lầy` 2023 vs 2019, row 78 `Cô Ba Sài Gòn` 2017 vs 2019 (the 2019 is actually a recommendation-block date). Some small gaps are legitimate international-vs-Vietnamese release dates (e.g. row 11 `Avatar` 2022 vs 2025). **Conclusion: the BOV release field is not reliable as stored, and no clean release-date column exists.**

2. **Titles across sources:** 82/92 rows have `title_bovn`; in 8 of those it differs from `movie_name`:
   - Row 7 `Thỏ Ơi!!` → `Thỏ Ơi` (punctuation only — benign)
   - Row 10 `Avengers: Hồi Kết (Endgame)` → `Avengers: Hồi Kết` (alternate title dropped — benign)
   - Row 42 `Heo 5 Móng` → `Heo Năm Móng` (digit/word normalization — benign)
   - Row 47 `Cám` → `CÁM`, row 49 `Tài` → `TÀI` (case only — benign)
   - Row 80 `Gái Già Lắm Chiêu V: ...` → `Gái Già Lắm Chiêu V – ...` (punctuation — benign)
   - **Row 51 `Chị Mười Ba: 3 Ngày Sinh Tử` → `Chị Mười Ba 2: 3 Ngày Sinh Tử`** (different sequel number — *potential wrong film*, auto-matched at 100)
   - **Row 84 `Kính Vạn Hoa: Phim Điện Ảnh` → `Kính Vạn Hoa: Bắt Đền Con Ma`** (different subtitle — correctly flagged `needs_review` at 83.25)
   Vietnamese and English titles are mixed in `movie_name` without a language flag; `original_title` is unusable (2/92, and both values are not true original titles — see report 01 §1.6).

3. **Revenue units and currency:** DTP values are rounded to billions ("tỷ") with inconsistent casing and sometimes hedged ("hơn 21 tỷ"); BOV values are exact VND with `₫`. Parsed with the project's own parser: DTP range 1,000,000,000–714,000,000,000 VND; BOV range 4,600,000–714,030,584,098 VND. **21/81 matched records (25.93%) differ by >10%** (see report 03 §3.4). `full_export.revenue` silently prefers BOV in all 81 cases, so it inherits every conflict.

4. **Ticket/screening semantics:** `tickets_sold` and `screening_count` mean "publicly displayed on the matched BOV page" by design, but both columns are 100% empty. Web-derived tickets are described as `cumulative` for 5 records based on keyword cues in headlines — not verified final totals. No screening counts are available from any source, so "ticket count ÷ screening count" style metrics cannot be computed.

5. **Conflicting values across datasets:** no conflicts between `movies.csv`, `collection_log.csv`, `unmatched_movies.csv` and `tickets_sold_web.csv` on shared fields (statuses agree on all 92 rows; join keys unique). The only material cross-source conflict is the DTP-vs-BOV revenue disagreement propagated into `full_export.csv` (21 records).

---

## 2.E Outlier detection

### Revenue (`revenue_bovn` parsed to VND, n = 81)

| Percentile | VND |
|---:|---:|
| 0 | 4,600,000 |
| 5 | 70,305,000 |
| 25 | 58,822,235,555 |
| 50 | 113,230,498,221 |
| 75 | 172,745,666,799 |
| 95 | 459,587,516,927 |
| 100 | 714,030,584,098 |

IQR bounds: Q1 = 58.82bn, Q3 = 172.75bn, upper fence = 343.63bn → **7 high outliers**, all plausible blockbusters: row 2 `Mưa Đỏ` 714.0bn, row 3 `Mai` 551.2bn, row 4 `Trại Buôn Người` 496.4bn, row 5 `Lật Mặt 7` 482.7bn, row 6 `Nhà Bà Nữ` 459.6bn, row 7 `Thỏ Ơi!!` 449.9bn, row 8 `Bố Già` 395.1bn. **These are legitimate extremes**, corroborated by DTP rounded values (714 tỷ, 551 tỷ, etc.).

The more serious anomalies are at the **low end**: 6 records where BOV and DTP differ by more than 10× (5 BOV values roughly 900×–4,350× smaller than DTP; 1 BOV value 14.4× larger). These are not IQR outliers in the BOV distribution alone, but are clear cross-source outliers (report 03 §3.4).

### Web ticket counts (n = 16)

Percentiles: min 4,000; 25th 53,750; median 380,000; 75th 2,375,000; 95th 8,325,000; max 9,000,000. IQR upper fence = 5,856,875 → 2 outliers:
- Row 2 `Mưa Đỏ` 8,100,000 — plausible for the highest-grossing film; supported by a Kenh14 headline and snippet (`ticket_status=found`, confidence 70). **Likely legitimate.**
- Row 22 `Exhuma: Quật Mộ Trùng Ma` 9,000,000 — `ticket_status=needs_review`, confidence 40, evidence "cán mốc 9 triệu vé" from a magazine; **suspicious/unverified** and correctly excluded from the export.

### Release years
Range 2007–2026, median 2024. 21 records (22.83%) are labelled 2026 (current year). No impossible years. Distribution is heavily right-skewed toward recent releases, as expected for a box-office ranking, but the sampling frame (all available DTP records) is not documented, so it should not be treated as a representative sample.

### Ratings / runtime / other numerical fields
No rating, runtime, budget, vote count or screening-count values exist, so no outlier analysis is possible. Frequency analysis of categorical fields is reported in §2.C and in report 03.

---

## 2.F Aggregate issue rate

| Definition | Records | Share of 92 |
|---|---:|---:|
| ≥1 **core** issue (match not accepted, revenue conflict >10%, no BOV revenue, no director, or uncertain ticket evidence) | **42** | **45.65%** |
| Clean under the core definition | 50 | 54.35% |
| ≥1 issue **including** missing `original_title` (broad definition) | 91 | 98.91% |

Contributing counts (overlapping): revenue conflict 21, uncertain ticket evidence 11, no BOV revenue 11, `not_found` 10, no director 3, `needs_review` 1. The broad 98.9% figure is driven almost entirely by the practically-unpopulated `original_title` field and should not be read as "99% of rows are unusable"; the core figure of **45.7%** is the defensible headline.

**Verdict for this section:** no duplicate keys or malformed records, but roughly half the records carry a material quality issue, two columns are 100% empty across all datasets, and the final export contains unreconciled cross-source revenue conflicts.
