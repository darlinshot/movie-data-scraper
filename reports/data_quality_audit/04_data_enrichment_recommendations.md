# 04 — Data Enrichment Recommendations

**Guiding principle:** fix trustworthiness of existing fields before adding new ones. Adding ratings or budgets to a dataset whose revenue scope and match identity are unresolved would amplify, not reduce, analytical error. Priorities assume a small research/personal-use project with no paid API budget.

## 4.1 Current coverage of candidate fields

| Field | Currently available? | Where / coverage |
|---|---|---|
| Movie name (Vietnamese/display) | Yes | 92/92 |
| Alternate/original title | **No (effectively)** | 2/92 and both values are not true original titles |
| Release year | Yes (year only) | 92/92 |
| Full release date (day/month/year) | No | Only polluted `bov_release_info` in state JSONL |
| Genre | Yes (raw) | 92/92, 62 different comma-separated strings |
| Director | Partial | 89/92 |
| Revenue (DTP rounded) | Yes | 92/92 |
| Revenue (BOV exact) | Partial | 81/92, 21 conflicting with DTP |
| Tickets sold | No | 0/92 from BOV; 5/92 heuristic web-derived in export |
| Screening count | No | 0/92 |
| Rating / vote count / runtime / budget / country / language / cast / distributor | **No** | No such columns exist anywhere |

---

## 4.2 Prioritized recommendations

"Obtainable from existing source" means from DTP or BOV pages already targeted by this repository (subject to their terms), not from new HTTP requests during this audit.

### P0 — needed to make current data usable (not optional)

| Field | Why useful | Already available? | From existing source? | Potential source | Essential / optional | Concerns |
|---|---|---|---|---|---|---|
| **Canonical `movie_id` + all source URLs** | Only stable way to join datasets and de-duplicate across exports; `full_export.csv` currently has no key | Partial (DTP URL exists, but dropped in export) | Yes | Existing `source_url_doanhthuphim` / BOV slug | **Essential** | None |
| **Revenue amount, numeric VND + raw string + `revenue_scope` (cumulative/daily/weekly) + `as_of_date` + `source`** | Resolves the 21 conflicts and the 6 extreme mismatches; prevents daily values being used as cumulative | Partially (two raw strings) | Yes, but extraction logic must be fixed and raw page text retained | DTP detail page + BOV `Doanh số` block | **Essential** | Must respect site terms; cache raw snippet for auditability |
| **Match provenance: `match_status`, `match_score`, `match_reason`, `review_status`, `reviewed_at`, `reviewer`** | Distinguishes auto-accepted from human-checked; needed to quarantine rows 51/32/84 | Partial (score/reason in `collection_log.csv` only) | Yes | Existing matcher + manual review | **Essential** | Manual review is a process change, not a data source |
| **Full release date as ISO `YYYY-MM-DD`** | Needed for time-series, cohort analysis, and verifying year consistency; 13 year disagreements exist | No | Yes (DTP `Khởi chiếu:` / BOV release line) | DTP / BOV detail pages | **Essential** | Parse carefully; BOV page text is polluted — store raw line |

### P1 — high analytical value, feasible

| Field | Why useful | Already available? | From existing source? | Potential source | Essential / optional | Concerns |
|---|---|---|---|---|---|---|
| **Original title + alias list** (Vietnamese, English, alternate) | Prevents false positives like `Chị Mười Ba` 2 vs 3 and improves future matching | No (2/92, invalid) | Partially (parenthetical on DTP, BOV `<title>`) | DTP detail, BOV page, TMDb | Important | Multilingual normalization required |
| **Tickets sold with `source`, `scope`, `as_of_date`, evidence URL/snippet** | Enables attendance analysis; current 5 accepted values are point-in-time headlines | No (0/92 official; 5 heuristic) | Partially (BOV premium data not public; news RSS) | BOV (if public), news articles, official distributor releases | Important | News snippets are unverified; premium BOV fields must not be bypassed |
| **Screening count** | Denominator for per-screening yield and efficiency analysis | No (0/92) | Only if publicly displayed; currently filtered as placeholder | BOV public page | Important | Premium-only placeholder `888888` observed by code; do not infer |
| **Genre normalized into a controlled vocabulary / link table** | 62 raw strings for 92 movies; current form is not groupable | Raw only | Yes | DTP genre + TMDb genres | Important | Mapping choices introduce analyst subjectivity |
| **Runtime (minutes)** | Strong control variable for screening capacity and revenue models | No | Not from current sources | TMDb / IMDb | Important | License attribution required for TMDb |
| **Original language + production country** | Distinguishes domestic vs imported films; confounders in box-office comparisons | No | Partially (BOV page shows `Country`, `Language` but often blank) | BOV, TMDb | Important | BOV fields frequently blank in cached text |
| **Director normalized** | 89/92 present but unnormalized (50 distinct strings) | Partial | Yes | DTP + TMDb | Important | Name variants/diacritics |

### P2 — optional enhancements (only after P0/P1 are closed)

| Field | Why useful | Already available? | From existing source? | Potential source | Essential / optional | Concerns |
|---|---|---|---|---|---|---|
| **IMDb rating + vote count** | Audience-quality control variable; vote count indicates reliability | No | No | IMDb / OMDb / TMDb | Optional | Licensing/restrictions; rating scale must be stored explicitly (1–10) and never confused with `match_score` |
| **TMDb rating + vote count** | Broader international coverage, especially for non-Vietnamese titles | No | No | TMDb API | Optional | Attribution required; API key; different audience from IMDb |
| **Production budget** | Core feature for revenue prediction and ROI | No | No | TMDb (sparse), news, industry reports | Optional (essential *only* for ROI/prediction) | Coverage poor, figures often estimates and currency-mixed |
| **Distributor** | Explains release width and marketing spend | No | Partially (BOV `Production Co`, often blank) | BOV, press kits, TMDb | Optional | Inconsistent naming |
| **Domestic box office revenue** | Clarifies what DTP/BOV figures actually measure | Implicit (both appear domestic VN) | Yes but unlabeled | DTP/BOV with explicit `market='VN'` | Optional but recommended | Avoid mislabeling as worldwide |
| **Worldwide box office revenue** | Enables international comparison | No | No | TMDb / Box Office Mojo (not for current target sites) | Optional | Coverage skewed to Hollywood titles; licensing |
| **Daily/weekly revenue history** | Enables trend, opening-weekend and decay analysis; would also resolve the cumulative-vs-daily ambiguity | No | BOV shows daily tables if public | BOV public pages (respect terms) | Optional | Increased crawl load; strict rate limiting required |
| **Daily ticket sales** | Finest-grained demand signal | No | No | BOV public daily tables if available | Optional | Same access/load concerns |
| **Cast** | Popularity/control variable for ML | No | No | TMDb | Optional | Large schema; many-to-many relation |
| **Cinema release information** (screen count, release width) | Needed to interpret per-screen performance | No | Not reliably | Distributor announcements, BOV | Optional | Sparse, unstructured |

---

## 4.3 Recommended acquisition sequence

1. **Do not add anything until P0 is fixed.** In particular, do not join IMDb/TMDb ratings onto uncertain matches (rows 51, 32, 84, 78) — that would launder a suspect match into a more authoritative-looking record.
2. Re-extract BOV revenue with the raw page text persisted, and label scope explicitly (`cumulative` vs `daily`/`weekly` vs `unknown`). Reconcile the 21 conflicts against DTP; do not auto-prefer either source.
3. Add `review_status` and complete the six-item review list in report 03 §3.9.
4. Add normalized release date, alias list and controlled-vocabulary genre.
5. Then, if a modelling use case is confirmed, add runtime, country/language and ratings with source + `as_of_date`.

## 4.4 Licensing and reliability caveats

- TMDb data requires attribution and an API key; IMDb/OMDb have separate terms and rate limits. Neither was queried in this audit.
- News-derived ticket figures are *evidence*, not verified facts: keep the original snippet, URL, publication timestamp and a `confidence` value, and never convert revenue to ticket counts.
- BOV premium fields (e.g. placeholder `888888` referenced in `scrape_boxofficevietnam.py`) must remain empty unless legitimately accessible; do not infer or reverse-engineer them.
- All sources have terms of use; the repository README notes the RSS feeds are intended for personal, non-commercial feed-reader use. Respect these before any redistribution or commercial BI use.
