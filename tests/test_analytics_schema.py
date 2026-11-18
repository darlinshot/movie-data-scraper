"""Standard-library tests for the analytics schema foundation."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    PROJECT_ROOT / "src" / "movie_data_collector" / "analytics" / "schema.py"
)

# The existing movie_data_collector.__init__ imports the CLI/pandas chain.
# Load schema.py directly so this test module remains standard-library only.
_spec = importlib.util.spec_from_file_location("analytics_schema_under_test", SCHEMA_PATH)
if _spec is None or _spec.loader is None:
    raise AssertionError(f"Could not load schema module from {SCHEMA_PATH}")
schema: ModuleType = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(schema)


APPROVED_COLUMNS = (
    # Group A — Movie identity and metadata (§3.3).
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
    # Group B — Matching information (§3.4).
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
    # Group C — Revenue by source (§3.5).
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
    # Group D — Ticket information (§3.6).
    "ticket_candidate_count",
    "ticket_found_count",
    "ticket_needs_review_count",
    "ticket_verified_admissions",
    "ticket_data_status",
    "ticket_context_status",
    "ticket_evidence_urls",
    # Group E — Data quality (§3.7).
    "has_missing_core_data",
    "has_revenue_gap_warning",
    "has_pending_review",
    "data_quality_status",
)


class AnalyticsSchemaTests(unittest.TestCase):
    def test_schema_column_list_is_non_empty(self) -> None:
        self.assertTrue(schema.FINAL_COLUMNS)

    def test_column_names_are_unique(self) -> None:
        self.assertEqual(
            len(schema.FINAL_COLUMNS), len(set(schema.FINAL_COLUMNS))
        )

    def test_movie_id_exists(self) -> None:
        self.assertIn("movie_id", schema.FINAL_COLUMNS)

    def test_primary_key_is_expected_field(self) -> None:
        self.assertEqual(schema.PRIMARY_KEY, "movie_id")
        self.assertEqual(schema.FINAL_COLUMNS[0], schema.PRIMARY_KEY)

    def test_expected_row_count_is_92(self) -> None:
        self.assertEqual(schema.EXPECTED_MOVIE_COUNT, 92)

    def test_exact_column_count_and_approved_order(self) -> None:
        self.assertEqual(schema.EXPECTED_COLUMN_COUNT, 54)
        self.assertEqual(len(schema.FINAL_COLUMNS), 54)
        self.assertEqual(schema.FINAL_COLUMNS, APPROVED_COLUMNS)

    def test_project_root_matches_repository_layout(self) -> None:
        self.assertEqual(schema.PROJECT_ROOT, PROJECT_ROOT)
        self.assertEqual(schema.DATA_DIR, PROJECT_ROOT / "data")
        self.assertEqual(schema.STATE_DIR, PROJECT_ROOT / "state")

    def test_all_required_input_paths_are_represented(self) -> None:
        relative_paths = tuple(
            path.relative_to(schema.PROJECT_ROOT)
            for path in schema.REQUIRED_BUILD_INPUT_PATHS
        )
        self.assertEqual(
            relative_paths,
            (
                Path("data") / "movies.csv",
                Path("data") / "collection_log.csv",
                Path("data") / "tickets_sold_web.csv",
                Path("state") / "boxoffice_matches.jsonl",
            ),
        )

    def test_mapping_metadata_path_is_distinct_from_final_csv(self) -> None:
        self.assertNotEqual(schema.ID_MAP_JSON_PATH, schema.MOVIE_ANALYTICS_CSV_PATH)
        self.assertNotIn(schema.ID_MAP_JSON_PATH, schema.ANALYTICAL_OUTPUT_PATHS)
        self.assertNotIn(schema.ID_MAP_JSON_PATH, schema.POWER_BI_INPUT_PATHS)
        self.assertEqual(
            schema.POWER_BI_INPUT_PATHS, (schema.MOVIE_ANALYTICS_CSV_PATH,)
        )

    def test_audit_only_and_deprecated_paths_are_not_required_inputs(self) -> None:
        for path in schema.AUDIT_ONLY_PATHS + schema.DEPRECATED_EXCLUDED_PATHS:
            self.assertNotIn(path, schema.REQUIRED_BUILD_INPUT_PATHS)

        self.assertEqual(
            tuple(
                path.relative_to(schema.PROJECT_ROOT)
                for path in schema.AUDIT_ONLY_PATHS
            ),
            (
                Path("state") / "doanhthuphim_movies.jsonl",
                Path("state") / "web_tickets_progress.jsonl",
                Path("data") / "unmatched_movies.csv",
            ),
        )
        self.assertEqual(
            tuple(
                path.relative_to(schema.PROJECT_ROOT)
                for path in schema.DEPRECATED_EXCLUDED_PATHS
            ),
            (Path("data") / "full_export.csv",),
        )

    def test_final_output_path_is_approved(self) -> None:
        self.assertEqual(
            schema.MOVIE_ANALYTICS_CSV_PATH.relative_to(schema.PROJECT_ROOT),
            Path("data") / "analytics" / "movie_analytics.csv",
        )

    def test_no_unapproved_preferred_or_combined_revenue_field(self) -> None:
        banned_fields = {
            "revenue",
            "revenue_raw",
            "revenue_vnd",
            "revenue_final",
            "revenue_official_vnd",
            "preferred_revenue",
            "preferred_revenue_vnd",
            "combined_revenue",
            "combined_revenue_vnd",
            "winner_takes_all_revenue",
        }
        columns = set(schema.FINAL_COLUMNS)
        self.assertFalse(banned_fields.intersection(columns))
        for token in ("preferred", "combined", "winner_takes_all"):
            self.assertFalse(any(token in column for column in columns))

    def test_no_mapping_or_build_metadata_columns(self) -> None:
        banned_metadata = {
            "schema_version",
            "generated_at",
            "source_anchor",
            "id_prefix",
            "url_history",
            "created_at",
            "last_seen_at",
            "notes",
            "input_hash_before_build",
            "mapping_hash_after_build",
        }
        self.assertFalse(banned_metadata.intersection(schema.FINAL_COLUMNS))

    def test_approved_count_constants(self) -> None:
        self.assertEqual(schema.EXPECTED_MOVIE_COUNT, 92)
        self.assertEqual(schema.ID_PREFIX, "M")
        self.assertEqual(schema.ID_DIGIT_WIDTH, 4)
        self.assertEqual(schema.MOVIE_ID_PATTERN, r"^M\d{4}$")
        self.assertEqual(
            schema.MATCH_STATUS_EXPECTED_COUNTS,
            {"matched": 81, "needs_review": 1, "not_found": 10},
        )
        self.assertEqual(
            schema.DTP_REVENUE_QUALITY_EXPECTED_COUNTS,
            {"rounded": 90, "lower_bound": 2},
        )
        self.assertEqual(schema.STORED_BOV_REVENUE_OBSERVATIONS, 80)
        self.assertEqual(
            schema.BOV_REVENUE_EXPECTED_COUNTS,
            {"valid": 79, "quarantined": 1, "candidate_held": 1},
        )
        self.assertEqual(schema.COMPARISON_ELIGIBLE_ROWS, 79)
        self.assertEqual(schema.MAGNITUDE_GAP_WARNING_TOTAL, 21)
        self.assertEqual(
            schema.MAGNITUDE_GAP_WARNING_EXPECTED_COUNTS,
            {"valid_comparison": 20, "candidate_only": 1},
        )
        self.assertEqual(schema.TICKET_CANDIDATE_COUNT, 16)
        self.assertEqual(
            schema.TICKET_STATUS_EXPECTED_COUNTS,
            {"found": 5, "needs_review": 11},
        )
        self.assertEqual(schema.TICKET_NO_CANDIDATE_COUNT, 76)
        self.assertEqual(schema.VERIFIED_ADMISSIONS_COUNT, 0)
        self.assertEqual(schema.PENDING_REVIEW_ROWS, 6)
        self.assertEqual(schema.MAPPING_HUMAN_REVIEWED_COUNT, 0)
        self.assertEqual(schema.HUMAN_CONFIRMED_MAPPINGS, 0)
        self.assertEqual(schema.HUMAN_REJECTED_MAPPINGS, 0)


if __name__ == "__main__":
    unittest.main()
