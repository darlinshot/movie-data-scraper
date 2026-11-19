# Movie Data Collector

Collects Vietnamese box office data from:

- [DoanhThuPhim](https://doanhthuphim.vn/tong-hop) — movie list, detail pages, cumulative revenue.
- [Box Office Vietnam](https://v1.boxofficevietnam.com/) — matched movie pages, cumulative `Doanh số`, tickets/screenings when publicly available.

Outputs:

- `data/movies.csv` — consolidated dataset.
- `data/unmatched_movies.csv` — movies without a reliable match (`not_found` / `needs_review`).
- `data/collection_log.csv` — per-movie collection/match status and source URLs.
- `data/tickets_sold_web.csv` — evidence-based ticket counts found on public web sources,
  with source URL, headline, snippet, and status.
- `data/full_export.csv` — final review-friendly CSV with `to_review_<field>` columns
  pointing to sources for fields that need manual checking.
- `data/filtered/2020_2026_checkpoint2_core_plus_bovn_discovery.csv` — checkpoint 2
  plus discovered BoVN movies; keeps the six checkpoint columns and appends only
  `to_review_director` / `to_review_revenue` for required-field backfills.

## Setup

```bash
uv sync
.venv/bin/playwright install chromium
```

## Usage

```bash
# Inspect both websites (pagination/detail/search structure)
.venv/bin/python scripts/inspect_sites.py

# Small test run (required 5-movie verification)
.venv/bin/python -m movie_data_collector.cli test --limit 5 --no-resume

# Full collection (resumable)
.venv/bin/python -m movie_data_collector.cli full

# Full collection, ignoring saved progress
.venv/bin/python -m movie_data_collector.cli full --no-resume

# Retry only records marked not_found / needs_review
.venv/bin/python -m movie_data_collector.cli rematch

# Only collect DoanhThuPhim records
.venv/bin/python -m movie_data_collector.cli collect-dtp

# Search the web for cumulative ticket counts (standalone script)
.venv/bin/python scripts/search_tickets_web.py --limit 5 --no-resume

# Same command through the main CLI; Bing is tried first, Google is fallback
.venv/bin/python -m movie_data_collector.cli tickets-web --backend both

# Build the final combined export
.venv/bin/python -m movie_data_collector.cli export-full

# Merge checkpoint 2 with discovered BoVN movies (required-field backfill only)
.venv/bin/python -m movie_data_collector.cli consolidate-checkpoint2
```

Progress is saved incrementally to `state/doanhthuphim_movies.jsonl`,
`state/boxoffice_matches.jsonl`, and `state/web_tickets_progress.jsonl`, so an
interrupted run resumes where it stopped.

## Notes

- Matching uses normalized titles, alternate/original titles, and fuzzy scoring.
  Ambiguous matches are marked `needs_review`; movies that cannot be found are
  marked `not_found`.
- Only cumulative revenue is recorded from Box Office Vietnam (`Doanh số`).
  Daily/weekly figures are never used as cumulative totals.
- Missing or masked values (for example premium-only ticket/screening counts)
  are left empty rather than invented.
- The collector uses retries, random delays, and does not bypass CAPTCHAs, login
  restrictions, or paid/premium content.
- The web ticket search reads public Bing/Google News RSS headlines and snippets,
  keeps the source URL and evidence text, and marks ambiguous figures as
  `needs_review`. It never converts revenue into ticket counts. These feeds are
  intended for personal, non-commercial feed-reader use; check each provider's
  terms before using the results commercially.

## Discover more movies (Box Office Vietnam search)

DoanhThuPhim only lists 92 films in total, so theatrical releases
outside that list (notably anime) are discovered by searching
Box Office Vietnam directly:

```
.venv/bin/python -m movie_data_collector.cli discover-bovn --seed-file seeds/bovn_anime_seed.txt
```

- Seed file: one search query per line. Use short keywords, not full
  titles: BoVN search often returns "No Movie Found" for a full title.
- Output: `data/bovn_discovered.csv` (one row per BoVN movie URL) and
  progress in `state/bovn_discovered.jsonl`. `data/movies.csv` is not
  touched by this command.
- Revenue is only filled when the BoVN detail page loads. If a detail
  page returns 502, the row is kept with `detail_status=bovn_detail_502`
  and empty revenue, to be backfilled later. No revenue is invented.
- Search hits that do not match the query are dropped, because BoVN
  search pages also list unrelated movies.

## Press revenue fallback (for discovered movies with no BoVN revenue)

When a BoVN detail page returns 502, the revenue stays empty in
`data/bovn_discovered.csv`. A press figure can be added as a fallback,
in a separate file, never overwriting `revenue_bovn`:

```
.venv/bin/python -m movie_data_collector.cli press-revenue
```

- Output: `data/bovn_discovered_press.csv`, progress in
  `state/bovn_press.jsonl`.
- `seeds/bovn_press_seed.json` holds press figures a human verified
  from articles, with source URL, published date, snippet and a note
  on the range or uncertainty. The command uses the seed first.
- Films with no seed entry are searched in public news RSS feeds
  (Bing / Google), the same way `tickets-web` searches for ticket
  counts. A figure is only accepted when the snippet itself names
  this film (subtitle or number), so a franchise article about
  another film cannot be recorded for this one.
- Every press row has `to_review_revenue=needs_review`, even when
  the search is confident. A press figure is evidence, not a BoVN
  exact total. Two seed figures are lower bounds only
  (`revenue_press_is_lower_bound=true`): Doraemon Movie 45
  (over 203.5 ty as of 2026-06-26) and Doraemon 2021
  (over 48 ty).

## Checkpoint 2 consolidation

`consolidate-checkpoint2` keeps checkpoint 2 untouched and writes a second file
in `data/filtered/`. It appends BoVN-discovered rows that are not already in
checkpoint 2, and fills only missing `director` and `revenue`:

- Exact `revenue_bovn` always wins. The press display text is used only when
  BoVN revenue is empty, and is marked `needs_review` with its article URL.
  Press values are never converted into precise-looking VND totals.
- Missing directors are taken from the public Wikipedia infobox, with the page
  URL stored in `to_review_director`. No other column is crawled or reviewed.
- One discovered title (`Doraemon: Nobita và Mặt Trăng Phiêu Lưu Ký`) is from
  2019. It is retained as-is because no year filter was requested; filter it out
  if a strict 2020–2026 range is required.
