"""Standard-library tests for in-memory analytics dataset assembly."""

from __future__ import annotations

import copy
import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

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


builder = _load_module(
    ANALYTICS_DIR / "build_dataset.py", "analytics_build_dataset_under_test"
)
load_raw = builder.load_raw
ids = builder.ids

# Fixture values are CSV line numbers, matching raw_source_row_dtp.
QUARANTINED_LINE = 51
CANDIDATE_LINE = 84
NO_REVENUE_LINE = 34
NOT_FOUND_LINES = frozenset({81, 82, 83, 85, 86, 87, 88, 89, 90, 92})
FOUND_TICKET_LINES = frozenset({2, 3, 4, 5, 6})
NEEDS_REVIEW_TICKET_LINES = frozenset({8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 49})


def _url(line: int) -> str:
    return f"https://doanhthuphim.vn/phim/film-{line:04d}"


def _movie_id(line: int) -> str:
    return f"M{line - 1:04d}"


def _movie_row(line: int, decision: str | None, warn: bool) -> dict[str, str]:
    not_found = line in NOT_FOUND_LINES
    needs_review = line == CANDIDATE_LINE
    matched = not not_found and not needs_review
    source_url_bovn = "" if not_found else f"https://v1.boxofficevietnam.com/movie/{line}"

    if line in (2, 3):
        dtp_raw = "hơn 46 tỷ" if line == 2 else "hơn 21 tỷ"
    else:
        dtp_raw = "100 tỷ"
    if (decision == "accepted" and warn) or decision == "candidate_held":
        bov_raw = "150,000,000,000₫"
    elif decision in {"accepted", "quarantined"}:
        bov_raw = "100,000,000,000₫"
    else:
        bov_raw = ""

    return {
        "movie_name": f"Film {line:04d}",
        "title_bovn": "" if not_found else f"Film {line:04d} BOV",
        "original_title": "",
        "release_year": "2024",
        "genre": "Drama",
        "director": f"Director {line:04d}",
        "revenue_doanhthuphim": dtp_raw,
        "revenue_bovn": bov_raw,
        "source_url_doanhthuphim": _url(line),
        "source_url_bovn": source_url_bovn,
        "_matched": "matched" if matched else ("needs_review" if needs_review else "not_found"),
    }


def _collection_row(line: int, match_status: str) -> dict[str, str]:
    return {
        "source_url_doanhthuphim": _url(line),
        "match_status": match_status,
        "match_score": "0.90" if match_status == "matched" else ("0.40" if match_status == "needs_review" else ""),
        "match_reason": (
            "auto" if match_status == "matched" else ("below_threshold" if match_status == "needs_review" else "no_candidates")
        ),
    }


def _ticket_row(line: int) -> dict[str, str]:
    found = line in FOUND_TICKET_LINES
    needs_review = line in NEEDS_REVIEW_TICKET_LINES
    status = "found" if found else ("needs_review" if needs_review else "not_found")
    populated = found or needs_review
    return {
        "source_url_doanhthuphim": _url(line),
        "tickets_sold_web": "1000000" if populated else "",
        "tickets_display": "1 triệu vé" if populated else "",
        "tickets_basis": "cumulative" if populated else "",
        "ticket_status": status,
        "source_title": f"Ticket headline {line}" if populated else "",
        "source_url": f"https://example.com/ticket-{line}" if populated else "",
        "source_name": "Example News" if populated else "",
    }


def _boxoffice_row(movie: dict[str, str], match_status: str) -> dict[str, object]:
    return {
        "movie_name": movie["movie_name"],
        "source_url_doanhthuphim": movie["source_url_doanhthuphim"],
        "source_url_bovn": movie["source_url_bovn"],
        "match_status": match_status,
        "match_score": 0.9 if match_status == "matched" else None,
        "match_reason": "auto" if match_status == "matched" else "no_candidates",
        "revenue_bovn": movie["revenue_bovn"],
        "bov_title": movie["title_bovn"],
        "bov_release_info": "2024",
        "_bov_candidate": None,
        "_bov_detail_raw": None,
    }


def _decision_for(line: int) -> str | None:
    if line == QUARANTINED_LINE:
        return "quarantined"
    if line == CANDIDATE_LINE:
        return "candidate_held"
    if line == NO_REVENUE_LINE or line in NOT_FOUND_LINES:
        return None
    return "accepted"


def _mapping_payload() -> dict[str, object]:
    created = "2026-01-01T00:00:00Z"
    movies: list[dict[str, object]] = []
    for line in range(2, 94):
        decision = _decision_for(line)
        review = None
        if decision is not None:
            review = {
                "decision": decision,
                "reason": {
                    "accepted": "matcher_accepted_bov_revenue",
                    "quarantined": "sequel_number_error",
                    "candidate_held": "different_subtitle",
                }[decision],
                "reviewed_at": None,
                "reviewer": None,
            }
        movies.append(
            {
                "movie_id": _movie_id(line),
                "source_url_dtp": _url(line),
                "canonical_title": f"Film {line:04d}",
                "release_year": 2024,
                "director_raw": f"Director {line:04d}",
                "url_history": [
                    {
                        "source_url_dtp": _url(line),
                        "first_seen_at": created,
                        "last_seen_at": created,
                        "verification": "initial_seed",
                        "approved_by": None,
                        "approved_at": None,
                    }
                ],
                "status": "active",
                "created_at": created,
                "last_seen_at": created,
                "notes": None,
                "revenue_review": review,
            }
        )
    return {
        "schema_version": ids.SUPPORTED_SCHEMA_VERSION,
        "generated_at": created,
        "source_anchor": ids.SOURCE_ANCHOR,
        "id_prefix": builder.schema.ID_PREFIX,
        "movies": movies,
    }


def _write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _make_fixture(root: Path) -> tuple[load_raw.RawInputPaths, Path]:
    accepted_lines = [line for line in range(2, 94) if _decision_for(line) == "accepted"]
    warning_lines = set(accepted_lines[:20])

    movie_payloads: list[dict[str, str]] = []
    collection_payloads: list[dict[str, str]] = []
    for line in range(2, 94):
        decision = _decision_for(line)
        movie = _movie_row(line, decision, line in warning_lines)
        match_status = movie.pop("_matched")
        movie_payloads.append(movie)
        collection_payloads.append(_collection_row(line, match_status))

    _write_csv(
        root / "movies.csv",
        load_raw.MOVIES_CSV_SPEC.required_columns,
        movie_payloads,
    )
    _write_csv(
        root / "collection_log.csv",
        load_raw.COLLECTION_LOG_CSV_SPEC.required_columns,
        collection_payloads,
    )
    _write_csv(
        root / "tickets_sold_web.csv",
        load_raw.TICKETS_SOLD_WEB_CSV_SPEC.required_columns,
        [_ticket_row(line) for line in range(2, 94)],
    )
    with (root / "boxoffice_matches.jsonl").open("w", encoding="utf-8") as handle:
        for movie, collection in zip(movie_payloads, collection_payloads):
            handle.write(
                json.dumps(
                    _boxoffice_row(movie, collection["match_status"]),
                    ensure_ascii=False,
                )
                + "\n"
            )

    mapping_path = root / "mapping.json"
    mapping_path.write_text(
        json.dumps(_mapping_payload(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    paths = load_raw.RawInputPaths(
        movies_csv=root / "movies.csv",
        collection_log_csv=root / "collection_log.csv",
        tickets_sold_web_csv=root / "tickets_sold_web.csv",
        boxoffice_matches_jsonl=root / "boxoffice_matches.jsonl",
    )
    return paths, mapping_path


class BuildDatasetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths, self.mapping_path = _make_fixture(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _build(self) -> builder.AnalyticsBuildResult:
        return builder.build_analytics_dataset(
            self.paths, mapping_path=self.mapping_path, seen_at="2026-01-02T00:00:00Z"
        )

    def test_successful_orchestration_and_all_invariants(self) -> None:
        result = self._build()
        self.assertEqual(len(result.rows), 92)
        self.assertEqual(tuple(result.rows[0]), tuple(builder.schema.FINAL_COLUMNS))
        self.assertEqual(builder.schema.FINAL_COLUMNS[0], "movie_id")
        self.assertEqual(len(set(builder.schema.FINAL_COLUMNS)), 54)
        self.assertEqual(
            result.validation,
            {
                "row_count": 92,
                "column_count": 54,
                "dtp_observations": 92,
                "accepted_bov_revenue": 79,
                "quarantined_bov_revenue": 1,
                "candidate_bov_revenue": 1,
                "eligible_revenue_comparisons": 79,
                "magnitude_gap_warnings": 21,
                "accepted_gap_warnings": 20,
                "candidate_gap_warnings": 1,
                "deduplicated_ticket_candidates": 16,
                "found_ticket_candidates": 5,
                "needs_review_ticket_candidates": 11,
                "movies_without_candidates": 76,
            },
        )

    def test_stable_id_join_and_revenue_ticket_segregation(self) -> None:
        result = self._build()
        by_url = {row["source_url_dtp"]: row["movie_id"] for row in result.rows}
        self.assertEqual(by_url, dict(result.id_assignment.movie_ids_by_url))
        by_id = {row["movie_id"]: row for row in result.rows}

        quarantined = by_id[_movie_id(QUARANTINED_LINE)]
        self.assertEqual(quarantined["bov_quarantined_revenue_vnd"], 100_000_000_000)
        self.assertIsNone(quarantined["bov_revenue_vnd"])
        self.assertEqual(quarantined["mapping_validation_status"], "known_false_positive_quarantined")
        self.assertEqual(quarantined["review_status"], "pending")
        self.assertEqual(quarantined["review_priority"], "high")

        candidate = by_id[_movie_id(CANDIDATE_LINE)]
        self.assertEqual(candidate["bov_candidate_revenue_vnd"], 150_000_000_000)
        self.assertIsNone(candidate["bov_revenue_vnd"])
        self.assertIsNone(candidate["revenue_gap_pct"])
        self.assertEqual(candidate["magnitude_gap_warning"], 1)
        self.assertEqual(candidate["ticket_data_status"], "no_candidates")

        first = by_id["M0001"]
        self.assertEqual(first["dtp_revenue_quality"], "lower_bound")
        self.assertEqual(first["dtp_revenue_vnd"], 46_000_000_000)
        self.assertEqual(first["ticket_found_count"], 1)
        self.assertEqual(first["ticket_verified_admissions"], None)

        high_priority_ids = {
            row["movie_id"] for row in result.rows if row["review_priority"] == "high"
        }
        self.assertEqual(
            high_priority_ids,
            {_movie_id(line) for line in builder.HIGH_PRIORITY_SOURCE_ROWS},
        )
        pending_ids = {row["movie_id"] for row in result.rows if row["has_pending_review"] == 1}
        self.assertEqual(len(pending_ids), 6)
        self.assertTrue(pending_ids <= high_priority_ids)

    def test_missing_mapping_failure(self) -> None:
        missing = self.root / "does-not-exist.json"
        with self.assertRaises(ids.MissingMovieIdMappingError):
            builder.build_analytics_dataset(
                self.paths, mapping_path=missing, seen_at="2026-01-02T00:00:00Z"
            )

    def test_corrupt_mapping_failure(self) -> None:
        corrupt = self.root / "corrupt-mapping.json"
        corrupt.write_text("{not json", encoding="utf-8")
        with self.assertRaises(ids.MovieIdMappingInvalidError):
            builder.build_analytics_dataset(
                self.paths, mapping_path=corrupt, seen_at="2026-01-02T00:00:00Z"
            )

    def test_duplicate_movie_id_rejection(self) -> None:
        rows = copy.deepcopy(list(self._build().rows))
        rows[1]["movie_id"] = rows[0]["movie_id"]
        with self.assertRaises(builder.DatasetValidationError) as caught:
            builder.validate_dataset(rows)
        self.assertIn("duplicate_movie_ids", str(caught.exception))

    def test_missing_and_extra_columns_rejection(self) -> None:
        rows = copy.deepcopy(list(self._build().rows))
        missing = copy.deepcopy(rows)
        del missing[0]["genre_raw"]
        with self.assertRaises(builder.DatasetValidationError) as caught:
            builder.validate_dataset(missing)
        self.assertIn("columns", str(caught.exception))

        extra = copy.deepcopy(rows)
        extra[0]["unexpected_column"] = "x"
        with self.assertRaises(builder.DatasetValidationError) as caught:
            builder.validate_dataset(extra)
        self.assertIn("columns", str(caught.exception))

    def test_null_preservation(self) -> None:
        rows = self._build().rows
        by_id = {row["movie_id"]: row for row in rows}
        no_revenue = by_id[_movie_id(NO_REVENUE_LINE)]
        self.assertIsNone(no_revenue["bov_revenue_raw"])
        self.assertIsNone(no_revenue["bov_revenue_vnd"])
        self.assertIsNone(no_revenue["revenue_gap_pct"])
        self.assertEqual(no_revenue["magnitude_gap_warning"], 0)

        not_found = by_id[_movie_id(85)]
        self.assertIsNone(not_found["bov_url"])
        self.assertIsNone(not_found["ticket_evidence_urls"])
        self.assertEqual(not_found["ticket_candidate_count"], 0)
        self.assertTrue(all(row["ticket_verified_admissions"] is None for row in rows))

    def test_inputs_are_unchanged_and_no_files_are_persisted(self) -> None:
        files = (
            self.paths.movies_csv,
            self.paths.collection_log_csv,
            self.paths.tickets_sold_web_csv,
            self.paths.boxoffice_matches_jsonl,
            self.mapping_path,
        )
        before = {path: path.read_bytes() for path in files}
        before_names = {path.name for path in self.root.iterdir()}
        raw_inputs = load_raw.load_raw_inputs(self.paths)
        raw_snapshot = copy.deepcopy(raw_inputs)

        self._build()

        self.assertEqual(raw_inputs, raw_snapshot)
        self.assertEqual({path: path.read_bytes() for path in files}, before)
        self.assertEqual({path.name for path in self.root.iterdir()}, before_names)
        self.assertFalse((self.root / "movie_analytics.csv").exists())

    def test_paths_and_raw_inputs_are_mutually_exclusive(self) -> None:
        raw_inputs = load_raw.load_raw_inputs(self.paths)
        with self.assertRaises(builder.AnalyticsBuildError):
            builder.build_analytics_dataset(
                self.paths,
                mapping_path=self.mapping_path,
                raw_inputs=raw_inputs,
            )


if __name__ == "__main__":
    unittest.main()
