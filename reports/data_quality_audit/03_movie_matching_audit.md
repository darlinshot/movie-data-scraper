# 03 — Movie Matching Audit

This report examines the reliability of the DoanhThuPhim (DTP) → Box Office Vietnam (BOV) matching, the web ticket evidence, and the provenance available for manual review. All findings are based on the local CSVs, the three state JSONL files and the source code (`matching.py`, `pipeline.py`, `scrape_boxofficevietnam.py`, `search_tickets_web.py`, `full_export.py`). **No website was contacted.**

---

## 3.1 Match-status distribution

| Status | `movies.csv` | `collection_log.csv` | `unmatched_movies.csv` |
|---|---:|---:|---:|
| `matched` | 81 (88.04%) | 81 | 0 |
| `needs_review` | 1 (1.09%) | 1 | 1 |
| `not_found` | 10 (10.87%) | 10 | 10 |

`unmatched_movies.csv` contains exactly the 11 non-`matched` records; `collection_status` mirrors `match_status` for all 92 rows.

Match scores (`collection_log.csv`, n = 92):

| Score band | Count | Interpretation |
|---|---:|---|
| exactly 100.0 | 80 | Exact normalized-title match (with or without year bonus; capped at 100) |
| 92.0–99.9 | 1 | Auto-accepted below exact (`Em Chưa 18`, 94.0) |
| 80.0–91.9 | 1 | `needs_review` (`Kính Vạn Hoa…`, 83.25) |
| < 80 | 10 | `not_found` |

`match_reason`: `auto` 81, `below_threshold` 9, `no_candidates` 1, `ambiguous_or_low_confidence` 1.

**Manual vs automatic review:** `match_reason` distinguishes the matching algorithm's decision path, but **no field records a human review outcome** (no `reviewed_by`, `reviewed_at`, `review_decision`). `full_export.csv` drops `match_score` and `match_reason` entirely; its `to_review_*` columns are *pointers to sources*, not evidence that a review happened. A reviewer cannot tell from `full_export.csv` alone whether the single `needs_review` record was ever checked.

---

## 3.2 How the matcher works (as implemented)

- `_candidate_strings()` collects `movie_name`, `original_title`, `detail_title`, `bov_title_hint`, plus titles split on ` / `, ` | ` or a trailing `(English)` parenthetical.
- `score_pair()` computes `max(token_sort_ratio, ratio)` and a length-penalized `token_set_ratio` (`rapidfuzz`), with:
  - exact normalized equality → 100;
  - **digit-to-word normalization** (`5 → nam`, `10 → muoi`) and accent stripping;
  - a **−35 penalty when different sequel numbers are detected** by `_sequel_digits()`;
  - **+4** when the source release year appears in the candidate context, **−6** when a different year appears.
- `choose_best_match()` auto-accepts at `score ≥ 92` with a ≥3-point margin over the runner-up (or exact title + matching year), flags 80–91.99 as `needs_review`, and marks below 80 as `not_found`.
- Up to 6 search-query variants are generated per movie (original title, word/number variants, pre-colon prefix, parenthetical alternate title).

Thresholds are from `config.py`: `AUTO_MATCH_THRESHOLD = 92`, `REVIEW_THRESHOLD = 80`.

---

## 3.3 Fuzzy-matching false-positive risk — confirmed weaknesses

### (a) Different instalment auto-accepted at score 100 — **confirmed algorithmic blind spot**

**Row 51** `Chị Mười Ba: 3 Ngày Sinh Tử` (DTP, 2020, `.../chi-muoi-ba-3-ngay-sinh-tu`) was matched at **100.0** to BOV **`Chị Mười Ba 2: 3 Ngày Sinh Tử`** (`.../movie/chi-muoi-ba-2-3-ngay-sinh-tu/`), status `matched`.

Root cause visible in code: `_sequel_digits()` takes the **last** 1–2 digit number in the string. For `Chị Mười Ba: 3 Ngày Sinh Tử` the only number is `3`; for `Chị Mười Ba 2: 3 Ngày Sinh Tử` the numbers are `2` and `3`, so it also returns `3`. The intended −35 sequel penalty therefore never fires, and the token-set/length-penalized score reaches 100. The two titles refer to different instalment numbering. **This record should be re-reviewed; it is a likely false positive.**

### (b) Title mismatch with a near-threshold score — **correctly flagged**

**Row 84** `Kính Vạn Hoa: Phim Điện Ảnh` (DTP, 2024) → BOV `Kính Vạn Hoa: Bắt Đền Con Ma`, score **83.25**, `needs_review`, `.../movie/kinh-van-hoa-bat-den-con-ma/`. Different subtitle; the uncertain status is appropriate, but the record still carries BOV revenue (`6,046,923,245₫`) that `full_export.csv` uses as its `revenue`. An uncertain match should not silently supply a headline metric.

### (c) Large release-year gap auto-accepted — **potential wrong-page match**

**Row 32** `Em Chưa 18` (DTP year **2017**) → BOV `Em Chưa 18`, score **94.0**, `matched`, `.../movie/em-chua-18/`. The cached `bov_release_info` starts `2025-06-24`, eight years later. The −6 year penalty was insufficient to prevent auto-acceptance (score 94 ≥ 92). Combined with BOV revenue of only `70,305,000₫` vs DTP `171 tỷ` (0.04%), this page may represent a different release/record. **Potential problem; requires manual verification against the live page (not performed in this audit).**

### (d) Duplicate-looking BOV page — **potential problem**

**Row 78** `Cô Ba Sài Gòn` (2017) → BOV URL `.../movie/co-ba-sai-gon-2/`, score 100, `matched`. The `-2` slug suggests a duplicate/alternate page; `bov_release_info` contains no release date and is polluted with "You may also like..." dates. BOV revenue `65,995,000₫` vs DTP `60 tỷ` (0.11%).

### (e) Benign title differences

Rows 7, 10, 42, 47, 49 and 80 differ only by punctuation, case, digit/word form or dropped parenthetical alternate title. These appear to be **correct** matches.

**Conclusion:** the 80 perfect scores are mostly reliable (exact normalized titles), but the "exact" score can mask semantic differences (sequel numbers, subtitles). Fuzzy matching was used as the *deciding* mechanism, not merely to suggest matches: 81 records were auto-accepted. At least one (row 51) is a probable false positive and one (row 32) is highly suspicious.

---

## 3.4 Cumulative vs daily/weekly revenue confusion — **confirmed conflict, root cause not verifiable locally**

- BOV detail extraction (`scrape_boxofficevietnam.py`) searches the page body for `Doanh số …₫`, falling back to `Tổng doanh thu`/`Doanh thu tích lũy`. It intentionally avoids daily/weekly figures, and `full_export.py` prefers the BOV value over DTP.
- In practice, **21 of 81 matched records (25.93%)** have BOV vs DTP revenue differing by >10% after parsing both to VND with the project's own parser:

| Band | Count |
|---|---:|
| Within 10% | 60 |
| 1.1×–10× larger than DTP | 5 |
| 10–90% of DTP | 10 |
| < 1% of DTP (≥100× smaller) | 5 |
| > 10× larger than DTP | 1 |

Six extreme cases (all propagated into `full_export.revenue`):

| Row | Movie | DTP | BOV | BOV/DTP |
|---:|---|---|---|---:|
| 32 | Em Chưa 18 | 171 tỷ | 70,305,000₫ | 0.0004 |
| 65 | Tháng Năm Rực Rỡ | 85 tỷ | 26,375,000₫ | 0.0003 |
| 76 | Tấm Cám: Chuyện Chưa Kể | 66,5 tỷ | 15,080,000₫ | 0.0002 |
| 78 | Cô Ba Sài Gòn | 60 tỷ | 65,995,000₫ | 0.0011 |
| 91 | Dòng Máu Anh Hùng | 10 tỷ | 4,600,000₫ | 0.0005 |
| 93 | Ramayana: Khởi Nguồn Một Huyền Thoại | 1 tỷ | 14,436,804,197₫ | 14.44 |

`full_export.revenue` equals the BOV string for all 81 rows where BOV revenue exists, and the DTP string only for the 11 rows without BOV revenue. Therefore **the final export systematically prefers the conflicting BOV figure**, including all six extreme cases.

**Limitations of the evidence:** the BOV scraper returns a `raw_body_snippet`, but `pipeline.py` does **not** persist it; `_bov_detail_raw` is empty in all 92 state records. Consequently we can confirm the *conflict* but **cannot confirm from local evidence** whether those small BOV numbers are daily values, a per-screening price, a stale snapshot, or a genuine different-scope total. For row 2 (`Mưa Đỏ`) BOV 714,030,584,098₫ matches DTP 714 tỷ, so the field *can* hold cumulative revenue; the small values are likely a scope/parse problem, but that remains a **potential**, not confirmed, root cause.

---

## 3.5 Original and alternate titles

- `original_title` is populated in only 2/92 rows:
  - Row 10 `Avengers: Hồi Kết (Endgame)` → `Endgame` (only the parenthetical fragment; the true original title is not stored).
  - Row 72 `Lật Mặt (Lật Mặt 1)` → `Lật Mặt 1` (franchise numbering, not an original-language title).
- `movie_name` mixes Vietnamese and English titles with no language indicator (e.g. row 11 `Avatar: Dòng Chảy Của Nước`, row 22 `Exhuma: Quật Mộ Trùng Ma`, row 92 `Clayface`).
- The matcher reads `original_title`, `detail_title` and split parentheticals, so the *matching* logic does use alternate strings, but the *stored* `original_title` field is not a dependable alternate-title index.

---

## 3.6 Different releases merged / incorrectly matched

- No two DTP records share a normalized title, so the pipeline did not merge two source rows into one.
- However, cross-source release-year disagreements were found in **13 of 81 matched rows** where the cached BOV text contained a year (68 agree, 11 no year). Examples: rows 5, 11, 22, 32, 39, 40, 43, 47, 55, 78, 79, 88, 91 (full list in report 02 §2.D). The `bov_release_info` field is polluted with boilerplate and recommendation-block dates, so these figures are **weak evidence**; they nevertheless indicate that several BOV pages may correspond to re-releases or different records (especially rows 32 and 91).
- The 10 `not_found` movies are: `Siêu Sao Siêu Ngố`, `Em Là Bà Nội Của Anh`, `Để Mai Tính 2`, `Lật Mặt: Ba Chàng Khuyết`, `Quả Tim Máu`, `Lật Mặt 2: Phim Trường`, `Tôi Thấy Hoa Vàng Trên Cỏ Xanh`, `Lật Mặt (Lật Mặt 1)`, `Mỹ Nhân Kế`, `Song Lang`. Several are franchise entries. **No assumption is made that a corresponding BOV page exists** — `not_found` may be correct. This could not be verified without new HTTP requests, which were prohibited.

---

## 3.7 Ticket-count evidence quality

- `tickets_sold` in `movies.csv` is **empty for all 92 rows** — the BOV page never yielded an accepted ticket count (premium placeholders such as `888888` are filtered by code).
- `tickets_sold_web.csv` contains 16 candidates: 5 `found`, 11 `needs_review`. Every one has a source URL, source name, published timestamp, display string and snippet.
- `full_export.tickets_sold` contains only the 5 `found` values:

| Row | Movie | Tickets | Confidence | Evidence source |
|---:|---|---:|---:|---|
| 2 | Mưa Đỏ | 8,100,000 | 70 | Kenh14 (direct article URL), snippet with "Tính đến sáng 28/9" |
| 29 | Tiệc Trăng Máu | 2,000,000 | **55** | Google News RSS redirect → Báo VietNamNet; headline-only snippet |
| 43 | Siêu Lừa Gặp Siêu Lầy | 360,000 | 70 | Google News RSS redirect → Laodong.vn; headline-only snippet |
| 67 | Bẫy Ngọt Ngào | 1,000,000 | **55** | Vietnamnet (direct article URL), snippet with "cán mốc 1 triệu vé" |
| 71 | Cô Dâu Hào Môn | 350,000 | 70 | Google News RSS redirect → SOHA; headline-only snippet |

Assessment:
- The two confidence-55 records pass `_is_confident()` only because the threshold is inclusive (`>= 55`); their evidence is a **headline/snippet at article time**, not a verified final cumulative figure. `tickets_basis='cumulative'` is assigned by keyword cues, not confirmed by a source stating a final total.
- Even the strongest case (`Mưa Đỏ`, 8.1M as of 28/09/2025) is a **point-in-time milestone**, not necessarily the final cumulative count.
- Three of five URLs are Google News RSS redirect links rather than publisher URLs, reducing direct verifiability.
- **False-positive candidate that was correctly quarantined:** row 49 `Tài` — the 4,000 "khán giả" candidate comes from a headline about singer Mỹ Tâm and Mai Tài Phến ("...trước sự chứng kiến của 4.000 khán giả"), matched via the short alias `Tài`. It is `needs_review` (confidence 55) and correctly excluded from `full_export.tickets_sold`.
- Other `needs_review` values that were correctly excluded include row 22 `Exhuma` 9,000,000, row 8 `Bố Già` 5,600,000 and row 4 `Trại Buôn Người` 3,500,000.

**Conclusion:** ticket figures have evidence links and are better than bare guesses, but they are **not trustworthy as final cumulative ticket counts**. Only 5/92 movies have an accepted figure, and evidence ranges from a dated news snippet to an RSS headline.

---

## 3.8 Evidence and provenance availability

| Provenance item | Available locally? | Where |
|---|---|---|
| DTP source URL | Yes, 92/92 | `movies.csv`, `collection_log.csv`, state |
| BOV source URL | Yes, 82/92 | `movies.csv`, `collection_log.csv`, state |
| Fuzzy score and reason | Yes, 92/92 | `collection_log.csv`, state (dropped in `full_export.csv`) |
| Candidate BOV search result (`_bov_candidate`) | 82/92 | `state/boxoffice_matches.jsonl` |
| Raw BOV page body / evidence snippet for revenue | **No** | `raw_body_snippet` is returned by scraper but never persisted; `_bov_detail_raw` empty in all 92 state rows |
| Web ticket source URL + snippet | 16/92 | `tickets_sold_web.csv`, state |
| Web ticket search queries | 92/92 | `tickets_sold_web.csv` |
| Human review decision / reviewer / timestamp | **No** | no such field exists |

---

## 3.9 Priority review list (concrete examples)

| Row | Movie | Field values | Why suspicious |
|---:|---|---|---|
| 51 | Chị Mười Ba: 3 Ngày Sinh Tử | auto, score 100, BOV title `Chị Mười Ba 2: 3 Ngày Sinh Tử` | Different sequel number; `_sequel_digits` bug |
| 32 | Em Chưa 18 | auto, score 94, DTP 2017 vs BOV 2025-06-24, 171 tỷ vs 70,305,000₫ | Wrong-page / wrong-release risk + extreme revenue conflict |
| 84 | Kính Vạn Hoa: Phim Điện Ảnh | `needs_review`, 83.25, BOV `Kính Vạn Hoa: Bắt Đền Con Ma`, 45 tỷ vs 6,046,923,245₫ | Different subtitle; uncertain match still feeds export revenue |
| 78 | Cô Ba Sài Gòn | auto, 100, BOV slug `-2`, 60 tỷ vs 65,995,000₫ | Possible duplicate page + extreme revenue conflict |
| 93 | Ramayana: Khởi Nguồn Một Huyền Thoại | auto, 100, 1 tỷ vs 14,436,804,197₫ | BOV 14.4× larger; likely stale/partial DTP figure |
| 91 | Dòng Máu Anh Hùng | auto, 100, DTP 2007 vs BOV 2025, 10 tỷ vs 4,600,000₫ | Release-year gap + extreme revenue conflict |
| 49 | Tài | web ticket candidate 4,000 from unrelated artist headline | Evidence false positive (already quarantined) |

**Recommendation:** manually verify at minimum rows 51, 32, 84, 78, 93 and 91 against the source pages before any analytical use, and add a `review_status`/`reviewed_at` field so that reviewed and auto-accepted records are distinguishable.
