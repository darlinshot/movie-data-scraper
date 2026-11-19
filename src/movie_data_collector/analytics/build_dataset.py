"""In-memory assembly of the single flat movie analytics dataset.

This module is standard-library only. It orchestrates the already-approved
loading, cleaning, stable-ID, revenue and ticket layers. It performs no file
writes, never initializes a mapping, and does not export the final CSV.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any


def _load_module(path: Path, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load analytics module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ANALYTICS_DIR = Path(__file__).resolve().parent
load_raw = _load_module(
    ANALYTICS_DIR / "load_raw.py", "analytics_load_raw_for_build_dataset"
)
clean = _load_module(ANALYTICS_DIR / "clean.py", "analytics_clean_for_build_dataset")
ids = _load_module(ANALYTICS_DIR / "ids.py", "analytics_ids_for_build_dataset")
revenue = _load_module(
    ANALYTICS_DIR / "revenue.py", "analytics_revenue_for_build_dataset"
)
tickets = _load_module(
    ANALYTICS_DIR / "tickets.py", "analytics_tickets_for_build_dataset"
)

schema = load_raw.schema


class AnalyticsBuildError(ValueError):
    """Base class for assembly and dataset-level validation failures."""


class DatasetValidationError(AnalyticsBuildError):
    """The assembled dataset violates an approved structure or domain invariant."""


HIGH_PRIORITY_SOURCE_ROWS = frozenset({32, 51, 78, 84, 91, 93})

_MISSING_MATCH_STATUSES = frozenset({"", "not_found", "unknown"})


@dataclass(frozen=True)
class AnalyticsBuildResult:
    """One flat dataset plus read-only references to intermediate stage outputs."""

    rows: tuple[dict[str, Any], ...]
    validation: MappingABC[str, Any]
    raw_inputs: Any
    cleaned_inputs: Any
    id_assignment: Any
    revenue_result: Any
    ticket_result: Any


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _exact_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _parse_score(value: Any) -> float | None:
    text = _text(value)
    if text is None or text.casefold() in {"nan", "none", "null"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _index_by_url(
    records: Any, field: str, label: str
) -> dict[str, MappingABC[str, Any]]:
    indexed: dict[str, MappingABC[str, Any]] = {}
    if records is None:
        return indexed
    try:
        iterator = iter(records)
    except TypeError as exc:
        raise AnalyticsBuildError(f"{label} must be iterable") from exc
    for row in iterator:
        if not isinstance(row, MappingABC):
            raise AnalyticsBuildError(f"{label} records must be objects")
        url = _text(row.get(field))
        if url is None:
            raise AnalyticsBuildError(f"{label} record is missing {field}")
        if url in indexed:
            raise AnalyticsBuildError(f"{label} duplicate {field}: {url}")
        indexed[url] = row
    return indexed


def _review_for_movie(mapped: Any, movie_id: str) -> Any:
    review = getattr(mapped, "revenue_review", None)
    if review is None:
        return None
    if isinstance(review, MappingABC):
        decision = review.get("decision")
    else:
        decision = getattr(review, "decision", None)
    if decision is None:
        return None
    if decision not in revenue.REVENUE_REVIEW_DECISIONS:
        raise AnalyticsBuildError(
            f"{movie_id} has an unsupported revenue_review decision: {decision!r}"
        )
    return review


def _review_value(review: Any, field: str) -> Any:
    if review is None:
        return None
    if isinstance(review, MappingABC):
        return review.get(field)
    return getattr(review, field, None)


def _group_b_fields(
    *,
    raw_movie: MappingABC[str, Any],
    collection_row: MappingABC[str, Any] | None,
    mapped: Any,
    movie_id: str,
    source_row: Any,
) -> dict[str, Any]:
    review = _review_for_movie(mapped, movie_id)
    decision = _review_value(review, "decision")
    reason = _text(_review_value(review, "reason"))

    match_status = _text(collection_row.get("match_status")) if collection_row else None
    bov_match_status = match_status or "unknown"
    match_score = _parse_score(collection_row.get("match_score")) if collection_row else None
    match_reason = _text(collection_row.get("match_reason")) if collection_row else None

    if decision == "quarantined":
        mapping_validation_status = "known_false_positive_quarantined"
        mapping_validation_reason = reason
    elif decision == "candidate_held":
        mapping_validation_status = "candidate_held"
        mapping_validation_reason = reason
    elif match_status == "matched":
        mapping_validation_status = "matcher_accepted"
        mapping_validation_reason = None
    else:
        mapping_validation_status = "no_mapping"
        mapping_validation_reason = None

    reviewed_at = _text(_review_value(review, "reviewed_at"))
    reviewer = _text(_review_value(review, "reviewer"))
    human_reviewed = int(reviewed_at is not None and reviewer is not None)

    if decision in {"quarantined", "candidate_held"}:
        review_status = "pending"
    elif source_row in HIGH_PRIORITY_SOURCE_ROWS:
        review_status = "pending"
    elif match_status == "matched":
        review_status = "auto_accepted"
    else:
        review_status = "not_applicable"

    return {
        "bov_match_status": bov_match_status,
        "match_score": match_score,
        "match_reason": match_reason,
        "bov_url": _exact_text(raw_movie.get("source_url_bovn")),
        "bov_title_raw": _exact_text(raw_movie.get("title_bovn")),
        "mapping_validation_status": mapping_validation_status,
        "mapping_validation_reason": mapping_validation_reason,
        "mapping_human_reviewed": human_reviewed,
        "mapping_reviewed_at": reviewed_at if human_reviewed else None,
        "mapping_reviewer": reviewer if human_reviewed else None,
        "review_status": review_status,
        "review_priority": "high" if source_row in HIGH_PRIORITY_SOURCE_ROWS else "normal",
    }


def _build_base_rows(
    raw_inputs: Any,
    cleaned_inputs: Any,
    id_assignment: Any,
) -> tuple[dict[str, Any], ...]:
    raw_by_url = _index_by_url(
        getattr(raw_inputs, "movies", ()), "source_url_doanhthuphim", "movies.csv"
    )
    collection_by_url = _index_by_url(
        getattr(cleaned_inputs, "collection_log", ()),
        "source_url_doanhthuphim",
        "collection_log.csv",
    )
    assignments = getattr(id_assignment, "movie_ids_by_url", None)
    if not isinstance(assignments, MappingABC):
        raise AnalyticsBuildError("id_assignment is missing movie_ids_by_url")

    mapping = getattr(id_assignment, "updated_mapping", None)
    mapped_by_id = {
        getattr(record, "movie_id", None): record
        for record in getattr(mapping, "movies", ())
    }

    rows: dict[str, dict[str, Any]] = {}
    for movie in getattr(cleaned_inputs, "movies", ()):
        url = _text(getattr(movie, "source_url_dtp", None))
        if url is None:
            raise AnalyticsBuildError("cleaned movie is missing source_url_dtp")
        movie_id = assignments.get(url)
        if not isinstance(movie_id, str) or not movie_id:
            raise AnalyticsBuildError(f"no stable movie_id assigned for DTP URL: {url}")
        if movie_id in rows:
            raise AnalyticsBuildError(f"duplicate assigned movie_id: {movie_id}")

        mapped = mapped_by_id.get(movie_id)
        if mapped is None:
            raise AnalyticsBuildError(f"mapping is missing assigned movie_id: {movie_id}")
        if getattr(mapped, "source_url_dtp", None) != url:
            raise AnalyticsBuildError(
                f"{movie_id} mapping URL does not match assigned URL: {url}"
            )

        raw_movie = raw_by_url.get(url)
        if raw_movie is None:
            raise AnalyticsBuildError(f"no raw movie row for DTP URL: {url}")

        source_row = getattr(movie, "raw_source_row_dtp", None)
        group_a = {
            "movie_id": movie_id,
            "canonical_title": getattr(movie, "canonical_title", None),
            "original_title_raw": getattr(movie, "original_title_raw", None),
            "release_year": getattr(movie, "release_year", None),
            "genre_raw": getattr(movie, "genre_raw", None),
            "genre_token_path": getattr(movie, "genre_token_path", None),
            "genre_grouped": getattr(movie, "genre_grouped", None),
            "director_raw": getattr(movie, "director_raw", None),
            "director_norm_key": getattr(movie, "director_norm_key", None),
            "source_url_dtp": getattr(movie, "source_url_dtp", None),
            "raw_source_row_dtp": source_row,
        }
        group_b = _group_b_fields(
            raw_movie=raw_movie,
            collection_row=collection_by_url.get(url),
            mapped=mapped,
            movie_id=movie_id,
            source_row=source_row,
        )
        row = dict(group_a)
        row.update(group_b)
        rows[movie_id] = row

    return tuple(rows[movie_id] for movie_id in sorted(rows))


def _apply_data_quality_fields(
    rows: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    updated_rows: list[dict[str, Any]] = []
    for row in rows:
        updated = dict(row)
        has_missing_core_data = int(
            any(
                updated.get(field) is None
                for field in (
                    "canonical_title",
                    "release_year",
                    "genre_raw",
                    "director_raw",
                )
            )
        )
        has_revenue_gap_warning = int(updated.get("magnitude_gap_warning") == 1)
        has_pending_review = int(updated.get("review_status") == "pending")

        if has_pending_review:
            data_quality_status = "pending_review"
        elif has_revenue_gap_warning:
            data_quality_status = "revenue_gap_warning"
        elif has_missing_core_data:
            data_quality_status = "missing_core_data"
        elif updated.get("bov_match_status") != "matched":
            data_quality_status = "no_bov_match"
        else:
            data_quality_status = "ok"

        updated["has_missing_core_data"] = has_missing_core_data
        updated["has_revenue_gap_warning"] = has_revenue_gap_warning
        updated["has_pending_review"] = has_pending_review
        updated["data_quality_status"] = data_quality_status
        updated_rows.append(updated)
    return tuple(updated_rows)


def _ids_where(
    rows: tuple[dict[str, Any], ...], predicate: Any
) -> tuple[str, ...]:
    return tuple(row.get("movie_id") for row in rows if predicate(row))


def _expect_count(
    errors: list[str],
    name: str,
    expected: int,
    actual: int,
    affected_ids: tuple[str, ...] | None = None,
) -> None:
    if actual == expected:
        return
    detail = ""
    if affected_ids:
        detail = f"; movie_ids={list(affected_ids)}"
    errors.append(f"{name}: expected {expected}, got {actual}{detail}")


def validate_dataset(
    rows: Any,
    *,
    expected_movie_ids: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Validate structure and all approved revenue/ticket invariants in memory."""
    errors: list[str] = []
    try:
        dataset = tuple(rows)
    except TypeError as exc:
        raise DatasetValidationError("dataset must be an iterable of rows") from exc

    if len(dataset) != schema.EXPECTED_MOVIE_COUNT:
        errors.append(
            f"row_count: expected {schema.EXPECTED_MOVIE_COUNT}, got {len(dataset)}"
        )

    for index, row in enumerate(dataset):
        if not isinstance(row, MappingABC):
            errors.append(f"row {index}: expected object, got {type(row).__name__}")
            continue
        keys = tuple(row.keys())
        if keys != schema.FINAL_COLUMNS:
            actual_keys = set(keys)
            expected_keys = set(schema.FINAL_COLUMNS)
            errors.append(
                f"row {index} columns: missing={sorted(expected_keys - actual_keys)}, "
                f"extra={sorted(actual_keys - expected_keys)}, "
                f"ordered={keys == schema.FINAL_COLUMNS}"
            )

    valid_rows = tuple(row for row in dataset if isinstance(row, MappingABC))
    movie_ids = tuple(row.get("movie_id") for row in valid_rows)
    missing_ids = _ids_where(valid_rows, lambda row: not _text(row.get("movie_id")))
    if missing_ids:
        errors.append(f"missing_movie_ids: {list(missing_ids)}")

    invalid_ids = tuple(
        row.get("movie_id")
        for row in valid_rows
        if isinstance(row.get("movie_id"), str)
        and re.fullmatch(schema.MOVIE_ID_PATTERN, row["movie_id"]) is None
    )
    if invalid_ids:
        errors.append(f"invalid_movie_ids: {list(invalid_ids)}")

    duplicate_ids = tuple(
        movie_id for movie_id in dict.fromkeys(movie_ids) if movie_ids.count(movie_id) > 1
    )
    if duplicate_ids:
        errors.append(f"duplicate_movie_ids: {list(duplicate_ids)}")

    source_urls = tuple(row.get("source_url_dtp") for row in valid_rows)
    duplicate_urls = tuple(
        url
        for url in dict.fromkeys(source_urls)
        if url is not None and source_urls.count(url) > 1
    )
    if duplicate_urls:
        errors.append(f"duplicate_source_url_dtp: {list(duplicate_urls)}")

    if expected_movie_ids is not None:
        expected_set = set(expected_movie_ids)
        actual_set = set(movie_ids)
        if expected_set != actual_set:
            errors.append(
                "movie_id_set: "
                f"missing={sorted(expected_set - actual_set)}, "
                f"extra={sorted(actual_set - expected_set)}"
            )

    dtp_ids = _ids_where(
        valid_rows, lambda row: row.get("dtp_revenue_vnd") is not None
    )
    _expect_count(errors, "dtp_observations", 92, len(dtp_ids), dtp_ids)
    _expect_count(
        errors,
        "dtp_quality_rounded",
        90,
        sum(row.get("dtp_revenue_quality") == "rounded" for row in valid_rows),
        _ids_where(valid_rows, lambda row: row.get("dtp_revenue_quality") == "rounded"),
    )
    _expect_count(
        errors,
        "dtp_quality_lower_bound",
        2,
        sum(row.get("dtp_revenue_quality") == "lower_bound" for row in valid_rows),
        _ids_where(
            valid_rows, lambda row: row.get("dtp_revenue_quality") == "lower_bound"
        ),
    )

    accepted_ids = _ids_where(
        valid_rows, lambda row: row.get("bov_revenue_vnd") is not None
    )
    _expect_count(errors, "accepted_bov_revenue", 79, len(accepted_ids), accepted_ids)
    quarantined_ids = _ids_where(
        valid_rows, lambda row: row.get("bov_quarantined_revenue_vnd") is not None
    )
    _expect_count(errors, "quarantined_bov_revenue", 1, len(quarantined_ids), quarantined_ids)
    candidate_ids = _ids_where(
        valid_rows, lambda row: row.get("bov_candidate_revenue_vnd") is not None
    )
    _expect_count(errors, "candidate_bov_revenue", 1, len(candidate_ids), candidate_ids)

    eligible_ids = _ids_where(
        valid_rows, lambda row: row.get("include_revenue_comparison") == 1
    )
    _expect_count(errors, "eligible_revenue_comparisons", 79, len(eligible_ids), eligible_ids)

    warning_ids = _ids_where(
        valid_rows, lambda row: row.get("magnitude_gap_warning") == 1
    )
    accepted_warning_ids = _ids_where(
        valid_rows,
        lambda row: row.get("magnitude_gap_warning") == 1
        and row.get("include_revenue_comparison") == 1,
    )
    candidate_warning_ids = _ids_where(
        valid_rows,
        lambda row: row.get("magnitude_gap_warning") == 1
        and row.get("bov_candidate_revenue_vnd") is not None,
    )
    _expect_count(errors, "magnitude_gap_warnings", 21, len(warning_ids), warning_ids)
    _expect_count(
        errors, "accepted_gap_warnings", 20, len(accepted_warning_ids), accepted_warning_ids
    )
    _expect_count(
        errors, "candidate_gap_warnings", 1, len(candidate_warning_ids), candidate_warning_ids
    )

    conflict_ids = _ids_where(
        valid_rows, lambda row: row.get("revenue_conflict_flag") == 1
    )
    _expect_count(errors, "revenue_conflicts", 0, len(conflict_ids), conflict_ids)
    scope_ids = _ids_where(
        valid_rows, lambda row: row.get("revenue_scope_verified") == 1
    )
    _expect_count(errors, "verified_revenue_scopes", 0, len(scope_ids), scope_ids)

    ticket_candidate_ids = tuple(
        row.get("movie_id")
        for row in valid_rows
        for _ in range(int(row.get("ticket_candidate_count") or 0))
    )
    _expect_count(
        errors, "deduplicated_ticket_candidates", 16, len(ticket_candidate_ids)
    )
    found_ids = _ids_where(
        valid_rows, lambda row: row.get("ticket_found_count") == 1
    )
    _expect_count(
        errors,
        "found_ticket_candidates",
        5,
        sum(int(row.get("ticket_found_count") or 0) for row in valid_rows),
        found_ids,
    )
    _expect_count(
        errors,
        "needs_review_ticket_candidates",
        11,
        sum(int(row.get("ticket_needs_review_count") or 0) for row in valid_rows),
        _ids_where(
            valid_rows, lambda row: (row.get("ticket_needs_review_count") or 0) > 0
        ),
    )
    no_candidate_ids = _ids_where(
        valid_rows, lambda row: row.get("ticket_data_status") == "no_candidates"
    )
    _expect_count(errors, "movies_without_candidates", 76, len(no_candidate_ids))
    admissions_ids = _ids_where(
        valid_rows, lambda row: row.get("ticket_verified_admissions") is not None
    )
    _expect_count(errors, "verified_admissions", 0, len(admissions_ids), admissions_ids)

    if errors:
        raise DatasetValidationError(
            "Dataset validation failed:\n- " + "\n- ".join(errors)
        )

    return {
        "row_count": len(dataset),
        "column_count": len(schema.FINAL_COLUMNS),
        "dtp_observations": len(dtp_ids),
        "accepted_bov_revenue": len(accepted_ids),
        "quarantined_bov_revenue": len(quarantined_ids),
        "candidate_bov_revenue": len(candidate_ids),
        "eligible_revenue_comparisons": len(eligible_ids),
        "magnitude_gap_warnings": len(warning_ids),
        "accepted_gap_warnings": len(accepted_warning_ids),
        "candidate_gap_warnings": len(candidate_warning_ids),
        "deduplicated_ticket_candidates": len(ticket_candidate_ids),
        "found_ticket_candidates": sum(
            int(row.get("ticket_found_count") or 0) for row in valid_rows
        ),
        "needs_review_ticket_candidates": sum(
            int(row.get("ticket_needs_review_count") or 0) for row in valid_rows
        ),
        "movies_without_candidates": len(no_candidate_ids),
    }


def build_analytics_dataset(
    paths: load_raw.RawInputPaths | None = None,
    *,
    mapping_path: str | Path | None = None,
    raw_inputs: Any | None = None,
    seen_at: str | None = None,
) -> AnalyticsBuildResult:
    """Assemble and validate one in-memory flat dataset; write nothing."""
    if raw_inputs is not None and paths is not None:
        raise AnalyticsBuildError("pass either paths or raw_inputs, not both")

    active_raw_inputs = (
        raw_inputs
        if raw_inputs is not None
        else load_raw.load_raw_inputs(paths)
    )
    cleaned_inputs = clean.clean_raw_inputs(active_raw_inputs)

    mapping = ids.load_movie_id_mapping(mapping_path)
    id_assignment = ids.assign_stable_movie_ids(
        cleaned_inputs.movies, mapping, seen_at=seen_at
    )

    revenue_result = revenue.process_revenue(
        active_raw_inputs, cleaned_inputs, id_assignment
    )
    ticket_result = tickets.process_tickets(
        active_raw_inputs, cleaned_inputs, id_assignment
    )

    base_rows = _build_base_rows(active_raw_inputs, cleaned_inputs, id_assignment)
    rows = revenue.apply_revenue_fields(base_rows, revenue_result)
    rows = tickets.apply_ticket_fields(rows, ticket_result.summaries)
    rows = _apply_data_quality_fields(rows)

    expected_ids = tuple(id_assignment.movie_ids_by_url.values())
    validation = validate_dataset(rows, expected_movie_ids=expected_ids)

    return AnalyticsBuildResult(
        rows=rows,
        validation=validation,
        raw_inputs=active_raw_inputs,
        cleaned_inputs=cleaned_inputs,
        id_assignment=id_assignment,
        revenue_result=revenue_result,
        ticket_result=ticket_result,
    )


__all__ = [
    "AnalyticsBuildError",
    "AnalyticsBuildResult",
    "DatasetValidationError",
    "HIGH_PRIORITY_SOURCE_ROWS",
    "build_analytics_dataset",
    "validate_dataset",
]
