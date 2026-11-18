"""Authoritative schema, paths and approved counts for the movie analytics build.

This module is intentionally standard-library only. It contains no pandas import,
no transformation logic, no ID assignment, no revenue calculation and no file
writing. All analytical column names and their order are defined here once.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DATA_DIR: Final[Path] = PROJECT_ROOT / "data"
STATE_DIR: Final[Path] = PROJECT_ROOT / "state"

# Required build inputs.
MOVIES_CSV_PATH: Final[Path] = DATA_DIR / "movies.csv"
COLLECTION_LOG_CSV_PATH: Final[Path] = DATA_DIR / "collection_log.csv"
TICKETS_SOLD_WEB_CSV_PATH: Final[Path] = DATA_DIR / "tickets_sold_web.csv"
BOXOFFICE_MATCHES_JSONL_PATH: Final[Path] = STATE_DIR / "boxoffice_matches.jsonl"

REQUIRED_BUILD_INPUT_PATHS: Final[tuple[Path, ...]] = (
    MOVIES_CSV_PATH,
    COLLECTION_LOG_CSV_PATH,
    TICKETS_SOLD_WEB_CSV_PATH,
    BOXOFFICE_MATCHES_JSONL_PATH,
)

# Persistent build metadata. This is not an analytical CSV or Power BI input.
ID_MAP_JSON_PATH: Final[Path] = STATE_DIR / "analytics_movie_id_map.json"

# Final analytical output and the only Power BI input.
MOVIE_ANALYTICS_CSV_PATH: Final[Path] = DATA_DIR / "analytics" / "movie_analytics.csv"
ANALYTICAL_OUTPUT_PATHS: Final[tuple[Path, ...]] = (MOVIE_ANALYTICS_CSV_PATH,)
POWER_BI_INPUT_PATHS: Final[tuple[Path, ...]] = (MOVIE_ANALYTICS_CSV_PATH,)

# Audit-only files. These are not build inputs.
DTP_MOVIES_JSONL_PATH: Final[Path] = STATE_DIR / "doanhthuphim_movies.jsonl"
WEB_TICKETS_PROGRESS_JSONL_PATH: Final[Path] = STATE_DIR / "web_tickets_progress.jsonl"
UNMATCHED_MOVIES_CSV_PATH: Final[Path] = DATA_DIR / "unmatched_movies.csv"

AUDIT_ONLY_PATHS: Final[tuple[Path, ...]] = (
    DTP_MOVIES_JSONL_PATH,
    WEB_TICKETS_PROGRESS_JSONL_PATH,
    UNMATCHED_MOVIES_CSV_PATH,
)

# Deprecated/excluded file. This is not a build input.
FULL_EXPORT_CSV_PATH: Final[Path] = DATA_DIR / "full_export.csv"
DEPRECATED_EXCLUDED_PATHS: Final[tuple[Path, ...]] = (FULL_EXPORT_CSV_PATH,)

# Group A — Movie identity and metadata (§3.3).
GROUP_A_MOVIE_IDENTITY_COLUMNS: Final[tuple[str, ...]] = (
    "movie_id",
    "canonical_title",
    "original_title_raw",
    "release_year",
    "genre_raw",
    "genre_token_path",
    "genre_grouped",
    "director_raw",
    "director_norm_key",
    "source_url_dtp",
    "raw_source_row_dtp",
)

# Group B — Matching information (§3.4).
GROUP_B_MATCHING_COLUMNS: Final[tuple[str, ...]] = (
    "bov_match_status",
    "match_score",
    "match_reason",
    "bov_url",
    "bov_title_raw",
    "mapping_validation_status",
    "mapping_validation_reason",
    "mapping_human_reviewed",
    "mapping_reviewed_at",
    "mapping_reviewer",
    "review_status",
    "review_priority",
)

# Group C — Revenue by source (§3.5).
GROUP_C_REVENUE_COLUMNS: Final[tuple[str, ...]] = (
    "dtp_revenue_raw",
    "dtp_revenue_vnd",
    "dtp_revenue_quality",
    "bov_revenue_raw",
    "bov_revenue_vnd",
    "bov_revenue_quality",
    "bov_quarantined_revenue_raw",
    "bov_quarantined_revenue_vnd",
    "bov_candidate_revenue_raw",
    "bov_candidate_revenue_vnd",
    "revenue_gap_pct",
    "magnitude_gap_warning",
    "revenue_conflict_flag",
    "revenue_comparability_class",
    "comparability_reason",
    "revenue_scope_verified",
    "bov_evidence_available",
    "include_revenue_comparison",
    "include_revenue_eda",
    "revenue_eda_basis",
)

# Group D — Ticket information (§3.6).
GROUP_D_TICKET_COLUMNS: Final[tuple[str, ...]] = (
    "ticket_candidate_count",
    "ticket_found_count",
    "ticket_needs_review_count",
    "ticket_verified_admissions",
    "ticket_data_status",
    "ticket_context_status",
    "ticket_evidence_urls",
)

# Group E — Data quality (§3.7).
GROUP_E_DATA_QUALITY_COLUMNS: Final[tuple[str, ...]] = (
    "has_missing_core_data",
    "has_revenue_gap_warning",
    "has_pending_review",
    "data_quality_status",
)

FINAL_COLUMNS: Final[tuple[str, ...]] = (
    GROUP_A_MOVIE_IDENTITY_COLUMNS
    + GROUP_B_MATCHING_COLUMNS
    + GROUP_C_REVENUE_COLUMNS
    + GROUP_D_TICKET_COLUMNS
    + GROUP_E_DATA_QUALITY_COLUMNS
)

EXPECTED_COLUMN_COUNT: Final[int] = len(FINAL_COLUMNS)

# Grain and stable ID constants (§3.1, §8.1).
PRIMARY_KEY: Final[str] = "movie_id"
EXPECTED_MOVIE_COUNT: Final[int] = 92
ID_PREFIX: Final[str] = "M"
ID_DIGIT_WIDTH: Final[int] = 4
MOVIE_ID_PATTERN: Final[str] = r"^M\d{4}$"

# Approved expected counts (§2.4, §3.1, §4, §5).
MATCH_STATUS_EXPECTED_COUNTS: Final[dict[str, int]] = {
    "matched": 81,
    "needs_review": 1,
    "not_found": 10,
}

DTP_REVENUE_QUALITY_EXPECTED_COUNTS: Final[dict[str, int]] = {
    "rounded": 90,
    "lower_bound": 2,
}

STORED_BOV_REVENUE_OBSERVATIONS: Final[int] = 80
BOV_REVENUE_EXPECTED_COUNTS: Final[dict[str, int]] = {
    "valid": 79,
    "quarantined": 1,
    "candidate_held": 1,
}

COMPARISON_ELIGIBLE_ROWS: Final[int] = 79

MAGNITUDE_GAP_WARNING_TOTAL: Final[int] = 21
MAGNITUDE_GAP_WARNING_EXPECTED_COUNTS: Final[dict[str, int]] = {
    "valid_comparison": 20,
    "candidate_only": 1,
}

TICKET_CANDIDATE_COUNT: Final[int] = 16
TICKET_STATUS_EXPECTED_COUNTS: Final[dict[str, int]] = {
    "found": 5,
    "needs_review": 11,
}
TICKET_NO_CANDIDATE_COUNT: Final[int] = 76
VERIFIED_ADMISSIONS_COUNT: Final[int] = 0

PENDING_REVIEW_ROWS: Final[int] = 6
MAPPING_HUMAN_REVIEWED_COUNT: Final[int] = 0
HUMAN_CONFIRMED_MAPPINGS: Final[int] = 0
HUMAN_REJECTED_MAPPINGS: Final[int] = 0
