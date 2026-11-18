"""Standard-library tests for stable movie ID mapping and assignment."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IDS_PATH = PROJECT_ROOT / "src" / "movie_data_collector" / "analytics" / "ids.py"
CLEAN_PATH = PROJECT_ROOT / "src" / "movie_data_collector" / "analytics" / "clean.py"


def _load_module(path: Path, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ids: ModuleType = _load_module(IDS_PATH, "analytics_ids_under_test")
clean: ModuleType = _load_module(CLEAN_PATH, "analytics_clean_under_test_ids")

FieldStatus = clean.FieldStatus

TS_OLD = "2026-01-01T00:00:00Z"
TS_MID = "2026-02-01T00:00:00Z"
TS_NEW = "2026-03-01T00:00:00Z"
TS_NAIVE_OLD = "2026-01-01T00:00:00"
TS_NAIVE_NEW = "2026-01-02T00:00:00"
TS_OFFSET_01Z = "2026-01-01T08:00:00+07:00"
TS_UTC_0130Z = "2026-01-01T01:30:00Z"
TS_CHANGE_OFFSET = "2026-03-01T08:00:00+07:00"
TS_CHANGE_UTC_0130Z = "2026-03-01T01:30:00Z"
DEFAULT_DIRECTOR = "Nguyễn Văn Đức"
DEFAULT_DIRECTOR_ALT = "NGUYEN VAN DUC"


def _url(name: str) -> str:
    return f"https://doanhthuphim.vn/phim/{name}"


def _movie(
    url: str,
    title: str,
    *,
    year: int | None = 2024,
    director: str | None = DEFAULT_DIRECTOR,
    row: int = 2,
) -> Any:
    return clean.CleanedMovie(
        raw_source_row_dtp=row,
        movie_name_raw=title,
        canonical_title=title,
        title_status=FieldStatus.VALID if title.strip() else FieldStatus.MISSING,
        original_title_source=None,
        original_title_raw=None,
        original_title_status=FieldStatus.MISSING,
        release_year_source=str(year) if year is not None else "",
        release_year=year,
        release_year_status=FieldStatus.VALID if year is not None else FieldStatus.MISSING,
        genre_source="",
        genre_raw=None,
        genre_status=FieldStatus.MISSING,
        genre_tokens=(),
        genre_token_path=None,
        genre_grouped=None,
        director_source=director,
        director_raw=director,
        director_status=FieldStatus.VALID if director else FieldStatus.MISSING,
        director_norm_key=(
            clean._normalize_grouping_key(director) if director else None
        ),
        source_url_dtp=url,
        source_url_dtp_status=FieldStatus.VALID,
    )


def _revenue_review(
    decision: str,
    *,
    reason: str | None = None,
    reviewed_at: str | None = None,
    reviewer: str | None = None,
) -> dict[str, Any]:
    return {
        "decision": decision,
        "reason": reason,
        "reviewed_at": reviewed_at,
        "reviewer": reviewer,
    }


def _history(
    url: str,
    *,
    verification: str = "initial_seed",
    first: str = TS_OLD,
    last: str = TS_OLD,
    approved_by: str | None = None,
    approved_at: str | None = None,
) -> dict[str, Any]:
    return {
        "source_url_dtp": url,
        "first_seen_at": first,
        "last_seen_at": last,
        "verification": verification,
        "approved_by": approved_by,
        "approved_at": approved_at,
    }


def _mapped(
    movie_id: str,
    url: str,
    title: str,
    *,
    year: int | None = 2024,
    director: str | None = DEFAULT_DIRECTOR,
    history: list[dict[str, Any]] | None = None,
    status: str = "active",
    notes: str | None = None,
    created_at: str = TS_OLD,
    last_seen_at: str = TS_MID,
    revenue_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "movie_id": movie_id,
        "source_url_dtp": url,
        "canonical_title": title,
        "release_year": year,
        "director_raw": director,
        "url_history": history if history is not None else [_history(url)],
        "status": status,
        "created_at": created_at,
        "last_seen_at": last_seen_at,
    }
    if notes is not None:
        record["notes"] = notes
    if revenue_review is not None:
        record["revenue_review"] = revenue_review
    return record


def _payload(
    movies: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "generated_at": TS_MID,
        "source_anchor": "source_url_doanhthuphim",
        "id_prefix": "M",
        "movies": movies if movies is not None else [],
    }
    payload.update(overrides)
    return payload


def _payload_from_mapping(mapping: Any) -> dict[str, Any]:
    return json.loads(json.dumps(asdict(mapping)))


def _validated(
    movies: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> Any:
    return ids.validate_movie_id_mapping(_payload(movies, **overrides))


class AnalyticsIdsTests(unittest.TestCase):
    def _assert_invalid(self, callback: Any) -> Any:
        with self.assertRaises(ids.MovieIdMappingInvalidError) as context:
            callback()
        self.assertEqual(context.exception.code, "ID_MAPPING_INVALID")
        return context.exception

    def _assert_unresolved(self, callback: Any) -> Any:
        with self.assertRaises(ids.MovieIdMappingUnresolvedError) as context:
            callback()
        self.assertEqual(context.exception.code, "ID_MAPPING_UNRESOLVED")
        return context.exception

    def test_valid_mapping_loads_successfully(self) -> None:
        payload = _payload([_mapped("M0001", _url("a"), "Phim A")])

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "mapping.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            mapping = ids.load_movie_id_mapping(path)

        self.assertIsInstance(mapping, ids.MovieIdMapping)
        self.assertEqual(mapping.schema_version, "1.0")
        self.assertEqual(mapping.generated_at, TS_MID)
        self.assertEqual(mapping.movies[0].movie_id, "M0001")
        self.assertEqual(mapping.movies[0].source_url_dtp, _url("a"))
        self.assertEqual(mapping.movies[0].url_history[0].verification, "initial_seed")

    def test_missing_mapping_file_raises_expected_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.json"
            error = self._assert_invalid(lambda: ids.load_movie_id_mapping(missing))

        self.assertIsInstance(error, ids.MissingMovieIdMappingError)
        self.assertIn(str(missing), str(error))

    def test_malformed_json_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "mapping.json"
            path.write_text("{not json", encoding="utf-8")
            error = self._assert_invalid(lambda: ids.load_movie_id_mapping(path))

        self.assertIn("invalid JSON", str(error))

    def test_missing_required_fields_are_rejected(self) -> None:
        base = _payload([_mapped("M0001", _url("a"), "Phim A")])

        top_level = copy.deepcopy(base)
        del top_level["id_prefix"]
        self._assert_invalid(
            lambda payload=top_level: ids.validate_movie_id_mapping(payload)
        )

        movie_level = copy.deepcopy(base)
        del movie_level["movies"][0]["status"]
        self._assert_invalid(
            lambda payload=movie_level: ids.validate_movie_id_mapping(payload)
        )

        history_level = copy.deepcopy(base)
        del history_level["movies"][0]["url_history"][0]["approved_by"]
        self._assert_invalid(
            lambda payload=history_level: ids.validate_movie_id_mapping(payload)
        )

    def test_unknown_fields_are_rejected(self) -> None:
        extra_top = _payload([_mapped("M0001", _url("a"), "Phim A")], surprise=True)
        self._assert_invalid(
            lambda payload=extra_top: ids.validate_movie_id_mapping(payload)
        )

        extra_movie = _payload(
            [_mapped("M0001", _url("a"), "Phim A", notes="ok")]
        )
        extra_movie["movies"][0]["surprise"] = "data"
        self._assert_invalid(
            lambda payload=extra_movie: ids.validate_movie_id_mapping(payload)
        )

    def test_all_revenue_review_decisions_are_valid(self) -> None:
        for decision in ("accepted", "quarantined", "candidate_held", "pending"):
            with self.subTest(decision=decision):
                review = _revenue_review(
                    decision,
                    reason=f"reviewed as {decision}",
                    reviewed_at=TS_MID,
                    reviewer="Reviewer A",
                )
                mapping = _validated(
                    [_mapped("M0001", _url("a"), "Phim A", revenue_review=review)]
                )

                parsed = mapping.movies[0].revenue_review
                self.assertIsInstance(parsed, ids.RevenueReview)
                self.assertEqual(parsed.decision, decision)
                self.assertEqual(parsed.reason, f"reviewed as {decision}")
                self.assertEqual(parsed.reviewed_at, TS_MID)
                self.assertEqual(parsed.reviewer, "Reviewer A")
                self.assertEqual(
                    ids.validate_movie_id_mapping(_payload_from_mapping(mapping)),
                    mapping,
                )

    def test_invalid_revenue_review_decisions_are_rejected(self) -> None:
        for bad_decision in ("accepted_revenue", "", "QUARANTINED", 1, None):
            with self.subTest(decision=bad_decision):
                review = _revenue_review(bad_decision)  # type: ignore[arg-type]
                payload = _payload(
                    [_mapped("M0001", _url("a"), "Phim A", revenue_review=review)]
                )
                error = self._assert_invalid(
                    lambda payload=payload: ids.validate_movie_id_mapping(payload)
                )
                self.assertIn("decision", str(error))

    def test_quarantined_and_candidate_held_reviews_require_reason(self) -> None:
        for decision in ("quarantined", "candidate_held"):
            for case in ("none", "empty", "absent"):
                with self.subTest(decision=decision, case=case):
                    review = _revenue_review(decision)
                    if case == "empty":
                        review["reason"] = "   "
                    elif case == "absent":
                        del review["reason"]
                    payload = _payload(
                        [
                            _mapped(
                                "M0001",
                                _url("a"),
                                "Phim A",
                                revenue_review=review,
                            )
                        ]
                    )
                    error = self._assert_invalid(
                        lambda payload=payload: ids.validate_movie_id_mapping(payload)
                    )
                    self.assertIn("reason", str(error))

    def test_revenue_review_nullable_fields_are_preserved(self) -> None:
        for decision in ("accepted", "pending"):
            with self.subTest(decision=decision):
                mapping = _validated(
                    [
                        _mapped(
                            "M0001",
                            _url("a"),
                            "Phim A",
                            revenue_review=_revenue_review(decision),
                        )
                    ]
                )

                parsed = mapping.movies[0].revenue_review
                self.assertEqual(parsed.decision, decision)
                self.assertIsNone(parsed.reason)
                self.assertIsNone(parsed.reviewed_at)
                self.assertIsNone(parsed.reviewer)

    def test_mapping_without_revenue_review_remains_valid(self) -> None:
        for case in ("omitted", "null"):
            with self.subTest(case=case):
                payload = _payload([_mapped("M0001", _url("a"), "Phim A")])
                if case == "null":
                    payload["movies"][0]["revenue_review"] = None

                mapping = ids.validate_movie_id_mapping(payload)

                self.assertIsNone(mapping.movies[0].revenue_review)

    def test_invalid_revenue_review_field_types_are_rejected(self) -> None:
        valid_review = _revenue_review(
            "accepted",
            reason="reviewed",
            reviewed_at=TS_MID,
            reviewer="Reviewer A",
        )
        cases: dict[str, Any] = {
            "not_an_object": "accepted",
            "decision_type": {**valid_review, "decision": 1},
            "reason_type": {**valid_review, "reason": 42},
            "reviewed_at_type": {**valid_review, "reviewed_at": 42},
            "reviewed_at_format": {**valid_review, "reviewed_at": "not-a-date"},
            "reviewer_type": {**valid_review, "reviewer": []},
            "unknown_field": {**valid_review, "surprise": "data"},
        }

        for case, review in cases.items():
            with self.subTest(case=case):
                payload = _payload([_mapped("M0001", _url("a"), "Phim A")])
                payload["movies"][0]["revenue_review"] = review
                self._assert_invalid(
                    lambda payload=payload: ids.validate_movie_id_mapping(payload)
                )

    def test_invalid_revenue_review_does_not_mutate_payload(self) -> None:
        payload = _payload(
            [
                _mapped(
                    "M0001",
                    _url("a"),
                    "Phim A",
                    revenue_review=_revenue_review("quarantined"),
                )
            ]
        )
        snapshot = copy.deepcopy(payload)

        self._assert_invalid(lambda: ids.validate_movie_id_mapping(payload))

        self.assertEqual(payload, snapshot)

    def test_revenue_review_survives_stable_id_assignment(self) -> None:
        review = _revenue_review(
            "quarantined",
            reason="sequel number mismatch",
            reviewed_at=TS_MID,
            reviewer="Reviewer A",
        )
        mapping = _validated(
            [_mapped("M0001", _url("old"), "Phim A", revenue_review=review)]
        )

        result = ids.assign_stable_movie_ids(
            (_movie(_url("new"), "Phim A"),), mapping, seen_at=TS_NEW
        )

        updated = result.updated_mapping.movies[0]
        self.assertEqual(updated.movie_id, "M0001")
        self.assertEqual(updated.revenue_review, mapping.movies[0].revenue_review)
        self.assertEqual(updated.revenue_review.decision, "quarantined")
        self.assertEqual(updated.url_history[-1].source_url_dtp, _url("new"))

    def test_invalid_schema_version_is_rejected(self) -> None:
        payload = _payload(
            [_mapped("M0001", _url("a"), "Phim A")], schema_version="2.0"
        )
        error = self._assert_invalid(
            lambda: ids.validate_movie_id_mapping(payload)
        )
        self.assertIn("schema_version", str(error))

    def test_invalid_movie_id_format_is_rejected(self) -> None:
        for bad_id in ("M1", "M0000", "X0001", 123):
            with self.subTest(movie_id=bad_id):
                payload = _payload(
                    [_mapped(bad_id, _url("a"), "Phim A")]  # type: ignore[arg-type]
                )
                self._assert_invalid(
                    lambda payload=payload: ids.validate_movie_id_mapping(payload)
                )

    def test_duplicate_movie_ids_are_rejected(self) -> None:
        payload = _payload(
            [
                _mapped("M0001", _url("a"), "Phim A"),
                _mapped("M0001", _url("b"), "Phim B"),
            ]
        )
        error = self._assert_invalid(lambda: ids.validate_movie_id_mapping(payload))
        self.assertIn("duplicates ID", str(error))

    def test_duplicate_dtp_urls_are_rejected(self) -> None:
        payload = _payload(
            [
                _mapped("M0001", _url("a"), "Phim A"),
                _mapped("M0002", _url("a"), "Phim B"),
            ]
        )
        error = self._assert_invalid(lambda: ids.validate_movie_id_mapping(payload))
        self.assertIn("source_url_dtp duplicates", str(error))

    def test_duplicate_url_history_ownership_is_rejected(self) -> None:
        shared = _url("shared")
        first_history = [
            _history(_url("a")),
            _history(
                shared,
                verification="identity_match",
                first=TS_MID,
                last=TS_MID,
            ),
            _history(_url("a"), verification="identity_match", first=TS_NEW, last=TS_NEW),
        ]
        second_history = [
            _history(_url("b")),
            _history(
                shared,
                verification="identity_match",
                first=TS_MID,
                last=TS_MID,
            ),
            _history(_url("b"), verification="identity_match", first=TS_NEW, last=TS_NEW),
        ]
        payload = _payload(
            [
                _mapped("M0001", _url("a"), "Phim A", history=first_history),
                _mapped("M0002", _url("b"), "Phim B", history=second_history),
            ]
        )
        error = self._assert_invalid(lambda: ids.validate_movie_id_mapping(payload))
        self.assertIn("url_history", str(error))

    def test_duplicate_mapping_identities_are_rejected(self) -> None:
        payload = _payload(
            [
                _mapped("M0001", _url("a"), "Phim A"),
                _mapped("M0002", _url("b"), "  PHIM   A  "),
            ]
        )
        error = self._assert_invalid(lambda: ids.validate_movie_id_mapping(payload))
        self.assertIn("duplicates identity", str(error))

    def test_invalid_history_timestamps_and_enums_are_rejected(self) -> None:
        base = _payload([_mapped("M0001", _url("a"), "Phim A")])

        bad_history_url = copy.deepcopy(base)
        bad_history_url["movies"][0]["url_history"][0]["source_url_dtp"] = _url("other")
        self._assert_invalid(
            lambda payload=bad_history_url: ids.validate_movie_id_mapping(payload)
        )

        bad_status = copy.deepcopy(base)
        bad_status["movies"][0]["status"] = "paused"
        self._assert_invalid(
            lambda payload=bad_status: ids.validate_movie_id_mapping(payload)
        )

        bad_verification = copy.deepcopy(base)
        bad_verification["movies"][0]["url_history"][0]["verification"] = "guess"
        self._assert_invalid(
            lambda payload=bad_verification: ids.validate_movie_id_mapping(payload)
        )

        bad_timestamp = copy.deepcopy(base)
        bad_timestamp["movies"][0]["created_at"] = "not-a-date"
        self._assert_invalid(
            lambda payload=bad_timestamp: ids.validate_movie_id_mapping(payload)
        )

    def test_existing_movies_retain_their_ids(self) -> None:
        mapping = _validated(
            [
                _mapped("M0001", _url("a"), "Phim A"),
                _mapped("M0002", _url("b"), "Phim B"),
            ]
        )
        current = (_movie(_url("a"), "Phim A"), _movie(_url("b"), "Phim B"))

        result = ids.assign_stable_movie_ids(current, mapping, seen_at=TS_NEW)

        self.assertEqual(
            dict(result.movie_ids_by_url),
            {_url("a"): "M0001", _url("b"): "M0002"},
        )
        self.assertEqual(result.summary.reused_ids, ("M0001", "M0002"))
        self.assertEqual(result.summary.url_changed_ids, ())
        self.assertEqual(result.summary.new_ids, ())
        self.assertEqual(result.summary.unseen_mapped_urls, ())
        self.assertEqual(result.updated_mapping.generated_at, mapping.generated_at)
        self.assertEqual(
            result.updated_mapping.movies[0].canonical_title, "Phim A"
        )

    def test_first_build_ids_are_deterministic_regardless_of_input_order(self) -> None:
        first = _movie(_url("b"), "Phim B", row=3)
        second = _movie(_url("a"), "Phim A", row=4)

        reversed_result = ids.assign_initial_movie_ids(
            (first, second), generated_at=TS_MID, seen_at=TS_MID
        )
        ordered_result = ids.assign_initial_movie_ids(
            (second, first), generated_at=TS_MID, seen_at=TS_MID
        )

        expected = {_url("a"): "M0001", _url("b"): "M0002"}
        self.assertEqual(dict(reversed_result.movie_ids_by_url), expected)
        self.assertEqual(dict(ordered_result.movie_ids_by_url), expected)
        self.assertEqual(reversed_result.updated_mapping, ordered_result.updated_mapping)
        self.assertEqual(
            tuple(record.movie_id for record in reversed_result.updated_mapping.movies),
            ("M0001", "M0002"),
        )
        self.assertEqual(
            reversed_result.updated_mapping.movies[0].url_history[0].verification,
            "initial_seed",
        )

    def test_new_movies_receive_the_next_available_ordinal(self) -> None:
        mapping = _validated(
            [
                _mapped("M0001", _url("a"), "Phim A"),
                _mapped("M0003", _url("c"), "Phim C"),
            ]
        )
        current = (
            _movie(_url("a"), "Phim A"),
            _movie(_url("d"), "Phim D"),
        )

        result = ids.assign_stable_movie_ids(current, mapping, seen_at=TS_NEW)

        self.assertEqual(result.movie_ids_by_url[_url("d")], "M0004")
        self.assertEqual(result.summary.new_ids, ("M0004",))
        self.assertEqual(result.summary.unseen_mapped_urls, (_url("c"),))

    def test_removed_or_retired_ids_are_never_reused(self) -> None:
        retired_mapping = _validated(
            [
                _mapped("M0001", _url("a"), "Phim A"),
                _mapped("M0002", _url("b"), "Phim B", status="retired"),
            ]
        )
        retired_result = ids.assign_stable_movie_ids(
            (
                _movie(_url("a"), "Phim A"),
                _movie(_url("c"), "Phim C"),
            ),
            retired_mapping,
            seen_at=TS_NEW,
        )
        self.assertEqual(retired_result.movie_ids_by_url[_url("c")], "M0003")

        gap_mapping = _validated(
            [
                _mapped("M0001", _url("a"), "Phim A"),
                _mapped("M0003", _url("c"), "Phim C", status="retired"),
            ]
        )
        gap_result = ids.assign_stable_movie_ids(
            (
                _movie(_url("a"), "Phim A"),
                _movie(_url("d"), "Phim D"),
            ),
            gap_mapping,
            seen_at=TS_NEW,
        )
        self.assertEqual(gap_result.movie_ids_by_url[_url("d")], "M0004")

    def test_url_change_with_valid_identity_keeps_existing_id(self) -> None:
        mapping = _validated(
            [_mapped("M0001", _url("old"), "Phim A", director=DEFAULT_DIRECTOR)]
        )
        current = (
            _movie(
                _url("new"),
                "  PHIM   A  ",
                director=DEFAULT_DIRECTOR_ALT,
            ),
        )

        result = ids.assign_stable_movie_ids(current, mapping, seen_at=TS_NEW)

        self.assertEqual(dict(result.movie_ids_by_url), {_url("new"): "M0001"})
        self.assertEqual(result.summary.url_changed_ids, ("M0001",))
        record = result.updated_mapping.movies[0]
        self.assertEqual(record.source_url_dtp, _url("new"))
        self.assertEqual(record.url_history[-1].source_url_dtp, _url("new"))
        self.assertEqual(record.url_history[-1].verification, "identity_match")
        self.assertEqual(record.director_raw, DEFAULT_DIRECTOR_ALT)
        self.assertEqual(result.summary.unseen_mapped_urls, (_url("old"),))

    def test_reviewer_alias_url_change_keeps_existing_id(self) -> None:
        new_url = _url("new")
        history = [
            _history(_url("old")),
            _history(
                new_url,
                verification="reviewer_alias",
                first=TS_MID,
                last=TS_MID,
                approved_by="reviewer-a",
                approved_at=TS_MID,
            ),
            _history(_url("old"), verification="identity_match", first=TS_NEW, last=TS_NEW),
        ]
        mapping = _validated(
            [
                _mapped(
                    "M0001",
                    _url("old"),
                    "Phim A",
                    history=history,
                )
            ]
        )
        current = (_movie(new_url, "Phim B"),)

        result = ids.assign_stable_movie_ids(current, mapping, seen_at=TS_NEW)

        self.assertEqual(result.movie_ids_by_url[new_url], "M0001")
        record = result.updated_mapping.movies[0]
        self.assertEqual(record.url_history[-1].verification, "reviewer_alias")
        self.assertEqual(record.url_history[-1].approved_by, "reviewer-a")
        self.assertEqual(record.url_history[-1].approved_at, TS_MID)
        self.assertEqual(record.canonical_title, "Phim B")

    def test_url_change_with_later_seen_at_keeps_valid_history(self) -> None:
        old_url = _url("old")
        new_url = _url("new")
        mapping = _validated(
            [
                _mapped(
                    "M0001",
                    old_url,
                    "Phim A",
                    history=[_history(old_url, first=TS_OLD, last=TS_MID)],
                    last_seen_at=TS_MID,
                )
            ]
        )

        result = ids.assign_stable_movie_ids(
            (_movie(new_url, "Phim A"),), mapping, seen_at=TS_NEW
        )

        record = result.updated_mapping.movies[0]
        self.assertEqual(
            tuple(entry.source_url_dtp for entry in record.url_history),
            (old_url, new_url),
        )
        self.assertEqual(record.url_history[-1].first_seen_at, TS_NEW)
        self.assertEqual(record.url_history[-1].last_seen_at, TS_NEW)
        validated = ids.validate_movie_id_mapping(
            _payload_from_mapping(result.updated_mapping)
        )
        self.assertEqual(validated.movies[0].url_history, record.url_history)

    def test_url_change_with_equal_seen_at_keeps_valid_history(self) -> None:
        old_url = _url("old")
        new_url = _url("new")
        mapping = _validated(
            [
                _mapped(
                    "M0001",
                    old_url,
                    "Phim A",
                    history=[_history(old_url, first=TS_OLD, last=TS_NEW)],
                    last_seen_at=TS_NEW,
                )
            ]
        )

        result = ids.assign_stable_movie_ids(
            (_movie(new_url, "Phim A"),), mapping, seen_at=TS_NEW
        )

        record = result.updated_mapping.movies[0]
        self.assertEqual(
            tuple(entry.source_url_dtp for entry in record.url_history),
            (old_url, new_url),
        )
        self.assertEqual(record.url_history[-1].first_seen_at, TS_NEW)
        self.assertEqual(record.url_history[-1].last_seen_at, TS_NEW)
        validated = ids.validate_movie_id_mapping(
            _payload_from_mapping(result.updated_mapping)
        )
        self.assertEqual(validated.movies[0].url_history, record.url_history)

    def test_url_change_with_earlier_seen_at_is_rejected(self) -> None:
        old_url = _url("old")
        mapping = _validated(
            [
                _mapped(
                    "M0001",
                    old_url,
                    "Phim A",
                    history=[_history(old_url, first=TS_OLD, last=TS_NEW)],
                    last_seen_at=TS_NEW,
                )
            ]
        )

        error = self._assert_invalid(
            lambda: ids.assign_stable_movie_ids(
                (_movie(_url("new"), "Phim A"),), mapping, seen_at=TS_MID
            )
        )
        self.assertIn("earlier than previous last_seen_at", str(error))

    def test_url_change_offset_timestamps_compare_in_utc(self) -> None:
        old_url = _url("old")
        new_url = _url("new")
        mapping = _validated(
            [
                _mapped(
                    "M0001",
                    old_url,
                    "Phim A",
                    history=[
                        _history(old_url, first=TS_OLD, last=TS_CHANGE_OFFSET)
                    ],
                    last_seen_at=TS_CHANGE_OFFSET,
                )
            ]
        )

        result = ids.assign_stable_movie_ids(
            (_movie(new_url, "Phim A"),), mapping, seen_at=TS_CHANGE_UTC_0130Z
        )

        record = result.updated_mapping.movies[0]
        self.assertEqual(record.url_history[-1].first_seen_at, TS_CHANGE_UTC_0130Z)
        self.assertEqual(record.url_history[-1].last_seen_at, TS_CHANGE_UTC_0130Z)
        validated = ids.validate_movie_id_mapping(
            _payload_from_mapping(result.updated_mapping)
        )
        self.assertEqual(validated.movies[0].url_history, record.url_history)

    def test_url_change_with_mixed_timestamp_awareness_is_rejected(self) -> None:
        mapping = _validated(
            [
                _mapped(
                    "M0001",
                    _url("old"),
                    "Phim A",
                    history=[_history(_url("old"), first=TS_OLD, last=TS_MID)],
                    last_seen_at=TS_MID,
                )
            ]
        )

        error = self._assert_invalid(
            lambda: ids.assign_stable_movie_ids(
                (_movie(_url("new"), "Phim A"),),
                mapping,
                seen_at=TS_NAIVE_NEW,
            )
        )
        self.assertIn("timezone-aware and timezone-naive", str(error))

    def test_rejected_url_change_does_not_mutate_mapping(self) -> None:
        old_url = _url("old")
        mapping = _validated(
            [
                _mapped(
                    "M0001",
                    old_url,
                    "Phim A",
                    history=[_history(old_url, first=TS_OLD, last=TS_NEW)],
                    last_seen_at=TS_NEW,
                )
            ]
        )
        snapshot = copy.deepcopy(mapping)

        self._assert_invalid(
            lambda: ids.assign_stable_movie_ids(
                (_movie(_url("new"), "Phim A"),), mapping, seen_at=TS_MID
            )
        )

        self.assertEqual(mapping, snapshot)
        self.assertEqual(mapping.movies[0].source_url_dtp, old_url)
        self.assertEqual(len(mapping.movies[0].url_history), 1)
        self.assertEqual(mapping.movies[0].url_history[0].last_seen_at, TS_NEW)

    def test_ambiguous_url_change_is_rejected(self) -> None:
        new_url = _url("new")
        alias_history = [
            _history(
                new_url,
                verification="reviewer_alias",
                first=TS_OLD,
                last=TS_MID,
                approved_by="reviewer-a",
                approved_at=TS_MID,
            ),
            _history(_url("old-b"), verification="identity_match", first=TS_MID, last=TS_MID),
        ]
        mapping = _validated(
            [
                _mapped("M0001", _url("old-a"), "Phim A"),
                _mapped("M0002", _url("old-b"), "Phim B", history=alias_history),
            ]
        )
        current = (_movie(new_url, "Phim A"),)

        error = self._assert_unresolved(
            lambda: ids.assign_stable_movie_ids(current, mapping, seen_at=TS_NEW)
        )
        self.assertIn("possible movie IDs", str(error))

    def test_similar_titles_with_different_sequel_numbers_are_not_merged(self) -> None:
        mapping = _validated(
            [_mapped("M0001", _url("old"), "Phim Hay 2")]
        )
        current = (_movie(_url("new"), "Phim Hay 3"),)

        result = ids.assign_stable_movie_ids(current, mapping, seen_at=TS_NEW)

        self.assertEqual(result.movie_ids_by_url[_url("new")], "M0002")
        self.assertEqual(result.summary.url_changed_ids, ())
        self.assertEqual(result.summary.new_ids, ("M0002",))
        self.assertEqual(
            result.updated_mapping.movies[0].source_url_dtp, _url("old")
        )

    def test_conflicting_identities_are_rejected(self) -> None:
        mapping_payload = _payload(
            [
                _mapped("M0001", _url("a"), "Phim A"),
                _mapped("M0002", _url("b"), "phim a"),
            ]
        )
        self._assert_invalid(
            lambda: ids.validate_movie_id_mapping(mapping_payload)
        )

    def test_direct_identity_update_collision_is_unresolved(self) -> None:
        mapping = _validated(
            [
                _mapped("M0001", _url("a"), "Phim A"),
                _mapped("M0002", _url("b"), "Phim B"),
            ]
        )
        current = (
            _movie(_url("a"), "Phim B"),
            _movie(_url("b"), "Phim C"),
        )

        error = self._assert_unresolved(
            lambda: ids.assign_stable_movie_ids(current, mapping, seen_at=TS_NEW)
        )
        self.assertIn("claimed by both", str(error))

    def test_duplicate_current_urls_are_rejected(self) -> None:
        mapping = _validated([_mapped("M0001", _url("a"), "Phim A")])
        current = (
            _movie(_url("a"), "Phim A"),
            _movie(_url("a"), "Phim B"),
        )

        error = self._assert_invalid(
            lambda: ids.assign_stable_movie_ids(current, mapping, seen_at=TS_NEW)
        )
        self.assertIn("duplicates URL", str(error))

    def test_input_mapping_object_is_not_mutated(self) -> None:
        mapping = _validated(
            [_mapped("M0001", _url("old"), "Phim A")]
        )
        snapshot = copy.deepcopy(mapping)
        current = (_movie(_url("new"), "Phim A"),)

        ids.assign_stable_movie_ids(current, mapping, seen_at=TS_NEW)

        self.assertEqual(mapping, snapshot)
        self.assertEqual(mapping.movies[0].source_url_dtp, _url("old"))
        self.assertEqual(len(mapping.movies[0].url_history), 1)

    def test_no_filesystem_writes_occur_during_assignment(self) -> None:
        mapping = _validated([_mapped("M0001", _url("a"), "Phim A")])
        current = (_movie(_url("a"), "Phim A"),)

        with (
            patch("builtins.open", side_effect=AssertionError("open() called")) as open_mock,
            patch.object(Path, "write_text", side_effect=AssertionError("write_text called")),
            patch.object(Path, "write_bytes", side_effect=AssertionError("write_bytes called")),
            patch.object(Path, "touch", side_effect=AssertionError("touch called")),
            patch.object(Path, "mkdir", side_effect=AssertionError("mkdir called")),
        ):
            result = ids.assign_stable_movie_ids(current, mapping, seen_at=TS_NEW)

        open_mock.assert_not_called()
        self.assertEqual(dict(result.movie_ids_by_url), {_url("a"): "M0001"})

    def test_validate_does_not_mutate_decoded_payload(self) -> None:
        payload = _payload([_mapped("M0001", _url("a"), "Phim A")])
        snapshot = copy.deepcopy(payload)

        ids.validate_movie_id_mapping(payload)

        self.assertEqual(payload, snapshot)


    def test_incomplete_current_identities_do_not_collide(self) -> None:
        mapping = _validated([])
        current = (
            _movie(_url("a"), "Phim A", director=None),
            _movie(_url("b"), "Phim A", director=None),
        )

        result = ids.assign_stable_movie_ids(current, mapping, seen_at=TS_NEW)

        self.assertEqual(
            dict(result.movie_ids_by_url),
            {_url("a"): "M0001", _url("b"): "M0002"},
        )

    def test_changed_url_with_missing_director_does_not_match(self) -> None:
        mapping = _validated([_mapped("M0001", _url("old"), "Phim A")])
        current = (_movie(_url("new"), "Phim A", director=None),)

        result = ids.assign_stable_movie_ids(current, mapping, seen_at=TS_NEW)

        self.assertEqual(result.movie_ids_by_url[_url("new")], "M0002")
        self.assertEqual(result.summary.url_changed_ids, ())
        self.assertEqual(
            result.updated_mapping.movies[0].source_url_dtp, _url("old")
        )

    def test_changed_url_with_missing_year_does_not_match(self) -> None:
        mapping = _validated([_mapped("M0001", _url("old"), "Phim A")])
        current = (_movie(_url("new"), "Phim A", year=None),)

        result = ids.assign_stable_movie_ids(current, mapping, seen_at=TS_NEW)

        self.assertEqual(result.movie_ids_by_url[_url("new")], "M0002")
        self.assertEqual(result.summary.url_changed_ids, ())

    def test_changed_url_with_empty_title_does_not_match(self) -> None:
        mapping = _validated([_mapped("M0001", _url("old"), "Phim A")])
        current = (_movie(_url("new"), ""),)

        result = ids.assign_stable_movie_ids(current, mapping, seen_at=TS_NEW)

        self.assertEqual(result.movie_ids_by_url[_url("new")], "M0002")
        self.assertEqual(result.summary.url_changed_ids, ())

    def test_complete_normalized_identity_still_matches(self) -> None:
        mapping = _validated(
            [_mapped("M0001", _url("old"), "Phim A: Phần 2")]
        )
        current = (
            _movie(
                _url("new"),
                "  PHIM  A: PHẦN  2 ",
                director=DEFAULT_DIRECTOR_ALT,
            ),
        )

        result = ids.assign_stable_movie_ids(current, mapping, seen_at=TS_NEW)

        self.assertEqual(result.movie_ids_by_url[_url("new")], "M0001")
        self.assertEqual(result.summary.url_changed_ids, ("M0001",))

    def test_sequel_number_change_is_not_identity_match(self) -> None:
        mapping = _validated([_mapped("M0001", _url("old"), "Chị Mười Ba 2")])
        current = (_movie(_url("new"), "Chị Mười Ba 3"),)

        result = ids.assign_stable_movie_ids(current, mapping, seen_at=TS_NEW)

        self.assertEqual(result.movie_ids_by_url[_url("new")], "M0002")
        self.assertEqual(result.summary.url_changed_ids, ())

    def test_existing_url_reuse_allowed_with_incomplete_identity(self) -> None:
        mapping = _validated(
            [
                _mapped(
                    "M0001",
                    _url("a"),
                    "Phim A",
                    year=None,
                    director=None,
                )
            ]
        )
        current = (_movie(_url("a"), "Phim A", year=None, director=None),)

        result = ids.assign_stable_movie_ids(current, mapping, seen_at=TS_NEW)

        self.assertEqual(result.movie_ids_by_url, {_url("a"): "M0001"})
        self.assertEqual(result.summary.reused_ids, ("M0001",))
        self.assertEqual(result.summary.new_ids, ())

    def test_incomplete_mapping_identities_do_not_create_false_duplicate(self) -> None:
        mapping = ids.validate_movie_id_mapping(
            _payload(
                [
                    _mapped("M0001", _url("a"), "Phim A", director=None),
                    _mapped("M0002", _url("b"), "Phim A", director=None),
                ]
            )
        )

        self.assertEqual(
            tuple(record.movie_id for record in mapping.movies), ("M0001", "M0002")
        )

    def test_reviewer_alias_can_establish_incomplete_identity_relationship(self) -> None:
        new_url = _url("new")
        history = [
            _history(_url("old")),
            _history(
                new_url,
                verification="reviewer_alias",
                first=TS_MID,
                last=TS_MID,
                approved_by="reviewer-a",
                approved_at=TS_MID,
            ),
            _history(_url("old"), verification="identity_match", first=TS_NEW, last=TS_NEW),
        ]
        mapping = _validated(
            [_mapped("M0001", _url("old"), "Phim A", history=history)]
        )
        current = (_movie(new_url, "Phim B", director=None),)

        result = ids.assign_stable_movie_ids(current, mapping, seen_at=TS_NEW)

        self.assertEqual(result.movie_ids_by_url[new_url], "M0001")
        self.assertEqual(result.summary.url_changed_ids, ("M0001",))

    def test_utc_timestamps_are_preserved(self) -> None:
        mapping = ids.validate_movie_id_mapping(
            _payload(
                [
                    _mapped(
                        "M0001",
                        _url("a"),
                        "Phim A",
                        history=[_history(_url("a"), first=TS_OLD, last=TS_OLD)],
                    )
                ],
                generated_at=TS_NEW,
            )
        )

        self.assertEqual(mapping.generated_at, TS_NEW)
        self.assertEqual(mapping.movies[0].created_at, TS_OLD)
        self.assertEqual(mapping.movies[0].last_seen_at, TS_MID)
        self.assertEqual(mapping.movies[0].url_history[0].first_seen_at, TS_OLD)
        self.assertEqual(mapping.movies[0].url_history[0].last_seen_at, TS_OLD)

    def test_offset_aware_timestamps_compare_in_utc(self) -> None:
        payload = _payload(
            [
                _mapped(
                    "M0001",
                    _url("a"),
                    "Phim A",
                    history=[
                        _history(_url("a"), first=TS_OFFSET_01Z, last=TS_OFFSET_01Z)
                    ],
                    created_at=TS_OFFSET_01Z,
                    last_seen_at=TS_UTC_0130Z,
                )
            ],
            generated_at=TS_UTC_0130Z,
        )

        mapping = ids.validate_movie_id_mapping(payload)

        self.assertEqual(mapping.movies[0].created_at, TS_OFFSET_01Z)
        self.assertEqual(mapping.movies[0].last_seen_at, TS_UTC_0130Z)

    def test_timezone_naive_timestamps_are_accepted(self) -> None:
        mapping = ids.validate_movie_id_mapping(
            _payload(
                [
                    _mapped(
                        "M0001",
                        _url("a"),
                        "Phim A",
                        history=[
                            _history(_url("a"), first=TS_NAIVE_OLD, last=TS_NAIVE_OLD)
                        ],
                        created_at=TS_NAIVE_OLD,
                        last_seen_at=TS_NAIVE_NEW,
                    )
                ],
                generated_at=TS_NAIVE_NEW,
            )
        )

        self.assertEqual(mapping.movies[0].created_at, TS_NAIVE_OLD)
        self.assertEqual(mapping.movies[0].last_seen_at, TS_NAIVE_NEW)

    def test_mixed_timezone_aware_and_naive_timestamps_are_rejected(self) -> None:
        mixed_movie = _payload(
            [
                _mapped(
                    "M0001",
                    _url("a"),
                    "Phim A",
                    created_at=TS_OLD,
                    last_seen_at=TS_NAIVE_NEW,
                )
            ]
        )
        mixed_history = _payload(
            [
                _mapped(
                    "M0001",
                    _url("a"),
                    "Phim A",
                    history=[
                        _history(_url("a"), first=TS_OLD, last=TS_NAIVE_NEW)
                    ],
                )
            ]
        )
        for payload in (mixed_movie, mixed_history):
            with self.subTest(payload=payload):
                error = self._assert_invalid(
                    lambda payload=payload: ids.validate_movie_id_mapping(payload)
                )
                self.assertIn("timezone-aware and timezone-naive", str(error))

        mapping = _validated([_mapped("M0001", _url("a"), "Phim A")])
        error = self._assert_invalid(
            lambda: ids.assign_stable_movie_ids(
                (_movie(_url("a"), "Phim A"),), mapping, seen_at=TS_NAIVE_NEW
            )
        )
        self.assertIn("timezone-aware and timezone-naive", str(error))

    def test_last_seen_at_does_not_move_backward(self) -> None:
        mapping = _validated(
            [_mapped("M0001", _url("a"), "Phim A", last_seen_at=TS_NEW)]
        )

        result = ids.assign_stable_movie_ids(
            (_movie(_url("a"), "Phim A"),), mapping, seen_at=TS_OLD
        )

        self.assertEqual(result.updated_mapping.movies[0].last_seen_at, TS_NEW)

    def test_later_candidate_updates_last_seen_at(self) -> None:
        mapping = _validated([_mapped("M0001", _url("a"), "Phim A")])

        result = ids.assign_stable_movie_ids(
            (_movie(_url("a"), "Phim A"),), mapping, seen_at=TS_NEW
        )

        record = result.updated_mapping.movies[0]
        self.assertEqual(record.last_seen_at, TS_NEW)
        self.assertEqual(record.url_history[-1].last_seen_at, TS_NEW)

    def test_offset_aware_candidate_compares_in_utc_during_assignment(self) -> None:
        mapping = _validated(
            [
                _mapped(
                    "M0001",
                    _url("a"),
                    "Phim A",
                    history=[
                        _history(_url("a"), first=TS_OFFSET_01Z, last=TS_OFFSET_01Z)
                    ],
                    created_at=TS_OFFSET_01Z,
                    last_seen_at=TS_OFFSET_01Z,
                )
            ]
        )

        result = ids.assign_stable_movie_ids(
            (_movie(_url("a"), "Phim A"),), mapping, seen_at=TS_UTC_0130Z
        )

        record = result.updated_mapping.movies[0]
        self.assertEqual(record.last_seen_at, TS_UTC_0130Z)
        self.assertEqual(record.url_history[-1].last_seen_at, TS_UTC_0130Z)

    def test_out_of_order_url_history_is_rejected(self) -> None:
        backward_history = [
            _history(_url("old"), first=TS_NEW, last=TS_NEW),
            _history(
                _url("current"),
                verification="identity_match",
                first=TS_MID,
                last=TS_MID,
            ),
        ]
        payload = _payload(
            [
                _mapped(
                    "M0001",
                    _url("current"),
                    "Phim A",
                    history=backward_history,
                )
            ]
        )
        error = self._assert_invalid(
            lambda: ids.validate_movie_id_mapping(payload)
        )
        self.assertIn("first_seen_at is earlier", str(error))

        invalid_entry = _payload(
            [
                _mapped(
                    "M0001",
                    _url("a"),
                    "Phim A",
                    history=[_history(_url("a"), first=TS_NEW, last=TS_OLD)],
                )
            ]
        )
        error = self._assert_invalid(
            lambda: ids.validate_movie_id_mapping(invalid_entry)
        )
        self.assertIn("first_seen_at is later", str(error))

    def test_valid_url_history_with_repeated_url_is_accepted(self) -> None:
        old_url = _url("old")
        other_url = _url("other")
        history = [
            _history(old_url, first=TS_OLD, last=TS_OLD),
            _history(
                other_url,
                verification="identity_match",
                first=TS_MID,
                last=TS_MID,
            ),
            _history(
                old_url,
                verification="identity_match",
                first=TS_NEW,
                last=TS_NEW,
            ),
        ]

        mapping = ids.validate_movie_id_mapping(
            _payload([_mapped("M0001", old_url, "Phim A", history=history)])
        )

        self.assertEqual(
            tuple(entry.source_url_dtp for entry in mapping.movies[0].url_history),
            (old_url, other_url, old_url),
        )


class AnalyticsIdsPersistenceTests(unittest.TestCase):
    def _assert_invalid(self, callback: Any) -> Any:
        with self.assertRaises(ids.MovieIdMappingInvalidError) as context:
            callback()
        self.assertEqual(context.exception.code, "ID_MAPPING_INVALID")
        return context.exception

    def test_serialization_is_deterministic_and_round_trips(self) -> None:
        review = _revenue_review(
            "candidate_held",
            reason="different_subtitle",
            reviewed_at=TS_MID,
            reviewer="Reviewer A",
        )
        mapping = _validated(
            [
                _mapped(
                    "M0001",
                    _url("a"),
                    "Phim A",
                    notes="keep me",
                    revenue_review=review,
                )
            ]
        )

        first = ids.serialize_movie_id_mapping(mapping)
        second = ids.serialize_movie_id_mapping(mapping)

        self.assertEqual(first, second)
        self.assertEqual(first["movies"][0]["notes"], "keep me")
        self.assertEqual(first["movies"][0]["revenue_review"], review)
        self.assertEqual(ids.validate_movie_id_mapping(first), mapping)
        self.assertNotIn(
            "revenue_review",
            ids.serialize_movie_id_mapping(
                _validated([_mapped("M0002", _url("b"), "Phim B")])
            )["movies"][0],
        )

    def test_save_mapping_writes_deterministic_json_and_reads_back(self) -> None:
        mapping = _validated([_mapped("M0001", _url("a"), "Phim A")])

        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "mapping.json"
            saved = ids.save_movie_id_mapping(mapping, target)
            text = target.read_text(encoding="utf-8")
            expected = (
                json.dumps(
                    ids.serialize_movie_id_mapping(mapping),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )

            self.assertEqual(saved, mapping)
            self.assertEqual(text, expected)
            self.assertEqual(ids.load_movie_id_mapping(target), mapping)
            self.assertEqual(list(Path(temp_dir).glob(".mapping.json.*.tmp")), [])

    def test_invalid_mapping_is_rejected_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "mapping.json"
            invalid_payload = {"schema_version": "1.0"}

            with patch.object(
                ids, "_atomic_write_text", side_effect=AssertionError("write attempted")
            ) as write_mock:
                error = self._assert_invalid(
                    lambda: ids.save_movie_id_mapping(invalid_payload, target)  # type: ignore[arg-type]
                )

            self.assertIn("validated MovieIdMapping", str(error))
            write_mock.assert_not_called()
            self.assertFalse(target.exists())

    def test_initialization_requires_explicit_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "mapping.json"
            analytics = Path(temp_dir) / "movie_analytics.csv"

            with patch.object(
                ids, "_atomic_write_text", side_effect=AssertionError("write attempted")
            ) as write_mock:
                error = self._assert_invalid(
                    lambda: ids.initialize_movie_id_mapping(
                        (_movie(_url("a"), "Phim A"),),
                        revenue_reviews={},
                        destination=target,
                        analytics_output_path=analytics,
                    )
                )

            self.assertIn("confirm_initialize=True", str(error))
            write_mock.assert_not_called()
            self.assertFalse(target.exists())

    def test_initialization_refuses_existing_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "mapping.json"
            analytics = Path(temp_dir) / "movie_analytics.csv"
            sentinel = "existing mapping contents"
            target.write_text(sentinel, encoding="utf-8")

            error = self._assert_invalid(
                lambda: ids.initialize_movie_id_mapping(
                    (_movie(_url("a"), "Phim A"),),
                    revenue_reviews={},
                    confirm_initialize=True,
                    destination=target,
                    analytics_output_path=analytics,
                )
            )

            self.assertIn("destination already exists", str(error))
            self.assertEqual(target.read_text(encoding="utf-8"), sentinel)

    def test_initialization_refuses_existing_analytical_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "mapping.json"
            analytics = Path(temp_dir) / "movie_analytics.csv"
            analytics.write_text("existing output", encoding="utf-8")

            error = self._assert_invalid(
                lambda: ids.initialize_movie_id_mapping(
                    (_movie(_url("a"), "Phim A"),),
                    revenue_reviews={},
                    confirm_initialize=True,
                    destination=target,
                    analytics_output_path=analytics,
                )
            )

            self.assertIn("analytical CSV already exists", str(error))
            self.assertFalse(target.exists())

    def test_initialization_applies_explicit_reviews_and_verifies_read_back(self) -> None:
        reviews = {
            "M0001": _revenue_review(
                "accepted",
                reason="matcher_accepted_bov_revenue",
                reviewer=None,
                reviewed_at=None,
            ),
            "M0002": _revenue_review(
                "quarantined", reason="sequel_number_error"
            ),
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "mapping.json"
            analytics = Path(temp_dir) / "movie_analytics.csv"
            current = (_movie(_url("b"), "Phim B"), _movie(_url("a"), "Phim A"))

            mapping = ids.initialize_movie_id_mapping(
                current,
                revenue_reviews=reviews,
                confirm_initialize=True,
                destination=target,
                analytics_output_path=analytics,
                seen_at=TS_NEW,
                generated_at=TS_NEW,
            )

            self.assertEqual(mapping.movies[0].movie_id, "M0001")
            self.assertEqual(mapping.movies[0].source_url_dtp, _url("a"))
            self.assertEqual(mapping.movies[1].movie_id, "M0002")
            self.assertEqual(mapping.movies[0].revenue_review.decision, "accepted")
            self.assertIsNone(mapping.movies[0].revenue_review.reviewed_at)
            self.assertIsNone(mapping.movies[0].revenue_review.reviewer)
            self.assertEqual(
                mapping.movies[1].revenue_review.decision, "quarantined"
            )
            self.assertEqual(
                mapping.movies[1].revenue_review.reason, "sequel_number_error"
            )
            self.assertEqual(ids.load_movie_id_mapping(target), mapping)
            self.assertFalse(analytics.exists())
            self.assertEqual(list(Path(temp_dir).glob(".mapping.json.*.tmp")), [])

    def test_initialization_rejects_unknown_review_id_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "mapping.json"
            analytics = Path(temp_dir) / "movie_analytics.csv"

            error = self._assert_invalid(
                lambda: ids.initialize_movie_id_mapping(
                    (_movie(_url("a"), "Phim A"),),
                    revenue_reviews={
                        "M0099": _revenue_review("accepted", reason="audit")
                    },
                    confirm_initialize=True,
                    destination=target,
                    analytics_output_path=analytics,
                )
            )

            self.assertIn("unknown movie_id", str(error))
            self.assertFalse(target.exists())

    def test_failed_write_cleans_temp_and_preserves_existing_mapping(self) -> None:
        mapping = _validated([_mapped("M0001", _url("a"), "Phim A")])

        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "mapping.json"
            ids.save_movie_id_mapping(mapping, target)
            original = target.read_bytes()

            with patch.object(ids.os, "replace", side_effect=OSError("boom")):
                error = self._assert_invalid(
                    lambda: ids.save_movie_id_mapping(
                        mapping, target, overwrite=True
                    )
                )

            self.assertIn("Could not write mapping file", str(error))
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(list(Path(temp_dir).glob(".mapping.json.*.tmp")), [])

    def test_update_preserves_ids_history_notes_and_other_metadata(self) -> None:
        old_url = _url("old")
        new_url = _url("new")
        existing = _validated(
            [
                _mapped(
                    "M0001",
                    old_url,
                    "Phim A",
                    notes="keep me",
                    history=[_history(old_url, first=TS_OLD, last=TS_MID)],
                    last_seen_at=TS_MID,
                    revenue_review=_revenue_review("pending"),
                )
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "mapping.json"
            ids.save_movie_id_mapping(existing, target)

            updated = ids.update_movie_id_mapping(
                (_movie(new_url, "Phim A"),),
                path=target,
                seen_at=TS_NEW,
                revenue_reviews={
                    "M0001": _revenue_review(
                        "accepted",
                        reason="matcher_accepted_bov_revenue",
                        reviewer=None,
                        reviewed_at=None,
                    )
                },
            )

            record = updated.movies[0]
            self.assertEqual(record.movie_id, "M0001")
            self.assertEqual(record.source_url_dtp, new_url)
            self.assertEqual(
                tuple(entry.source_url_dtp for entry in record.url_history),
                (old_url, new_url),
            )
            self.assertEqual(record.notes, "keep me")
            self.assertEqual(record.revenue_review.decision, "accepted")
            self.assertEqual(updated.generated_at, existing.generated_at)
            self.assertEqual(ids.load_movie_id_mapping(target), updated)

    def test_update_does_not_create_missing_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "mapping.json"

            self._assert_invalid(
                lambda: ids.update_movie_id_mapping(
                    (_movie(_url("a"), "Phim A"),), path=target
                )
            )

            self.assertFalse(target.exists())

    def test_update_does_not_rebuild_corrupt_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "mapping.json"
            corrupt = '{"movies": ['
            target.write_text(corrupt, encoding="utf-8")

            error = self._assert_invalid(
                lambda: ids.update_movie_id_mapping(
                    (_movie(_url("a"), "Phim A"),), path=target
                )
            )

            self.assertIn("invalid JSON", str(error))
            self.assertEqual(target.read_text(encoding="utf-8"), corrupt)


if __name__ == "__main__":
    unittest.main()
