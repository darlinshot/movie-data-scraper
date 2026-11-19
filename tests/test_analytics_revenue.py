"""Standard-library tests for the analytics revenue transformation layer."""

from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALYTICS_DIR = PROJECT_ROOT / "src" / "movie_data_collector" / "analytics"


def _load_module(path: Path, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


clean = _load_module(ANALYTICS_DIR / "clean.py", "analytics_clean_for_revenue_tests")
ids = _load_module(ANALYTICS_DIR / "ids.py", "analytics_ids_for_revenue_tests")
revenue = _load_module(
    ANALYTICS_DIR / "revenue.py", "analytics_revenue_under_test"
)


def _cleaned_movie(url: str) -> Any:
    missing = clean.FieldStatus.MISSING
    valid = clean.FieldStatus.VALID
    return clean.CleanedMovie(
        raw_source_row_dtp=1,
        movie_name_raw="Synthetic Film",
        canonical_title="Synthetic Film",
        title_status=valid,
        original_title_source=None,
        original_title_raw=None,
        original_title_status=missing,
        release_year_source=None,
        release_year=None,
        release_year_status=missing,
        genre_source=None,
        genre_raw=None,
        genre_status=missing,
        genre_tokens=(),
        genre_token_path=None,
        genre_grouped=None,
        director_source=None,
        director_raw=None,
        director_status=missing,
        director_norm_key=None,
        source_url_dtp=url,
        source_url_dtp_status=valid,
    )


def _case(
    *,
    movie_id: str = "M0001",
    decision: str | None = "accepted",
    dtp_raw: str = "100 tỷ",
    bov_raw: str = "95,000,000,000₫",
    has_bov_url: bool = True,
    collection_match_status: str = "matched",
    raw_match_status: str = "matched",
    match_score: str = "0.99",
    detail_raw: str | None = None,
    canonical_title: str = "Synthetic Film",
) -> SimpleNamespace:
    url = f"https://doanhthuphim.vn/phim/{movie_id.lower()}"
    bov_url = "https://v1.boxofficevietnam.com/movie/synthetic" if has_bov_url else ""

    raw_movie = {
        "movie_name": canonical_title,
        "original_title": "Synthetic Film",
        "release_year": "2024",
        "genre": "Drama",
        "director": "Synthetic Director",
        "source_url_doanhthuphim": url,
        "source_url_bovn": bov_url,
        "title_bovn": canonical_title,
        "revenue_doanhthuphim": dtp_raw,
        "revenue_bovn": bov_raw,
        "match_status": raw_match_status,
    }
    collection_row = {
        "source_url_doanhthuphim": url,
        "match_status": collection_match_status,
        "match_score": match_score,
        "match_reason": "auto",
    }
    boxoffice_row = {
        "source_url_doanhthuphim": url,
        "_bov_candidate": None,
        "_bov_detail_raw": detail_raw,
    }

    review = (
        None
        if decision is None
        else ids.RevenueReview(
            decision=decision,
            reason="synthetic_test",
            reviewed_at=None,
            reviewer=None,
        )
    )
    mapped = ids.MappedMovie(
        movie_id=movie_id,
        source_url_dtp=url,
        canonical_title=canonical_title,
        release_year=2024,
        director_raw="Synthetic Director",
        url_history=(),
        status="active",
        created_at="2026-01-01T00:00:00Z",
        last_seen_at="2026-01-01T00:00:00Z",
        revenue_review=review,
    )
    mapping = ids.MovieIdMapping(
        schema_version="1.0",
        generated_at="2026-01-01T00:00:00Z",
        source_anchor="source_url_doanhthuphim",
        id_prefix="M",
        movies=(mapped,),
    )
    assignment = ids.IdAssignmentResult(
        movie_ids_by_url={url: movie_id},
        updated_mapping=mapping,
        summary=ids.AssignmentSummary(),
    )
    raw_inputs = clean.RawInputs(
        movies=(raw_movie,),
        collection_log=(),
        tickets_sold_web=(),
        boxoffice_matches=(boxoffice_row,),
    )
    cleaned_inputs = clean.CleanedInputs(
        movies=(_cleaned_movie(url),),
        collection_log=(collection_row,),
        tickets_sold_web=(),
        boxoffice_matches=(boxoffice_row,),
    )
    return SimpleNamespace(
        raw_inputs=raw_inputs,
        cleaned_inputs=cleaned_inputs,
        id_assignment=assignment,
        movie_id=movie_id,
        url=url,
    )


def _process(case: SimpleNamespace) -> dict[str, Any]:
    result = revenue.process_revenue(
        case.raw_inputs, case.cleaned_inputs, case.id_assignment
    )
    assert list(result) == [case.movie_id]
    return result[case.movie_id]


class ParseRevenueTests(unittest.TestCase):
    def test_parse_dtp_rounded_revenue(self) -> None:
        parsed = revenue.parse_dtp_revenue("714 tỷ")
        self.assertEqual(parsed.raw, "714 tỷ")
        self.assertEqual(parsed.value, 714_000_000_000)
        self.assertEqual(parsed.quality, revenue.DTP_QUALITY_ROUNDED)

        uppercase = revenue.parse_dtp_revenue("496 Tỷ")
        self.assertEqual(uppercase.value, 496_000_000_000)
        self.assertEqual(uppercase.quality, revenue.DTP_QUALITY_ROUNDED)

    def test_parse_dtp_lower_bound_revenue(self) -> None:
        for raw, expected in (
            ("hơn 46 tỷ", 46_000_000_000),
            ("trên 21 tỷ", 21_000_000_000),
            ("> 5 triệu", 5_000_000),
            ("≥ 7 tỷ", 7_000_000_000),
        ):
            with self.subTest(raw=raw):
                parsed = revenue.parse_dtp_revenue(raw)
                self.assertEqual(parsed.raw, raw)
                self.assertEqual(parsed.value, expected)
                self.assertEqual(parsed.quality, revenue.DTP_QUALITY_LOWER_BOUND)

    def test_parse_dtp_decimal_and_grouped_values(self) -> None:
        self.assertEqual(
            revenue.parse_dtp_revenue("12,5 triệu").value, 12_500_000
        )
        self.assertEqual(
            revenue.parse_dtp_revenue("1.250.000₫").value, 1_250_000
        )

    def test_parse_missing_and_malformed_revenue(self) -> None:
        for raw in (None, "", "không rõ", "đang cập nhật", "N/A"):
            with self.subTest(raw=raw):
                parsed = revenue.parse_dtp_revenue(raw)
                self.assertIsNone(parsed.value)
                self.assertIsNone(parsed.quality)
                self.assertEqual(parsed.raw, raw if isinstance(raw, str) else None)

    def test_parse_bov_exact_and_reject_lower_bound(self) -> None:
        parsed = revenue.parse_bov_revenue("714,030,584,098₫")
        self.assertEqual(parsed.raw, "714,030,584,098₫")
        self.assertEqual(parsed.value, 714_030_584_098)
        self.assertEqual(parsed.quality, revenue.BOV_QUALITY_EXACT)

        lower_bound = revenue.parse_bov_revenue("hơn 46 tỷ")
        self.assertIsNone(lower_bound.value)
        self.assertIsNone(lower_bound.quality)

        malformed = revenue.parse_bov_revenue("không rõ")
        self.assertIsNone(malformed.value)
        self.assertIsNone(malformed.quality)

    def test_compute_gap_pct_and_zero_denominator(self) -> None:
        self.assertEqual(revenue.compute_gap_pct(100, 90), 10.0)
        self.assertEqual(revenue.compute_gap_pct(100, 125), 25.0)
        self.assertIsNone(revenue.compute_gap_pct(0, 10))
        self.assertIsNone(revenue.compute_gap_pct(0, 0))
        self.assertIsNone(revenue.compute_gap_pct(None, 10))
        self.assertIsNone(revenue.compute_gap_pct(100, None))
        self.assertIsNone(revenue.compute_gap_pct(True, 10))


class RevenueProcessingTests(unittest.TestCase):
    def test_exact_field_names_and_null_handling(self) -> None:
        accepted = _process(_case())
        self.assertEqual(
            tuple(accepted), tuple(revenue.schema.GROUP_C_REVENUE_COLUMNS)
        )

        case = _case(
            movie_id="M0002",
            decision=None,
            dtp_raw="",
            bov_raw="",
            has_bov_url=False,
        )
        record = _process(case)
        self.assertEqual(
            tuple(record), tuple(revenue.schema.GROUP_C_REVENUE_COLUMNS)
        )
        self.assertEqual(record["dtp_revenue_raw"], "")
        for field in (
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
            "revenue_eda_basis",
        ):
            with self.subTest(field=field):
                self.assertIsNone(record[field])

    def test_accepted_bov_revenue_is_separate_and_eligible(self) -> None:
        record = _process(_case(detail_raw="<html>stored detail</html>"))
        self.assertEqual(record["dtp_revenue_raw"], "100 tỷ")
        self.assertEqual(record["dtp_revenue_vnd"], 100_000_000_000)
        self.assertEqual(record["dtp_revenue_quality"], "rounded")
        self.assertEqual(record["bov_revenue_raw"], "95,000,000,000₫")
        self.assertEqual(record["bov_revenue_vnd"], 95_000_000_000)
        self.assertEqual(record["bov_revenue_quality"], "exact")
        self.assertIsNone(record["bov_quarantined_revenue_raw"])
        self.assertIsNone(record["bov_candidate_revenue_raw"])
        self.assertEqual(record["revenue_gap_pct"], 5.0)
        self.assertEqual(record["bov_evidence_available"], 1)
        self.assertEqual(record["revenue_comparability_class"], "insufficient_evidence")
        self.assertEqual(record["comparability_reason"], "scope_unknown")
        self.assertEqual(record["revenue_scope_verified"], 0)
        self.assertEqual(record["include_revenue_comparison"], 1)
        self.assertEqual(record["include_revenue_eda"], 1)
        self.assertEqual(record["revenue_eda_basis"], "dtp_rounded_numeric_agreement")
        self.assertEqual(record["magnitude_gap_warning"], 0)
        self.assertEqual(record["revenue_conflict_flag"], 0)

    def test_bov_evidence_placeholder_is_not_evidence(self) -> None:
        record = _process(_case(detail_raw="None"))
        self.assertEqual(record["bov_evidence_available"], 0)

        missing = _process(_case(detail_raw=None))
        self.assertEqual(missing["bov_evidence_available"], 0)

    def test_quarantined_bov_revenue_never_enters_comparison(self) -> None:
        record = _process(
            _case(
                movie_id="M0016",
                decision="quarantined",
                dtp_raw="100 tỷ",
                bov_raw="99,000,000,000₫",
            )
        )
        self.assertIsNone(record["bov_revenue_raw"])
        self.assertIsNone(record["bov_revenue_vnd"])
        self.assertEqual(record["bov_quarantined_revenue_raw"], "99,000,000,000₫")
        self.assertEqual(record["bov_quarantined_revenue_vnd"], 99_000_000_000)
        self.assertIsNone(record["bov_candidate_revenue_raw"])
        self.assertIsNone(record["revenue_gap_pct"])
        self.assertEqual(record["magnitude_gap_warning"], 0)
        self.assertEqual(record["include_revenue_comparison"], 0)
        self.assertEqual(record["include_revenue_eda"], 1)
        self.assertEqual(record["revenue_comparability_class"], "not_applicable")
        self.assertEqual(
            record["comparability_reason"], "mapping_quarantined_false_positive"
        )
        self.assertEqual(record["revenue_conflict_flag"], 0)

    def test_candidate_bov_revenue_is_warning_only(self) -> None:
        record = _process(
            _case(
                movie_id="M0043",
                decision="candidate_held",
                dtp_raw="100 tỷ",
                bov_raw="150,000,000,000₫",
                collection_match_status="needs_review",
                match_score="0.71",
            )
        )
        self.assertIsNone(record["bov_revenue_raw"])
        self.assertIsNone(record["bov_revenue_vnd"])
        self.assertIsNone(record["bov_quarantined_revenue_raw"])
        self.assertEqual(record["bov_candidate_revenue_raw"], "150,000,000,000₫")
        self.assertEqual(record["bov_candidate_revenue_vnd"], 150_000_000_000)
        self.assertIsNone(record["revenue_gap_pct"])
        self.assertEqual(record["magnitude_gap_warning"], 1)
        self.assertEqual(record["include_revenue_comparison"], 0)
        self.assertEqual(record["revenue_comparability_class"], "not_applicable")
        self.assertEqual(record["comparability_reason"], "candidate_held")
        self.assertEqual(record["revenue_eda_basis"], "dtp_rounded_single_source")
        self.assertEqual(record["revenue_conflict_flag"], 0)

    def test_missing_review_metadata_is_never_accepted(self) -> None:
        record = _process(
            _case(
                movie_id="M0026",
                decision=None,
                dtp_raw="100 tỷ",
                bov_raw="95,000,000,000₫",
                canonical_title="Synthetic Film",
                match_score="1.0",
            )
        )
        self.assertIsNone(record["bov_revenue_raw"])
        self.assertIsNone(record["bov_revenue_vnd"])
        self.assertIsNone(record["revenue_gap_pct"])
        self.assertEqual(record["include_revenue_comparison"], 0)
        self.assertEqual(record["comparability_reason"], "missing_revenue_review")

    def test_pending_review_decision_is_excluded(self) -> None:
        record = _process(
            _case(
                movie_id="M0031",
                decision="pending",
                dtp_raw="100 tỷ",
                bov_raw="95,000,000,000₫",
            )
        )
        self.assertIsNone(record["bov_revenue_raw"])
        self.assertIsNone(record["revenue_gap_pct"])
        self.assertEqual(record["include_revenue_comparison"], 0)
        self.assertEqual(record["comparability_reason"], "pending_revenue_review")

    def test_no_comparison_without_bov_revenue(self) -> None:
        record = _process(
            _case(
                movie_id="M0034",
                decision="accepted",
                dtp_raw="100 tỷ",
                bov_raw="",
            )
        )
        self.assertIsNone(record["bov_revenue_raw"])
        self.assertIsNone(record["revenue_gap_pct"])
        self.assertEqual(record["magnitude_gap_warning"], 0)
        self.assertEqual(record["include_revenue_comparison"], 0)
        self.assertEqual(record["comparability_reason"], "no_bov_revenue")

    def test_no_comparison_without_dtp_revenue(self) -> None:
        record = _process(
            _case(
                movie_id="M0046",
                decision="accepted",
                dtp_raw="không rõ",
                bov_raw="95,000,000,000₫",
            )
        )
        self.assertIsNone(record["revenue_gap_pct"])
        self.assertIsNone(record["revenue_eda_basis"])
        self.assertEqual(record["include_revenue_comparison"], 0)
        self.assertEqual(record["include_revenue_eda"], 0)
        self.assertEqual(record["comparability_reason"], "no_dtp_revenue")

    def test_no_bov_mapping_and_unaccepted_match_are_excluded(self) -> None:
        no_mapping = _process(
            _case(
                movie_id="M0047",
                decision="accepted",
                has_bov_url=False,
                bov_raw="",
            )
        )
        self.assertEqual(no_mapping["comparability_reason"], "no_bov_mapping")
        self.assertEqual(no_mapping["include_revenue_comparison"], 0)

        not_accepted = _process(
            _case(
                movie_id="M0053",
                decision="accepted",
                collection_match_status="not_found",
                raw_match_status="matched",
            )
        )
        self.assertEqual(not_accepted["comparability_reason"], "bov_match_not_accepted")
        self.assertEqual(not_accepted["include_revenue_comparison"], 0)

    def test_gap_warning_threshold_and_no_false_conflict(self) -> None:
        at_threshold = _process(
            _case(movie_id="M0060", dtp_raw="100 tỷ", bov_raw="90,000,000,000₫")
        )
        self.assertEqual(at_threshold["revenue_gap_pct"], 10.0)
        self.assertEqual(at_threshold["magnitude_gap_warning"], 0)
        self.assertEqual(
            at_threshold["revenue_eda_basis"], "dtp_rounded_numeric_agreement"
        )

        above_threshold = _process(
            _case(movie_id="M0061", dtp_raw="100 tỷ", bov_raw="89,900,000,000₫")
        )
        self.assertAlmostEqual(above_threshold["revenue_gap_pct"], 10.1)
        self.assertEqual(above_threshold["magnitude_gap_warning"], 1)
        self.assertEqual(
            above_threshold["revenue_eda_basis"], "dtp_rounded_single_source"
        )
        self.assertEqual(above_threshold["revenue_conflict_flag"], 0)

    def test_zero_denominator_does_not_create_warning(self) -> None:
        record = _process(
            _case(movie_id="M0072", dtp_raw="0 tỷ", bov_raw="0₫")
        )
        self.assertIsNone(record["revenue_gap_pct"])
        self.assertEqual(record["magnitude_gap_warning"], 0)
        self.assertEqual(record["revenue_conflict_flag"], 0)

    def test_lower_bound_dtp_preserves_basis(self) -> None:
        record = _process(
            _case(
                movie_id="M0079",
                dtp_raw="hơn 46 tỷ",
                bov_raw="46,000,000,000₫",
            )
        )
        self.assertEqual(record["dtp_revenue_raw"], "hơn 46 tỷ")
        self.assertEqual(record["dtp_revenue_quality"], "lower_bound")
        self.assertEqual(record["dtp_revenue_vnd"], 46_000_000_000)
        self.assertEqual(record["include_revenue_comparison"], 1)
        self.assertEqual(record["revenue_eda_basis"], "dtp_lower_bound")

    def test_high_priority_workflow_fields_survive_field_application(self) -> None:
        case = _case()
        revenue_by_id = revenue.process_revenue(
            case.raw_inputs, case.cleaned_inputs, case.id_assignment
        )
        base_row = {
            "movie_id": case.movie_id,
            "canonical_title": "Synthetic Film",
            "review_status": "pending",
            "review_priority": "high",
            "mapping_human_reviewed": 0,
            "dtp_revenue_raw": "stale value",
        }
        updated = revenue.apply_revenue_fields([base_row], revenue_by_id)[0]

        self.assertEqual(updated["review_priority"], "high")
        self.assertEqual(updated["review_status"], "pending")
        self.assertEqual(updated["canonical_title"], "Synthetic Film")
        self.assertEqual(updated["mapping_human_reviewed"], 0)
        self.assertEqual(updated["dtp_revenue_raw"], "100 tỷ")
        self.assertEqual(updated["bov_revenue_vnd"], 95_000_000_000)

    def test_inputs_and_base_rows_are_not_mutated(self) -> None:
        case = _case(detail_raw="<html>stored detail</html>")
        snapshot = copy.deepcopy(
            (
                case.raw_inputs.movies,
                case.raw_inputs.boxoffice_matches,
                case.cleaned_inputs.collection_log,
            )
        )
        base_row = {
            "movie_id": case.movie_id,
            "review_priority": "high",
            "custom_note": "keep me",
        }
        base_snapshot = copy.deepcopy(base_row)

        revenue_by_id = revenue.process_revenue(
            case.raw_inputs, case.cleaned_inputs, case.id_assignment
        )
        updated = revenue.apply_revenue_fields([base_row], revenue_by_id)

        self.assertEqual(
            (
                case.raw_inputs.movies,
                case.raw_inputs.boxoffice_matches,
                case.cleaned_inputs.collection_log,
            ),
            snapshot,
        )
        self.assertEqual(base_row, base_snapshot)
        self.assertEqual(updated[0]["custom_note"], "keep me")
        self.assertIsNot(updated[0], base_row)


if __name__ == "__main__":
    unittest.main()
