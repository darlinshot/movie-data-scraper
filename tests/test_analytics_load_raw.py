"""Standard-library tests for raw input loading and structural validation."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOAD_RAW_PATH = (
    PROJECT_ROOT / "src" / "movie_data_collector" / "analytics" / "load_raw.py"
)

_spec = importlib.util.spec_from_file_location("analytics_load_raw_under_test", LOAD_RAW_PATH)
if _spec is None or _spec.loader is None:
    raise AssertionError(f"Could not load load_raw module from {LOAD_RAW_PATH}")
load_raw: ModuleType = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = load_raw
_spec.loader.exec_module(load_raw)


MOVIES_HEADER = (
    "movie_name",
    "title_bovn",
    "original_title",
    "release_year",
    "genre",
    "director",
    "revenue_doanhthuphim",
    "revenue_bovn",
    "tickets_sold",
    "screening_count",
    "source_url_doanhthuphim",
    "source_url_bovn",
    "match_status",
    "collection_status",
)

COLLECTION_HEADER = (
    "movie_name",
    "title_bovn",
    "source_url_doanhthuphim",
    "source_url_bovn",
    "match_status",
    "collection_status",
    "match_score",
    "match_reason",
)

BOV_DETAIL_KEYS = (
    "bov_title",
    "bov_release_info",
    "_bov_candidate",
    "_bov_detail_raw",
)

TICKETS_HEADER = (
    "movie_name",
    "title_bovn",
    "source_url_doanhthuphim",
    "tickets_sold_web",
    "tickets_display",
    "tickets_basis",
    "ticket_status",
    "confidence",
    "source_title",
    "source_url",
    "source_name",
    "published",
    "snippet",
    "search_backend",
    "matched_query",
    "search_queries",
    "candidate_count",
    "error",
    "collected_at",
)


def _url(index: int) -> str:
    return f"https://example.test/movie/{index:04d}"


def _movie_rows(count: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index in range(count):
        row = {column: f"value_{index}_{column}" for column in MOVIES_HEADER}
        row["movie_name"] = (
            "  Phim  test — Đưa  " if index == 0 else f"Phim {index}"
        )
        row["release_year"] = "2024"
        row["source_url_doanhthuphim"] = _url(index)
        row["source_url_bovn"] = f"https://bov.test/{index:04d}"
        row["match_status"] = "matched"
        row["collection_status"] = "ok"
        rows.append(row)
    return rows


def _collection_rows(count: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index in range(count):
        row = {column: f"value_{index}_{column}" for column in COLLECTION_HEADER}
        row["source_url_doanhthuphim"] = _url(index)
        row["match_status"] = "matched"
        row["match_score"] = "95.5"
        row["match_reason"] = "auto"
        rows.append(row)
    return rows


def _ticket_rows(count: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index in range(count):
        row = {column: f"value_{index}_{column}" for column in TICKETS_HEADER}
        row["source_url_doanhthuphim"] = _url(index)
        row["ticket_status"] = "found" if index < 5 else ""
        row["source_url"] = f"https://news.test/{index:04d}" if index < 5 else ""
        row["source_title"] = f"Ticket headline {index}" if index < 5 else ""
        rows.append(row)
    return rows


def _jsonl_records(count: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index in range(count):
        records.append(
            {
                "movie_name": f"Phim {index}",
                "original_title": None,
                "release_year": 2024,
                "genre": "Drama",
                "director": None,
                "revenue_doanhthuphim": "100 tỷ",
                "revenue_bovn": "101 tỷ" if index < 79 else None,
                "tickets_sold": None,
                "screening_count": None,
                "source_url_doanhthuphim": _url(index),
                "source_url_bovn": f"https://bov.test/{index:04d}" if index < 82 else None,
                "match_status": "matched" if index < 81 else "not_found",
                "collection_status": "ok",
                "_dtp_raw": None,
                "_dtp_detail_raw": None,
                "match_score": 95.5,
                "match_reason": "auto",
                "bov_title": f"BOV Title {index}",
                "bov_release_info": None,
                "original_title_from_bovn": None,
                "_bov_candidate": False,
                "_bov_detail_raw": None,
            }
        )
    return records


def _write_csv_dict(
    path: Path, header: Sequence[str], rows: Iterable[Mapping[str, Any]]
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(header))
        writer.writeheader()
        writer.writerows(rows)


def _write_csv_matrix(
    path: Path, header: Sequence[str], rows: Iterable[Sequence[Any]]
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _valid_paths(root: Path, count: int = 92) -> Any:
    root.mkdir(parents=True, exist_ok=True)
    movies_path = root / "movies.csv"
    collection_path = root / "collection_log.csv"
    tickets_path = root / "tickets_sold_web.csv"
    boxoffice_path = root / "boxoffice_matches.jsonl"

    _write_csv_dict(movies_path, MOVIES_HEADER, _movie_rows(count))
    _write_csv_dict(collection_path, COLLECTION_HEADER, _collection_rows(count))
    _write_csv_dict(tickets_path, TICKETS_HEADER, _ticket_rows(count))
    _write_jsonl(boxoffice_path, _jsonl_records(count))

    return load_raw.RawInputPaths(
        movies_csv=movies_path,
        collection_log_csv=collection_path,
        tickets_sold_web_csv=tickets_path,
        boxoffice_matches_jsonl=boxoffice_path,
    )


class AnalyticsLoadRawTests(unittest.TestCase):
    def test_valid_csv_loading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            raw = load_raw.load_raw_inputs(paths)

            self.assertEqual(len(raw.movies), 92)
            self.assertEqual(len(raw.collection_log), 92)
            self.assertEqual(len(raw.tickets_sold_web), 92)
            self.assertIsInstance(raw.movies[0], dict)
            self.assertEqual(raw.movies[0]["movie_name"], "  Phim  test — Đưa  ")

    def test_valid_jsonl_loading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            raw = load_raw.load_raw_inputs(paths)

            self.assertEqual(len(raw.boxoffice_matches), 92)
            self.assertEqual(raw.boxoffice_matches[0]["bov_title"], "BOV Title 0")
            self.assertIsNone(raw.boxoffice_matches[0]["_bov_detail_raw"])
            self.assertEqual(raw.boxoffice_matches[0]["match_score"], 95.5)

    def test_missing_required_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            missing = Path(tmp) / "missing_movies.csv"
            paths = replace(paths, movies_csv=missing)

            with self.assertRaises(load_raw.MissingInputError) as ctx:
                load_raw.load_raw_inputs(paths)
            self.assertIn(str(missing), str(ctx.exception))

    def test_input_path_is_directory_instead_of_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            directory = Path(tmp) / "collection_directory"
            directory.mkdir()
            paths = replace(paths, collection_log_csv=directory)

            with self.assertRaises(load_raw.InvalidInputTypeError) as ctx:
                load_raw.load_raw_inputs(paths)
            self.assertIn("not a regular file", str(ctx.exception))

    def test_empty_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            empty = Path(tmp) / "empty_movies.csv"
            empty.write_text("", encoding="utf-8-sig")
            paths = replace(paths, movies_csv=empty)

            with self.assertRaises(load_raw.CsvHeaderError) as ctx:
                load_raw.load_raw_inputs(paths)
            self.assertIn("has no CSV header", str(ctx.exception))

    def test_missing_csv_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            no_header = Path(tmp) / "no_header_movies.csv"
            no_header.write_text("a,b\n1,2\n", encoding="utf-8-sig")
            paths = replace(paths, movies_csv=no_header)

            with self.assertRaises(load_raw.CsvHeaderError) as ctx:
                load_raw.load_raw_inputs(paths)
            self.assertIn("missing required columns", str(ctx.exception))

    def test_duplicate_csv_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            duplicate_header_path = Path(tmp) / "duplicate_header_movies.csv"
            header = tuple(MOVIES_HEADER) + ("source_url_doanhthuphim",)
            rows = [tuple(row[column] for column in MOVIES_HEADER) + ("x",) for row in _movie_rows(92)]
            _write_csv_matrix(duplicate_header_path, header, rows)
            paths = replace(paths, movies_csv=duplicate_header_path)

            with self.assertRaises(load_raw.CsvHeaderError) as ctx:
                load_raw.load_raw_inputs(paths)
            self.assertIn("duplicate header names", str(ctx.exception))

    def test_csv_header_empty_name_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            invalid_path = Path(tmp) / "empty_header_name_movies.csv"
            header = ("",) + MOVIES_HEADER[1:]
            rows = [
                tuple(row[column] for column in MOVIES_HEADER)
                for row in _movie_rows(92)
            ]
            _write_csv_matrix(invalid_path, header, rows)
            paths = replace(paths, movies_csv=invalid_path)

            with self.assertRaises(load_raw.CsvHeaderError) as ctx:
                load_raw.load_raw_inputs(paths)
            message = str(ctx.exception)
            self.assertIn("invalid header names", message)
            self.assertIn(str(list(header)), message)

    def test_csv_header_whitespace_only_name_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            invalid_path = Path(tmp) / "whitespace_header_name_movies.csv"
            header = ("   ",) + MOVIES_HEADER[1:]
            rows = [
                tuple(row[column] for column in MOVIES_HEADER)
                for row in _movie_rows(92)
            ]
            _write_csv_matrix(invalid_path, header, rows)
            paths = replace(paths, movies_csv=invalid_path)

            with self.assertRaises(load_raw.CsvHeaderError) as ctx:
                load_raw.load_raw_inputs(paths)
            message = str(ctx.exception)
            self.assertIn("invalid header names", message)
            self.assertIn(str(list(header)), message)

    def test_csv_header_name_with_outer_whitespace_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            invalid_path = Path(tmp) / "outer_whitespace_header_movies.csv"
            header = (" movie_name",) + MOVIES_HEADER[1:]
            rows = [
                tuple(row[column] for column in MOVIES_HEADER)
                for row in _movie_rows(92)
            ]
            _write_csv_matrix(invalid_path, header, rows)
            paths = replace(paths, movies_csv=invalid_path)

            with self.assertRaises(load_raw.CsvHeaderError) as ctx:
                load_raw.load_raw_inputs(paths)
            message = str(ctx.exception)
            self.assertIn("invalid header names", message)
            self.assertIn(str(list(header)), message)

    def test_csv_row_with_extra_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            extra_path = Path(tmp) / "extra_field_movies.csv"
            rows = [tuple(row[column] for column in MOVIES_HEADER) for row in _movie_rows(92)]
            rows[0] = rows[0] + ("unexpected",)
            _write_csv_matrix(extra_path, MOVIES_HEADER, rows)
            paths = replace(paths, movies_csv=extra_path)

            with self.assertRaises(load_raw.CsvRowShapeError) as ctx:
                load_raw.load_raw_inputs(paths)
            self.assertIn("row 2 has extra fields", str(ctx.exception))

    def test_csv_row_with_missing_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            short_path = Path(tmp) / "short_row_movies.csv"
            rows = [tuple(row[column] for column in MOVIES_HEADER) for row in _movie_rows(92)]
            rows[0] = rows[0][:-1]
            _write_csv_matrix(short_path, MOVIES_HEADER, rows)
            paths = replace(paths, movies_csv=short_path)

            with self.assertRaises(load_raw.CsvRowShapeError) as ctx:
                load_raw.load_raw_inputs(paths)
            self.assertIn("row 2 has missing fields", str(ctx.exception))

    def test_malformed_jsonl_reports_exact_line_number(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            malformed = Path(tmp) / "malformed.jsonl"
            records = _jsonl_records(92)
            lines = [
                json.dumps(records[0], ensure_ascii=False),
                "{this is not json}",
                json.dumps(records[2], ensure_ascii=False),
            ]
            malformed.write_text("\n".join(lines) + "\n", encoding="utf-8")
            paths = replace(paths, boxoffice_matches_jsonl=malformed)

            with self.assertRaises(load_raw.JsonlParseError) as ctx:
                load_raw.load_raw_inputs(paths)
            self.assertIn("line 2", str(ctx.exception))

    def test_jsonl_non_object_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            non_object = Path(tmp) / "non_object.jsonl"
            records = _jsonl_records(92)
            lines = [
                json.dumps(records[0], ensure_ascii=False),
                "[]",
                json.dumps(records[2], ensure_ascii=False),
            ]
            non_object.write_text("\n".join(lines) + "\n", encoding="utf-8")
            paths = replace(paths, boxoffice_matches_jsonl=non_object)

            with self.assertRaises(load_raw.JsonlParseError) as ctx:
                load_raw.load_raw_inputs(paths)
            self.assertIn("line 2", str(ctx.exception))
            self.assertIn("expected a JSON object", str(ctx.exception))

    def test_jsonl_identifier_as_list_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            records = _jsonl_records(92)
            records[0]["source_url_doanhthuphim"] = ["not", "a", "string"]
            _write_jsonl(paths.boxoffice_matches_jsonl, records)

            with self.assertRaises(load_raw.MissingIdentifierError) as ctx:
                load_raw.load_raw_inputs(paths)
            message = str(ctx.exception)
            self.assertIn(str(paths.boxoffice_matches_jsonl), message)
            self.assertIn("line 1", message)
            self.assertIn("source_url_doanhthuphim", message)
            self.assertIn("must be a string", message)
            self.assertIn("list", message)

    def test_jsonl_identifier_as_dictionary_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            records = _jsonl_records(92)
            records[0]["source_url_doanhthuphim"] = {"url": "not-a-string"}
            _write_jsonl(paths.boxoffice_matches_jsonl, records)

            with self.assertRaises(load_raw.MissingIdentifierError) as ctx:
                load_raw.load_raw_inputs(paths)
            message = str(ctx.exception)
            self.assertIn(str(paths.boxoffice_matches_jsonl), message)
            self.assertIn("line 1", message)
            self.assertIn("source_url_doanhthuphim", message)
            self.assertIn("must be a string", message)
            self.assertIn("dict", message)

    def test_jsonl_string_identifier_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            records = _jsonl_records(92)
            identifier = "https://example.test/custom/string-identifier"
            records[0]["source_url_doanhthuphim"] = identifier
            _write_jsonl(paths.boxoffice_matches_jsonl, records)

            raw = load_raw.load_raw_inputs(paths)
            self.assertEqual(
                raw.boxoffice_matches[0]["source_url_doanhthuphim"], identifier
            )

    def test_unexpected_record_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            short_movies = Path(tmp) / "short_movies.csv"
            _write_csv_dict(short_movies, MOVIES_HEADER, _movie_rows(91))
            paths = replace(paths, movies_csv=short_movies)

            with self.assertRaises(load_raw.RecordCountMismatchError) as ctx:
                load_raw.load_raw_inputs(paths)
            self.assertIn("has 91 records; expected 92", str(ctx.exception))

    def test_duplicate_identifier_where_uniqueness_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            duplicate_path = Path(tmp) / "duplicate_url_movies.csv"
            rows = _movie_rows(92)
            rows[1]["source_url_doanhthuphim"] = rows[0]["source_url_doanhthuphim"]
            _write_csv_dict(duplicate_path, MOVIES_HEADER, rows)
            paths = replace(paths, movies_csv=duplicate_path)

            with self.assertRaises(load_raw.DuplicateIdentifierError) as ctx:
                load_raw.load_raw_inputs(paths)
            self.assertIn("duplicate 'source_url_doanhthuphim'", str(ctx.exception))

    def test_valid_dataset_returns_all_four_named_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            raw = load_raw.load_raw_inputs(paths)

            self.assertIsInstance(raw, load_raw.RawInputs)
            self.assertEqual(len(raw.movies), 92)
            self.assertEqual(len(raw.collection_log), 92)
            self.assertEqual(len(raw.tickets_sold_web), 92)
            self.assertEqual(len(raw.boxoffice_matches), 92)
            self.assertEqual(
                set(raw.__dataclass_fields__),
                {
                    "movies",
                    "collection_log",
                    "tickets_sold_web",
                    "boxoffice_matches",
                },
            )

    def test_csv_values_remain_unmodified_strings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            raw = load_raw.load_raw_inputs(paths)

            first = raw.movies[0]
            self.assertEqual(first["movie_name"], "  Phim  test — Đưa  ")
            self.assertEqual(first["release_year"], "2024")
            self.assertTrue(all(isinstance(value, str) for value in first.values()))
            self.assertTrue(all(isinstance(value, str) for row in raw.movies for value in row.values()))


    def test_not_found_record_may_omit_bov_detail_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            records = _jsonl_records(92)
            record = records[0]
            record["match_status"] = "not_found"
            record["collection_status"] = "not_found"
            record["source_url_bovn"] = None
            record["revenue_bovn"] = None
            for key in BOV_DETAIL_KEYS:
                record.pop(key, None)
            _write_jsonl(paths.boxoffice_matches_jsonl, records)

            raw = load_raw.load_raw_inputs(paths)
            loaded = raw.boxoffice_matches[0]
            self.assertEqual(loaded["match_status"], "not_found")
            self.assertIsNone(loaded["source_url_bovn"])
            self.assertIsNone(loaded["revenue_bovn"])
            for key in BOV_DETAIL_KEYS:
                self.assertNotIn(key, loaded)

    def test_not_found_record_may_use_explicit_null_bov_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            records = _jsonl_records(92)
            record = records[0]
            record["match_status"] = "not_found"
            record["collection_status"] = "not_found"
            record["source_url_bovn"] = None
            record["revenue_bovn"] = None
            for key in BOV_DETAIL_KEYS:
                record[key] = None
            _write_jsonl(paths.boxoffice_matches_jsonl, records)

            raw = load_raw.load_raw_inputs(paths)
            loaded = raw.boxoffice_matches[0]
            self.assertIsNone(loaded["source_url_bovn"])
            self.assertIsNone(loaded["revenue_bovn"])
            for key in BOV_DETAIL_KEYS:
                self.assertIn(key, loaded)
                self.assertIsNone(loaded[key])

    def test_matched_record_requires_all_bov_detail_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            for missing_key in BOV_DETAIL_KEYS:
                with self.subTest(missing_key=missing_key):
                    records = _jsonl_records(92)
                    self.assertEqual(records[0]["match_status"], "matched")
                    del records[0][missing_key]
                    _write_jsonl(paths.boxoffice_matches_jsonl, records)

                    with self.assertRaises(load_raw.JsonlSchemaError) as ctx:
                        load_raw.load_raw_inputs(paths)
                    self.assertIn("line 1", str(ctx.exception))
                    self.assertIn(missing_key, str(ctx.exception))

    def test_matched_record_with_all_required_fields_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            records = _jsonl_records(92)
            _write_jsonl(paths.boxoffice_matches_jsonl, records)

            raw = load_raw.load_raw_inputs(paths)
            loaded = raw.boxoffice_matches[0]
            self.assertEqual(loaded["match_status"], "matched")
            for key in BOV_DETAIL_KEYS:
                self.assertIn(key, loaded)

    def test_needs_review_record_with_complete_bov_fields_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            records = _jsonl_records(92)
            records[0]["match_status"] = "needs_review"
            records[0]["collection_status"] = "needs_review"
            records[0]["match_reason"] = "ambiguous_or_low_confidence"
            records[0]["_bov_candidate"] = {
                "title": "Candidate title",
                "href": "https://bov.test/candidate",
            }
            _write_jsonl(paths.boxoffice_matches_jsonl, records)

            raw = load_raw.load_raw_inputs(paths)
            loaded = raw.boxoffice_matches[0]
            self.assertEqual(loaded["match_status"], "needs_review")
            self.assertEqual(loaded["_bov_candidate"]["title"], "Candidate title")

    def test_needs_review_record_cannot_use_not_found_sparse_form(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            records = _jsonl_records(92)
            records[0]["match_status"] = "needs_review"
            for key in BOV_DETAIL_KEYS:
                records[0].pop(key, None)
            _write_jsonl(paths.boxoffice_matches_jsonl, records)

            with self.assertRaises(load_raw.JsonlSchemaError) as ctx:
                load_raw.load_raw_inputs(paths)
            self.assertIn("line 1", str(ctx.exception))
            self.assertIn("match_status 'needs_review'", str(ctx.exception))

    def test_not_found_record_still_requires_non_optional_bov_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            for missing_key in ("source_url_bovn", "revenue_bovn"):
                with self.subTest(missing_key=missing_key):
                    records = _jsonl_records(92)
                    records[0]["match_status"] = "not_found"
                    del records[0][missing_key]
                    _write_jsonl(paths.boxoffice_matches_jsonl, records)

                    with self.assertRaises(load_raw.JsonlSchemaError) as ctx:
                        load_raw.load_raw_inputs(paths)
                    self.assertIn(missing_key, str(ctx.exception))

    def test_jsonl_wrong_field_types_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            bad_values = (
                ("match_score", "high"),
                ("source_url_bovn", ["not", "a", "string"]),
                ("revenue_bovn", 123),
                ("bov_title", {"title": "not-a-string"}),
                ("bov_release_info", 45),
                ("_bov_candidate", "not-a-dict-or-bool"),
                ("_bov_detail_raw", ["not-a-string"]),
            )
            for field, value in bad_values:
                with self.subTest(field=field):
                    records = _jsonl_records(92)
                    records[0][field] = value
                    _write_jsonl(paths.boxoffice_matches_jsonl, records)

                    with self.assertRaises(load_raw.JsonlSchemaError) as ctx:
                        load_raw.load_raw_inputs(paths)
                    self.assertIn("line 1", str(ctx.exception))
                    self.assertIn(field, str(ctx.exception))

    def test_jsonl_missing_identity_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            records = _jsonl_records(92)
            del records[0]["movie_name"]
            _write_jsonl(paths.boxoffice_matches_jsonl, records)

            with self.assertRaises(load_raw.JsonlSchemaError) as ctx:
                load_raw.load_raw_inputs(paths)
            self.assertIn("movie_name", str(ctx.exception))

    def test_jsonl_empty_identifier_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            records = _jsonl_records(92)
            records[0]["source_url_doanhthuphim"] = "   "
            _write_jsonl(paths.boxoffice_matches_jsonl, records)

            with self.assertRaises(load_raw.MissingIdentifierError) as ctx:
                load_raw.load_raw_inputs(paths)
            self.assertIn("source_url_doanhthuphim", str(ctx.exception))

    def test_jsonl_invalid_match_status_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            for status in ("pending", 123, None):
                with self.subTest(status=status):
                    records = _jsonl_records(92)
                    records[0]["match_status"] = status
                    _write_jsonl(paths.boxoffice_matches_jsonl, records)

                    with self.assertRaises(load_raw.JsonlSchemaError) as ctx:
                        load_raw.load_raw_inputs(paths)
                    self.assertIn("match_status", str(ctx.exception))

    def test_duplicate_jsonl_source_identifier_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _valid_paths(Path(tmp))
            records = _jsonl_records(92)
            records[1]["source_url_doanhthuphim"] = records[0][
                "source_url_doanhthuphim"
            ]
            _write_jsonl(paths.boxoffice_matches_jsonl, records)

            with self.assertRaises(load_raw.DuplicateIdentifierError) as ctx:
                load_raw.load_raw_inputs(paths)
            self.assertIn("duplicate 'source_url_doanhthuphim'", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
