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
