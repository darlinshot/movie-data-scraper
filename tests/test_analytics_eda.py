"""Standard-library tests for the read-only analytics EDA layer."""

from __future__ import annotations

import ast
import copy
import csv
import importlib.util
import sys
import tempfile
import unittest
from collections import Counter
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, Iterable, Mapping
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EDA_PATH = PROJECT_ROOT / "src" / "movie_data_collector" / "analytics" / "eda.py"
REAL_CSV = PROJECT_ROOT / "data" / "analytics" / "movie_analytics.csv"

_spec = importlib.util.spec_from_file_location("analytics_eda_under_test", EDA_PATH)
if _spec is None or _spec.loader is None:
    raise AssertionError(f"Could not load EDA module from {EDA_PATH}")
eda: ModuleType = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = eda
_spec.loader.exec_module(eda)

schema = eda.schema
FINAL_COLUMNS: tuple[str, ...] = tuple(schema.FINAL_COLUMNS)
WARNING = str(eda.EXPLORATORY_WARNING)
WARNING_LABEL = str(eda.REVENUE_WARNING_LABEL)
GAP_REFERENCE = eda.GAP_REFERENCE_PCT

_QUARANTINED = eda.QUARANTINED_MOVIE_ID
_CANDIDATE = eda.CANDIDATE_MOVIE_ID
_HIGH_IDS = frozenset(eda.PENDING_WORKFLOW_IDS)
_PENDING_IDS = frozenset(eda.PENDING_WORKFLOW_IDS)
_ACCEPTED_HIGH_IDS = frozenset({"M0020", "M0029", "M0030", "M0077"})
_LOWER_BOUND_IDS = frozenset(eda.LOWER_BOUND_IDS)


def _synthetic_rows() -> tuple[dict[str, Any], ...]:
    """Build 92 valid rows without touching any project input or output file."""
    accepted_ids = (
        {f"M{index:04d}" for index in range(1, 83)}
        - {_QUARANTINED, _CANDIDATE, "M0081"}
    )
    warning_valid_ids = {
        f"M{index:04d}" for index in (*range(1, 16), *range(17, 22))
    }
    rows: list[dict[str, Any]] = []

    for index in range(1, 93):
        movie_id = f"M{index:04d}"
        accepted = movie_id in accepted_ids
        quarantined = movie_id == _QUARANTINED
        candidate = movie_id == _CANDIDATE
        no_bov_revenue = movie_id == "M0081"
        not_found = index >= 83
        lower_bound = movie_id in _LOWER_BOUND_IDS
        warning = movie_id in warning_valid_ids or candidate
        high = movie_id in _HIGH_IDS
        missing_director = index >= 90
        ticket_found = index <= 5
        ticket_needs_review = 6 <= index <= 16

        if candidate:
            status = "needs_review"
        elif not_found:
            status = "not_found"
        else:
            status = "matched"

        if quarantined:
            mapping_status = "known_false_positive_quarantined"
        elif candidate:
            mapping_status = "candidate_held"
        elif status == "not_found":
            mapping_status = "no_match"
        else:
            mapping_status = "matcher_accepted"

        if high:
            data_quality_status = "pending_review"
        elif warning:
            data_quality_status = "revenue_gap_warning"
        elif missing_director:
            data_quality_status = "missing_core_data"
        elif not_found:
            data_quality_status = "no_bov_match"
        else:
            data_quality_status = "ok"

        if accepted:
            comparability_class = "insufficient_evidence"
            comparability_reason = "scope_unknown"
        elif quarantined:
            comparability_class = "not_applicable"
            comparability_reason = "mapping_quarantined_false_positive"
        elif candidate:
            comparability_class = "not_applicable"
            comparability_reason = "candidate_held"
        elif no_bov_revenue:
            comparability_class = "not_applicable"
            comparability_reason = "no_bov_revenue"
        elif not_found:
            comparability_class = "not_applicable"
            comparability_reason = "no_bov_mapping"
        else:
            comparability_class = "not_applicable"
            comparability_reason = None

        revenue_vnd = 100_000_000_000 + index * 1_000_000
        row: dict[str, Any] = {field: None for field in FINAL_COLUMNS}
        row.update(
            {
                "movie_id": movie_id,
                "canonical_title": f"Film {movie_id}",
                "original_title_raw": f"Original title {movie_id}",
                "release_year": 2026 if index <= 21 else 2023 if missing_director else 2024,
                "genre_raw": f"Raw genre {index % 4}",
                "genre_token_path": (
                    f"token{(index % 3) + 1}|token{(index % 4) + 1}"
                ),
                "genre_grouped": f"Group {index % 4}",
                "director_raw": None if missing_director else f"Director {index % 5}",
                "director_norm_key": (
                    None if missing_director else f"director {index % 5}"
                ),
                "source_url_dtp": f"https://doanhthuphim.test/phim-{movie_id}",
                "raw_source_row_dtp": index + 1,
                "bov_match_status": status,
                "match_score": 0.9,
                "match_reason": "auto",
                "bov_url": (
                    None
                    if not_found
                    else f"https://boxofficevietnam.test/phim-{movie_id}"
                ),
                "bov_title_raw": None if not_found else f"BOV film {movie_id}",
                "mapping_validation_status": mapping_status,
                "mapping_validation_reason": (
                    "sequel_number_error"
                    if quarantined
                    else "candidate_url_unverified"
                    if candidate
                    else None
                ),
                "mapping_human_reviewed": 0,
                "review_status": (
                    "pending"
                    if high
                    else "needs_review"
                    if candidate
                    else "not_found"
                    if not_found
                    else "auto_accepted"
                ),
                "review_priority": "high" if high else "normal",
                "dtp_revenue_raw": "hơn 100 tỷ" if lower_bound else "100 tỷ",
                "dtp_revenue_vnd": revenue_vnd,
                "dtp_revenue_quality": "lower_bound" if lower_bound else "rounded",
                "bov_revenue_raw": "100,000,000,000₫" if accepted else None,
                "bov_revenue_vnd": revenue_vnd if accepted else None,
                "bov_revenue_quality": "exact" if accepted else None,
                "bov_quarantined_revenue_raw": (
                    "108,654,235,000₫" if quarantined else None
                ),
                "bov_quarantined_revenue_vnd": (
                    108_654_235_000 if quarantined else None
                ),
                "bov_candidate_revenue_raw": (
                    "6,046,923,245₫" if candidate else None
                ),
                "bov_candidate_revenue_vnd": 6_046_923_245 if candidate else None,
                "revenue_gap_pct": (
                    12.5
                    if movie_id in warning_valid_ids
                    else 1.0
                    if accepted
                    else None
                ),
                "magnitude_gap_warning": int(warning),
                "revenue_conflict_flag": 0,
                "revenue_comparability_class": comparability_class,
                "comparability_reason": comparability_reason,
                "revenue_scope_verified": 0,
                "bov_evidence_available": int(
                    accepted or quarantined or candidate or no_bov_revenue
                ),
                "include_revenue_comparison": int(accepted),
                "include_revenue_eda": 1,
                "revenue_eda_basis": (
                    "dtp_lower_bound" if lower_bound else "dtp_rounded_numeric_agreement"
                ),
                "ticket_candidate_count": int(ticket_found or ticket_needs_review),
                "ticket_found_count": int(ticket_found),
                "ticket_needs_review_count": int(ticket_needs_review),
                "ticket_verified_admissions": None,
                "ticket_data_status": (
                    "found"
                    if ticket_found
                    else "needs_review"
                    if ticket_needs_review
                    else "no_candidates"
                ),
                "ticket_context_status": (
                    "event_attendance_quarantined"
                    if movie_id == "M0006"
                    else "cinema_candidate_unverified"
                    if ticket_found or ticket_needs_review
                    else None
                ),
                "ticket_evidence_urls": (
                    f"https://news.test/ticket-{movie_id}"
                    if ticket_found or ticket_needs_review
                    else None
                ),
                "has_missing_core_data": int(missing_director),
                "has_revenue_gap_warning": int(warning),
                "has_pending_review": int(high),
                "data_quality_status": data_quality_status,
            }
        )
        rows.append(row)
    return tuple(rows)


def _csv_value(value: Any) -> str:
    return "" if value is None else str(value)


def _write_csv(
    path: Path,
    rows: Iterable[Mapping[str, Any]],
    header: tuple[str, ...] = FINAL_COLUMNS,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in rows:
            writer.writerow([_csv_value(row.get(field)) for field in header])


def _records(table: Any) -> tuple[dict[str, Any], ...]:
    return tuple(dict(zip(table.columns, row)) for row in table.rows)


def _ids(table: Any) -> tuple[Any, ...]:
    column = table.columns.index("movie_id")
    return tuple(row[column] for row in table.rows)


def _metrics(table: Any) -> dict[str, Any]:
    return {row[0]: row[1] for row in table.rows}


def _snapshot(directory: Path) -> tuple[str, ...]:
    return tuple(
        sorted(path.relative_to(directory).as_posix() for path in directory.rglob("*"))
    )


class AnalyticsEdaLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.rows = _synthetic_rows()
        self.csv = self.root / "movie_analytics.csv"
        _write_csv(self.csv, self.rows)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_exact_header_order_and_column_count(self) -> None:
        loaded = eda.load_eda_dataset(self.csv)

        self.assertEqual(len(FINAL_COLUMNS), 54)
        self.assertEqual(tuple(loaded[0].keys()), FINAL_COLUMNS)
        self.assertEqual(len(loaded), 92)

        reordered = list(FINAL_COLUMNS)
        reordered[0], reordered[1] = reordered[1], reordered[0]
        shuffled = self.root / "shuffled.csv"
        _write_csv(shuffled, self.rows, tuple(reordered))
        with self.assertRaises(eda.EdaValidationError):
            eda.load_eda_dataset(shuffled)

    def test_missing_unexpected_and_extra_fields_are_rejected(self) -> None:
        missing_header = tuple(field for field in FINAL_COLUMNS if field != "genre_raw")
        missing = self.root / "missing.csv"
        _write_csv(missing, self.rows, missing_header)
        with self.assertRaises(eda.EdaValidationError):
            eda.load_eda_dataset(missing)

        extra_header = FINAL_COLUMNS + ("unexpected_column",)
        extra = self.root / "extra.csv"
        _write_csv(extra, self.rows, extra_header)
        with self.assertRaises(eda.EdaValidationError):
            eda.load_eda_dataset(extra)

        overlong = self.root / "overlong.csv"
        lines = self.csv.read_text(encoding="utf-8").splitlines()
        lines[1] = f"{lines[1]},unexpected_value"
        overlong.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with self.assertRaises(eda.EdaValidationError):
            eda.load_eda_dataset(overlong)

    def test_row_count_and_unique_valid_ids_are_required(self) -> None:
        short = self.root / "short.csv"
        _write_csv(short, self.rows[:-1])
        with self.assertRaises(eda.EdaValidationError):
            eda.load_eda_dataset(short)

        duplicate_rows = list(self.rows)
        duplicate_rows[1] = copy.deepcopy(duplicate_rows[0])
        duplicate = self.root / "duplicate.csv"
        _write_csv(duplicate, duplicate_rows)
        with self.assertRaises(eda.EdaValidationError):
            eda.load_eda_dataset(duplicate)

        invalid_rows = copy.deepcopy(list(self.rows))
        invalid_rows[0]["movie_id"] = "not-a-valid-id"
        invalid = self.root / "invalid.csv"
        _write_csv(invalid, invalid_rows)
        with self.assertRaises(eda.EdaValidationError):
            eda.load_eda_dataset(invalid)

    def test_empty_cells_become_none_and_known_fields_are_parsed(self) -> None:
        loaded = {row["movie_id"]: row for row in eda.load_eda_dataset(self.csv)}

        self.assertIsNone(loaded["M0081"]["bov_revenue_raw"])
        self.assertIsNone(loaded["M0081"]["bov_revenue_vnd"])
        self.assertIsNone(loaded["M0090"]["director_raw"])
        self.assertIsNone(loaded["M0043"]["revenue_gap_pct"])
        self.assertIsNone(loaded["M0001"]["ticket_verified_admissions"])

        first = loaded["M0001"]
        self.assertIsInstance(first["release_year"], int)
        self.assertIsInstance(first["raw_source_row_dtp"], int)
        self.assertIsInstance(first["dtp_revenue_vnd"], int)
        self.assertIsInstance(first["bov_revenue_vnd"], int)
        self.assertIsInstance(first["magnitude_gap_warning"], int)
        self.assertIsInstance(first["include_revenue_comparison"], int)
        self.assertIsInstance(first["ticket_candidate_count"], int)
        self.assertIsInstance(first["match_score"], float)
        self.assertIsInstance(first["revenue_gap_pct"], float)

    def test_raw_strings_are_preserved_without_trimming_or_normalizing(self) -> None:
        rows = copy.deepcopy(list(self.rows))
        rows[0].update(
            {
                "canonical_title": '  Phim Việt: "Đường xa"  ',
                "genre_raw": "Hài|Trinh thám|",
                "genre_token_path": "Hài|Trinh thám|",
                "bov_revenue_raw": "  keep spaces  ",
            }
        )
        path = self.root / "preserve.csv"
        _write_csv(path, rows)
        loaded = eda.load_eda_dataset(path)

        self.assertEqual(loaded[0]["canonical_title"], '  Phim Việt: "Đường xa"  ')
        self.assertEqual(loaded[0]["genre_raw"], "Hài|Trinh thám|")
        self.assertEqual(loaded[0]["genre_token_path"], "Hài|Trinh thám|")
        self.assertEqual(loaded[0]["bov_revenue_raw"], "  keep spaces  ")

    def test_loading_does_not_write_any_file(self) -> None:
        before = _snapshot(self.root)
        eda.load_eda_dataset(self.csv)
        self.assertEqual(_snapshot(self.root), before)

    def test_invalid_numeric_values_are_rejected(self) -> None:
        rows = copy.deepcopy(list(self.rows))
        rows[0]["dtp_revenue_vnd"] = "not-a-number"
        path = self.root / "bad_number.csv"
        _write_csv(path, rows)
        with self.assertRaises(eda.EdaValidationError):
            eda.load_eda_dataset(path)


class AnalyticsEdaSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = _synthetic_rows()

    def test_headline_kpis_and_status_counts(self) -> None:
        statuses = _metrics(eda.movie_status_counts(self.rows))
        self.assertEqual(
            statuses, {"matched": 81, "needs_review": 1, "not_found": 10}
        )

        metrics = _metrics(eda.headline_kpis(self.rows))
        expected = {
            "movies": 92,
            "matched": 81,
            "needs_review": 1,
            "not_found": 10,
            "movies_labelled_2026": 21,
            "distinct_raw_genres": 4,
            "distinct_directors": 5,
            "missing_directors": 3,
            "dtp_rounded_rows": 90,
            "dtp_lower_bound_rows": 2,
            "accepted_bov_revenue_rows": 79,
            "quarantined_bov_rows": 1,
            "candidate_held_bov_rows": 1,
            "comparison_rows": 79,
            "gap_warning_rows": 21,
            "ticket_candidate_rows": 16,
            "ticket_found_rows": 5,
            "ticket_needs_review_rows": 11,
            "verified_admission_values_present": 0,
            "high_priority_rows": 6,
        }
        for name, value in expected.items():
            self.assertEqual(metrics[name], value, name)

    def test_release_year_tables_have_no_revenue_series(self) -> None:
        distribution = eda.release_year_distribution(self.rows)
        matrix = eda.release_year_match_matrix(self.rows)

        self.assertEqual(distribution.columns, ("release_year", "movie_count"))
        self.assertEqual(
            matrix.columns, ("release_year", "bov_match_status", "movie_count")
        )
        self.assertEqual(sum(row[1] for row in distribution.rows), 92)
        self.assertEqual(dict(distribution.rows)[2026], 21)
        self.assertEqual(sum(row[2] for row in matrix.rows), 92)

        for table in (distribution, matrix):
            self.assertFalse(any("revenue" in column.lower() for column in table.columns))
            self.assertTrue(
                any("No revenue" in note or "no revenue" in note for note in table.notes)
            )

    def test_genre_tokens_use_stored_pipe_delimiter(self) -> None:
        rows = copy.deepcopy(list(self.rows))
        rows[0]["genre_token_path"] = "Hài||Trinh thám|"
        expected: Counter[str] = Counter()
        for row in rows:
            for token in row["genre_token_path"].split("|"):
                if token != "":
                    expected[token] += 1

        table = eda.genre_token_frequency(rows)
        actual = {row[0]: row[1] for row in table.rows}

        self.assertEqual(actual, dict(expected))
        self.assertNotIn("", actual)
        self.assertIn("Hài", actual)
        self.assertIn("Trinh thám", actual)
        self.assertTrue(any("non-additive" in note for note in table.notes))

    def test_director_profile_keeps_missing_directors_separate(self) -> None:
        table = eda.director_profile(self.rows)
        records = _records(table)

        self.assertEqual(len(records), 5)
        self.assertEqual(sum(record["director_count"] for record in records), 89)
        self.assertFalse(any(record["director_raw"] is None for record in records))
        self.assertIn("3 rows with missing director_raw", table.exclusions)
        self.assertTrue(
            any("Missing directors are reported separately" in note for note in table.notes)
        )

    def test_missing_values_and_flags_are_independent(self) -> None:
        missing = {row[0]: (row[1], row[2]) for row in eda.missing_value_summary(self.rows).rows}
        self.assertEqual(len(missing), 54)
        self.assertEqual(missing["movie_id"], (0, 92))
        self.assertEqual(missing["director_raw"], (3, 89))
        self.assertEqual(missing["ticket_verified_admissions"], (92, 0))

        flag_table = eda.flag_summary(self.rows)
        flags = {record["flag"]: record for record in _records(flag_table)}
        self.assertEqual(
            tuple(flags["has_pending_review"][key] for key in ("true_count", "false_count", "missing_count")),
            (6, 86, 0),
        )
        self.assertEqual(
            tuple(flags["include_revenue_comparison"][key] for key in ("true_count", "false_count", "missing_count")),
            (79, 13, 0),
        )
        self.assertEqual(
            tuple(flags["revenue_scope_verified"][key] for key in ("true_count", "false_count", "missing_count")),
            (0, 92, 0),
        )
        for record in flags.values():
            self.assertEqual(
                record["true_count"] + record["false_count"] + record["missing_count"],
                92,
            )
            self.assertTrue(record["flag_label"])
        self.assertTrue(any("not mutually exclusive" in note for note in flag_table.notes))

        quality = _metrics(eda.data_quality_summary(self.rows))
        self.assertEqual(quality["missing_core_data_rows"], 3)
        self.assertEqual(quality["gap_warning_rows"], 21)
        self.assertEqual(quality["pending_review_rows"], 6)
        self.assertEqual(quality["mapping_human_reviewed_rows"], 0)
        self.assertEqual(quality["mapping_quarantined_rows"], 1)
        self.assertEqual(quality["mapping_candidate_held_rows"], 1)


class AnalyticsEdaEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = _synthetic_rows()

    def test_gap_audit_excludes_quarantine_and_marks_candidate(self) -> None:
        table = eda.gap_audit_table(self.rows)
        records = {record["movie_id"]: record for record in _records(table)}
        ids = _ids(table)

        self.assertEqual(len(ids), 21)
        self.assertNotIn(_QUARANTINED, ids)
        self.assertIn(_CANDIDATE, ids)
        self.assertIn(_QUARANTINED, table.exclusions[0])

        candidate = records[_CANDIDATE]
        self.assertEqual(candidate["warning_type"], "candidate_hold_warning_only")
        self.assertEqual(candidate["warning_type_label"], "Candidate-held warning only")
        self.assertEqual(candidate["mapping_validation_status_label"], "Candidate held, not accepted")
        self.assertIsNone(candidate["revenue_gap_pct"])
        self.assertEqual(candidate["include_revenue_comparison"], 0)
        self.assertEqual(candidate["mapping_validation_status"], "candidate_held")
        self.assertEqual(candidate["bov_candidate_revenue_vnd"], 6_046_923_245)

        for movie_id, record in records.items():
            self.assertIn(
                record["warning_type_label"],
                {"Valid comparison warning", "Candidate-held warning only"},
            )
            self.assertTrue(record["mapping_validation_status"])
            self.assertTrue(record["mapping_validation_status_label"])
            if movie_id != _CANDIDATE:
                self.assertEqual(record["warning_type"], "valid_comparison_warning")
                self.assertEqual(record["warning_type_label"], "Valid comparison warning")
                self.assertEqual(record["revenue_gap_pct"], 12.5)

    def test_quarantine_audit_is_the_only_m0016_bov_evidence_table(self) -> None:
        quarantine = eda.quarantine_audit_table(self.rows)
        record = _records(quarantine)[0]

        self.assertEqual(_ids(quarantine), (_QUARANTINED,))
        self.assertEqual(record["bov_quarantined_revenue_vnd"], 108_654_235_000)
        self.assertIsNone(record["bov_revenue_vnd"])
        self.assertEqual(record["include_revenue_comparison"], 0)
        self.assertEqual(record["mapping_validation_status"], "known_false_positive_quarantined")

        self.assertNotIn(_QUARANTINED, _ids(eda.gap_audit_table(self.rows)))
        self.assertNotIn(_QUARANTINED, _ids(eda.high_priority_review_table(self.rows)))
        self.assertNotIn(_QUARANTINED, _ids(eda.bov_comparison_scatter(self.rows)))

        pending = eda.pending_workflow_table(self.rows)
        self.assertIn(_QUARANTINED, _ids(pending))
        pending_record = next(
            record for record in _records(pending) if record["movie_id"] == _QUARANTINED
        )
        self.assertFalse(
            any("revenue" in column and "bov" in column for column in pending.columns)
        )
        self.assertEqual(
            pending_record["mapping_validation_status"],
            "known_false_positive_quarantined",
        )
        self.assertEqual(pending_record["mapping_validation_reason"], "sequel_number_error")

    def test_ticket_evidence_preserves_context_without_admissions(self) -> None:
        table = eda.ticket_evidence_table(self.rows)
        records = _records(table)

        self.assertEqual(len(records), 16)
        self.assertEqual(sum(record["ticket_found_count"] for record in records), 5)
        self.assertEqual(
            sum(record["ticket_needs_review_count"] for record in records), 11
        )
        by_id = {record["movie_id"]: record for record in records}
        self.assertEqual(
            by_id["M0006"]["ticket_context_status"], "event_attendance_quarantined"
        )
        self.assertTrue(
            all(record["ticket_verified_admissions"] is None for record in records)
        )

        columns = " ".join(table.columns).lower()
        self.assertNotIn("sum", columns)
        self.assertNotIn("ranking", columns)
        self.assertNotIn("screening", columns)
        self.assertTrue(
            any(
                "no ticket values are summed" in str(record["evidence_note"]).lower()
                for record in records
            )
        )

    def test_high_priority_rows_keep_candidate_and_accepted_states(self) -> None:
        table = eda.high_priority_review_table(self.rows)
        ids = set(_ids(table))
        records = {record["movie_id"]: record for record in _records(table)}

        self.assertEqual(
            ids, {"M0020", "M0029", "M0030", "M0043", "M0077"}
        )
        self.assertNotIn(_QUARANTINED, ids)
        candidate = records[_CANDIDATE]
        self.assertEqual(candidate["mapping_validation_status"], "candidate_held")
        self.assertEqual(candidate["include_revenue_comparison"], 0)

        scatter_ids = set(_ids(eda.bov_comparison_scatter(self.rows)))
        self.assertTrue(_ACCEPTED_HIGH_IDS.issubset(scatter_ids))
        self.assertNotIn(_CANDIDATE, scatter_ids)

    def test_pending_workflow_table_reconciles_all_six_rows(self) -> None:
        table = eda.pending_workflow_table(self.rows)
        records = {record["movie_id"]: record for record in _records(table)}
        source = {row["movie_id"]: row for row in self.rows}

        self.assertEqual(set(records), _PENDING_IDS)
        self.assertEqual(len(records), 6)

        quarantined = records[_QUARANTINED]
        self.assertEqual(
            quarantined["mapping_validation_status"],
            "known_false_positive_quarantined",
        )
        self.assertEqual(
            quarantined["mapping_validation_status_label"],
            "Known false positive, quarantined",
        )
        self.assertEqual(quarantined["mapping_validation_reason"], "sequel_number_error")
        self.assertEqual(quarantined["review_status"], "pending")
        self.assertEqual(quarantined["review_status_label"], "Pending review")
        self.assertEqual(quarantined["include_revenue_comparison"], 0)
        self.assertFalse(
            any("bov" in column and "revenue" in column for column in table.columns)
        )

        candidate = records[_CANDIDATE]
        self.assertEqual(candidate["mapping_validation_status"], "candidate_held")
        self.assertEqual(candidate["mapping_validation_status_label"], "Candidate held, not accepted")
        self.assertEqual(candidate["include_revenue_comparison"], 0)

        for movie_id in _PENDING_IDS - {_QUARANTINED, _CANDIDATE}:
            record = records[movie_id]
            self.assertEqual(
                record["mapping_validation_status"],
                source[movie_id]["mapping_validation_status"],
            )
            self.assertEqual(record["review_status"], source[movie_id]["review_status"])
            self.assertEqual(
                record["review_priority"], source[movie_id]["review_priority"]
            )
        for record in records.values():
            self.assertTrue(record["mapping_validation_status_label"])
            self.assertTrue(record["review_status_label"])
            self.assertTrue(record["review_priority_label"])

    def test_lower_bound_values_are_visible_and_not_averaged(self) -> None:
        table = eda.lower_bound_revenue_table(self.rows)
        records = _records(table)

        self.assertEqual(
            {record["movie_id"] for record in records}, {"M0001", "M0024"}
        )
        self.assertTrue(
            all(str(record["display_value"]).startswith("≥") for record in records)
        )
        self.assertTrue(all(record["dtp_revenue_quality"] == "lower_bound" for record in records))
        self.assertIn(WARNING, table.notes)
        self.assertTrue(
            any(
                "no mean" in note.lower()
                and "total" in note.lower()
                and "ranking" in note.lower()
                for note in table.notes
            )
        )
        self.assertTrue(
            any("exact-value histogram" in note and "scatter" in note for note in table.notes)
        )

    def test_display_labels_preserve_machine_readable_source_values(self) -> None:
        flags = {
            record["flag"]: record
            for record in _records(eda.flag_summary(self.rows))
        }
        self.assertEqual(flags["has_pending_review"]["flag"], "has_pending_review")
        self.assertEqual(flags["has_pending_review"]["flag_label"], "Has pending review")
        self.assertEqual(flags["revenue_scope_verified"]["flag_label"], "Revenue scope verified")

        gap_records = _records(eda.gap_audit_table(self.rows))
        for record in gap_records:
            expected = {
                "valid_comparison_warning": "Valid comparison warning",
                "candidate_hold_warning_only": "Candidate-held warning only",
            }[record["warning_type"]]
            self.assertEqual(record["warning_type_label"], expected)

        scatter_records = _records(eda.bov_comparison_scatter(self.rows))
        for record in scatter_records:
            expected_band = {
                "above_10pct_warning": "Above 10% reference warning",
                "within_10pct_reference": "Within 10% reference",
            }[record["gap_band"]]
            self.assertEqual(record["gap_band_label"], expected_band)
            self.assertEqual(
                record["review_priority_label"],
                {"high": "High", "normal": "Normal"}[record["review_priority"]],
            )
            self.assertTrue(
                record["review_status"]
                and record["review_status_label"]
                and record["mapping_validation_status"]
                and record["mapping_validation_status_label"]
            )

        pending_records = _records(eda.pending_workflow_table(self.rows))
        for record in pending_records:
            self.assertEqual(
                record["review_status_label"],
                {
                    "pending": "Pending review",
                    "needs_review": "Needs review",
                    "auto_accepted": "Automatically accepted",
                    "not_applicable": "Not applicable",
                    "not_found": "Not found",
                }[record["review_status"]],
            )

    def test_revenue_warning_metadata_is_machine_readable_and_consistent(self) -> None:
        self.assertEqual(WARNING_LABEL, WARNING)
        self.assertIs(eda.REVENUE_SCOPE_VERIFIED, False)
        self.assertEqual(GAP_REFERENCE, 10)
        self.assertIsInstance(GAP_REFERENCE, int)

        report = eda.build_eda_report(rows=self.rows)
        tables = (
            *report.summaries.values(),
            *report.chart_data.values(),
            *report.tables.values(),
        )
        revenue_table_names = {
            "headline_kpis",
            "data_quality_summary",
            "flag_summary",
            "missing_value_summary",
            "gap_audit_table",
            "quarantine_audit_table",
            "high_priority_review_table",
            "pending_workflow_table",
            "lower_bound_revenue_table",
            "dtp_revenue_population",
            "dtp_revenue_histogram",
            "bov_comparison_scatter",
        }
        for table in tables:
            self.assertEqual(table.metadata["revenue_warning_label"], WARNING_LABEL)
            self.assertIs(table.metadata["revenue_scope_verified"], False)
            self.assertIsInstance(table.metadata, MappingProxyType)
            if table.name in revenue_table_names:
                self.assertIn(WARNING, table.notes, table.name)

        scatter = report.chart_data["bov_comparison_scatter"]
        gap_audit = report.tables["gap_audit_table"]
        for table in (scatter, gap_audit):
            self.assertEqual(table.metadata["gap_reference_pct"], 10)
        self.assertTrue(
            any(
                "reference" in note.lower()
                and "threshold" in note.lower()
                and "proof of conflict" in note.lower()
                for note in scatter.notes
            )
        )
        self.assertIn(WARNING_LABEL, report.warnings)


class AnalyticsEdaChartDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = _synthetic_rows()

    def test_reported_structures_are_immutable(self) -> None:
        report = eda.build_eda_report(rows=self.rows)

        self.assertIsInstance(report, eda.EdaReport)
        for group in (report.summaries, report.chart_data, report.tables):
            for table in group.values():
                self.assertIsInstance(table, eda.EdaTable)
                self.assertIsInstance(table.columns, tuple)
                self.assertIsInstance(table.rows, tuple)
                self.assertTrue(all(isinstance(row, tuple) for row in table.rows))
                self.assertIsInstance(table.filters, tuple)
                self.assertIsInstance(table.exclusions, tuple)
                self.assertIsInstance(table.notes, tuple)
                self.assertIsInstance(table.metadata, MappingProxyType)
                with self.assertRaises(FrozenInstanceError):
                    table.name = "changed"
                with self.assertRaises(TypeError):
                    table.metadata["changed"] = True

        with self.assertRaises(TypeError):
            report.summaries["changed"] = None

    def test_dtp_population_and_exact_histogram_report_all_counts(self) -> None:
        population = eda.dtp_revenue_population(self.rows)
        metrics = _metrics(population)
        self.assertEqual(metrics["eligible_rows"], 92)
        self.assertEqual(metrics["rounded_exact_rows"], 90)
        self.assertEqual(metrics["lower_bound_rows"], 2)
        self.assertEqual(metrics["missing_invalid_rows"], 0)
        self.assertIn("eligible=92", population.population)
        self.assertIn("rounded_exact=90", population.population)
        self.assertIn("lower_bound=2", population.population)
        self.assertIn("missing_invalid=0", population.population)

        distribution = eda.dtp_revenue_distribution(self.rows)
        self.assertEqual(
            distribution.columns, ("revenue_bin_vnd", "movie_count")
        )
        self.assertIn("eligible=92", distribution.population)
        self.assertIn("rounded_exact=90", distribution.population)
        self.assertIn("lower_bound=2", distribution.population)
        self.assertIn("missing_invalid=0", distribution.population)
        self.assertEqual(sum(row[1] for row in distribution.rows), 90)
        self.assertNotIn("lower_bound_count", distribution.columns)
        self.assertFalse(any("bov" in column.lower() for column in distribution.columns))
        self.assertIn(WARNING, distribution.notes)
        self.assertEqual(
            distribution.metadata["revenue_warning_label"], WARNING_LABEL
        )
        self.assertIs(distribution.metadata["revenue_scope_verified"], False)

    def test_exact_histogram_excludes_lower_bound_and_counts_missing_invalid(self) -> None:
        baseline = sum(row[1] for row in eda.dtp_revenue_distribution(self.rows).rows)
        self.assertEqual(baseline, 90)

        rows = copy.deepcopy(list(self.rows))
        rows[2]["dtp_revenue_quality"] = "lower_bound"
        rows[1]["dtp_revenue_quality"] = "rounded"
        rows[1]["dtp_revenue_vnd"] = None
        population = _metrics(eda.dtp_revenue_population(rows))
        self.assertEqual(population["eligible_rows"], 92)
        self.assertEqual(population["rounded_exact_rows"], 88)
        self.assertEqual(population["lower_bound_rows"], 3)
        self.assertEqual(population["missing_invalid_rows"], 1)
        self.assertEqual(
            sum(row[1] for row in eda.dtp_revenue_distribution(rows).rows), 88
        )

    def test_scatter_excludes_lower_bounds_and_keeps_high_priority_flags(self) -> None:
        flags = {
            record["flag"]: record
            for record in _records(eda.flag_summary(self.rows))
        }
        self.assertEqual(flags["include_revenue_comparison"]["true_count"], 79)

        table = eda.bov_comparison_scatter(self.rows)
        records = _records(table)
        ids = set(_ids(table))

        self.assertEqual(len(records), 77)
        self.assertIn("from 79 eligible comparisons", table.population)
        self.assertIn("77 exact-value diagnostic BOV comparison rows", table.population)
        self.assertNotIn(_QUARANTINED, ids)
        self.assertNotIn(_CANDIDATE, ids)
        self.assertFalse(ids & _LOWER_BOUND_IDS)
        self.assertTrue(_ACCEPTED_HIGH_IDS.issubset(ids))
        self.assertIn("dtp_revenue_vnd", table.columns)
        self.assertIn("bov_revenue_vnd", table.columns)
        self.assertIn("dtp_revenue_quality", table.columns)
        self.assertIn("review_priority", table.columns)
        self.assertTrue(
            all(record["dtp_revenue_quality"] == "rounded" for record in records)
        )
        self.assertTrue(all(record["dtp_revenue_vnd"] is not None for record in records))
        self.assertTrue(all(record["bov_revenue_vnd"] is not None for record in records))
        self.assertEqual(
            {record["review_priority"] for record in records if record["movie_id"] in _ACCEPTED_HIGH_IDS},
            {"high"},
        )
        self.assertTrue(
            all(record["review_priority_label"] for record in records)
        )
        self.assertTrue(all(record["gap_band_label"] for record in records))
        self.assertEqual(table.metadata["gap_reference_pct"], 10)
        self.assertIs(table.metadata["revenue_scope_verified"], False)
        self.assertTrue(any("10%" in note for note in table.notes))
        self.assertTrue(any("no fitted line" in note for note in table.notes))
        self.assertTrue(any("not a statistical threshold" in note for note in table.notes))
        self.assertIn(WARNING, table.notes)

    def test_scatter_rejects_wrong_eligible_count(self) -> None:
        rows = copy.deepcopy(list(self.rows))
        rows[0]["include_revenue_comparison"] = 0
        with self.assertRaises(eda.EdaValidationError):
            eda.bov_comparison_scatter(rows)


class AnalyticsEdaReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.rows = _synthetic_rows()
        self.csv = self.root / "movie_analytics.csv"
        _write_csv(self.csv, self.rows)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_supplied_rows_are_used_without_reloading(self) -> None:
        with mock.patch.object(
            eda, "load_eda_dataset", side_effect=AssertionError("CSV was reloaded")
        ):
            report = eda.build_eda_report(rows=self.rows)

        self.assertIsNone(report.source_path)
        self.assertEqual(report.row_count, 92)
        self.assertEqual(report.column_count, 54)
        self.assertEqual(
            set(report.summaries),
            {
                "headline_kpis",
                "movie_status_counts",
                "release_year_distribution",
                "release_year_match_matrix",
                "genre_token_frequency",
                "director_profile",
                "data_quality_summary",
                "flag_summary",
                "missing_value_summary",
                "dtp_revenue_population",
            },
        )
        self.assertEqual(
            set(report.chart_data),
            {
                "movie_match_status_donut",
                "release_year_histogram",
                "release_year_match_status_stacked",
                "genre_frequency_bar",
                "director_profile_bar",
                "independent_data_quality_flags",
                "dtp_revenue_histogram",
                "bov_comparison_scatter",
            },
        )
        self.assertEqual(
            set(report.tables),
            {
                "gap_audit_table",
                "quarantine_audit_table",
                "ticket_evidence_table",
                "high_priority_review_table",
                "pending_workflow_table",
                "lower_bound_revenue_table",
            },
        )

    def test_csv_is_loaded_once_when_rows_are_not_supplied(self) -> None:
        with mock.patch.object(
            eda, "load_eda_dataset", wraps=eda.load_eda_dataset
        ) as loader:
            report = eda.build_eda_report(path=self.csv)

        self.assertEqual(loader.call_count, 1)
        self.assertEqual(report.source_path, self.csv)

    def test_build_report_and_analyses_do_not_mutate_input_rows(self) -> None:
        before = copy.deepcopy(self.rows)
        eda.build_eda_report(rows=self.rows)
        for function in (
            eda.headline_kpis,
            eda.movie_status_counts,
            eda.release_year_distribution,
            eda.release_year_match_matrix,
            eda.genre_token_frequency,
            eda.director_profile,
            eda.data_quality_summary,
            eda.flag_summary,
            eda.missing_value_summary,
            eda.gap_audit_table,
            eda.quarantine_audit_table,
            eda.ticket_evidence_table,
            eda.high_priority_review_table,
            eda.pending_workflow_table,
            eda.lower_bound_revenue_table,
            eda.dtp_revenue_population,
            eda.dtp_revenue_distribution,
            eda.bov_comparison_scatter,
        ):
            function(self.rows)
        self.assertEqual(self.rows, before)

    def test_no_forbidden_ranking_forecast_or_efficiency_outputs(self) -> None:
        report = eda.build_eda_report(rows=self.rows)
        forbidden = (
            "official",
            "preferred_revenue",
            "top_grossing",
            "ranking",
            "forecast",
            "revenue_trend",
            "screening_efficiency",
            "admissions_sum",
            "admissions_rank",
        )
        tables = (*report.summaries.values(), *report.chart_data.values(), *report.tables.values())
        for table in tables:
            labels = [table.name, *table.columns]
            if table.columns and table.columns[0] in {"metric", "flag", "column"}:
                labels.extend(str(row[0]) for row in table.rows)
            text = " ".join(str(label).lower() for label in labels)
            for term in forbidden:
                self.assertNotIn(term, text, f"{table.name}: {term}")

    def test_forbidden_visualisation_libraries_are_not_imported(self) -> None:
        tree = ast.parse(EDA_PATH.read_text(encoding="utf-8"))
        banned = {"pandas", "numpy", "matplotlib", "seaborn", "plotly"}
        found: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module.split(".")[0])
        self.assertFalse(found & banned)


class RealDataEdaTests(unittest.TestCase):
    def test_approved_csv_invariants_and_safety_rules(self) -> None:
        self.assertTrue(REAL_CSV.is_file())
        rows = eda.load_eda_dataset(REAL_CSV)
        report = eda.build_eda_report()
        metrics = _metrics(report.summaries["headline_kpis"])

        self.assertEqual(report.row_count, 92)
        self.assertEqual(report.column_count, 54)
        self.assertEqual(len(rows), 92)
        self.assertEqual(
            _metrics(report.summaries["movie_status_counts"]),
            {"matched": 81, "needs_review": 1, "not_found": 10},
        )
        self.assertEqual(metrics["movies_labelled_2026"], 21)
        self.assertEqual(metrics["distinct_raw_genres"], 62)
        self.assertEqual(metrics["distinct_directors"], 50)
        self.assertEqual(metrics["missing_directors"], 3)
        self.assertEqual(metrics["dtp_rounded_rows"], 90)
        self.assertEqual(metrics["dtp_lower_bound_rows"], 2)
        self.assertEqual(metrics["accepted_bov_revenue_rows"], 79)
        self.assertEqual(metrics["quarantined_bov_rows"], 1)
        self.assertEqual(metrics["candidate_held_bov_rows"], 1)
        self.assertEqual(metrics["comparison_rows"], 79)
        self.assertEqual(metrics["gap_warning_rows"], 21)
        self.assertEqual(metrics["ticket_candidate_rows"], 16)
        self.assertEqual(metrics["ticket_found_rows"], 5)
        self.assertEqual(metrics["ticket_needs_review_rows"], 11)
        self.assertEqual(metrics["verified_admission_values_present"], 0)

        histogram = report.chart_data["dtp_revenue_histogram"]
        scatter = report.chart_data["bov_comparison_scatter"]
        gap = report.tables["gap_audit_table"]
        quarantine = report.tables["quarantine_audit_table"]
        high_priority = report.tables["high_priority_review_table"]
        pending = report.tables["pending_workflow_table"]
        lower_bound = report.tables["lower_bound_revenue_table"]
        ticket = report.tables["ticket_evidence_table"]

        self.assertEqual(sum(row[1] for row in histogram.rows), 90)
        self.assertEqual(
            sum(row[1] for row in eda.dtp_revenue_distribution(rows).rows), 90
        )
        self.assertEqual(_ids(lower_bound), ("M0001", "M0024"))
        self.assertTrue(
            all(str(row["display_value"]).startswith("≥") for row in _records(lower_bound))
        )
        self.assertEqual(len(scatter.rows), 77)
        self.assertFalse(set(_ids(scatter)) & _LOWER_BOUND_IDS)
        self.assertNotIn(_QUARANTINED, _ids(scatter))
        self.assertNotIn(_CANDIDATE, _ids(scatter))
        self.assertTrue(_ACCEPTED_HIGH_IDS.issubset(set(_ids(scatter))))
        self.assertEqual(
            {record["review_priority"] for record in _records(scatter) if record["movie_id"] in _ACCEPTED_HIGH_IDS},
            {"high"},
        )
        self.assertEqual(len(gap.rows), 21)
        self.assertNotIn(_QUARANTINED, _ids(gap))
        self.assertIn(_CANDIDATE, _ids(gap))
        gap_records = _records(gap)
        self.assertEqual(
            sum(record["warning_type"] == "valid_comparison_warning" for record in gap_records),
            20,
        )
        self.assertEqual(
            sum(record["warning_type"] == "candidate_hold_warning_only" for record in gap_records),
            1,
        )
        self.assertEqual(_ids(quarantine), (_QUARANTINED,))
        self.assertEqual(
            set(_ids(high_priority)),
            {"M0020", "M0029", "M0030", "M0043", "M0077"},
        )
        self.assertEqual(set(_ids(pending)), _PENDING_IDS)
        self.assertEqual(len(pending.rows), 6)
        self.assertEqual(
            set(_ids(report.tables["lower_bound_revenue_table"])), _LOWER_BOUND_IDS
        )

        flag_records = {
            record["flag"]: record
            for record in _records(report.summaries["flag_summary"])
        }
        self.assertEqual(flag_records["revenue_scope_verified"]["true_count"], 0)
        for table in (histogram, scatter, lower_bound, gap, pending):
            self.assertEqual(table.metadata["revenue_warning_label"], WARNING_LABEL)
            self.assertIs(table.metadata["revenue_scope_verified"], False)
        self.assertEqual(scatter.metadata["gap_reference_pct"], 10)

        records = {row["movie_id"]: row for row in rows}
        pending_records = {record["movie_id"]: record for record in _records(pending)}
        self.assertTrue(all(row["ticket_verified_admissions"] is None for row in rows))
        self.assertTrue(all(row["revenue_scope_verified"] == 0 for row in rows))
        self.assertTrue(
            any(
                record["ticket_context_status"] == "event_attendance_quarantined"
                for record in _records(ticket)
            )
        )
        self.assertTrue(
            all(
                record["revenue_gap_pct"] is None
                for record in gap_records
                if record["movie_id"] == _CANDIDATE
            )
        )
        self.assertEqual(
            records[_QUARANTINED]["bov_quarantined_revenue_vnd"], 108_654_235_000
        )
        self.assertEqual(
            pending_records[_QUARANTINED]["mapping_validation_status"],
            "known_false_positive_quarantined",
        )
        self.assertEqual(
            pending_records[_QUARANTINED]["mapping_validation_reason"],
            "sequel_number_error",
        )
        self.assertFalse(
            any("bov" in column and "revenue" in column for column in pending.columns)
        )
        self.assertEqual(
            pending_records[_CANDIDATE]["mapping_validation_status"], "candidate_held"
        )
        self.assertEqual(pending_records[_CANDIDATE]["include_revenue_comparison"], 0)
        self.assertIsNone(records[_QUARANTINED]["bov_revenue_vnd"])
        self.assertIsNone(records[_CANDIDATE]["bov_revenue_vnd"])


if __name__ == "__main__":
    unittest.main()
