# Task: Build an Automated Vietnamese Box Office Data Collector

This is a small Python project that collects movie information from:

1. https://doanhthuphim.vn/tong-hop
2. https://v1.boxofficevietnam.com/

## Objective

Automate the process of collecting movie records from DoanhThuPhim and matching them with their corresponding Box Office Vietnam pages.

The final output should be a CSV file that can be used for a data visualization project.

## Requirements

### 1. Collect the movie list

- Open the DoanhThuPhim summary page.
- Extract all available movie records, not just the initially visible 15 records.
- Handle the "Show more" button or other pagination mechanisms.
- Collect movie names, detail page URLs, release years, genres, directors, and displayed revenue information when available.
- Preserve the original movie names.

### 2. Match movies on Box Office Vietnam

- Search for each movie on Box Office Vietnam.
- Find the corresponding movie detail page.
- Extract available cumulative box office revenue, tickets sold, release information, and screening statistics.
- Do not confuse daily or weekly revenue with cumulative revenue.
- Do not invent missing values.
- If a movie cannot be found, mark it as `not_found`.

### 3. Data matching

- Normalize movie names for matching.
- Handle Vietnamese and English titles, subtitles, punctuation, and alternate titles.
- Use fuzzy matching only to suggest possible matches.
- Store the original names from both websites.
- Mark uncertain matches as `needs_review` instead of automatically accepting them.

### 4. Output

Generate:

- `movies.csv`: consolidated movie dataset.
- `unmatched_movies.csv`: movies without a reliable Box Office Vietnam match.
- `collection_log.csv`: collection status and source URLs.

Suggested columns:

- movie_name
- original_title
- release_year
- genre
- director
- revenue_doanhthuphim
- revenue_bovn
- tickets_sold
- screening_count
- source_url_doanhthuphim
- source_url_bovn
- match_status
- collection_status

### 5. Technical requirements

- Use Python and Playwright.
- Use pandas for data processing.
- Use a modular project structure.
- Add retry handling and reasonable delays between requests.
- Save progress incrementally so interrupted runs can resume.
- Avoid aggressive crawling and respect website terms and access restrictions.
- Do not bypass CAPTCHAs, login restrictions, or paid access controls.

### 6. Important

Before implementing the full collector:

1. Inspect both websites.
2. Determine how pagination and movie detail pages work.
3. Test the extraction process on 5 movies.
4. Show the extracted results and verify that the revenue fields are correct.
5. Only then implement the full collection process.

Do not assume that all movie records have corresponding Box Office Vietnam records.