"""Standard-library tests for the atomic analytics CSV export layer."""

from __future__ import annotations

import copy
import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, Mapping
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPORT_PATH = (
    PROJECT_ROOT / "src" / "movie_data_collector" / "analytics" / "export.py"
)

_spec = importlib.util.spec_from_file_location("analytics_export_under_test", EXPORT_PATH)
if _spec is None or _spec.loader is None:
    raise AssertionError(f"Could not load export module from {EXPORT_PATH}")
export: ModuleType = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = export
_spec.loader.exec_module(export)

schema = export.schema
FINAL_COLUMNS: tuple[str, ...] = tuple(schema.FINAL_COLUMNS)


def _synthetic_rows() -> tuple[dict[str, Any], ...]:
    """Build 92 valid rows without touching any project input or output file."""
    rows: list[dict[str, Any]] = []
    for index in range(1, 93):
        row: dict[str, Any] = {field: None for field in FINAL_COLUMNS}
        accepted_bov = index <= 79
        quarantined = index == 80
        candidate = index == 81
        warning = index <= 20 or candidate

        row.update(
            {
                "movie_id": f"M{index:04d}",
                "canonical_title": f"Film {index:04d}",
                "original_title_raw": f"Original title {index:04d}",
                "release_year": 2024,
                "genre_raw": "Drama",
                "genre_token_path": "drama",
                "genre_grouped": "Drama",
                "director_raw": f"Director {index:04d}",
                "director_norm_key": f"director {index:04d}",
                "source_url_dtp": f"https://doanhthuphim.test/phim-{index:04d}",
                "raw_source_row_dtp": index + 1,
                "bov_match_status": "not_found" if index >= 82 else "matched",
                "match_score": 0.9,
                "match_reason": "auto",
                "bov_url": (
                    None if index >= 82 else f"https://boxoffice.test/movie-{index:04d}"
                ),
                "bov_title_raw": None if index >= 82 else f"BOV film {index:04d}",
                "mapping_validation_status": "matcher_accepted",
                "mapping_human_reviewed": 0,
                "review_status": "auto_accepted",
                "review_priority": "normal",
                "dtp_revenue_raw": "100 tỷ",
                "dtp_revenue_vnd": 100_000_000_000,
                "dtp_revenue_quality": "lower_bound" if index <= 2 else "rounded",
                "bov_revenue_raw": "100,000,000,000₫" if accepted_bov else None,
                "bov_revenue_vnd": 100_000_000_000 if accepted_bov else None,
                "bov_revenue_quality": "parsed" if accepted_bov else None,
                "bov_quarantined_revenue_vnd": (
                    100_000_000_000 if quarantined else None
                ),
                "bov_candidate_revenue_vnd": 150_000_000_000 if candidate else None,
                "revenue_gap_pct": 12.5 if index <= 20 else None,
                "magnitude_gap_warning": int(warning),
                "revenue_conflict_flag": 0,
                "revenue_comparability_class": "comparable",
                "include_revenue_comparison": int(accepted_bov),
                "include_revenue_eda": int(accepted_bov),
                "revenue_eda_basis": "both_sources" if accepted_bov else None,
                "ticket_verified_admissions": None,
                "has_missing_core_data": 0,
                "has_revenue_gap_warning": int(warning),
                "has_pending_review": 0,
                "data_quality_status": (
                    "revenue_gap_warning" if warning else "ok"
                ),
            }
        )

        if index <= 5:
            row.update(
                {
                    "ticket_candidate_count": 1,
                    "ticket_found_count": 1,
                    "ticket_needs_review_count": 0,
                    "ticket_data_status": "found",
                    "ticket_context_status": "cumulative",
                    "ticket_evidence_urls": f"https://news.test/ticket-{index:04d}",
                }
            )
        elif index <= 16:
            row.update(
                {
                    "ticket_candidate_count": 1,
                    "ticket_found_count": 0,
                    "ticket_needs_review_count": 1,
                    "ticket_data_status": "needs_review",
                    "ticket_context_status": "unclear",
                    "ticket_evidence_urls": f"https://news.test/ticket-{index:04d}",
                }
            )
        else:
            row.update(
                {
                    "ticket_candidate_count": 0,
                    "ticket_found_count": 0,
                    "ticket_needs_review_count": 0,
                    "ticket_data_status": "no_candidates",
                    "ticket_context_status": None,
                    "ticket_evidence_urls": None,
                }
            )

        rows.append(row)
    return tuple(rows)


def _read_csv(path: Path) -> tuple[tuple[str, ...], tuple[dict[str, str], ...]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = tuple(reader.fieldnames or ())
        rows = tuple(
            {field: row[field] for field in header}
            for row in reader
        )
    return header, rows


def _read_raw_csv(path: Path) -> tuple[tuple[str, ...], ...]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return tuple(tuple(row) for row in csv.reader(handle))


def _temp_files(directory: Path) -> tuple[Path, ...]:
    return tuple(
        path for path in directory.iterdir() if path.is_file() and ".tmp" in path.name
    )


class AnalyticsExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.rows = _synthetic_rows()
        self.output = self.root / "output" / "movie_analytics.csv"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_successful_export(self) -> None:
        original = copy.deepcopy(self.rows)
        result = export.export_analytics_dataset(self.rows, self.output)

        self.assertEqual(result.output_path, self.output)
        self.assertEqual(result.row_count, 92)
        self.assertEqual(result.column_count, 54)
        self.assertEqual(result.validation, export.build_dataset.validate_dataset(self.rows))
        self.assertTrue(self.output.is_file())
        self.assertEqual(tuple(path.name for path in self.output.parent.iterdir()), ("movie_analytics.csv",))

        header, rows = _read_csv(self.output)
        self.assertEqual(header, FINAL_COLUMNS)
        self.assertEqual(len(rows), 92)
        self.assertEqual(
            tuple(row["movie_id"] for row in rows),
            tuple(row["movie_id"] for row in self.rows),
        )
        self.assertEqual(result.readback_validation["final"]["row_count"], 92)
        self.assertEqual(result.readback_validation["final"]["column_count"], 54)
        self.assertEqual(self.rows, original)

    def test_exact_column_order(self) -> None:
        result = export.export_analytics_dataset(self.rows, self.output)
        header, rows = _read_csv(self.output)

        self.assertEqual(len(FINAL_COLUMNS), 54)
        self.assertEqual(FINAL_COLUMNS[0], "movie_id")
        self.assertEqual(header, schema.FINAL_COLUMNS)
        self.assertTrue(all(tuple(row.keys()) == FINAL_COLUMNS for row in rows))
        self.assertEqual(result.readback_validation["final"]["structural_validation"]["column_count"], 54)

    def test_utf8_vietnamese_text_is_preserved(self) -> None:
        rows = copy.deepcopy(self.rows)
        rows[0]["canonical_title"] = "Phim Việt Nam — Đi tìm mặt trời"
        rows[0]["original_title_raw"] = 'Tiêu đề gốc: "Đường xa hun hắt"'
        rows[0]["bov_title_raw"] = "Phim Việt Nam — Đi tìm mặt trời (Bản dịch)"

        export.export_analytics_dataset(rows, self.output)
        raw = self.output.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertIn("Phim Việt Nam — Đi tìm mặt trời".encode("utf-8"), raw)
        self.assertIn("Đường xa hun hắt".encode("utf-8"), raw)

        _, exported = _read_csv(self.output)
        self.assertEqual(exported[0]["canonical_title"], rows[0]["canonical_title"])
        self.assertEqual(exported[0]["original_title_raw"], rows[0]["original_title_raw"])
        self.assertEqual(exported[0]["bov_title_raw"], rows[0]["bov_title_raw"])

    def test_none_is_serialized_as_empty_field(self) -> None:
        export.export_analytics_dataset(self.rows, self.output)
        _, exported = _read_csv(self.output)

        for field in ("bov_url", "bov_title_raw", "bov_revenue_raw", "revenue_gap_pct", "ticket_evidence_urls"):
            self.assertIsNone(self.rows[81][field])
            self.assertEqual(exported[81][field], "")
        self.assertIsNone(export._convert_readback_value("bov_url", None, ""))

        result = export.export_analytics_dataset(self.rows, self.output)
        self.assertGreater(result.readback_validation["final"]["empty_field_count"], 0)

    def test_empty_string_is_preserved_without_trimming(self) -> None:
        rows = copy.deepcopy(self.rows)
        rows[0]["match_reason"] = ""
        rows[0]["mapping_validation_reason"] = ""
        rows[0]["bov_revenue_raw"] = "  "
        rows[0]["comparability_reason"] = ""

        export.export_analytics_dataset(rows, self.output)
        _, exported = _read_csv(self.output)
        self.assertEqual(exported[0]["match_reason"], "")
        self.assertEqual(exported[0]["mapping_validation_reason"], "")
        self.assertEqual(exported[0]["bov_revenue_raw"], "  ")
        self.assertEqual(exported[0]["comparability_reason"], "")
        self.assertEqual(
            export._convert_readback_value("mapping_validation_reason", "", ""), ""
        )

    def test_numeric_and_percentage_serialization(self) -> None:
        rows = copy.deepcopy(self.rows)
        rows[0]["dtp_revenue_vnd"] = 46_000_000_000
        rows[0]["bov_revenue_vnd"] = 100_000_000_000
        rows[0]["revenue_gap_pct"] = 12.5

        export.export_analytics_dataset(rows, self.output)
        raw_rows = _read_raw_csv(self.output)
        header = raw_rows[0]
        first = raw_rows[1]
        by_field = dict(zip(header, first))
        self.assertEqual(by_field["dtp_revenue_vnd"], "46000000000")
        self.assertEqual(by_field["bov_revenue_vnd"], "100000000000")
        self.assertEqual(by_field["revenue_gap_pct"], "12.5")

        _, exported = _read_csv(self.output)
        self.assertEqual(exported[0]["dtp_revenue_vnd"], "46000000000")
        self.assertEqual(
            export._convert_readback_value("revenue_gap_pct", 12.5, "12.5"), 12.5
        )
        self.assertEqual(
            export._convert_readback_value("dtp_revenue_vnd", 46_000_000_000, "46000000000"),
            46_000_000_000,
        )

    def test_no_index_column_is_written(self) -> None:
        export.export_analytics_dataset(self.rows, self.output)
        header, rows = _read_csv(self.output)

        self.assertEqual(len(header), 54)
        self.assertNotIn("", header)
        self.assertNotIn("index", header)
        self.assertNotIn("Unnamed: 0", header)
        raw_rows = _read_raw_csv(self.output)
        self.assertTrue(all(len(row) == 54 for row in raw_rows))
        self.assertFalse(any(None in row for row in rows))

    def test_invalid_row_count_is_rejected(self) -> None:
        rows = list(self.rows)
        rows.pop()

        with self.assertRaises(export.ExportValidationError) as caught:
            export.export_analytics_dataset(rows, self.output)
        self.assertIn("row_count", str(caught.exception))
        self.assertFalse(self.output.exists())

    def test_duplicate_movie_ids_are_rejected(self) -> None:
        rows = copy.deepcopy(self.rows)
        rows[1]["movie_id"] = rows[0]["movie_id"]

        with self.assertRaises(export.ExportValidationError) as caught:
            export.export_analytics_dataset(rows, self.output)
        self.assertIn("duplicate_movie_ids", str(caught.exception))
        self.assertFalse(self.output.exists())

    def test_missing_and_unexpected_columns_are_rejected(self) -> None:
        missing = copy.deepcopy(self.rows)
        del missing[0]["genre_raw"]
        with self.assertRaises(export.ExportValidationError) as caught:
            export.export_analytics_dataset(missing, self.output)
        self.assertIn("columns", str(caught.exception))
        self.assertFalse(self.output.exists())

        extra = copy.deepcopy(self.rows)
        extra[0]["unexpected_column"] = "x"
        with self.assertRaises(export.ExportValidationError) as caught:
            export.export_analytics_dataset(extra, self.output)
        self.assertIn("columns", str(caught.exception))
        self.assertFalse(self.output.exists())

    def test_validation_failure_does_not_overwrite_existing_destination(self) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_bytes(b"existing destination\n")
        rows = copy.deepcopy(self.rows)
        rows[0]["movie_id"] = "not-a-valid-id"

        with self.assertRaises(export.ExportValidationError):
            export.export_analytics_dataset(rows, self.output)
        self.assertEqual(self.output.read_bytes(), b"existing destination\n")
        self.assertEqual(_temp_files(self.output.parent), ())

    def test_temporary_file_is_cleaned_up_after_write_failure(self) -> None:
        with mock.patch.object(export.os, "fsync", side_effect=OSError("fsync failed")):
            with self.assertRaises(OSError):
                export.export_analytics_dataset(self.rows, self.output)

        self.assertTrue(self.output.parent.is_dir())
        self.assertFalse(self.output.exists())
        self.assertEqual(_temp_files(self.output.parent), ())

    def test_readback_validation_failure_is_reported(self) -> None:
        real_validate = export._validate_readback
        calls: list[Path] = []

        def flaky_validate(
            path: Path, source_rows: Iterable[Mapping[str, Any]], expected_ids: tuple[str, ...]
        ) -> dict[str, Any]:
            calls.append(path)
            if len(calls) == 1:
                return real_validate(path, source_rows, expected_ids)
            raise export.ExportReadBackError("simulated final read-back failure")

        with mock.patch.object(export, "_validate_readback", side_effect=flaky_validate):
            with self.assertRaises(export.ExportReadBackError) as caught:
                export.export_analytics_dataset(self.rows, self.output)

        self.assertIn("simulated final read-back failure", str(caught.exception))
        self.assertEqual(len(calls), 2)
        self.assertEqual(_temp_files(self.output.parent), ())

    def test_custom_output_path_creates_parent_directories(self) -> None:
        custom = self.root / "custom" / "deeper" / "analytics.csv"
        result = export.export_analytics_dataset(self.rows, str(custom))

        self.assertEqual(result.output_path, custom)
        self.assertTrue(custom.is_file())
        header, rows = _read_csv(custom)
        self.assertEqual(header, FINAL_COLUMNS)
        self.assertEqual(len(rows), 92)
        self.assertEqual(tuple(path.name for path in custom.parent.iterdir()), ("analytics.csv",))

    def test_default_output_path_can_be_redirected_in_test(self) -> None:
        redirected = self.root / "default" / "movie_analytics.csv"
        with mock.patch.object(schema, "MOVIE_ANALYTICS_CSV_PATH", redirected):
            result = export.export_analytics_dataset(self.rows)

        self.assertEqual(result.output_path, redirected)
        self.assertTrue(redirected.is_file())

    def test_input_rows_are_not_mutated(self) -> None:
        before = copy.deepcopy(self.rows)
        export.export_analytics_dataset(self.rows, self.output)
        self.assertEqual(self.rows, before)

        with self.assertRaises(export.ExportValidationError):
            invalid = copy.deepcopy(list(self.rows))
            invalid.pop()
            export.export_analytics_dataset(invalid, self.output)
        self.assertEqual(self.rows, before)


if __name__ == "__main__":
    unittest.main()
